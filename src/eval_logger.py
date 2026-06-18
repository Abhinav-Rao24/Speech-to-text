import sqlite3
import datetime
import os
import sys

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcripts.db")


def init_db():
    """
    Initialise the SQLite database and create the transcription_logs table if it
    does not already exist.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcription_logs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT    NOT NULL,
            filename         TEXT    NOT NULL,
            engine_provider  TEXT    NOT NULL,
            raw_text         TEXT,
            duration_seconds REAL,
            wer_score        REAL
        )
    """)
    conn.commit()
    conn.close()


def log_transcription(
    filename: str,
    engine_provider: str,
    raw_text: str,
    duration_seconds: float,
    reference_text: str = None,
) -> int:
    """
    Write one transcription result to the database.

    Parameters
    ----------
    filename        : Path or name of the audio file that was transcribed.
    engine_provider : 'local' or 'sarvam'.
    raw_text        : The transcribed text returned by the engine.
    duration_seconds: Processing / network round-trip time in seconds.
    reference_text  : Optional ground-truth text used to compute WER.

    Returns
    -------
    The row-id of the newly inserted record.
    """
    wer_score = None
    if reference_text and raw_text:
        try:
            import jiwer
            wer_score = round(jiwer.wer(reference_text.strip(), raw_text.strip()), 4)
        except Exception as e:
            print(f"[eval_logger] WER calculation failed: {e}")

    timestamp = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transcription_logs
            (timestamp, filename, engine_provider, raw_text, duration_seconds, wer_score)
        VALUES
            (?, ?, ?, ?, ?, ?)
        """,
        (timestamp, os.path.basename(filename), engine_provider, raw_text, duration_seconds, wer_score),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def fetch_logs(limit: int = 20):
    """
    Return the most recent *limit* transcription log entries as a list of dicts.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM transcription_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def print_recent_logs(limit: int = 10):
    """Pretty-print the most recent log entries to the console."""
    rows = fetch_logs(limit)
    if not rows:
        print("No log entries found.")
        return

    separator = "-" * 80
    print(f"\n{'='*80}")
    print(f"  TRANSCRIPTION LOG  (last {limit} entries)")
    print(f"{'='*80}")
    for row in rows:
        wer_display = f"{row['wer_score']:.4f}" if row["wer_score"] is not None else "N/A"
        print(separator)
        print(f"  ID        : {row['id']}")
        print(f"  Timestamp : {row['timestamp']}")
        print(f"  File      : {row['filename']}")
        print(f"  Engine    : {row['engine_provider']}")
        print(f"  Duration  : {row['duration_seconds']:.2f}s")
        print(f"  WER       : {wer_display}")
        print(f"  Transcript: {(row['raw_text'] or '').strip()[:120]}")
    print(separator)


# Initialise DB on import so callers never have to worry about it.
init_db()
