import logging
import asyncio
from contextlib import asynccontextmanager
 
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
 
from nanoclaw.agent import run_agent, clear_session_id
from nanoclaw.conversations import archive_exchange
from nanoclaw.config import ASSISTANT_NAME, DB_PATH
from nanoclaw.scheduler import setup_scheduler
 
logger = logging.getLogger(__name__)
 
# ── Lifespan: start scheduler on boot ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fixed: Removed the outdated bot=None argument
    scheduler = setup_scheduler(str(DB_PATH))
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")
 
 
app = FastAPI(title="NanoClaw Web Chat", lifespan=lifespan)
 
# Serve static files (your index.html lives here)
app.mount("/static", StaticFiles(directory="static"), name="static")
 
 
# ── REST: serve the chat page ─────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse("static/index.html")
 
 
# ── REST: clear session ───────────────────────────────────────────────────────
@app.post("/api/clear")
async def clear_session():
    clear_session_id()
    return {"status": "ok", "message": "Session cleared. Starting fresh!"}
 
 
# ── REST: assistant name ──────────────────────────────────────────────────────
@app.get("/api/info")
async def info():
    return {"assistant_name": ASSISTANT_NAME}
 
 
# ── WebSocket: real-time chat ─────────────────────────────────────────────────
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection opened")
 
    # Fake chat_id for web sessions (no Telegram user here)
    WEB_CHAT_ID = 0
 
    try:
        while True:
            # Receive user message as plain text
            user_text = await websocket.receive_text()
 
            if not user_text.strip():
                continue
 
            logger.info(f"User: {user_text}")
 
            # Send typing indicator
            await websocket.send_json({"type": "typing", "content": ""})
 
            # Fixed: Updated to match the new run_agent signature (prompt, db_path)
            response = await run_agent(user_text, str(DB_PATH))
 
            # Archive conversation for long-term memory
            await archive_exchange(user_text, response, WEB_CHAT_ID)
 
            logger.info(f"Assistant: {response[:80]}...")
 
            # Send the full response back
            await websocket.send_json({"type": "message", "content": response})
 
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.exception("WebSocket error")
        await websocket.send_json({"type": "error", "content": str(e)})