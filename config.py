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
STT_PROVIDER = "local" # Options: "local" or "sarvam"
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
