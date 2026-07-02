"""Trina tool registry — definitions, implementations, and Claude tool loop."""

import base64
import csv
import io
import json
import os
import random
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from anthropic import Anthropic

# ── Workspace ─────────────────────────────────────────────────────────────────

WORKSPACE = Path(os.getenv("TRINA_WORKSPACE", Path.home() / "TrinaDocs"))
WORKSPACE.mkdir(parents=True, exist_ok=True)

MEMORY_DB  = WORKSPACE / "memory.db"
MEMORY_DOC = WORKSPACE / "memory.qmd"

# ── LLM provider state ────────────────────────────────────────────────────────

_provider        = os.getenv("LLM_PROVIDER",    "anthropic")   # "anthropic" | "ollama"
_ollama_model    = os.getenv("OLLAMA_MODEL",    "kimi-k2")
_ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""\
You are Trina, a personal life assistant running on the user's desktop.

Personality: warm, concise, and practical — like a very competent friend.
Mode: reactive. You speak only when spoken to; never volunteer unprompted.

You have tools that let you create folders, write files, and generate data on
the user's computer. All files land in the workspace: {WORKSPACE}

You also have a persistent memory system backed by SQLite. Use it proactively:
- Store important facts about the user (preferences, names, habits) with remember.
- Recall relevant memories before answering questions about the user's life.
- Forget outdated or incorrect information with forget.
Memory persists across conversations — use it to build a lasting picture of
who the user is and what they care about.

You can track daily habits (add_habit, log_habit, habit_status, delete_habit).
When the user mentions completing something habitual — working out, meditating,
reading — proactively offer to log it. On morning check-ins, call habit_status
unprompted to show the day's slate.

You can set spoken reminders that fire at a future time (set_reminder). When
the user asks to be reminded of something, always confirm the exact time back
to them.

You can see through the webcam (describe_camera) or describe any image file
in the workspace (describe_image). These always use Claude vision.

You can search across all documents in the workspace semantically
(search_documents). Use this whenever the user asks about something they wrote,
a past note, a file, or any content stored in their workspace. You can also
index_workspace to refresh the search index after new files are added.

When you finish a task, confirm it's done and mention the file or folder name.
Keep replies brief unless the user asks for depth.\
"""

# ── Fake contact data ─────────────────────────────────────────────────────────

_FIRST = [
    "James","Mary","John","Patricia","Robert","Jennifer","Michael","Linda",
    "William","Barbara","David","Elizabeth","Richard","Susan","Joseph","Jessica",
    "Thomas","Sarah","Charles","Karen","Christopher","Lisa","Daniel","Nancy",
    "Matthew","Betty","Anthony","Margaret","Mark","Sandra","Donald","Ashley",
    "Steven","Dorothy","Paul","Kimberly","Andrew","Emily","Kenneth","Donna",
    "George","Michelle","Joshua","Carol","Kevin","Amanda","Brian","Melissa",
    "Edward","Deborah",
]
_LAST = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
    "Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson",
    "White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker",
    "Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell",
    "Carter","Roberts",
]
_DOMAINS = [
    "gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com",
    "protonmail.com","company.com","business.net","work.org","mail.com",
]
_COMPANIES = [
    "Apex Solutions","Blue Ridge Tech","Cedar Analytics","Driftwood Media",
    "Echo Systems","Falcon Industries","Granite Works","Harbor Digital",
    "Iris Consulting","Jade Ventures","Keystone Group","Lunar Labs",
    "Maple Street Co","Nova Dynamics","Orbit Creative","Pinnacle Corp",
    "Quest Analytics","Redwood Agency","Summit Tech","Tandem Logic",
    "Unity Partners","Vantage Group","Wavecrest Inc","Zenith Media",
    "Cobalt Systems","Emerald Data",
]
_MESSAGES = [
    "I'd like to learn more about your services.",
    "Please send me pricing information.",
    "I'm interested in scheduling a demo.",
    "Can we set up a call to discuss options?",
    "I have a question about your product line.",
    "I'd like to request a quote for my team.",
    "Please add me to your newsletter.",
    "I need help with my existing account.",
    "Can you explain your refund policy?",
    "We're exploring vendors for an upcoming project.",
    "Do you offer enterprise or volume pricing?",
    "I saw your ad online and want more information.",
    "Can someone from sales reach out to me?",
    "I'm looking for a custom integration solution.",
    "We're interested in a long-term partnership.",
]

# ── Path safety ───────────────────────────────────────────────────────────────

def _safe(rel: str) -> Path:
    full = (WORKSPACE / rel).resolve()
    if not str(full).startswith(str(WORKSPACE.resolve())):
        raise ValueError(f"Path '{rel}' is outside the workspace.")
    return full

# ── Memory database ───────────────────────────────────────────────────────────

def _init_db() -> None:
    con = sqlite3.connect(MEMORY_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            category   TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_key ON memories(key)"
    )
    con.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message    TEXT NOT NULL,
            fire_at    TEXT NOT NULL,
            fired      INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS habit_checkins (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id     INTEGER NOT NULL REFERENCES habits(id),
            checked_date TEXT NOT NULL,
            checked_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(habit_id, checked_date)
        )
    """)
    con.commit()
    con.close()


_init_db()


def _refresh_memory_doc() -> None:
    con = sqlite3.connect(MEMORY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT key, value, category, updated_at FROM memories ORDER BY category, updated_at DESC"
    ).fetchall()
    con.close()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not rows:
        MEMORY_DOC.write_text(
            f"---\ntitle: Trina Memory\ndate: {now}\nformat: html\n---\n\n"
            "# Trina Memory\n\n_No memories stored yet._\n",
            encoding="utf-8",
        )
        return

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)

    lines = [
        "---",
        "title: Trina Memory",
        f"date: {now}",
        "format: html",
        "---",
        "",
        "# Trina Memory",
        "",
        f"> Last updated: {now}",
        "",
    ]

    for cat in sorted(groups):
        lines.append(f"## {cat.title()}")
        lines.append("")
        for item in groups[cat]:
            lines.append(f"**{item['key']}**")
            lines.append(f": {item['value']}")
            lines.append(f"<small>Updated: {item['updated_at']}</small>")
            lines.append("")

    MEMORY_DOC.write_text("\n".join(lines), encoding="utf-8")


def remember(key: str, value: str, category: str = "general") -> str:
    con = sqlite3.connect(MEMORY_DB)
    con.execute(
        """
        INSERT INTO memories (key, value, category, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value      = excluded.value,
            category   = excluded.category,
            updated_at = datetime('now')
        """,
        (key, value, category),
    )
    con.commit()
    con.close()
    _refresh_memory_doc()
    return f"Remembered [{category}] {key}: {value}"


def recall(query: str) -> str:
    con = sqlite3.connect(MEMORY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT key, value, category FROM memories
           WHERE key LIKE ? OR value LIKE ?
           ORDER BY updated_at DESC LIMIT 20""",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    con.close()
    if not rows:
        return f"No memories found matching '{query}'."
    return "\n".join(f"[{r['category']}] {r['key']}: {r['value']}" for r in rows)


def forget(key: str) -> str:
    con = sqlite3.connect(MEMORY_DB)
    cur = con.execute("DELETE FROM memories WHERE key = ?", (key,))
    con.commit()
    deleted = cur.rowcount
    con.close()
    if deleted:
        _refresh_memory_doc()
        return f"Forgot: {key}"
    return f"No memory found with key '{key}'."


def list_memories(category: str = "") -> str:
    con = sqlite3.connect(MEMORY_DB)
    con.row_factory = sqlite3.Row
    if category:
        rows = con.execute(
            "SELECT key, value, category FROM memories WHERE category = ? ORDER BY updated_at DESC",
            (category,),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT key, value, category FROM memories ORDER BY category, updated_at DESC"
        ).fetchall()
    con.close()
    if not rows:
        return "No memories stored yet."
    return "\n".join(f"[{r['category']}] {r['key']}: {r['value']}" for r in rows)


# ── Reminders ─────────────────────────────────────────────────────────────────

def _parse_when(when: str) -> datetime | None:
    w = when.strip().lower()

    m = re.match(r'in (\d+)\s*seconds?', w)
    if m:
        return datetime.now() + timedelta(seconds=int(m.group(1)))

    m = re.match(r'in (\d+)\s*min(?:utes?)?', w)
    if m:
        return datetime.now() + timedelta(minutes=int(m.group(1)))

    m = re.match(r'in (\d+)\s*hours?', w)
    if m:
        return datetime.now() + timedelta(hours=int(m.group(1)))

    # "at 3:30 pm" / "at 15:30"
    m = re.match(r'(?:tomorrow\s+)?at\s+(\d{1,2}):(\d{2})(?:\s*(am|pm))?', w)
    if m:
        h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        if ampm == 'pm' and h < 12:
            h += 12
        elif ampm == 'am' and h == 12:
            h = 0
        base = datetime.now() + timedelta(days=1) if w.startswith('tomorrow') else datetime.now()
        dt = base.replace(hour=h, minute=mi, second=0, microsecond=0)
        if not w.startswith('tomorrow') and dt <= datetime.now():
            dt += timedelta(days=1)
        return dt

    return None


def set_reminder(message: str, when: str) -> str:
    dt = _parse_when(when)
    if dt is None:
        return (
            f"Couldn't parse '{when}'. "
            "Try: 'in 30 minutes', 'in 2 hours', 'at 3:30 pm', 'tomorrow at 9:00 am'."
        )
    con = sqlite3.connect(MEMORY_DB)
    cur = con.execute(
        "INSERT INTO reminders (message, fire_at) VALUES (?, ?)",
        (message, dt.strftime("%Y-%m-%d %H:%M:%S")),
    )
    rid = cur.lastrowid
    con.commit()
    con.close()
    return f"Reminder #{rid} set for {dt.strftime('%B %d at %I:%M %p')}: {message}"


def list_reminders() -> str:
    con = sqlite3.connect(MEMORY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, message, fire_at FROM reminders WHERE fired=0 ORDER BY fire_at"
    ).fetchall()
    con.close()
    if not rows:
        return "No pending reminders."
    return "\n".join(f"#{r['id']} — {r['fire_at']} — {r['message']}" for r in rows)


def cancel_reminder(reminder_id: int) -> str:
    con = sqlite3.connect(MEMORY_DB)
    cur = con.execute("DELETE FROM reminders WHERE id=? AND fired=0", (reminder_id,))
    con.commit()
    con.close()
    return f"Reminder #{reminder_id} cancelled." if cur.rowcount else f"No pending reminder #{reminder_id}."


def check_due_reminders() -> list[str]:
    """Return messages for any reminders that are now due; marks them fired."""
    con = sqlite3.connect(MEMORY_DB)
    rows = con.execute(
        "SELECT id, message FROM reminders WHERE fired=0 AND fire_at <= datetime('now') ORDER BY fire_at"
    ).fetchall()
    due = [msg for _, msg in rows]
    for rid, _ in rows:
        con.execute("UPDATE reminders SET fired=1 WHERE id=?", (rid,))
    con.commit()
    con.close()
    return due


# ── Habit tracker ─────────────────────────────────────────────────────────────

def _habit_streak(habit_id: int, con: sqlite3.Connection) -> int:
    today = datetime.now().date()
    row = con.execute(
        "SELECT checked_date FROM habit_checkins WHERE habit_id=? ORDER BY checked_date DESC LIMIT 1",
        (habit_id,),
    ).fetchone()
    if not row:
        return 0
    last = datetime.fromisoformat(row[0]).date()
    if (today - last).days > 1:
        return 0
    streak, day = 0, last
    while True:
        if not con.execute(
            "SELECT 1 FROM habit_checkins WHERE habit_id=? AND checked_date=?",
            (habit_id, day.isoformat()),
        ).fetchone():
            break
        streak += 1
        day -= timedelta(days=1)
    return streak


def add_habit(name: str, description: str = "") -> str:
    con = sqlite3.connect(MEMORY_DB)
    try:
        con.execute("INSERT INTO habits (name, description) VALUES (?, ?)", (name, description))
        con.commit()
        return f"Habit '{name}' created. Check in daily with 'log {name}'."
    except sqlite3.IntegrityError:
        return f"A habit named '{name}' already exists."
    finally:
        con.close()


def log_habit(name: str) -> str:
    today = datetime.now().date().isoformat()
    con = sqlite3.connect(MEMORY_DB)
    row = con.execute(
        "SELECT id FROM habits WHERE lower(name)=lower(?)", (name,)
    ).fetchone()
    if not row:
        con.close()
        return f"No habit named '{name}'. Use habit_status to see your habits."
    hid = row[0]
    try:
        con.execute(
            "INSERT INTO habit_checkins (habit_id, checked_date) VALUES (?, ?)",
            (hid, today),
        )
        con.commit()
        streak = _habit_streak(hid, con)
        days = "day" if streak == 1 else "days"
        return f"Logged '{name}' for today. {streak}-{days} streak."
    except sqlite3.IntegrityError:
        streak = _habit_streak(hid, con)
        return f"'{name}' already logged today. Current streak: {streak} days."
    finally:
        con.close()


def habit_status() -> str:
    today = datetime.now().date().isoformat()
    con = sqlite3.connect(MEMORY_DB)
    rows = con.execute(
        "SELECT id, name, description FROM habits ORDER BY name"
    ).fetchall()
    if not rows:
        con.close()
        return "No habits tracked yet. Use add_habit to create your first one."
    lines = [f"Habits - {today}", ""]
    for hid, name, desc in rows:
        done   = con.execute(
            "SELECT 1 FROM habit_checkins WHERE habit_id=? AND checked_date=?",
            (hid, today),
        ).fetchone()
        streak = _habit_streak(hid, con)
        mark   = "[x]" if done else "[ ]"
        detail = f" ({desc})" if desc else ""
        lines.append(f"{mark} {name}{detail}  - {streak}d streak")
    con.close()
    return "\n".join(lines)


def delete_habit(name: str) -> str:
    con = sqlite3.connect(MEMORY_DB)
    row = con.execute(
        "SELECT id FROM habits WHERE lower(name)=lower(?)", (name,)
    ).fetchone()
    if not row:
        con.close()
        return f"No habit named '{name}'."
    hid = row[0]
    con.execute("DELETE FROM habit_checkins WHERE habit_id=?", (hid,))
    con.execute("DELETE FROM habits WHERE id=?", (hid,))
    con.commit()
    con.close()
    return f"Habit '{name}' and all its check-in history deleted."


# ── Camera / image vision ─────────────────────────────────────────────────────

def describe_camera(prompt: str = "Describe what you see in detail.") -> str:
    try:
        import cv2
    except ImportError:
        return "Camera support requires opencv-python. Run: pip install opencv-python"

    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return "Could not capture a frame from the camera. Is a camera connected?"

    _, buf = cv2.imencode(".jpg", frame)
    img_b64 = base64.b64encode(buf).decode()

    client = Anthropic()
    resp = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                {"type": "text",  "text": prompt},
            ],
        }],
    )
    return resp.content[0].text


def describe_image(path: str, prompt: str = "Describe this image in detail.") -> str:
    p = _safe(path)
    if not p.exists():
        return f"File not found in workspace: {path}"

    _MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".gif": "image/gif", ".webp": "image/webp"}
    media_type = _MEDIA.get(p.suffix.lower(), "image/jpeg")
    img_b64 = base64.b64encode(p.read_bytes()).decode()

    client = Anthropic()
    resp = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                {"type": "text",  "text": prompt},
            ],
        }],
    )
    return resp.content[0].text


# ── File / folder tools ───────────────────────────────────────────────────────

def create_folder(name: str) -> str:
    path = _safe(name)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def write_file(path: str, content: str) -> str:
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


def generate_contacts_csv(path: str, count: int) -> str:
    count = max(1, min(count, 1000))
    base  = datetime(2024, 1, 1)
    rows  = []
    for i in range(count):
        first = random.choice(_FIRST)
        last  = random.choice(_LAST)
        email = f"{first.lower()}.{last.lower()}{random.randint(1,99)}@{random.choice(_DOMAINS)}"
        phone = f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"
        ts    = base + timedelta(
            days=random.randint(0, 364),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        rows.append({
            "id":           i + 1,
            "first_name":   first,
            "last_name":    last,
            "email":        email,
            "phone":        phone,
            "company":      random.choice(_COMPANIES),
            "message":      random.choice(_MESSAGES),
            "submitted_at": ts.strftime("%Y-%m-%d %H:%M:%S"),
        })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(buf.getvalue(), encoding="utf-8")
    return str(p)


def search_documents(query: str, n: int = 5) -> str:
    """Semantic search across indexed workspace documents."""
    from rag import search
    return search(query, n=n)


def index_workspace() -> str:
    """Re-index all workspace documents into the RAG store."""
    from rag import index_workspace as _index
    return _index(verbose=False)


def execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "switch_model":
            return switch_model(inputs["provider"], inputs.get("model", ""))
        if name == "set_reminder":
            return set_reminder(inputs["message"], inputs["when"])
        if name == "list_reminders":
            return list_reminders()
        if name == "cancel_reminder":
            return cancel_reminder(int(inputs["id"]))
        if name == "add_habit":
            return add_habit(inputs["name"], inputs.get("description", ""))
        if name == "log_habit":
            return log_habit(inputs["name"])
        if name == "habit_status":
            return habit_status()
        if name == "delete_habit":
            return delete_habit(inputs["name"])
        if name == "describe_camera":
            return describe_camera(inputs.get("prompt", "Describe what you see in detail."))
        if name == "describe_image":
            return describe_image(inputs["path"], inputs.get("prompt", "Describe this image in detail."))
        if name == "remember":
            return remember(inputs["key"], inputs["value"], inputs.get("category", "general"))
        if name == "recall":
            return recall(inputs["query"])
        if name == "forget":
            return forget(inputs["key"])
        if name == "list_memories":
            return list_memories(inputs.get("category", ""))
        if name == "create_folder":
            return f"Created: {create_folder(inputs['name'])}"
        if name == "write_file":
            return f"Written: {write_file(inputs['path'], inputs['content'])}"
        if name == "generate_contacts_csv":
            p = generate_contacts_csv(inputs["path"], inputs["count"])
            return f"CSV ready: {p}  ({inputs['count']} records)"
        if name == "search_documents":
            return search_documents(inputs["query"], int(inputs.get("n", 5)))
        if name == "index_workspace":
            return index_workspace()
        return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error executing {name}: {exc}"

# ── Tool schema ───────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "switch_model",
        "description": (
            "Switch the active LLM between Anthropic Claude and a local Ollama model. "
            "Use provider='anthropic' to switch back to Claude, or provider='ollama' "
            "to switch to the local Ollama model (default: kimi-k2). "
            "Optionally specify a different Ollama model name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["anthropic", "ollama"],
                    "description": "Which provider to activate.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional Ollama model name, e.g. 'kimi-k2', 'llama3'. Ignored for anthropic.",
                },
            },
            "required": ["provider"],
        },
    },
    {
        "name": "add_habit",
        "description": "Create a new daily habit to track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":        {"type": "string", "description": "Short habit name, e.g. 'Meditate', 'Exercise', 'Read'."},
                "description": {"type": "string", "description": "Optional detail, e.g. '10 minutes of meditation'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "log_habit",
        "description": "Check in a habit for today. Call this when the user says they did something (e.g. 'I meditated', 'I worked out').",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The habit name to log for today."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "habit_status",
        "description": "Show all habits with today's check-in status and current streak. Use this for morning check-ins or when the user asks how they're doing.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_habit",
        "description": "Permanently delete a habit and all its history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The exact habit name to delete."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_reminder",
        "description": "Schedule a spoken reminder at a future time. Trina will speak the message aloud when the time arrives.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to say when the reminder fires, e.g. 'Take your medication'."},
                "when":    {"type": "string", "description": "Natural language time: 'in 30 minutes', 'in 2 hours', 'at 3:30 pm', 'tomorrow at 9:00 am'."},
            },
            "required": ["message", "when"],
        },
    },
    {
        "name": "list_reminders",
        "description": "List all pending (unfired) reminders.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a pending reminder by its ID number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "The reminder ID shown in list_reminders."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "describe_camera",
        "description": "Capture a frame from the webcam and describe what Trina sees. Always uses Claude vision regardless of active LLM provider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Optional instruction for the vision model, e.g. 'Is anyone in the room?'"},
            },
            "required": [],
        },
    },
    {
        "name": "describe_image",
        "description": "Describe an image file that exists in the workspace. Always uses Claude vision.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "Relative path to the image in the workspace, e.g. 'photo.jpg'."},
                "prompt": {"type": "string", "description": "Optional instruction for the vision model."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Store a fact in Trina's long-term memory (SQLite). "
            "Use a short descriptive key (e.g. 'user_name', 'preferred_coffee'). "
            "Overwrites any existing memory with the same key. "
            "Also refreshes memory.qmd in the workspace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Short identifier, e.g. 'user_name' or 'work_schedule'.",
                },
                "value": {
                    "type": "string",
                    "description": "The fact to store.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional grouping, e.g. 'personal', 'work', 'preferences'. Defaults to 'general'.",
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Search Trina's long-term memory by keyword. "
            "Returns matching memories (key, value, category). "
            "Use this when you need to look up something the user has told you before."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to search for in memory keys and values.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "forget",
        "description": "Delete a specific memory by its exact key.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The exact key of the memory to delete.",
                }
            },
            "required": ["key"],
        },
    },
    {
        "name": "list_memories",
        "description": "List all stored memories, optionally filtered by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter to a specific category (e.g. 'personal'). Omit to list all.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "create_folder",
        "description": (
            f"Creates a folder inside the workspace ({WORKSPACE}). "
            "Parent directories are created automatically. Returns the full path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Folder name or relative path, e.g. 'Reports' or 'Data/2024'.",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "write_file",
        "description": f"Creates or overwrites a text file inside the workspace ({WORKSPACE}).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path, e.g. 'notes.txt' or 'Reports/summary.md'.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "generate_contacts_csv",
        "description": (
            "Generates a CSV filled with fabricated contact-form records: "
            "id, first_name, last_name, email, phone, company, message, submitted_at."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path for the CSV, e.g. 'contacts.csv' or 'Leads/contacts.csv'.",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of records to generate (1–1000).",
                    "minimum": 1,
                    "maximum": 1000,
                },
            },
            "required": ["path", "count"],
        },
    },
    {
        "name": "search_documents",
        "description": (
            "Semantically search all documents indexed from the workspace. "
            "Use this when the user asks about something they wrote, a past note, "
            "a file, a meeting, a proposal, or any content in their files. "
            "Returns the most relevant passages with source file names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query, e.g. 'client proposal March' or 'budget notes Q2'.",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 20).",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "index_workspace",
        "description": (
            "Re-index all documents in the workspace so they appear in search results. "
            "Call this after the user adds new files, or if search returns no results. "
            "Takes a moment for large workspaces."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# ── Provider switch ───────────────────────────────────────────────────────────

def switch_model(provider: str, model: str = "") -> str:
    global _provider, _ollama_model
    provider = provider.lower().strip()
    if provider not in ("anthropic", "ollama"):
        return f"Unknown provider '{provider}'. Use 'anthropic' or 'ollama'."
    _provider = provider
    if model:
        _ollama_model = model
    if provider == "ollama":
        return f"Switched to Ollama / {_ollama_model}."
    return f"Switched to Anthropic / {os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-6')}."


# ── History format helpers ────────────────────────────────────────────────────

def _to_openai_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOL_DEFINITIONS
    ]


def _to_openai_history(history: list[dict]) -> list[dict]:
    """Convert Anthropic-format history to OpenAI-format messages."""
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role    = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            msgs.append({"role": role, "content": content})
            continue

        if not isinstance(content, list) or not content:
            continue

        # Peek at the first block type (dict or SDK object)
        first = content[0]
        ftype = first.get("type") if isinstance(first, dict) else getattr(first, "type", None)

        if ftype == "tool_result":
            for block in content:
                if isinstance(block, dict):
                    msgs.append({
                        "role":        "tool",
                        "content":     block.get("content", ""),
                        "tool_call_id": block.get("tool_use_id", ""),
                    })
            continue

        # Assistant turn: text blocks + optional tool_use blocks
        texts: list[str] = []
        tool_calls: list[dict] = []
        for block in content:
            btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if btype == "text":
                t = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                if t:
                    texts.append(t)
            elif btype == "tool_use":
                if isinstance(block, dict):
                    bid, bname, binput = block["id"], block["name"], block.get("input", {})
                else:
                    bid, bname, binput = block.id, block.name, block.input
                tool_calls.append({
                    "id":   bid,
                    "type": "function",
                    "function": {
                        "name":      bname,
                        "arguments": json.dumps(binput),
                    },
                })

        oai_msg: dict = {"role": role, "content": " ".join(texts) or None}
        if tool_calls:
            oai_msg["tool_calls"] = tool_calls
        msgs.append(oai_msg)

    return msgs


# ── Ollama tool loop (sync) ───────────────────────────────────────────────────

def _call_ollama(history: list[dict]) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return "Ollama support requires the 'openai' package. Run: pip install openai"

    client    = OpenAI(base_url=_ollama_base_url, api_key="ollama")
    oai_msgs  = _to_openai_history(history)
    oai_tools = _to_openai_tools()

    while True:
        resp   = client.chat.completions.create(
            model=_ollama_model,
            messages=oai_msgs,
            tools=oai_tools,
        )
        choice = resp.choices[0]
        msg_obj = choice.message

        if not msg_obj.tool_calls or choice.finish_reason == "stop":
            reply = msg_obj.content or ""
            history.append({"role": "assistant", "content": reply})
            return reply

        # Append assistant tool_calls turn locally
        oai_msgs.append({
            "role":    "assistant",
            "content": msg_obj.content,
            "tool_calls": [
                {
                    "id":   tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg_obj.tool_calls
            ],
        })

        anthropic_uses:    list[dict] = []
        tool_results_oai:  list[dict] = []
        tool_results_ant:  list[dict] = []

        for tc in msg_obj.tool_calls:
            inputs  = json.loads(tc.function.arguments)
            outcome = execute_tool(tc.function.name, inputs)

            tool_results_oai.append({
                "role":        "tool",
                "content":     outcome,
                "tool_call_id": tc.id,
            })
            anthropic_uses.append({
                "type":  "tool_use",
                "id":    tc.id,
                "name":  tc.function.name,
                "input": inputs,
            })
            tool_results_ant.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,
                "content":     outcome,
            })

        oai_msgs.extend(tool_results_oai)

        # Keep external Anthropic-format history in sync
        history.append({"role": "assistant", "content": anthropic_uses})
        history.append({"role": "user",      "content": tool_results_ant})


# ── Anthropic tool loop (sync) ────────────────────────────────────────────────

def _call_anthropic(history: list[dict]) -> str:
    model  = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = Anthropic()

    while True:
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=history,
        )

        if resp.stop_reason == "end_turn":
            for block in resp.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if resp.stop_reason == "tool_use":
            history.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    outcome = execute_tool(block.name, block.input)
                    results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     outcome,
                    })
            history.append({"role": "user", "content": results})
        else:
            return ""


# ── Public dispatcher ─────────────────────────────────────────────────────────

def call_claude(history: list[dict]) -> str:
    if _provider == "ollama":
        return _call_ollama(history)
    return _call_anthropic(history)
