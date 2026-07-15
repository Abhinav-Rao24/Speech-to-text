import os
import sys
from fastapi import FastAPI, Request, Form, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import uuid
import wave
import time
import config

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

# Mount static files directory
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "web", "static")), name="static")

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
    """Renders the landing home dashboard page."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
    
    theme_class = request.cookies.get("theme", "dark")
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "user": user,
            "theme_class": theme_class,
            "active_session_id": session_id
        }
    )

@app.get("/conversations", response_class=HTMLResponse)
async def conversations(request: Request, session_id: str = None):
    """Renders the logistics conversation dashboard panel."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
    
    theme_class = request.cookies.get("theme", "dark")
    sessions = database.get_user_sessions(user["id"])
    
    active_session = None
    messages = []
    
    if session_id:
        active_session = database.get_session(session_id)
        if active_session and active_session["user_id"] == user["id"]:
            messages = database.get_session_messages(session_id)
        else:
            active_session = None
            session_id = None
            
    return templates.TemplateResponse(
        request=request,
        name="conversations.html",
        context={
            "user": user,
            "sessions": sessions,
            "active_session": active_session,
            "messages": messages,
            "active_session_id": session_id,
            "theme_class": theme_class
        }
    )

@app.get("/telemetry", response_class=HTMLResponse)
async def telemetry(request: Request, session_id: str = None):
    """Renders the pipeline latency diagnostics dashboard."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
    
    theme_class = request.cookies.get("theme", "dark")
    sessions = database.get_user_sessions(user["id"])
    
    active_session = None
    if session_id:
        active_session = database.get_session(session_id)
        if not active_session or active_session["user_id"] != user["id"]:
            active_session = None
            session_id = None
            
    return templates.TemplateResponse(
        request=request,
        name="telemetry.html",
        context={
            "user": user,
            "sessions": sessions,
            "active_session": active_session,
            "active_session_id": session_id,
            "theme_class": theme_class
        }
    )

@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, session_id: str = None):
    """Renders the user account details page."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
        
    theme_class = request.cookies.get("theme", "dark")
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "user": user,
            "theme_class": theme_class,
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
    
    return RedirectResponse(url=f"/conversations?session_id={session_id}", status_code=303)

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
        
    return RedirectResponse(url="/conversations", status_code=303)

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
        return RedirectResponse(url=f"/conversations?session_id={session_id}", status_code=303)
        
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
        
    return RedirectResponse(url=f"/conversations?session_id={session_id}", status_code=303)


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket, session_id: str):
    """
    Handles real-time client microphone audio streaming.
    Verifies user authentication context via scope session cookie.
    Accumulates binary PCM data, routes it to STT, LLM, and TTS pipelines.
    Logs transaction latencies and token bandwidth metrics.
    """
    # Access Session context for security/isolation check
    session_user = websocket.scope.get("session", {}).get("user")
    if not session_user:
        await websocket.close(code=1008) # Policy Violation
        return

    # Check active session ownership
    session_data = database.get_session(session_id)
    if not session_data or session_data["user_id"] != session_user["id"]:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    
    pcm_data = bytearray()
    
    try:
        while True:
            # Accept binary audio chunks or control commands
            message = await websocket.receive()
            if "bytes" in message:
                pcm_data.extend(message["bytes"])
            elif "text" in message:
                import json
                cmd = json.loads(message["text"])
                if cmd.get("type") == "stop_recording":
                    # Stop signal received, run pipeline
                    await run_voice_pipeline(websocket, session_id, pcm_data, session_data)
                    pcm_data = bytearray() # Clear stream buffer
    except WebSocketDisconnect:
        print(f"[WebSocket] Session {session_id} disconnected")
    except Exception as e:
        print(f"[WebSocket Error] Session {session_id}: {e}")
        try:
            await websocket.close()
        except:
            pass

async def run_voice_pipeline(websocket: WebSocket, session_id: str, pcm_data: bytearray, session_data: dict):
    if len(pcm_data) == 0:
        return
        
    start_turn_time = time.time()
    
    # Save raw PCM bytes as a temporary 16kHz Mono 16-bit WAV file
    temp_wav_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        f"temp_input_{uuid.uuid4().hex}.wav"
    )
    
    try:
        with wave.open(temp_wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit PCM
            wav_file.setframerate(16000) # 16kHz
            wav_file.writeframes(pcm_data)
    except Exception as e:
        print(f"[Error] Failed to write temp input WAV: {e}")
        return

    # 1. Speech-to-Text (STT) processing
    stt_start_time = time.time()
    stt_result = None
    try:
        provider = getattr(config, "STT_PROVIDER", "sarvam").lower()
        if provider == "local":
            from src.stt_engine import transcribe_local
            stt_result = transcribe_local(temp_wav_path)
        else:
            from src.sarvam_engine import transcribe_sarvam
            stt_result = transcribe_sarvam(temp_wav_path)
    except Exception as e:
        print(f"[STT Error] Speech recognition failed: {e}")
    finally:
        # Delete temp audio input file immediately to clean up workspace
        try:
            if os.path.exists(temp_wav_path):
                os.remove(temp_wav_path)
        except Exception as e:
            print(f"[Warning] Failed to remove temp audio file: {e}")

    if not stt_result or not stt_result.get("text", "").strip():
        # Inform client of silence / recognition failure
        await websocket.send_json({
            "type": "transcript",
            "sender": "assistant",
            "text": "I couldn't catch that. Please speak again while holding the mic."
        })
        return

    user_text = stt_result["text"].strip()
    
    # 2. Commit User dialogue transcript bubble to SQLite
    database.save_message(session_id, "user", user_text)
    
    # Send user's text back to dynamically append transcript on client screen
    await websocket.send_json({
        "type": "transcript",
        "sender": "user",
        "text": user_text
    })

    # 3. Instantiate and restore ConversationManager state
    manager = ConversationManager()
    manager.current_workflow = session_data["workflow"] or "NONE"
    manager.slots = {
        "tracking_id": session_data["tracking_id"],
        "pickup_location": session_data["pickup_location"],
        "pickup_date": session_data["pickup_date"]
    }
    
    # Fetch historical rolling window
    history_messages = database.get_session_messages(session_id)
    manager.history = []
    for msg in history_messages[-6:]:
        manager.history.append({
            "role": msg["sender"],
            "content": msg["text"]
        })

    # 4. Generate Logistics response intent
    ai_response, intent = manager.process_message(user_text)

    # Commit Assistant response to SQLite
    database.save_message(session_id, "assistant", ai_response)
    
    # Update active slots state in SQLite
    database.update_session_state(
        session_id,
        workflow=manager.current_workflow,
        tracking_id=manager.slots["tracking_id"],
        pickup_location=manager.slots["pickup_location"],
        pickup_date=manager.slots["pickup_date"]
    )

    # Send assistant's text back to dynamically append transcript on client screen
    await websocket.send_json({
        "type": "transcript",
        "sender": "assistant",
        "text": ai_response
    })

    # Update session name if it was default "New Chat"
    if session_data["name"] == "New Chat":
        new_name = user_text[:24]
        if len(user_text) > 24:
            new_name += "..."
        conn = database.get_db_connection()
        conn.execute("UPDATE chat_sessions SET name = ? WHERE session_id = ?", (new_name, session_id))
        conn.commit()
        conn.close()

    # 5. Text-to-Speech (TTS) generation
    tts_start_time = time.time()
    
    # Active language mapping
    raw_lang = stt_result.get("language", "en-IN")
    lang_mapping = {
        "te": "te-IN",
        "hi": "hi-IN",
        "en": "en-IN"
    }
    language_code = lang_mapping.get(raw_lang, raw_lang)
    if not language_code or language_code == "Unknown":
        language_code = "en-IN"

    from src.tts_engine import generate_voice_output
    tts_audio_path = generate_voice_output(ai_response, language_code)
    
    # Telemetry measurements
    turn_latency = time.time() - start_turn_time
    vad_latency = 150.0  # mock VAD silence interruption threshold
    
    words_count = len(ai_response.split())
    tokens_processed = int(words_count * 1.3)
    if tokens_processed == 0:
        tokens_processed = 1

    # Commit Latency metrics to DB
    database.save_telemetry(session_id, turn_latency, vad_latency, tokens_processed)

    # Stream synthesized audio binary data back to client
    if tts_audio_path and os.path.exists(tts_audio_path):
        try:
            with open(tts_audio_path, "rb") as f:
                audio_bytes = f.read()
            await websocket.send_bytes(audio_bytes)
            
            # Safe delete generated audio file to prevent junk accumulation
            os.remove(tts_audio_path)
        except Exception as e:
            print(f"[Error] Failed to stream audio file: {e}")
