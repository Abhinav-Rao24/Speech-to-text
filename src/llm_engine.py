import os
import sqlite3
import sys
from openai import OpenAI

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

PROMPT_LIBRARY = {
    "tracking": "The user wants to track their shipments. Scan the immediate short-term history window. If they have mentioned multiple products in this active session (e.g., watch_101 and laptop_101), summarize and provide mock locations/ETAs for BOTH items at the same time in a single response, rather than making them ask individually.",
    "pickup": "The user wants to schedule a pickup. Ask for the item description. When acknowledging the items, assign them simple, memorable human-readable shipment IDs combining the item name with a sequential number matching the session's numeric part (e.g., if session is abhinav_101 and they are shipping a watch, name the shipment ID 'watch_101').",
    "delays": "The user is asking about delays. Express professional empathy, look at the active session products, and explain transit delays affecting their specific custom item IDs.",
    "faq": "General logistics FAQs. Delivery takes 2-3 business days. Operating hours are 24/7.",
    "unknown": "The user request is ambiguous, invalid, or off-topic (e.g., gibberish, jokes). Politely redirect them to logistics support."
}

def fetch_short_term_memory(session_id: str, db_path: str, limit: int = 10) -> list:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_text, ai_response FROM transcripts
        WHERE session_id = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()

    messages = []
    # reverse to chronological
    for row in reversed(rows):
        user_text, ai_response = row
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if ai_response:
            messages.append({"role": "assistant", "content": ai_response})
            
    return messages

def generate_llm_response(session_id: str, transcript: str, db_path: str) -> str:
    client = OpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY
    )
    
    base_prompt = "You are a logistics support assistant for Saaras Logistics. Provide clear, professional, short responses. Keep answers under 4 sentences. Do not provide information unrelated to logistics."
    
    # Simple Intent Routing
    lower_t = transcript.lower()
    scenario = "unknown"
    if "track" in lower_t or "status" in lower_t or "where" in lower_t:
        scenario = "tracking"
    elif "pickup" in lower_t or "schedule" in lower_t or "ship" in lower_t:
        scenario = "pickup"
    elif "delay" in lower_t or "late" in lower_t:
        scenario = "delays"
    elif "faq" in lower_t or "how long" in lower_t or "hours" in lower_t or "days" in lower_t:
        scenario = "faq"
        
    system_prompt = base_prompt + " " + PROMPT_LIBRARY[scenario]
    
    messages = [{"role": "system", "content": system_prompt}]
    
    short_term_memory = fetch_short_term_memory(session_id, db_path)
    messages.extend(short_term_memory)
    
    messages.append({"role": "user", "content": transcript})
    
    try:
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            return "I'm unable to understand your request. Could you please provide more details?"
        return content.strip()
    except Exception as e:
        return "System error: Unable to connect to central dispatch."
