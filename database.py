"""
database.py — SQLite async layer
جداول:
  users        → معلومات المستخدم وتفضيلاته
  messages     → سجل كل المحادثات
  scheduled    → المهام المجدولة
"""
import json
import aiosqlite
from datetime import datetime

DB_PATH = "hermes.db"

# ══════════════════════════════════════════
#  تهيئة قاعدة البيانات
# ══════════════════════════════════════════
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id     TEXT PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                preferences TEXT DEFAULT '{}',
                created_at  TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    TEXT,
                role       TEXT,        -- 'user' | 'assistant'
                content    TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    TEXT,
                topic      TEXT,
                hour       INTEGER,
                minute     INTEGER,
                active     INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        # فهارس للسرعة
        await db.execute("CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sch_chat ON scheduled(chat_id, active)")
        await db.commit()

# ══════════════════════════════════════════
#  المستخدمون
# ══════════════════════════════════════════
async def upsert_user(chat_id: str, username: str, first_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (chat_id, username, first_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (chat_id, username or "", first_name or "", datetime.utcnow().isoformat()))
        await db.commit()

async def get_user(chat_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def set_preference(chat_id: str, key: str, value):
    """حفظ تفضيل واحد"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT preferences FROM users WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
        prefs = json.loads(row[0]) if row else {}
        prefs[key] = value
        await db.execute("UPDATE users SET preferences=? WHERE chat_id=?",
                         (json.dumps(prefs, ensure_ascii=False), chat_id))
        await db.commit()

async def get_preferences(chat_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT preferences FROM users WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
        return json.loads(row[0]) if row else {}

# ══════════════════════════════════════════
#  الرسائل / الذاكرة
# ══════════════════════════════════════════
async def save_message(chat_id: str, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?,?,?,?)",
            (chat_id, role, content, datetime.utcnow().isoformat())
        )
        await db.commit()

async def get_history(chat_id: str, limit: int = 20) -> list[dict]:
    """آخر N رسالة كـ list of {role, content}"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content FROM messages
            WHERE chat_id=?
            ORDER BY id DESC LIMIT ?
        """, (chat_id, limit)) as cur:
            rows = await cur.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

async def get_history_text(chat_id: str, limit: int = 50) -> str:
    """آخر N رسالة كنص مقروء للعرض"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content, created_at FROM messages
            WHERE chat_id=?
            ORDER BY id DESC LIMIT ?
        """, (chat_id, limit)) as cur:
            rows = await cur.fetchall()
    if not rows:
        return "لا توجد محادثات مسجّلة."
    lines = []
    for role, content, ts in reversed(rows):
        label = "أنت" if role == "user" else "Hermes"
        short_ts = ts[:16].replace("T", " ")
        lines.append(f"[{short_ts}] {label}:\n{content}")
    return "\n\n".join(lines)

async def clear_history(chat_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        await db.commit()

# ══════════════════════════════════════════
#  الجدولة
# ══════════════════════════════════════════
async def add_task(chat_id: str, topic: str, hour: int, minute: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO scheduled (chat_id, topic, hour, minute, created_at)
            VALUES (?,?,?,?,?)
        """, (chat_id, topic, hour, minute, datetime.utcnow().isoformat()))
        await db.commit()
        return cur.lastrowid

async def get_tasks(chat_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scheduled WHERE chat_id=? AND active=1 ORDER BY id",
            (chat_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def get_all_active_tasks() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scheduled WHERE active=1") as cur:
            return [dict(r) for r in await cur.fetchall()]

async def delete_task(task_id: int, chat_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE scheduled SET active=0 WHERE id=? AND chat_id=?",
            (task_id, chat_id)
        )
        await db.commit()
        return cur.rowcount > 0
