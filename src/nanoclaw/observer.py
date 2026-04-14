import time
from pynput import mouse, keyboard
from nanoclaw.perception import perception
from pathlib import Path

class Observer:
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.steps = []
        self.output_path = Path(f"workspace/procedures/{task_name}.md")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def on_click(self, x, y, button, pressed):
        if pressed:
            # Calculate percentages for resolution independence
            x_pct = (x / perception.screen_width) * 100
            y_pct = (y / perception.screen_height) * 100
            
            print(f"Captured click at {x_pct:.2f}%, {y_pct:.2f}%")
            _, img_path = perception.capture_screen(label=f"step_{len(self.steps)}")
            
            self.steps.append({
                "action": "click",
                "x": round(x_pct, 2),
                "y": round(y_pct, 2),
                "image": img_path
            })

    def save_sop(self):
        content = f"# SOP: {self.task_name}\n\n"
        for i, step in enumerate(self.steps):
            content += f"## Step {i+1}\n- **Action**: {step['action']}\n- **Location**: {step['x']}%, {step['y']}%\n- **Screenshot**: {step['image']}\n\n"
        
        self.output_path.write_text(content)
        print(f"SOP saved to {self.output_path}")

# Usage: Run this, perform the task, then stop the script.
if __name__ == "__main__":
    obs = Observer("Setup_New_Server")
    print("Observer Mode Active. Perform your task. (Ctrl+C to save)")
    
    with mouse.Listener(on_click=obs.on_click) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            obs.save_sop()