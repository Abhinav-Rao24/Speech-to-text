# CHANGELOG

All notable changes to the **Speech-to-Text Module** are documented here.
This project follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **`src/eval_logger.py`** – SQLite-backed evaluation logger.
  - Automatically creates `transcripts.db` in the project root on first import.
  - `init_db()` – idempotently creates the `transcription_logs` table with columns:
    `id`, `timestamp`, `filename`, `engine_provider`, `raw_text`,
    `duration_seconds`, `wer_score`.
  - `log_transcription()` – inserts one transcription run; optionally computes
    Word Error Rate via `jiwer.wer()` when a ground-truth reference is supplied.
  - `fetch_logs()` / `print_recent_logs()` – query helpers for reviewing stored runs.
- **`demo.py`** – Unified master orchestrator / evaluation dashboard.
  - Reads `STT_PROVIDER` from `config.py` to pick the active engine at startup.
  - `--engine {local,sarvam}` flag overrides `config.py` for a single run.
  - `--audio PATH` skips live recording and transcribes an existing file directly.
  - `--reference "TEXT"` accepts an optional ground-truth string; computes and
    displays WER in the printed result block *and* persists it to the DB.
  - `--logs [N]` prints the last N entries (default 10) from `transcripts.db`.
  - Full pipeline: **Record → Transcribe → Log → Print comparison block**.

---

## Dual-Engine Architecture Comparison

| Dimension          | Local Engine (`faster-whisper`)         | Cloud Engine (Sarvam AI `saaras:v3`)         |
|--------------------|------------------------------------------|----------------------------------------------|
| **Model**          | OpenAI Whisper `base` (CPU, int8)        | `saaras:v3` hosted by Sarvam AI              |
| **Mode**           | Auto language-detect (beam=5)            | `codemix` – optimised for Indian code-switch |
| **Latency**        | 1–5 s (CPU-bound, local)                 | 1–3 s (network round-trip)                   |
| **Privacy**        | ✅ Fully offline – audio never leaves device | ❌ Audio uploaded to Sarvam API             |
| **Languages**      | 99+ languages auto-detected              | Indian languages + English code-mix          |
| **Accuracy**       | Moderate on accented / code-mixed speech | Higher for Hinglish / regional accents       |
| **Cost**           | Free (compute only)                      | API subscription required                    |
| **Output fields**  | `text`, `language`, `probability`, `execution_time` | `text`, `language`, `execution_time`  |
| **Entry point**    | `src/stt_engine.py::transcribe_local()`  | `src/sarvam_engine.py::transcribe_sarvam()`  |
| **Config switch**  | `STT_PROVIDER = "local"` in `config.py`  | `STT_PROVIDER = "sarvam"` in `config.py`     |

The `demo.py` orchestrator abstracts these differences so the caller interacts
with a single unified interface regardless of which engine is active.

---

## [0.3.0] – 2026-06-18 (feat/sarvam-api)

### Added
- `src/sarvam_engine.py` – Sarvam AI cloud transcription engine.
  - HTTP POST to `https://api.sarvam.ai/speech-to-text` with `saaras:v3` model.
  - `codemix` mode for Hinglish / Indian-accented speech.
  - Explicit MIME-type detection with Windows-safe fallback map (fixes
    `"Invalid file type: None"` errors caused by OS registry mismatches).
  - Measures and returns network round-trip duration.
- `config.py` – added `STT_PROVIDER` toggle and `SARVAM_API_KEY` via
  `python-dotenv` (reads from `.env`).
- `requirements.txt` – added `requests` and `python-dotenv`.
- `.env` – stores `SARVAM_API_KEY` secret (excluded from VCS via `.gitignore`).

### Fixed
- Sarvam API `400 Bad Request` due to missing MIME type (`Content-Type: None`)
  in multipart upload; resolved by passing explicit `(filename, fileobj, mime)`
  tuple in the `files` dict.
- Sarvam API `400 Bad Request` – `mode` value corrected from `"code-mix"` to
  `"codemix"` to match the API's accepted enum values.

---

## [0.2.0] – 2026-06-18 (feat/audio-recording)

### Added
- `recorder.py` – real-time microphone capture using `sounddevice`.
  - Integrates **Silero VAD** (via `torch.hub`) for automatic speech-start
    detection and silence-based stop (configurable `SILENCE_TIMEOUT_THRESHOLD`).
  - Saves captured audio as 16-bit PCM WAV via `scipy.io.wavfile`.
- `src/stt_engine.py` – local transcription using `faster-whisper`.
  - Forces `device="cpu"` and `compute_type="int8"` to avoid CUDA DLL errors on
    machines without an NVIDIA GPU.
  - Multi-language auto-detection (English, Hindi, Telugu + 96 others).
  - Returns `text`, `language`, `probability`, and `execution_time`.
- `requirements.txt` – added `torchaudio` (Silero VAD dependency).

---

## [0.1.0] – 2026-06-18 (main)

### Added
- Initial repository scaffolding: `.gitignore`, `requirements.txt`, `config.py`,
  `README.md`.
- Core configuration parameters: `SAMPLE_RATE`, `SILENCE_TIMEOUT_THRESHOLD`,
  `WHISPER_MODEL_SIZE`.
