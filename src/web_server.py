import os
import sys
from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv

# Ensure parent directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import database
from src.conversation_manager import ConversationManager

load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Colaberry Logistics Voice Assistant")

# Add session middleware
secret_key = os.getenv("SECRET_KEY", "fallback_secret_key_for_testing")
app.add_middleware(SessionMiddleware, secret_key=secret_key)

# Configure OAuth client
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)

# Setup templates directory
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "web", "templates"))

@app.on_event("startup")
def startup_event():
    """Ensure database tables are initialized at app launch."""
    database.init_db()

@app.get("/login")
async def login(request: Request):
    """Redirects to the Google login screen."""
    if "user" in request.session:
        return RedirectResponse(url="/")
    
    # Allow local HTTP redirect URI in dev environment
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    
    redirect_uri = request.url_for("auth")
    # Allow override in .env for custom redirect URIs if needed
    env_redirect = os.getenv("OAUTH_REDIRECT_URI")
    if env_redirect:
        redirect_uri = env_redirect
        
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth")
async def auth(request: Request):
    """Processes Google OAuth callback and sets up session isolation."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        print(f"[Error] Google OAuth authentication failed: {e}")
        return RedirectResponse(url="/login?error=authentication_failed")
    
    userinfo = token.get("userinfo")
    if not userinfo:
        print("[Error] User profile information not received from Google")
        return RedirectResponse(url="/login?error=missing_user_profile")
    
    user_id = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name", "")
    picture_url = userinfo.get("picture", "")
    
    if not user_id or not email:
        print("[Error] Google identity attributes incomplete")
        return RedirectResponse(url="/login?error=incomplete_identity")
    
    # Upsert user record in database
    database.create_or_update_user(user_id, email, name, picture_url)
    
    # Save user credentials to session
    request.session["user"] = {
        "id": user_id,
        "email": email,
        "name": name,
        "picture_url": picture_url
    }
    
    return RedirectResponse(url="/")

@app.get("/logout")
async def logout(request: Request):
    """Wipes the active session and redirects to the login route."""
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, session_id: str = None):
    """Renders the main logistics assistant dashboard."""
    user = request.session.get("user")
    if not user:
        # Redirect to login route if unauthenticated
        return RedirectResponse(url="/login")
    
    # Fetch all user active chat sessions
    sessions = database.get_user_sessions(user["id"])
    
    active_session = None
    messages = []
    
    if session_id:
        active_session = database.get_session(session_id)
        # Security/isolation: Ensure the session is owned by current user
        if active_session and active_session["user_id"] == user["id"]:
            messages = database.get_session_messages(session_id)
        else:
            active_session = None
            session_id = None
            
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "sessions": sessions,
            "active_session": active_session,
            "messages": messages,
            "active_session_id": session_id
        }
    )

@app.post("/session")
async def create_new_session(request: Request, name: str = Form("New Chat")):
    """Creates a new logistics assistant chat session."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    session_id = database.create_session(user["id"], name=name)
    
    # Pre-populate session with the Logistics Voice Agent greeting message
    manager = ConversationManager()
    greeting = manager.initiate_conversation()
    database.save_message(session_id, "assistant", greeting)
    
    # Persist the initial greeting state
    database.update_session_state(
        session_id,
        workflow=manager.current_workflow,
        tracking_id=manager.slots["tracking_id"],
        pickup_location=manager.slots["pickup_location"],
        pickup_date=manager.slots["pickup_date"]
    )
    
    return RedirectResponse(url=f"/?session_id={session_id}", status_code=303)

@app.post("/session/delete/{session_id}")
async def delete_chat_session(request: Request, session_id: str):
    """Deletes a logistics chat session and its corresponding messages."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Security/isolation check
    session = database.get_session(session_id)
    if session and session["user_id"] == user["id"]:
        database.delete_session(session_id)
        
    return RedirectResponse(url="/", status_code=303)

@app.post("/session/{session_id}/message")
async def send_chat_message(request: Request, session_id: str, text: str = Form(...)):
    """Receives and processes text messages, matching logistics conversation flow."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    session_data = database.get_session(session_id)
    if not session_data or session_data["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if not text.strip():
        return RedirectResponse(url=f"/?session_id={session_id}", status_code=303)
        
    # 1. Save user's incoming message
    database.save_message(session_id, "user", text.strip())
    
    # 2. Instantiate and restore conversation manager state
    manager = ConversationManager()
    manager.current_workflow = session_data["workflow"] or "NONE"
    manager.slots = {
        "tracking_id": session_data["tracking_id"],
        "pickup_location": session_data["pickup_location"],
        "pickup_date": session_data["pickup_date"]
    }
    
    # Retrieve messages history
    history_messages = database.get_session_messages(session_id)
    manager.history = []
    for msg in history_messages[-6:]:
        manager.history.append({
            "role": msg["sender"],
            "content": msg["text"]
        })
        
    # 3. Process message through Logistics LLM agent
    response, intent = manager.process_message(text.strip())
    
    # 4. Save response to database
    database.save_message(session_id, "assistant", response)
    
    # 5. Save updated state and slots to database
    database.update_session_state(
        session_id,
        workflow=manager.current_workflow,
        tracking_id=manager.slots["tracking_id"],
        pickup_location=manager.slots["pickup_location"],
        pickup_date=manager.slots["pickup_date"]
    )
    
    # Update default "New Chat" title with user's first input for UX elegance
    if session_data["name"] == "New Chat":
        new_name = text.strip()[:24]
        if len(text.strip()) > 24:
            new_name += "..."
        conn = database.get_db_connection()
        conn.execute("UPDATE chat_sessions SET name = ? WHERE session_id = ?", (new_name, session_id))
        conn.commit()
        conn.close()
        
    return RedirectResponse(url=f"/?session_id={session_id}", status_code=303)
