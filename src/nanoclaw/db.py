import uuid
import aiosqlite
from datetime import datetime, timezone

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    schedule_value TEXT NOT NULL,
    next_run TEXT,
    last_run TEXT,
    last_result TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS web_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER DEFAULT 0
);
"""

async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_CREATE_TABLES)
        await db.commit()

async def add_notification(db_path: str, content: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO web_notifications (content, created_at) VALUES (?, ?)",
            (content, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()

async def get_notifications(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM web_notifications WHERE is_read = 0 ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        await db.execute("UPDATE web_notifications SET is_read = 1 WHERE is_read = 0")
        await db.commit()
        return [dict(r) for r in rows]

async def create_task(db_path: str, prompt: str, schedule_type: str, schedule_value: str, next_run: str) -> str:
    task_id = uuid.uuid4().hex[:8]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO scheduled_tasks (id, prompt, schedule_type, schedule_value, next_run, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, prompt, schedule_type, schedule_value, next_run, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    return task_id

async def get_due_tasks(db_path: str) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM scheduled_tasks WHERE status = 'active' AND next_run <= ?", (now,))
        return [dict(r) for r in (await cursor.fetchall())]

async def update_task_after_run(db_path: str, task_id: str, last_result: str, next_run: str | None, status: str = "active") -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE scheduled_tasks SET last_run = ?, last_result = ?, next_run = ?, status = ? WHERE id = ?",
            (now, last_result, next_run, status, task_id),
        )
        await db.commit()