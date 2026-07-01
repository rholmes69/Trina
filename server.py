#!/usr/bin/env python3
"""Trina web server — real-time voice conversation via browser."""

import asyncio
import json
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from tools import call_claude
from tts import generate_audio

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

CLAUDE_MODEL    = os.getenv("CLAUDE_MODEL",    "claude-sonnet-4-6")
DEEPGRAM_MODEL  = os.getenv("DEEPGRAM_MODEL",  "nova-2")
MIC_RATE        = 16_000

_DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    f"?model={DEEPGRAM_MODEL}&language=en-US&encoding=linear16"
    f"&sample_rate={MIC_RATE}&channels=1"
    "&smart_format=true&endpointing=500&interim_results=true"
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI()
app.mount("/static", StaticFiles(directory="web"), name="static")


@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/worklet.js")
def worklet():
    return FileResponse("web/worklet.js")


async def _generate_speech(text: str) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, generate_audio, text)


async def _call_claude(history: list[dict]) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, call_claude, history)


# ── WebSocket session ─────────────────────────────────────────────────────────

def _agent_config() -> dict:
    """Current agent config snapshot — sent to browser so UI matches active profile."""
    return {
        "type":        "config",
        "ring_color":  os.getenv("AGENT_RING_COLOR", "#0055ff"),
        "agent_name":  os.getenv("AGENT_NAME",       "Trina"),
    }


async def _ws_session_deepgram(browser: WebSocket) -> None:
    """Deepgram cloud STT path — streams browser PCM to Deepgram, handles transcripts."""
    history: list[dict] = []
    parts: list[str]    = []
    busy                = asyncio.Lock()
    last_config: dict   = _agent_config()

    try:
        from websockets.asyncio.client import connect as dg_connect
    except ImportError:
        from websockets import connect as dg_connect

    dg_headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}

    async with dg_connect(_DG_URL, additional_headers=dg_headers) as dg_ws:

        audio_chunks = 0

        async def forward_audio():
            nonlocal audio_chunks
            try:
                while True:
                    data = await browser.receive()
                    if data["type"] == "websocket.disconnect":
                        break
                    raw = data.get("bytes")
                    if raw:
                        audio_chunks += 1
                        if audio_chunks == 1:
                            print("[audio] first PCM chunk received from browser", flush=True)
                        await dg_ws.send(raw)
            except Exception as e:
                print(f"[audio] forward_audio error: {e}", flush=True)

        async def handle_transcripts():
            try:
                async for raw in dg_ws:
                    if isinstance(raw, bytes):
                        continue
                    msg = json.loads(raw)
                    if msg.get("type") != "Results":
                        print(f"[dg] non-Results message: {msg.get('type')}", flush=True)
                        continue

                    alts         = msg.get("channel", {}).get("alternatives", [{}])
                    text         = alts[0].get("transcript", "")
                    is_final     = msg.get("is_final", False)
                    speech_final = msg.get("speech_final", False)

                    if text:
                        print(f"[dg] transcript is_final={is_final} speech_final={speech_final}: {text!r}", flush=True)
                        await browser.send_json({"type": "transcript", "text": text, "is_final": is_final})

                    if is_final and text:
                        parts.append(text)

                    if speech_final and parts:
                        user_text = " ".join(parts)
                        parts.clear()

                        if busy.locked():
                            print("[trina] busy — skipping utterance", flush=True)
                            continue

                        async with busy:
                            await _handle_turn(browser, history, last_config, user_text)

            except Exception as e:
                print(f"[dg] handle_transcripts error: {e}", flush=True)

        async def reminder_checker():
            from tools import check_due_reminders
            while True:
                await asyncio.sleep(20)
                try:
                    loop = asyncio.get_running_loop()
                    due = await loop.run_in_executor(None, check_due_reminders)
                    for msg in due:
                        text = f"Reminder: {msg}"
                        if busy.locked():
                            continue
                        async with busy:
                            await _speak_to_browser(browser, text)
                except Exception:
                    break

        await asyncio.gather(forward_audio(), handle_transcripts(), reminder_checker())


async def _ws_session_whisper(browser: WebSocket) -> None:
    """faster-whisper local STT path — accumulates browser PCM, detects silence, transcribes."""
    from stt import WhisperSession

    history: list[dict] = []
    busy                = asyncio.Lock()
    last_config: dict   = _agent_config()
    session             = WhisperSession()

    async def receive_audio():
        try:
            while True:
                data = await browser.receive()
                if data["type"] == "websocket.disconnect":
                    break
                raw = data.get("bytes")
                if not raw:
                    continue
                session.feed(raw)
                if session.ready():
                    loop = asyncio.get_running_loop()
                    user_text = await loop.run_in_executor(None, session.flush)
                    if user_text:
                        print(f"[whisper] transcript: {user_text!r}", flush=True)
                        await browser.send_json({"type": "transcript", "text": user_text, "is_final": True})
                        if not busy.locked():
                            asyncio.create_task(_run_turn(user_text))
                        else:
                            print("[trina] busy — skipping utterance", flush=True)
        except Exception as e:
            print(f"[whisper] receive_audio error: {e}", flush=True)

    async def _run_turn(user_text: str):
        async with busy:
            await _handle_turn(browser, history, last_config, user_text)

    async def reminder_checker():
        from tools import check_due_reminders
        while True:
            await asyncio.sleep(20)
            try:
                loop = asyncio.get_running_loop()
                due = await loop.run_in_executor(None, check_due_reminders)
                for msg in due:
                    text = f"Reminder: {msg}"
                    if busy.locked():
                        continue
                    async with busy:
                        await _speak_to_browser(browser, text)
            except Exception:
                break

    await asyncio.gather(receive_audio(), reminder_checker())


async def _handle_turn(
    browser: WebSocket,
    history: list[dict],
    last_config: dict,
    user_text: str,
) -> None:
    """Run one Claude turn: think → reply → TTS → push to browser."""
    print(f"[trina] → Claude: {user_text!r}", flush=True)
    await browser.send_json({"type": "state", "value": "thinking"})

    history.append({"role": "user", "content": user_text})
    reply = await _call_claude(history)
    history.append({"role": "assistant", "content": reply})

    new_cfg = _agent_config()
    if new_cfg != last_config:
        last_config.update(new_cfg)
        await browser.send_json(new_cfg)

    print(f"[trina] ← Claude: {reply!r}", flush=True)
    await browser.send_json({"type": "trina_text", "text": reply})
    await _speak_to_browser(browser, reply)


async def _speak_to_browser(browser: WebSocket, text: str) -> None:
    """TTS a string and stream the WAV bytes to the browser."""
    await browser.send_json({"type": "state", "value": "speaking"})
    wav = await _generate_speech(text)
    if wav:
        await browser.send_bytes(wav)
    else:
        print("[trina] TTS returned no audio", flush=True)
    await browser.send_json({"type": "state", "value": "listening"})


@app.websocket("/ws")
async def ws_session(browser: WebSocket):
    await browser.accept()
    await browser.send_json(_agent_config())

    from stt import get_provider
    if get_provider() == "whisper":
        await _ws_session_whisper(browser)
    else:
        await _ws_session_deepgram(browser)

    try:
        await browser.close()
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host       = "localhost"
    port       = 8080
    agent_name = os.getenv("AGENT_NAME", "Trina")
    print(f"{agent_name} is live → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
