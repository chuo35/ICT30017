import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Required
OWNER_ID = os.environ["OWNER_ID"]  # This will act as your Web API Key
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Optional
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Ape")
SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACE_DIR = BASE_DIR / "workspace"
STORE_DIR = BASE_DIR / "store"
DATA_DIR = BASE_DIR / "data"
DB_PATH = STORE_DIR / "nanoclaw.db"
STATE_FILE = DATA_DIR / "state.json"

def get_chat_workspace(chat_id: int) -> Path:
    return WORKSPACE_DIR