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

def generate_voice_output(text: str, language_code: str = "en-IN") -> str:
    """
    Primary unified factory function to generate voice output from text.
    Reads config.TTS_PROVIDER to dynamically route to private engines.
    Returns the absolute path of the generated audio file, or None if an exception occurs.
    """
    provider = getattr(config, "TTS_PROVIDER", "sarvam").lower()
    print(f"Generating voice output using TTS provider: '{provider}'")
    
    try:
        if provider == "sarvam":
            return _call_sarvam_tts(text, language_code)
        elif provider == "elevenlabs":
            return _call_elevenlabs_tts(text)
        elif provider == "google":
            return _call_google_tts(text)
        else:
            print(f"Unknown TTS provider: '{provider}'. Defaulting to 'sarvam'.")
            return _call_sarvam_tts(text, language_code)
    except Exception as e:
        print(f"Error during TTS generation with provider '{provider}': {e}", file=sys.stderr)
        return None
