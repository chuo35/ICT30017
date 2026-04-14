import base64
import io
import os
import time
import pyautogui
from PIL import Image, ImageDraw
from pathlib import Path
from nanoclaw.config import DATA_DIR

# Safety settings: move mouse to corner to abort
pyautogui.FAILSAFE = True

class PerceptionModule:
    def __init__(self):
        self.screenshot_dir = DATA_DIR / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.screen_width, self.screen_height = pyautogui.size()

    def capture_screen(self, label="current_state", add_grid=False):
        """
        Captures the screen and returns a base64 encoded image.
        Optionally adds a coordinate grid to help the VLM pinpoint elements.
        """
        screenshot = pyautogui.screenshot()
        
        if add_grid:
            screenshot = self._draw_grid(screenshot)
            
        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # Save locally for the web UI/Log review
        filename = f"{label}_{int(time.time())}.png"
        screenshot.save(self.screenshot_dir / filename)
        
        return img_str, str(self.screenshot_dir / filename)

    def _draw_grid(self, img):
        """Adds a visual grid to the image to improve VLM spatial accuracy."""
        draw = ImageDraw.Draw(img)
        width, height = img.size
        # Draw 10x10 grid
        for x in range(0, width, width // 10):
            draw.line([(x, 0), (x, height)], fill="red", width=1)
        for y in range(0, height, height // 10):
            draw.line([(0, y), (width, y)], fill="red", width=1)
        return img

    # --- Hands: Execution Tools ---

    def click_at(self, x_percent: float, y_percent: float, clicks=1):
        """Clicks at a percentage-based coordinate (0-100) to remain resolution-independent."""
        x = int((x_percent / 100) * self.screen_width)
        y = int((y_percent / 100) * self.screen_height)
        pyautogui.click(x, y, clicks=clicks, interval=0.25)
        return f"Clicked at ({x}, {y})"

    def type_text(self, text: str, press_enter=True):
        """Types text into the active element."""
        pyautogui.write(text, interval=0.05)
        if press_enter:
            pyautogui.press('enter')
        return f"Typed: {text}"

    def press_key(self, key: str):
        """Presses a specific keyboard key (e.g., 'esc', 'tab', 'f5')."""
        pyautogui.press(key)
        return f"Pressed key: {key}"

    # --- Reflection: The Verification Step ---

    def verify_state(self, expected_description: str):
        """
        A 'Reflection' hook. Captures a new screenshot after an action 
        and allows the VLM to compare the current state against the SOP.
        """
        img_b64, file_path = self.capture_screen(label="reflection")
        return {
            "status": "success",
            "image_data": img_b64,
            "path": file_path,
            "instruction": f"Compare this screen to the SOP goal: {expected_description}"
        }

# Global instance
perception = PerceptionModule()