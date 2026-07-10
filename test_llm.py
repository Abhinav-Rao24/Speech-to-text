import os
import sqlite3
from dotenv import load_dotenv
from src.llm_engine import generate_llm_response
from src.eval_logger import get_next_sequential_session_id

# 1. Load variables and verify environment setup
load_dotenv()
print("--- ENVIRONMENT CHECK ---")
print(f"OpenRouter Key Found: {bool(os.getenv('OPENROUTER_API_KEY'))}")
print(f"Base URL: {os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')}\n")

DB_PATH = "transcripts.db"

def setup_mock_db():
    """Ensures the transcripts table exists for local validation."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_text TEXT,
            ai_response TEXT,
            latency_ms INTEGER
        )
    """)
    conn.commit()
    conn.close()

def log_exchange_mock(session_id, user_text, ai_response):
    """Mocks the continuous sync logging loop from Phase 3/4."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transcripts (session_id, user_text, ai_response, latency_ms) VALUES (?, ?, ?, ?)",
        (session_id, user_text, ai_response, 1500)
    )
    conn.commit()
    conn.close()

# --- RUN EXECUTION TEST ---
setup_mock_db()

# Test ID generation sequence (Task 9)
session_id = get_next_sequential_session_id("abhinav", DB_PATH)
print(f"--- SESSION GENERATION TEST ---")
print(f"Generated Session ID: {session_id}\n")

print(f"--- LIVE LLM & PROMPT LIBRARY TEST ---")
# Turn 1: Test Scenario 2 (Pickup Scheduling & Human-Readable IDs)
query_1 = "I want to place an order to ship a watch and a camera."
print(f"User: {query_1}")
reply_1 = generate_llm_response(session_id, query_1, DB_PATH)
print(f"AI: {reply_1}\n")
log_exchange_mock(session_id, query_1, reply_1)

# Turn 2: Test Scenario 1 & Context Handling (Batch Tracking via memory)
query_2 = "Where are my packages right now?"
print(f"User: {query_2}")
reply_2 = generate_llm_response(session_id, query_2, DB_PATH)
print(f"AI: {reply_2}\n")
log_exchange_mock(session_id, query_2, reply_2)

# Turn 3: Test Scenario 5 (Unknown / Off-topic validation)
query_3 = "Can you tell me a joke?"
print(f"User: {query_3}")
reply_3 = generate_llm_response(session_id, query_3, DB_PATH)
print(f"AI: {reply_3}\n")