import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter
from nanoclaw import db
from nanoclaw.agent import run_agent
from nanoclaw.config import SCHEDULER_INTERVAL

logger = logging.getLogger(__name__)

def setup_scheduler(db_path: str) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_check_tasks, "interval", seconds=SCHEDULER_INTERVAL, args=[db_path])
    return scheduler

async def _check_tasks(db_path: str) -> None:
    tasks = await db.get_due_tasks(db_path)
    for task in tasks:
        wrapped_prompt = f"Executing scheduled task: {task['prompt']}. Use send_message to notify the user."
        result = await run_agent(wrapped_prompt, db_path)
        
        now = datetime.now(timezone.utc)
        next_run = None
        if task["schedule_type"] == "cron":
            next_run = croniter(task["schedule_value"], now).get_next(datetime).isoformat()
        elif task["schedule_type"] == "interval":
            next_run = (now + timedelta(milliseconds=int(task["schedule_value"]))).isoformat()
        
        await db.update_task_after_run(db_path, task["id"], result, next_run, "active" if next_run else "completed")