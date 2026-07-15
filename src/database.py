import os
import sqlite3
import uuid
from datetime import datetime

# Default database path in the project root folder
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "colaberry_voice.db"
)

def get_db_connection(db_path=None):
    """
    Establishes a connection to the SQLite database.
    Enables Foreign Key constraints and returns Row objects for dictionary-like access.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    """
    Initializes the database schema by creating all required tables if they do not exist.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        picture_url TEXT
    );
    """)

    # Create chat_sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        workflow TEXT DEFAULT 'NONE',
        tracking_id TEXT,
        pickup_location TEXT,
        pickup_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # Create messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        sender TEXT CHECK(sender IN ('user', 'assistant')) NOT NULL,
        text TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id) ON DELETE CASCADE
    );
    """)

    # Create telemetrics table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        turn_latency REAL,
        vad_latency REAL,
        tokens_processed INTEGER,
        FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()
    print("Database schema initialized successfully.")

def create_or_update_user(user_id: str, email: str, name: str, picture_url: str, db_path=None):
    """
    Inserts a new user or updates details for an existing user after Google OAuth login.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO users (id, email, name, picture_url)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        email=excluded.email,
        name=excluded.name,
        picture_url=excluded.picture_url;
    """, (user_id, email, name, picture_url))
    conn.commit()
    conn.close()

def get_user(user_id: str, db_path=None):
    """
    Retrieves user profile details by their user ID.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, name, picture_url FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_session(user_id: str, name: str = "New Chat", db_path=None) -> str:
    """
    Generates a unique session_id, creates a new chat session for a user, and returns the session_id.
    """
    session_id = str(uuid.uuid4())
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO chat_sessions (session_id, user_id, name, workflow)
    VALUES (?, ?, ?, 'NONE');
    """, (session_id, user_id, name))
    conn.commit()
    conn.close()
    return session_id

def get_user_sessions(user_id: str, db_path=None) -> list:
    """
    Retrieves all chat sessions corresponding to a user, sorted by creation date descending.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT session_id, user_id, name, created_at, workflow, tracking_id, pickup_location, pickup_date
    FROM chat_sessions
    WHERE user_id = ?
    ORDER BY created_at DESC;
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_session(session_id: str, db_path=None) -> dict:
    """
    Retrieves metadata for a specific chat session.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT session_id, user_id, name, created_at, workflow, tracking_id, pickup_location, pickup_date
    FROM chat_sessions
    WHERE session_id = ?;
    """, (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_session_state(session_id: str, workflow: str, tracking_id: str = None, pickup_location: str = None, pickup_date: str = None, db_path=None):
    """
    Updates logistics context/state fields for an active chat session.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE chat_sessions
    SET workflow = ?, tracking_id = ?, pickup_location = ?, pickup_date = ?
    WHERE session_id = ?;
    """, (workflow, tracking_id, pickup_location, pickup_date, session_id))
    conn.commit()
    conn.close()

def delete_session(session_id: str, db_path=None):
    """
    Deletes a session and cascading records (messages/telemetry).
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?;", (session_id,))
    conn.commit()
    conn.close()

def get_session_messages(session_id: str, db_path=None) -> list:
    """
    Retrieves all transcript messages from a session, ordered chronologically.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, session_id, sender, text, timestamp
    FROM messages
    WHERE session_id = ?
    ORDER BY timestamp ASC;
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_message(session_id: str, sender: str, text: str, db_path=None):
    """
    Appends a new conversation message to a session.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO messages (session_id, sender, text)
    VALUES (?, ?, ?);
    """, (session_id, sender, text))
    conn.commit()
    conn.close()

def save_telemetry(session_id: str, turn_latency: float, vad_latency: float, tokens_processed: int, db_path=None):
    """
    Records telemetrics for evaluating processing time and token counts.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO telemetrics (session_id, turn_latency, vad_latency, tokens_processed)
    VALUES (?, ?, ?, ?);
    """, (session_id, turn_latency, vad_latency, tokens_processed))
    conn.commit()
    conn.close()
