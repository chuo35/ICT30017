import asyncio
import logging
import uvicorn
from nanoclaw.server import app  # Fixed: Pointing to the rich WebSocket server
from nanoclaw.config import ASSISTANT_NAME, DATA_DIR, DB_PATH, STORE_DIR, WORKSPACE_DIR
from nanoclaw.db import init_db
from nanoclaw.memory import ensure_workspace
from nanoclaw.scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def _prepare_runtime() -> None:
    for d in (WORKSPACE_DIR, STORE_DIR, DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)
    await init_db(str(DB_PATH))
    ensure_workspace()

def main() -> None:
    asyncio.run(_prepare_runtime())
    
    # Start Scheduler
    scheduler = setup_scheduler(str(DB_PATH))
    scheduler.start()
    
    # Start Web Server
    logger.info(f"{ASSISTANT_NAME} starting on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()