"""
demo.py – Unified Speech-to-Text Demo & Evaluation Dashboard
=============================================================
Reads STT_PROVIDER from config.py to decide which engine to use:
  • "local"  → faster-whisper  (src/stt_engine.py)
  • "sarvam" → Sarvam AI cloud  (src/sarvam_engine.py)

Usage
-----
  # Use the engine defined in config.py
  python demo.py

  # Override engine for this run only
  python demo.py --engine sarvam
  python demo.py --engine local

  # Supply a ground-truth reference for WER scoring
  python demo.py --engine local --reference "Hello this is a test"

  # Transcribe an existing audio file (skip recording)
  python demo.py --audio path/to/file.wav --reference "..."

  # Print the last N log entries from the DB
  python demo.py --logs [N]
"""

import argparse
import os
import sys
import textwrap

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so we can import config and src/*
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "src")
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import STT_PROVIDER          # noqa: E402
from src.eval_logger import log_transcription, print_recent_logs, get_next_sequential_session_id, DB_PATH  # noqa: E402
from src.llm_engine import generate_llm_response # noqa: E402
import sqlite3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator(char: str = "=", width: int = 72) -> str:
    return char * width


def _print_banner(engine: str):
    print(_separator())
    print("  Speech-to-Text Evaluation Dashboard")
    print(f"  Active engine : {engine.upper()}")
    print(_separator())


def _print_result_block(result: dict, engine: str, ref: str = None):
    """Print a formatted comparison / result block."""
    print(f"\n{_separator('-')}")
    print(f"  ENGINE      : {engine.upper()}")
    print(f"  FILE        : {result.get('_filename', 'recorded audio')}")
    print(f"  LANGUAGE    : {result.get('language', 'N/A')}")
    print(f"  DURATION    : {result.get('execution_time', 0):.2f}s")

    if engine == "local":
        print(f"  CONFIDENCE  : {result.get('probability', 0):.2f}")

    if ref:
        try:
            import jiwer
            wer_val = jiwer.wer(ref.strip(), result.get("text", "").strip())
            print(f"  WER vs ref  : {wer_val:.4f}  ({wer_val*100:.1f}%)")
        except Exception:
            print("  WER vs ref  : (jiwer not available)")

    print(f"\n  TRANSCRIPT  :")
    wrapped = textwrap.fill(result.get("text", "").strip(), width=68, initial_indent="    ", subsequent_indent="    ")
    print(wrapped or "    (empty)")

    if ref:
        print(f"\n  GROUND TRUTH:")
        wrapped_ref = textwrap.fill(ref.strip(), width=68, initial_indent="    ", subsequent_indent="    ")
        print(wrapped_ref)

    print(_separator("-"))


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def log_interaction(session_id, user_text, ai_response):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transcripts (session_id, user_text, ai_response, latency_ms) VALUES (?, ?, ?, ?)",
        (session_id, user_text, ai_response, 0)
    )
    conn.commit()
    conn.close()

def acquire_and_transcribe(engine: str, audio_path: str = None, reference: str = None):
    # Step 1: Audio acquisition
    if audio_path:
        wav_path = audio_path
        print(f"[demo] Using provided audio file: {wav_path}")
    else:
        print("[demo] Starting recorder – speak into your microphone...")
        from recorder import record_audio
        wav_path = record_audio(output_filename=os.path.join(ROOT, "output.wav"))
        if not wav_path:
            print("[demo] No audio captured. Exiting.")
            return None

    # Step 2: Transcription
    result = None
    if engine == "local":
        from src.stt_engine import transcribe_local
        result = transcribe_local(wav_path)
    elif engine == "sarvam":
        from src.sarvam_engine import transcribe_sarvam
        result = transcribe_sarvam(wav_path)
    else:
        print(f"[demo] Unknown engine '{engine}'.")
        return None

    if result is None:
        print("[demo] Transcription returned no result.")
        return None

    result["_filename"] = wav_path

    # Step 3: Log to SQLite (legacy STT logs)
    log_transcription(
        filename=wav_path,
        engine_provider=engine,
        raw_text=result.get("text", ""),
        duration_seconds=result.get("execution_time", 0.0),
        reference_text=reference,
    )
    return result

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unified STT Demo & Evaluation Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--engine",
        choices=["local", "sarvam"],
        default=STT_PROVIDER,
        help='Engine to use: "local" (faster-whisper) or "sarvam" (Sarvam AI API). '
             f'Defaults to STT_PROVIDER from config.py (currently: "{STT_PROVIDER}")',
    )
    parser.add_argument(
        "--audio",
        metavar="PATH",
        default=None,
        help="Path to an existing audio file. Skips the live recorder when supplied.",
    )
    parser.add_argument(
        "--reference",
        metavar="TEXT",
        default=None,
        help="Ground-truth transcript used to compute Word Error Rate (WER).",
    )
    parser.add_argument(
        "--logs",
        nargs="?",
        const=10,
        type=int,
        metavar="N",
        help="Print the last N log entries from transcripts.db and exit (default N=10).",
    )

    args = parser.parse_args()

    if args.logs is not None:
        print_recent_logs(limit=args.logs)
        return

    _print_banner(args.engine)

    while True:
        try:
            user_input = input("Enter User ID or type 'new': ").strip()
            if not user_input:
                continue
            if user_input.lower() == 'new':
                user_name = input("Enter your name: ").strip()
                session_id = get_next_sequential_session_id(user_name, DB_PATH)
                print(f"Registration complete! Active Session: {session_id}")
            else:
                session_id = user_input
                print("Session rehydrated.")

            while True:
                result = acquire_and_transcribe(args.engine, args.audio, args.reference)
                if not result:
                    break
                
                transcript = result.get("text", "").strip()
                if not transcript:
                    continue

                lower_t = transcript.lower()
                if "/switch" in lower_t or "/exit" in lower_t:
                    break

                print(f"User: {transcript}")
                ai_response = generate_llm_response(session_id, transcript, DB_PATH)
                print(f"Assistant: {ai_response}")
                log_interaction(session_id, transcript, ai_response)
                
                # If reading from a static file, we don't want an infinite loop
                if args.audio:
                    break
                    
            if args.audio:
                break
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except EOFError:
            break

if __name__ == "__main__":
    main()
