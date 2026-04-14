import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, create_sdk_mcp_server, query, tool
from croniter import croniter
from nanoclaw import db
from nanoclaw.config import ANTHROPIC_API_KEY, DATA_DIR, STATE_FILE, WORKSPACE_DIR
from nanoclaw.perception import perception

_agent_lock = asyncio.Lock()

def _create_tools(db_path: str, notify_state: dict[str, bool] | None = None) -> list:
    @tool("send_message", "Notify the user UI", {"text": str})
    async def send_message(args: dict[str, Any]) -> dict[str, Any]:
        await db.add_notification(db_path, args["text"])
        if notify_state: notify_state["sent"] = True
        return {"content": [{"type": "text", "text": "Notification sent to UI."}]}

    @tool("schedule_task", "Schedule a task", {"prompt": str, "schedule_type": str, "schedule_value": str})
    async def schedule_task(args: dict[str, Any]) -> dict[str, Any]:
        stype, svalue = args["schedule_type"], args["schedule_value"]
        now = datetime.now(timezone.utc)
        try:
            if stype == "cron":
                next_run = croniter(svalue, now).get_next(datetime).isoformat()
            elif stype == "interval":
                next_run = (now + timedelta(milliseconds=int(svalue))).isoformat()
            else:
                next_run = svalue
            task_id = await db.create_task(db_path, args["prompt"], stype, svalue, next_run)
            return {"content": [{"type": "text", "text": f"Task {task_id} scheduled for {next_run}"}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": str(e)}], "is_error": True}

    # --- New Perception & GUI Tools (The "Hands" and "Eyes") ---

    @tool("gui_capture", "Capture the current screen state to see the GUI", {"use_grid": bool})
    async def gui_capture(args: dict[str, Any]) -> dict[str, Any]:
        img_b64, file_path = perception.capture_screen(label="observation", add_grid=args.get("use_grid", True))
        return {
            "content": [
                {"type": "text", "text": f"Screenshot captured at {file_path}. Use this to find coordinates."},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}}
            ]
        }

    @tool("gui_action", "Perform a mouse click or type text", {"action_type": str, "x": float, "y": float, "text": str, "reflection_goal": str})
    async def gui_action(args: dict[str, Any]) -> dict[str, Any]:
        """
        Executes a GUI action followed by a mandatory reflection verification.
        action_type: 'click', 'type', 'double_click'
        reflection_goal: Description of what should appear on screen after the action.
        """
        results = []
        
        # 1. Execution
        if args["action_type"] == "click":
            results.append(perception.click_at(args["x"], args["y"]))
        elif args["action_type"] == "double_click":
            results.append(perception.click_at(args["x"], args["y"], clicks=2))
        elif args["action_type"] == "type":
            results.append(perception.type_text(args["text"]))

        # 2. Mandatory Reflection (The Handrail)
        time.sleep(1) # Wait for UI to update
        verification = perception.verify_state(args["reflection_goal"])
        
        return {
            "content": [
                {"type": "text", "text": f"Action performed: {results}. Verify against goal: {args['reflection_goal']}"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": verification['image_data']}}
            ]
        }

    return [send_message, schedule_task, gui_capture, gui_action]

async def run_agent(prompt: str, db_path: str) -> str:
    async with _agent_lock:
        tools = _create_tools(db_path)
        mcp_server = create_sdk_mcp_server(name="nanoclaw", tools=tools)
        session_id = json.loads(STATE_FILE.read_text()).get("session_id") if STATE_FILE.exists() else None

        # Added new GUI tools to the allowed list
        options = ClaudeAgentOptions(
            cwd=str(WORKSPACE_DIR),
            allowed_tools=[
                "Bash", "Read", "Write", "Edit", "WebSearch", 
                "mcp__nanoclaw__send_message", 
                "mcp__nanoclaw__schedule_task",
                "mcp__nanoclaw__gui_capture",
                "mcp__nanoclaw__gui_action"
            ],
            mcp_servers={"nanoclaw": mcp_server},
            env={"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
            resume=session_id
        )

        # System Prompt Enforcement (The "Deterministic" Instruction)
        system_instructions = (
            "You are a deterministic agentic assistant. IMPORTANT:\n"
            "1. Before performing ANY GUI action, you MUST Read the 'conversations/' directory to see if a verified SOP exists.\n"
            "2. You MUST use gui_capture to see the screen before clicking.\n"
            "3. Every gui_action MUST include a reflection_goal to verify the outcome."
        )

        resp = []
        # Pass instructions into the query
        async for msg in query(prompt=[{"role": "user", "content": f"{system_instructions}\n\nUser Task: {prompt}"}], options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock): resp.append(block.text)
            elif isinstance(msg, ResultMessage):
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text(json.dumps({"session_id": msg.session_id}))
        
        return "".join(resp) or "Task completed."

def clear_session_id():
    if STATE_FILE.exists(): STATE_FILE.unlink()