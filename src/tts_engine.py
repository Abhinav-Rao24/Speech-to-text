import os
import sys
import uuid
import base64
import requests

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def _call_sarvam_tts(text: str, language_code: str) -> str:
    """
    Private helper to call Sarvam AI Text-to-Speech API.
    Model: bulbul:v3, Speaker: shubh.
    Decodes the returned base64 string payload and saves as an uncompressed .wav file.
    """
    if not config.SARVAM_API_KEY:
        raise ValueError("SARVAM_API_KEY is not configured in the environment.")
        
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": config.SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": text,
        "model": "bulbul:v3",
        "speaker": "shubh",
        "target_language_code": language_code
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    if "audios" not in data or not data["audios"]:
        raise ValueError("No audio content returned from Sarvam API.")
        
    audio_base64 = data["audios"][0]
    audio_bytes = base64.b64decode(audio_base64)
    
    # Save locally as an uncompressed .wav file
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = f"tts_sarvam_{uuid.uuid4().hex}.wav"
    file_path = os.path.join(root_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(audio_bytes)
        
    return os.path.abspath(file_path)

def _call_elevenlabs_tts(text: str) -> str:
    """
    Private helper to call ElevenLabs Text-to-Speech API.
    Model: eleven_flash_v2_5.
    Saves the returned binary stream output locally as an .mp3 file.
    """
    if not config.ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is not configured in the environment.")
        
    from elevenlabs.client import ElevenLabs
    
    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
    
    # Rachel is a standard default voice
    audio_stream = client.text_to_speech.convert(
        text=text,
        voice_id="Rachel",
        model_id="eleven_flash_v2_5"
    )
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = f"tts_elevenlabs_{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(root_dir, filename)
    
    with open(file_path, "wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)
                
    return os.path.abspath(file_path)

def _call_google_tts(text: str) -> str:
    """
    Private helper to call Google Cloud Text-to-Speech API.
    Saves the synthesized MP3 stream to a local .mp3 file.
    """
    if config.GOOGLE_APPLICATION_CREDENTIALS:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config.GOOGLE_APPLICATION_CREDENTIALS
        
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is not configured in the environment.")
        
    from google.cloud import texttospeech
    
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    # Use en-IN neutral voice
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-IN",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = f"tts_google_{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(root_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(response.audio_content)
        
    return os.path.abspath(file_path)

import re

def normalize_logistics_text(text: str) -> str:
    """
    Sanitize text strings before sending them to a TTS provider API.
    Replaces complex alpha-numeric formatting strings with explicit, phonetically conversational phrases.
    """
    if not text:
        return text

    digit_words = {
        '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
        '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
    }

    # 1. Expand tracking codes or strings containing underscores like "watch_101" to "watch, one, zero, one"
    def expand_underscore(match):
        prefix = match.group(1)
        digits = match.group(2)
        digit_names = ", ".join(digit_words[d] for d in digits)
        return f"{prefix}, {digit_names}"

    text = re.sub(r'\b([A-Za-z]+)_(\d+)\b', expand_underscore, text)

    # 2. Expand alphanumeric identifiers like "SH12345" to spelled-out letters and numbers: "S, H, 1, 2, 3, 4, 5"
    def expand_alphanumeric(match):
        code = match.group(0)
        parts = []
        for char in code:
            if char.isalpha():
                parts.append(char.upper())
            elif char.isdigit():
                parts.append(char)
        return ", ".join(parts)

    # Matches words containing both letters and digits, e.g., SH12345, WB98765
    text = re.sub(r'\b(?=[A-Za-z]*\d)(?=[\d]*[A-Za-z])[A-Za-z\d]+\b', expand_alphanumeric, text)

    # 3. Replace "ID" with "I.D"
    text = re.sub(r'\bID\b', 'I.D', text, flags=re.IGNORECASE)

    return text

def generate_voice_output(text: str, language_code: str = "en-IN") -> str:
    """
    Primary unified factory function to generate voice output from text.
    Reads config.TTS_PROVIDER to dynamically route to private engines.
    Returns the absolute path of the generated audio file, or None if an exception occurs.
    """
    provider = getattr(config, "TTS_PROVIDER", "sarvam").lower()
    print(f"Generating voice output using TTS provider: '{provider}'")
    
    # Apply text normalization layer
    normalized_text = normalize_logistics_text(text)
    
    try:
        if provider == "sarvam":
            return _call_sarvam_tts(normalized_text, language_code)
        elif provider == "elevenlabs":
            return _call_elevenlabs_tts(normalized_text)
        elif provider == "google":
            return _call_google_tts(normalized_text)
        else:
            print(f"Unknown TTS provider: '{provider}'. Defaulting to 'sarvam'.")
            return _call_sarvam_tts(normalized_text, language_code)
    except Exception as e:
        print(f"[WARNING] TTS Provider failed or timed out. Transitioning to text-only communication fallback. Error: {e}", file=sys.stderr)
        return None
