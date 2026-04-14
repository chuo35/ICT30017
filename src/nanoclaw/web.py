from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from nanoclaw.agent import run_agent, clear_session_id
from nanoclaw.conversations import archive_exchange
from nanoclaw.config import DB_PATH, OWNER_ID
from nanoclaw import db

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

async def verify_owner(x_api_key: str = Header(None)):
    if x_api_key != str(OWNER_ID):
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/chat")
async def chat(request: ChatRequest, _=Depends(verify_owner)):
    response = await run_agent(request.message, str(DB_PATH))
    await archive_exchange(request.message, response, 0)
    return {"response": response}

@app.get("/notifications")
async def fetch_notifications(_=Depends(verify_owner)):
    return {"notifications": await db.get_notifications(str(DB_PATH))}

@app.post("/clear")
async def reset(_=Depends(verify_owner)):
    clear_session_id()
    return {"status": "Session cleared"}