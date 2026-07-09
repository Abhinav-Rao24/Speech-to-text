import os
from dotenv import load_dotenv

load_dotenv()

# Configuration parameters for Speech-to-Text Module

# Audio recording configuration
SAMPLE_RATE = 16000
SILENCE_TIMEOUT_THRESHOLD = 1.5  # in seconds

# Whisper model configuration
WHISPER_MODEL_SIZE = 'base'

# STT Provider Options
STT_PROVIDER = "sarvam" # Options: "local" or "sarvam"
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# TTS Provider Options
TTS_PROVIDER = "sarvam" # Options: "sarvam", "elevenlabs", "google"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = "google/gemini-2.5-flash"
