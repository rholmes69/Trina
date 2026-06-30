#!/usr/bin/env python3
"""Trina — personal life OS.  Voice-in (Deepgram) + Voice-out (Gemini TTS) + orb UI."""

import argparse
import asyncio
import json
import os
import queue as _queue
import sys
import tempfile
import threading
import time as _time

from dotenv import load_dotenv

load_dotenv()

import pygame
import sounddevice as sd
import websockets
from rich.console import Console
from rich.panel import Panel
from tools import call_claude
from tts import generate_audio

# ── Config ────────────────────────────────────────────────────────────────────

CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL",   "claude-sonnet-4-6")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-2")
WS_PORT        = int(os.getenv("WS_PORT",    "8765"))
MIC_RATE       = 16_000
MIC_CHANNELS   = 1
MIC_DTYPE      = "int16"
MIC_BLOCKSIZE  = 4096

_DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    f"?model={DEEPGRAM_MODEL}"
    "&language=en-US"
    "&encoding=linear16"
    f"&sample_rate={MIC_RATE}"
    f"&channels={MIC_CHANNELS}"
    "&smart_format=true"
    "&endpointing=500"
)

console = Console()
pygame.mixer.init()

PORCUPINE_KEY  = os.getenv("PORCUPINE_ACCESS_KEY", "")
WAKE_WORD_PATH = os.getenv("WAKE_WORD_PATH", "")
WAKE_WORD_ENABLED = bool(PORCUPINE_KEY)

_reminder_q: _queue.Queue[str] = _queue.Queue()

# ── WebSocket server (browser orb) ────────────────────────────────────────────

_ws_clients: set = set()
_ws_loop: asyncio.AbstractEventLoop | None = None


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        _ws_clients.discard(websocket)


async def _ws_serve():
    async with websockets.serve(_ws_handler, "localhost", WS_PORT):
        await asyncio.Future()


def _start_ws_server():
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)
    _ws_loop.run_until_complete(_ws_serve())


def _broadcast(data: str | bytes) -> None:
    if not _ws_loop or not _ws_clients:
        return

    async def _send():
        for ws in list(_ws_clients):
            try:
                await ws.send(data)
            except Exception:
                pass

    asyncio.run_coroutine_threadsafe(_send(), _ws_loop).result(timeout=5)


# ── Voice input (Deepgram via raw WebSocket) ──────────────────────────────────

async def _listen_async(result_holder: list, thread_done: threading.Event) -> None:
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    done  = asyncio.Event()
    parts: list[str] = []

    async with websockets.connect(_DG_URL, additional_headers=headers) as dg_ws:

        async def recv():
            try:
                async for raw in dg_ws:
                    if isinstance(raw, bytes):
                        continue
                    msg = json.loads(raw)
                    if msg.get("type") != "Results":
                        continue
                    alts = msg.get("channel", {}).get("alternatives", [{}])
                    text = alts[0].get("transcript", "")
                    if msg.get("is_final") and text:
                        parts.append(text)
                    if msg.get("speech_final") and parts:
                        result_holder.append(" ".join(parts))
                        done.set()
                        return
            except Exception:
                done.set()

        recv_task = asyncio.create_task(recv())
        loop = asyncio.get_running_loop()

        def mic_cb(indata, frames, time, status):
            asyncio.run_coroutine_threadsafe(dg_ws.send(bytes(indata)), loop)

        with sd.InputStream(
            samplerate=MIC_RATE, channels=MIC_CHANNELS,
            dtype=MIC_DTYPE, callback=mic_cb, blocksize=MIC_BLOCKSIZE,
        ):
            try:
                await asyncio.wait_for(done.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                done.set()

        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

    thread_done.set()


def listen() -> str:
    """Open the mic and block until Deepgram returns a final transcript."""
    result_holder: list[str] = []
    thread_done = threading.Event()

    def run():
        asyncio.run(_listen_async(result_holder, thread_done))

    threading.Thread(target=run, daemon=True).start()

    with console.status("[dim]listening…[/dim]", spinner="dots"):
        thread_done.wait()

    return result_holder[0] if result_holder else ""


# ── Voice output ──────────────────────────────────────────────────────────────

def speak(text: str) -> None:
    wav = generate_audio(text)
    if not wav:
        return

    if _ws_clients:
        _broadcast("speaking:start")
        _broadcast(wav)
        _broadcast("speaking:end")
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            tmp = f.name
        try:
            pygame.mixer.music.load(tmp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
        finally:
            pygame.mixer.music.unload()
            os.unlink(tmp)


# ── Wake word ─────────────────────────────────────────────────────────────────

def _detect_wake_word() -> None:
    """Block until the wake word is heard. No-ops if Porcupine is not configured."""
    if not WAKE_WORD_ENABLED:
        return
    try:
        import pvporcupine
    except ImportError:
        console.print("[dim]pvporcupine not installed — wake word disabled[/dim]")
        return

    try:
        if WAKE_WORD_PATH and Path(WAKE_WORD_PATH).exists():
            pp = pvporcupine.create(access_key=PORCUPINE_KEY, keyword_paths=[WAKE_WORD_PATH])
        else:
            pp = pvporcupine.create(access_key=PORCUPINE_KEY, keywords=["porcupine"])
    except Exception as exc:
        console.print(f"[dim]Wake word init error: {exc}[/dim]")
        return

    frame_len = pp.frame_length
    buf: list[int] = []
    detected = threading.Event()

    def _cb(indata, frames, t, status):
        buf.extend(indata[:, 0].tolist())
        while len(buf) >= frame_len:
            chunk = [int(x) for x in buf[:frame_len]]
            del buf[:frame_len]
            if pp.process(chunk) >= 0:
                detected.set()

    console.print("\n[dim]Waiting for wake word…[/dim]")
    with sd.InputStream(samplerate=pp.sample_rate, channels=1, dtype="int16",
                        blocksize=frame_len, callback=_cb):
        detected.wait()

    pp.delete()
    console.print("[dim]Wake word detected.[/dim]")


# ── Reminder background thread ────────────────────────────────────────────────

def _reminder_worker() -> None:
    from tools import check_due_reminders
    while True:
        for msg in check_due_reminders():
            _reminder_q.put(msg)
        _time.sleep(20)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(text_mode: bool) -> None:
    history: list[dict] = []

    # Start reminder background thread
    threading.Thread(target=_reminder_worker, daemon=True).start()

    agent_name = os.getenv("AGENT_NAME", "Trina")
    wake_hint  = " · Wake word active" if WAKE_WORD_ENABLED else ""
    mode_hint  = "Type to talk" if text_mode else "Speak to talk"
    console.print(
        Panel(
            f"[bold]{agent_name}[/bold]  ·  personal life OS\n"
            f"[dim]{mode_hint}  ·  Ctrl+C to quit  ·  "
            f"Open web/index.html  ·  ws://localhost:{WS_PORT}{wake_hint}[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    while True:
        # ── Fire any pending reminders ────────────────────────────────────────
        while not _reminder_q.empty():
            try:
                msg = _reminder_q.get_nowait()
                console.print(f"\n[bold yellow]⏰ Reminder:[/bold yellow] {msg}")
                speak(f"Reminder: {msg}")
            except _queue.Empty:
                break

        # ── Get user input ────────────────────────────────────────────────────
        try:
            if text_mode:
                user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
            else:
                if WAKE_WORD_ENABLED:
                    _detect_wake_word()
                console.print("\n[dim]You:[/dim] ", end="")
                user_input = listen()
                if not user_input:
                    continue
                console.print(f"[bold cyan]{user_input}[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Trina: Goodbye.[/dim]")
            break

        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

        with console.status("[dim]thinking…[/dim]", spinner="dots"):
            reply = call_claude(history)

        history.append({"role": "assistant", "content": reply})

        console.print(f"\n[bold green]Trina:[/bold green] {reply}")
        speak(reply)


# ── Startup checks ────────────────────────────────────────────────────────────

def _check_env(text_mode: bool) -> None:
    required = ["ANTHROPIC_API_KEY", "GEMINI_API_KEY"]
    if not text_mode:
        required.append("DEEPGRAM_API_KEY")
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        for v in missing:
            console.print(f"[red]Error:[/red] {v} is not set.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trina — personal life OS")
    parser.add_argument(
        "--text", action="store_true",
        help="Use keyboard input instead of microphone"
    )
    args = parser.parse_args()

    _check_env(text_mode=args.text)

    ws_thread = threading.Thread(target=_start_ws_server, daemon=True)
    ws_thread.start()

    run(text_mode=args.text)
