import time
import queue
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import torch
from config import SAMPLE_RATE, SILENCE_TIMEOUT_THRESHOLD

# Silero VAD typically expects chunk sizes of 512, 1024, or 1536
CHUNK_SIZE = 512
INITIAL_TIMEOUT = 5.0  # seconds to wait for speech before aborting

def record_audio(output_filename="output.wav"):
    print("Loading Silero VAD model...")
    # Initialize Silero VAD from Torch Hub
    model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                  model='silero_vad',
                                  force_reload=False)
    
    print("Initializing microphone...")
    q = queue.Queue()

    def callback(indata, frames, time_info, status):
        """This is called for each audio block by sounddevice."""
        if status:
            print(status, flush=True)
        q.put(indata.copy())

    audio_buffer = []
    has_speech_started = False
    silence_start_time = None
    start_time = time.time()

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE, callback=callback):
            print("Listening...")
            while True:
                chunk = q.get()
                
                # Convert chunk to torch tensor
                tensor_chunk = torch.from_numpy(chunk).squeeze()
                
                # Predict speech probability
                speech_prob = model(tensor_chunk, SAMPLE_RATE).item()
                
                if not has_speech_started:
                    if speech_prob > 0.5:
                        has_speech_started = True
                        print("Speech detected. Recording...")
                        audio_buffer.append(chunk)
                    else:
                        if time.time() - start_time > INITIAL_TIMEOUT:
                            print("No speech detected. Please try again.")
                            return None
                else:
                    audio_buffer.append(chunk)
                    if speech_prob < 0.5:
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time > SILENCE_TIMEOUT_THRESHOLD:
                            print(f"Silence threshold reached ({SILENCE_TIMEOUT_THRESHOLD}s). Stopping recording.")
                            break
                    else:
                        silence_start_time = None

    except KeyboardInterrupt:
        print("\nRecording interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    if audio_buffer:
        print(f"Saving recording to {output_filename}...")
        audio_data = np.concatenate(audio_buffer, axis=0)
        # Convert to 16-bit PCM for standard wav file
        audio_data_int16 = np.int16(audio_data * 32767)
        wav.write(output_filename, SAMPLE_RATE, audio_data_int16)
        return output_filename
    return None

if __name__ == "__main__":
    record_audio()
