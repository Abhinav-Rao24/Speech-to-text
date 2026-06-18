import time
import os
import sys
from faster_whisper import WhisperModel

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WHISPER_MODEL_SIZE

def transcribe_local(audio_path: str):
    """
    Transcribe the given audio file using faster-whisper.
    Auto-detects language (English, Hindi, or Telugu) and measures execution time.
    """
    print(f"Loading faster-whisper model ({WHISPER_MODEL_SIZE})...")
    # Initialize model - device auto-detection
    model = WhisperModel(WHISPER_MODEL_SIZE, device="auto", compute_type="default")
    
    print(f"Transcribing {audio_path}...")
    start_time = time.time()
    
    # Transcribe with language auto-detection
    segments, info = model.transcribe(audio_path, beam_size=5)
    
    detected_language = info.language
    language_prob = info.language_probability
    
    # Process segments to build the full transcript
    transcript = ""
    for segment in segments:
        transcript += segment.text + " "
        
    execution_time = time.time() - start_time
    
    print(f"Detected language: '{detected_language}' with probability {language_prob:.2f}")
    print(f"Transcription took {execution_time:.2f} seconds.")
    print(f"\nTranscript:\n{transcript.strip()}")
    
    return {
        "text": transcript.strip(),
        "language": detected_language,
        "probability": language_prob,
        "execution_time": execution_time
    }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_audio_path = sys.argv[1]
        transcribe_local(test_audio_path)
    else:
        print("Usage: python stt_engine.py <path_to_audio_file>")
