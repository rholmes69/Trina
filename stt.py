"""Trina STT — multi-provider speech-to-text.

Providers
---------
deepgram  (default) Cloud streaming STT via Deepgram WebSocket
whisper   Local transcription via faster-whisper (no cloud, no API key)

Set STT_PROVIDER=whisper in .env to switch.

Whisper settings (all optional):
  WHISPER_MODEL    model size: tiny / base / small / medium / large-v3 (default)
  WHISPER_DEVICE   cuda / cpu / auto (default)
  WHISPER_COMPUTE  float16 (GPU) / int8 (CPU) / auto (default)
  WHISPER_LANGUAGE en / es / fr / … or blank for auto-detect
"""

import os
import threading
import time

import numpy as np

# ── Model loading ─────────────────────────────────────────────────────────────
# Cached globally — large-v3 is ~1.5 GB and takes a moment to load once.

_model      = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    with _model_lock:
        if _model is not None:
            return _model

        from faster_whisper import WhisperModel

        size    = os.getenv("WHISPER_MODEL",   "large-v3")
        device  = os.getenv("WHISPER_DEVICE",  "auto")
        compute = os.getenv("WHISPER_COMPUTE", "auto")

        if device == "auto":
            device = "cpu"
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
            except ImportError:
                pass

        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"

        print(f"[whisper] loading {size} on {device}/{compute} …", flush=True)
        _model = WhisperModel(size, device=device, compute_type=compute)
        print("[whisper] ready.", flush=True)
        return _model


def _transcribe(audio: np.ndarray) -> str:
    """Run faster-whisper on a float32 mono array. Returns plain text."""
    if audio.size < 100:
        return ""
    model = _load_model()
    lang  = os.getenv("WHISPER_LANGUAGE") or None   # None = auto-detect
    segments, _ = model.transcribe(
        audio,
        language=lang,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
    )
    return " ".join(s.text.strip() for s in segments).strip()


# ── CLI mic recording ─────────────────────────────────────────────────────────

def transcribe_mic(
    sample_rate: int   = 16_000,
    rms_threshold: float = 0.013,   # raise if picking up background noise
    min_speech_sec: float = 0.4,    # ignore sounds shorter than this
    silence_sec: float   = 1.3,     # stop after this many silent seconds
    max_sec: float       = 30.0,
) -> str:
    """Record from the default mic until silence, then transcribe. Blocking."""
    import sounddevice as sd

    chunk_ms       = 50
    chunk_frames   = int(sample_rate * chunk_ms / 1000)
    silence_needed = int(silence_sec    * 1000 / chunk_ms)
    min_speech     = int(min_speech_sec * 1000 / chunk_ms)
    max_chunks     = int(max_sec        * 1000 / chunk_ms)

    frames         = []
    silent_count   = 0
    speech_count   = 0
    speech_started = False
    done           = threading.Event()

    def _cb(indata, nframes, t, status):
        nonlocal speech_started, silent_count, speech_count
        chunk = indata[:, 0].copy()
        rms   = float(np.sqrt(np.mean(chunk ** 2)))
        frames.append(chunk)

        if rms >= rms_threshold:
            speech_started = True
            speech_count  += 1
            silent_count   = 0
        elif speech_started:
            silent_count += 1
            if silent_count >= silence_needed and speech_count >= min_speech:
                done.set()

        if len(frames) >= max_chunks:
            done.set()

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32",
                        blocksize=chunk_frames, callback=_cb):
        done.wait()

    if not frames or speech_count < min_speech:
        return ""

    return _transcribe(np.concatenate(frames))


# ── Browser WebSocket accumulator (server mode) ───────────────────────────────

class WhisperSession:
    """
    Accumulates raw Int16 PCM bytes pushed from the browser WebSocket,
    detects end-of-speech via energy-based silence detection, then
    transcribes with faster-whisper.

    Usage (inside an async WebSocket handler):

        session = WhisperSession()
        session.feed(pcm_bytes)      # call for every audio chunk received
        if session.ready():
            text = session.flush()   # blocking — run in executor
    """

    SAMPLE_RATE    = 16_000
    RMS_THRESHOLD  = 0.013
    MIN_SPEECH_SEC = 0.4
    SILENCE_SEC    = 1.3
    MAX_SEC        = 30.0

    def __init__(self) -> None:
        self._buf:         list[np.ndarray] = []
        self._speech_sec:  float = 0.0
        self._silent_sec:  float = 0.0
        self._last_ts:     float = time.monotonic()
        self._has_speech:  bool  = False

    def feed(self, pcm_int16: bytes) -> None:
        """Push a raw PCM Int16 byte chunk from the browser."""
        arr  = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float32) / 32768.0
        rms  = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
        now  = time.monotonic()
        dt   = min(now - self._last_ts, 0.5)   # cap to avoid jumps on first call
        self._last_ts = now

        if rms >= self.RMS_THRESHOLD:
            self._has_speech  = True
            self._speech_sec += dt
            self._silent_sec  = 0.0
            self._buf.append(arr)
        elif self._has_speech:
            self._silent_sec += dt
            self._buf.append(arr)   # keep trailing silence for Whisper context

        # Hard cap: auto-flush if utterance is very long
        total = self._speech_sec + self._silent_sec
        if total >= self.MAX_SEC:
            self._silent_sec = self.SILENCE_SEC   # force ready

    def ready(self) -> bool:
        """True once speech is heard and then silence long enough to end the utterance."""
        return (
            self._has_speech
            and self._speech_sec >= self.MIN_SPEECH_SEC
            and self._silent_sec >= self.SILENCE_SEC
        )

    def flush(self) -> str:
        """Transcribe accumulated audio and reset. Blocking — run in executor."""
        buf = list(self._buf)
        self._reset()
        if not buf:
            return ""
        return _transcribe(np.concatenate(buf))

    def _reset(self) -> None:
        self._buf        = []
        self._speech_sec = 0.0
        self._silent_sec = 0.0
        self._has_speech = False


# ── Public helper ─────────────────────────────────────────────────────────────

def get_provider() -> str:
    return os.getenv("STT_PROVIDER", "deepgram").lower()
