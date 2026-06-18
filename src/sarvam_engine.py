import requests
import time
import os
import sys

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SARVAM_API_KEY

def transcribe_sarvam(audio_path: str):
    """
    Transcribe the given audio file using the Sarvam AI Cloud API.
    Uses saaras:v3 model with code-mix optimizations.
    """
    print("Sending audio to Sarvam AI API...")
    url = "https://api.sarvam.ai/speech-to-text"
    
    headers = {
        "api-subscription-key": SARVAM_API_KEY
    }
    
    # Configure the payload to use the saaras:v3 model with the mode set to transcribe or codemix
    data = {
        "model": "saaras:v3",
        "mode": "codemix" # Using codemix mode for Indian accents and code-mixed speech
    }
    
    start_time = time.time()
    
    try:
        import mimetypes
        
        filename = os.path.basename(audio_path)
        mime_type, _ = mimetypes.guess_type(audio_path)
        
        # Explicit fallback map for common extensions if mimetypes fails on Windows
        if not mime_type:
            ext = os.path.splitext(audio_path)[1].lower()
            mime_map = {
                '.wav': 'audio/wav',
                '.mp3': 'audio/mpeg',
                '.mpeg': 'audio/mpeg',
                '.ogg': 'audio/ogg',
                '.webm': 'audio/webm',
                '.m4a': 'audio/x-m4a',
                '.mp4': 'audio/mp4'
            }
            mime_type = mime_map.get(ext, 'application/octet-stream')
            
        with open(audio_path, "rb") as audio_file:
            files = {
                "file": (filename, audio_file, mime_type)
            }
            response = requests.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            
    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}")
        if 'response' in locals() and response is not None:
            print(f"Response details: {response.text}")
        return None
            
    execution_time = time.time() - start_time
    result = response.json()
    
    # Extract the response text string and language parameters
    transcript = result.get("transcript", "")
    detected_language = result.get("language_code", "Unknown")
    
    print(f"Detected language (from API): '{detected_language}'")
    print(f"Transcription network round-trip took {execution_time:.2f} seconds.")
    print(f"\nTranscript:\n{transcript.strip()}")
    
    return {
        "text": transcript.strip(),
        "language": detected_language,
        "execution_time": execution_time
    }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_audio_path = sys.argv[1]
        transcribe_sarvam(test_audio_path)
    else:
        print("Usage: python sarvam_engine.py <path_to_audio_file>")
