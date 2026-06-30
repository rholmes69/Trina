"""Trina TTS — multi-provider voice synthesis.

Providers
---------
gemini      (default) Gemini TTS with any pre-built voice (e.g. Zephyr)
elevenlabs  ElevenLabs with a cloned or pre-built voice

Set TTS_PROVIDER in .env to switch. Both providers return raw WAV bytes so
trina.py and server.py can play or stream without caring which backend ran.
"""

import os
import struct

from dotenv import load_dotenv

load_dotenv()

TTS_PROVIDER     = os.getenv("TTS_PROVIDER",         "gemini")
TTS_MODEL        = os.getenv("TTS_MODEL",            "gemini-3.1-flash-tts-preview")
TTS_VOICE        = os.getenv("TTS_VOICE",            "Zephyr")
EL_API_KEY       = os.getenv("ELEVENLABS_API_KEY",   "")
EL_VOICE_ID      = os.getenv("ELEVENLABS_VOICE_ID",  "")
EL_MODEL         = os.getenv("ELEVENLABS_MODEL",     "eleven_turbo_v2_5")


# ── WAV helpers ───────────────────────────────────────────────────────────────

def _parse_audio_mime(mime_type: str) -> dict:
    bits, rate = 16, 24000
    for part in mime_type.split(";"):
        part = part.strip()
        if part.lower().startswith("rate="):
            try:
                rate = int(part.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        elif part.startswith("audio/L"):
            try:
                bits = int(part.split("L", 1)[1])
            except (ValueError, IndexError):
                pass
    return {"bits_per_sample": bits, "rate": rate}


def to_wav(pcm: bytes, mime_type: str = "audio/L16;rate=24000") -> bytes:
    p = _parse_audio_mime(mime_type)
    bps, rate, ch = p["bits_per_sample"], p["rate"], 1
    block = ch * (bps // 8)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, ch, rate, rate * block, block, bps,
        b"data", len(pcm),
    )
    return header + pcm


# ── Gemini provider ───────────────────────────────────────────────────────────

def _gemini_audio(text: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
            )
        ),
    )

    pcm      = b""
    mime     = "audio/L16;rate=24000"
    for chunk in client.models.generate_content_stream(
        model=TTS_MODEL, contents=text, config=config
    ):
        try:
            part = chunk.candidates[0].content.parts[0]
        except (AttributeError, IndexError):
            continue
        if part.inline_data and part.inline_data.data:
            pcm  += part.inline_data.data
            mime  = part.inline_data.mime_type or mime

    return to_wav(pcm, mime) if pcm else b""


# ── ElevenLabs provider ───────────────────────────────────────────────────────

def _elevenlabs_audio(text: str) -> bytes:
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        raise RuntimeError(
            "ElevenLabs provider requires: pip install elevenlabs"
        )
    if not EL_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in .env")
    if not EL_VOICE_ID:
        raise RuntimeError(
            "ELEVENLABS_VOICE_ID is not set in .env — "
            "clone a voice at elevenlabs.io and paste the Voice ID."
        )

    client = ElevenLabs(api_key=EL_API_KEY)
    # output_format=pcm_24000 → raw 16-bit LE PCM at 24 kHz (no container)
    chunks = client.text_to_speech.convert(
        text=text,
        voice_id=EL_VOICE_ID,
        model_id=EL_MODEL,
        output_format="pcm_24000",
    )
    pcm = b"".join(chunks)
    return to_wav(pcm, "audio/L16;rate=24000")


# ── Public API ────────────────────────────────────────────────────────────────

def generate_audio(text: str) -> bytes:
    """Return WAV bytes for `text` using the configured TTS provider."""
    if TTS_PROVIDER == "elevenlabs":
        return _elevenlabs_audio(text)
    return _gemini_audio(text)
