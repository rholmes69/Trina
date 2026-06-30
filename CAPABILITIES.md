# Trina — Capabilities & Example Prompts

Trina is a voice-first personal life OS running on your Windows desktop. Speak to her through the browser interface (`http://localhost:8080`) or the terminal (`python trina.py`). Everything is local or API-backed — no cloud middleman beyond the model providers you configure.

---

## Table of Contents

1. [Voice I/O](#voice-io)
2. [Long-Term Memory](#long-term-memory)
3. [Reminders](#reminders)
4. [Habit Tracker](#habit-tracker)
5. [File & Folder Management](#file--folder-management)
6. [Camera & Image Vision](#camera--image-vision)
7. [Model Switching](#model-switching)
8. [Configuration Reference](#configuration-reference)

---

## Voice I/O

Trina listens through your microphone via Deepgram and speaks back via Gemini TTS or ElevenLabs (voice cloning). The browser orb animates to reflect her state: listening → thinking → speaking.

### Wake Word *(optional)*

Set `PORCUPINE_ACCESS_KEY` in `.env` to enable always-on wake word detection. Without it, click the orb to begin a session.

| Example Phrase | What Happens |
|---|---|
| *"Hey Trina"* | Trina wakes up and starts listening |
| *(silence after response)* | Returns to wake-word standby |

**To get a custom "Hey Trina" wake word:**
1. Create a free account at [console.picovoice.ai](https://console.picovoice.ai)
2. Go to **Wake Word** → enter "Hey Trina" → download the `.ppn` file
3. Set `WAKE_WORD_PATH=` in `.env` to the file path

### Voice Output

Two TTS providers are supported. Switch by setting `TTS_PROVIDER` in `.env`.

| Provider | Setting | Quality | Notes |
|---|---|---|---|
| Gemini TTS | `TTS_PROVIDER=gemini` | Good | Free with Gemini API key. Voice set via `TTS_VOICE` (e.g. `Zephyr`) |
| ElevenLabs | `TTS_PROVIDER=elevenlabs` | Excellent | Supports voice cloning. Set `ELEVENLABS_VOICE_ID` after cloning |

**To clone your voice with ElevenLabs:**
1. Create a free account at [elevenlabs.io](https://elevenlabs.io)
2. Go to **Voices → Add Voice → Instant Voice Clone**
3. Upload 1–5 minutes of clean audio (your voice, no background music)
4. Copy the **Voice ID** from the voice settings page
5. Set in `.env`:
   ```
   TTS_PROVIDER=elevenlabs
   ELEVENLABS_API_KEY=your_key
   ELEVENLABS_VOICE_ID=your_voice_id
   ```

---

## Long-Term Memory

Trina remembers facts about you across conversations using a SQLite database (`TrinaDocs/memory.db`). A human-readable Quarto Markdown document (`TrinaDocs/memory.qmd`) stays in sync automatically.

| Example Phrase | What Happens |
|---|---|
| *"Remember that I prefer dark mode in all apps"* | Stores `[preferences] dark_mode: prefers dark mode in all apps` |
| *"My wife's name is Sarah"* | Stores `[personal] wife_name: Sarah` |
| *"I work at Apex Solutions as a data engineer"* | Stores under `[work]` category |
| *"What do you know about me?"* | Trina calls `list_memories` and summarizes |
| *"What do you remember about my coffee preference?"* | Trina calls `recall` with "coffee" |
| *"Forget my old phone number"* | Trina calls `forget` to delete that entry |

**Categories** (optional, Trina assigns automatically): `personal`, `work`, `preferences`, `health`, `general`

---

## Reminders

Trina schedules spoken reminders that fire at a set time. Both the desktop app and browser interface check every 20 seconds. When a reminder fires, Trina speaks it aloud unprompted.

| Example Phrase | What Happens |
|---|---|
| *"Remind me to take my medication in 30 minutes"* | Fires in 30 min, speaks "Reminder: take your medication" |
| *"Set a reminder for the team meeting at 2:00 pm"* | Fires today at 2:00 PM |
| *"Remind me to call Mom tomorrow at 9:00 am"* | Fires tomorrow morning |
| *"What reminders do I have?"* | Lists all pending reminders with IDs and times |
| *"Cancel reminder 3"* | Deletes reminder #3 |

**Supported time formats:**
- `in X minutes` / `in X hours` / `in X seconds`
- `at H:MM am/pm` (e.g. `at 3:30 pm`)
- `tomorrow at H:MM am/pm`

---

## Habit Tracker

Track daily habits with streaks. Trina logs check-ins in SQLite and reports your current streak each time you log. She will proactively offer to log a habit when you mention completing it.

| Example Phrase | What Happens |
|---|---|
| *"Add a habit: meditate for 10 minutes"* | Creates the `Meditate` habit |
| *"Track my exercise habit"* | Creates the `Exercise` habit |
| *"I meditated this morning"* | Trina logs `Meditate` for today, reports streak |
| *"Just finished my workout"* | Trina offers to log `Exercise` |
| *"Log my reading"* | Checks in `Reading` for today |
| *"How are my habits today?"* | Shows all habits with `[x]`/`[ ]` status and streak count |
| *"What's my meditation streak?"* | Trina calls `habit_status` and reads out the streak |
| *"Delete my journaling habit"* | Permanently removes habit and history |

**Streak rules:** Streaks count consecutive days with a check-in. Missing today does not break yesterday's streak — it breaks tomorrow if you miss today entirely.

**Morning check-in example:**
> *"Good morning Trina"*
> Trina: "Good morning! Here are your habits for today: [x] Exercise — 5-day streak. [ ] Meditate — 3-day streak. [ ] Read — 0-day streak. Would you like to log anything?"

---

## File & Folder Management

Trina can create folders, write files, and generate sample data — all landing in your configured workspace (`TrinaDocs/` by default).

### Create Folders

| Example Phrase | What Happens |
|---|---|
| *"Create a folder called Projects"* | Creates `TrinaDocs/Projects/` |
| *"Make a folder structure for my 2024 finances"* | Creates `TrinaDocs/Finances/2024/` |
| *"Set up a reading notes folder"* | Creates `TrinaDocs/Reading Notes/` |

### Write Files

| Example Phrase | What Happens |
|---|---|
| *"Write a meeting agenda for tomorrow's standup"* | Creates a `.md` file in the workspace |
| *"Save a note: buy groceries Saturday"* | Writes `notes.txt` or appends to it |
| *"Create a template for my weekly review"* | Generates a structured markdown file |
| *"Write a Python script that prints Hello World and save it"* | Saves `hello.py` to workspace |

### Generate Sample Data

| Example Phrase | What Happens |
|---|---|
| *"Generate 50 fake contacts as a CSV"* | Creates `contacts.csv` with name, email, phone, company, message |
| *"Make a leads file with 200 records in the Leads folder"* | Creates `TrinaDocs/Leads/contacts.csv` |

---

## Camera & Image Vision

Trina can see through your webcam or describe any image file in the workspace. Vision always uses Claude (Anthropic) regardless of your active LLM provider.

| Example Phrase | What Happens |
|---|---|
| *"What do you see?"* | Captures webcam frame, describes it |
| *"Is anyone else in the room?"* | Captures frame, answers the specific question |
| *"Describe what's on my desk"* | Detailed description of the camera view |
| *"Read the text in front of me"* | OCR-style description of visible text |
| *"Describe the photo I saved called diagram.png"* | Reads `TrinaDocs/diagram.png`, describes it |
| *"What's in the chart in report.jpg?"* | Analyzes a saved image file |

**Supported image formats:** `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`

---

## Model Switching

Switch between Anthropic Claude and a local Ollama model at any time. The switch is instant and persists for the session. Default provider is set by `LLM_PROVIDER` in `.env`.

| Example Phrase | What Happens |
|---|---|
| *"Switch to Ollama"* | Activates local Kimi K2 via Ollama |
| *"Switch to Kimi"* | Same as above |
| *"Use Claude"* or *"Switch back to Anthropic"* | Activates Claude API |
| *"Switch to Ollama, use llama3"* | Switches to Ollama and sets model to llama3 |

**To use Ollama:**
1. Install [Ollama](https://ollama.ai) and pull the model:
   ```
   ollama pull kimi-k2
   ```
2. Set in `.env`: `LLM_PROVIDER=ollama`
3. Ollama must be running locally (`ollama serve`)

**Vision note:** `describe_camera` and `describe_image` always use Claude vision, even when Ollama is the active text model.

---

## Configuration Reference

All settings live in `.env` in the project root.

```env
# API Keys
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
DEEPGRAM_API_KEY=...

# Models
CLAUDE_MODEL=claude-sonnet-4-6
DEEPGRAM_MODEL=nova-2

# TTS
TTS_PROVIDER=gemini              # "gemini" or "elevenlabs"
TTS_MODEL=gemini-3.1-flash-tts-preview
TTS_VOICE=Zephyr                 # Gemini pre-built voice name
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=             # from elevenlabs.io after cloning
ELEVENLABS_MODEL=eleven_turbo_v2_5

# LLM Provider
LLM_PROVIDER=ollama              # "anthropic" or "ollama"
OLLAMA_MODEL=kimi-k2
OLLAMA_BASE_URL=http://localhost:11434/v1

# Wake Word (pvporcupine)
PORCUPINE_ACCESS_KEY=            # free at console.picovoice.ai
WAKE_WORD_PATH=                  # path to custom "Hey Trina" .ppn file

# Server
WS_PORT=8765

# Workspace
TRINA_WORKSPACE=C:\Users\rholmes\TrinaDocs
```

### Running Trina

| Command | Mode |
|---|---|
| `python server.py` | Browser UI at `http://localhost:8080` |
| `python trina.py` | Voice mode via desktop mic + speakers |
| `python trina.py --text` | Text mode (no mic required) |
