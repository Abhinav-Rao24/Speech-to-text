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
import io
import math
import os
import struct
import sys
import textwrap
import threading
import time

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
from src.tts_engine import generate_voice_output  # noqa: E402
import sqlite3
import pygame

# Initialize pygame mixer at startup
pygame.mixer.init()

# ---------------------------------------------------------------------------
# Barge-In Constants
# ---------------------------------------------------------------------------
# RMS amplitude threshold (0–32767 range for 16-bit PCM).
# Raise this if background noise causes false triggers.
BARGE_IN_THRESHOLD   = 500
# How many consecutive milliseconds of above-threshold audio counts as speech.
BARGE_IN_DURATION_MS = 200
# PyAudio microphone monitoring settings
PYAUDIO_CHUNK        = 1024   # frames per read
PYAUDIO_RATE         = 16000  # Hz

class AudioPrefetcher:
    """
    A thread-safe audio prefetcher that fetches TTS audio for a list of sentences
    concurrently in a background thread.

    Key design improvements over the previous version:
    - Raw audio **bytes** are stored in memory (not disk paths), eliminating the
      disk-read latency between TTS download and pygame playback.
    - A ``threading.Event`` per sentence index replaces the busy-poll
      ``time.sleep(0.05)`` loop, so ``get_audio(idx)`` blocks efficiently until
      exactly that sentence is ready — not until all are done.
    - ``stop()`` signals the background thread *and* sets all pending Events so
      any waiting ``get_audio()`` call unblocks immediately (needed for barge-in).
    """

    def __init__(self, sentences: list, language_code: str):
        self.sentences = sentences
        self.language_code = language_code
        self._audio_bytes: dict[int, bytes | None] = {}   # index -> raw wav bytes (or None on failure)
        self._events: list[threading.Event] = [threading.Event() for _ in sentences]
        self._lock = threading.Lock()
        self.stopped = False
        self._thread = threading.Thread(target=self._fetch_loop, daemon=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background TTS prefetch thread."""
        self._thread.start()

    def stop(self) -> None:
        """
        Signal the background thread to stop and unblock any waiting
        ``get_audio()`` calls so the playback loop can exit cleanly.
        """
        self.stopped = True
        # Unblock all events so any thread blocked in get_audio() returns.
        for event in self._events:
            event.set()

    def get_audio(self, idx: int) -> bytes | None:
        """
        Block until the audio bytes for *idx* are available (or the prefetcher
        has been stopped), then return the raw WAV bytes.

        Returns ``None`` if TTS generation failed or the prefetcher was stopped
        before the sentence was ready.
        """
        # Wait efficiently (no CPU spin) for the event to be set by _fetch_loop.
        self._events[idx].wait()
        if self.stopped:
            return None
        with self._lock:
            return self._audio_bytes.get(idx)  # may be None if TTS failed

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _fetch_loop(self) -> None:
        for idx, sentence in enumerate(self.sentences):
            if self.stopped:
                break
            # generate_voice_output writes to disk and returns the path.
            # We read the bytes immediately so the file can be cleaned up
            # and the playback path is fully in-memory.
            path = generate_voice_output(sentence, self.language_code)
            raw: bytes | None = None
            if path and os.path.exists(path):
                try:
                    with open(path, "rb") as fh:
                        raw = fh.read()
                except OSError as exc:
                    print(f"[AudioPrefetcher] Could not read TTS file for sentence {idx + 1}: {exc}")
                finally:
                    # Remove the temp file — we have the bytes in memory now.
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            with self._lock:
                self._audio_bytes[idx] = raw
            # Signal the playback thread that this sentence is ready.
            self._events[idx].set()


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

                lower_t = transcript.lower().strip()
                exit_commands = ["that's it", "that is it", "exit", "stop", "/switch", "/exit"]
                if any(cmd in lower_t for cmd in exit_commands):
                    print("\nGracefully exiting voice session. Goodbye!\n")
                    break

                # Active conversational language code tracking with fallback mappings
                raw_lang = result.get("language", "en-IN")
                lang_mapping = {
                    "te": "te-IN",
                    "hi": "hi-IN",
                    "en": "en-IN"
                }
                language_code = lang_mapping.get(raw_lang, raw_lang)
                if not language_code or language_code == "Unknown":
                    language_code = "en-IN"

                # Define the system instruction modifier based on the active language_code
                brevity_instruction = " Your response MUST start with an ultra-short introductory sentence of fewer than 5 words (e.g., 'Sure, checking that now.' or 'Aapka status yeh hai.'). Put the main detailed logistics information in the subsequent sentences."
                if language_code == "hi-IN":
                    system_modifier = "Respond naturally in colloquial Hinglish (Hindi mixed with English words, written strictly using the Latin script/English alphabet). Keep it short and conversational." + brevity_instruction
                elif language_code == "te-IN":
                    system_modifier = "Respond naturally in conversational Telugu-English code-switched phrases written strictly using the Latin script/English alphabet. Keep it short and conversational." + brevity_instruction
                else:
                    system_modifier = "Respond in crisp, clear logistics English." + brevity_instruction

                print(f"\n\033[92mUser: {transcript}\033[0m")
                ai_response = generate_llm_response(session_id, transcript, DB_PATH, system_modifier=system_modifier)
                print(f"\033[96mAssistant: {ai_response}\033[0m\n")
                
                # Split the full response into clean sentences using regex
                import re
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', ai_response) if s.strip()]
                if not sentences:
                    sentences = [ai_response.strip()]

                # -------------------------------------------------------
                # Start background TTS prefetch (sentences -> memory bytes)
                # -------------------------------------------------------
                prefetcher = AudioPrefetcher(sentences, language_code)
                prefetcher.start()

                # -------------------------------------------------------
                # Open a PyAudio input stream for barge-in monitoring.
                # We open it once here and share it across all sentences.
                # -------------------------------------------------------
                import pyaudio
                _pa = pyaudio.PyAudio()
                _mic_stream = None
                try:
                    _mic_stream = _pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=PYAUDIO_RATE,
                        input=True,
                        frames_per_buffer=PYAUDIO_CHUNK,
                    )
                except Exception as _mic_err:
                    print(f"[demo] Could not open microphone for barge-in monitoring: {_mic_err}")
                    _mic_stream = None

                barged_in = False  # flag so outer loop knows to skip log and re-listen

                try:
                    for idx in range(len(sentences)):
                        if barged_in:
                            break

                        # Block here ONLY until THIS sentence's audio bytes are ready.
                        # Sentence 1 unblocks as soon as sentence 1 TTS finishes —
                        # regardless of whether sentences 2/3 are done yet.
                        raw_bytes = prefetcher.get_audio(idx)

                        if raw_bytes is None:
                            print(f"[demo] Skipping sentence {idx + 1}: TTS generation returned None.")
                            continue

                        # Load audio directly from in-memory bytes — no disk read.
                        try:
                            audio_buf = io.BytesIO(raw_bytes)
                            sound = pygame.mixer.Sound(file=audio_buf)
                            channel = sound.play()
                        except Exception as e:
                            print(f"[demo] Audio playback failed for sentence {idx + 1}: {e}")
                            continue

                        # ---------------------------------------------------
                        # Active mic-monitoring barge-in loop.
                        # Replaces the idle pygame.time.Clock().tick() wait.
                        # ---------------------------------------------------
                        above_threshold_ms = 0.0  # rolling counter of sustained speech
                        chunk_duration_ms = (PYAUDIO_CHUNK / PYAUDIO_RATE) * 1000  # ms per chunk

                        while channel is not None and channel.get_busy():
                            if _mic_stream is not None:
                                try:
                                    mic_data = _mic_stream.read(PYAUDIO_CHUNK, exception_on_overflow=False)
                                    # Compute RMS of the 16-bit PCM chunk
                                    num_samples = len(mic_data) // 2
                                    if num_samples > 0:
                                        samples = struct.unpack(f"{num_samples}h", mic_data)
                                        rms = math.sqrt(sum(s * s for s in samples) / num_samples)
                                    else:
                                        rms = 0.0

                                    if rms > BARGE_IN_THRESHOLD:
                                        above_threshold_ms += chunk_duration_ms
                                    else:
                                        above_threshold_ms = 0.0  # reset if voice drops below threshold

                                    if above_threshold_ms >= BARGE_IN_DURATION_MS:
                                        # --- BARGE-IN TRIGGERED ---
                                        pygame.mixer.stop()   # silence all channels instantly
                                        prefetcher.stop()     # halt background TTS fetch
                                        print("\n[BARGE-IN] User interrupted the agent. Halting playback and listening...")
                                        barged_in = True
                                        break
                                except OSError:
                                    # Mic read error — skip this chunk, keep playing
                                    pass
                            else:
                                # No mic available — fall back to a small sleep
                                time.sleep(0.02)

                        if barged_in:
                            break

                finally:
                    # Always clean up PyAudio resources
                    if _mic_stream is not None:
                        try:
                            _mic_stream.stop_stream()
                            _mic_stream.close()
                        except Exception:
                            pass
                    try:
                        _pa.terminate()
                    except Exception:
                        pass
                    if not barged_in:
                        prefetcher.stop()

                if barged_in:
                    # Skip logging this interaction and jump straight to STT
                    continue
                            
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
