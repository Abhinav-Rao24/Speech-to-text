import os
import sqlite3
import sys
from openai import OpenAI

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

PROMPT_LIBRARY = {
    "tracking": "tracking: If the user asks about the status or location of their items, scan the short-term history window. Summarize and provide updates for the respective active products mentioned in this session.",
    "pickup": "pickup / order placement: You must actively gather three specific parameters before confirming a shipment: 1) Product Type, 2) Delivery Address, you need not ask for the exact location, just the city and state is enough and 3) Expected Timeline. Scan the active session's short-term history window. If any of these are missing, do not confirm the order; politely prompt for the missing details. Once all 3 are gathered, assign a human-readable ID. You don't require specifications of the details like product model or pincode of the location etc. (e.g., watch_101) and explicitly state: 'CONFIRMED: Booking shipment for [Product] to [Address] with an expected timeline of [Timeline]. Tracking handle is [ID].'",
    "delays": "delays: If the user asks about a delayed item, express professional empathy, provide a realistic operational reason (like severe weather or sorting hub congestion), and offer an updated delivery buffer of exactly '24 to 48 hours'.",
    "faq": "faq: General logistics FAQs. Delivery takes 2-3 business days. Operating hours are 24/7.",
    "unknown": "unknown / off-topic: If the query is ambiguous, gibberish, or a joke, politely pivot back to logistics support."
}

def fetch_short_term_memory(session_id: str, db_path: str, limit: int = 50) -> list:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_text, ai_response FROM (
            SELECT id, user_text, ai_response FROM transcripts
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
        ) ORDER BY id ASC
        """,
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        user_text, ai_response = row
        if user_text:
            messages.append({"role": "user", "content": str(user_text)})
        if ai_response:
            messages.append({"role": "assistant", "content": str(ai_response)})
            
    return messages

def generate_llm_response(session_id: str, transcript: str, db_path: str, system_modifier: str = None) -> str:
    client = OpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY
    )
    
    base_prompt = "You are an automated Customer Support Assistant for Colaberry. Keep responses clear, professional, and strictly under 3 sentences. You are bilingual: if the user queries in Telugu, reply in clean, professional Telugu; if English, reply in English. Your response MUST start with an ultra-short introductory sentence of fewer than 5 words (e.g., 'Sure, checking that now.' or 'Aapka status yeh hai.'). Put the main detailed logistics information in the subsequent sentences."
    
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
    if system_modifier:
        system_prompt += " " + system_modifier
    
    history = fetch_short_term_memory(session_id, db_path)
    print(f"\n[DEBUG] Context Check: Sending {len(history)} past messages for session '{session_id}' to OpenRouter.\n")
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": transcript}]
    
    try:
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            max_tokens=500,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            return "I'm unable to understand your request. Could you please provide more details?"
        return content.strip()
    except Exception as e:
        return "System error: Unable to connect to central dispatch."
