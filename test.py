import sys
import os
import time
import json
import cv2
import pyautogui
import numpy as np
from pynput import mouse, keyboard
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QHBoxLayout, QPushButton, QFrame, QTextBrowser, QLineEdit
)
from PySide6.QtCore import Qt, QPoint, QTimer, QThread, Signal
from PySide6.QtGui import QCursor

# Ensure the directories exist
os.makedirs("tasks", exist_ok=True)
os.makedirs("record", exist_ok=True)

# ---------------- RECORDER THREADS ----------------
class VideoRecorderThread(QThread):
    def __init__(self):
        super().__init__()
        self.recording = True
        self.temp_filename = "temp_recording.avi"
        self.excluded_rect = None # Add this

    def exclude_region(self, coords):
        self.excluded_rect = coords # Tuple: (x, y, w, h)

    def run(self):
        resolution = pyautogui.size()  
        codec = cv2.VideoWriter_fourcc(*"XVID")  
        fps = 20.0  
        out = cv2.VideoWriter(self.temp_filename, codec, fps, resolution)

        while self.recording:
            img = pyautogui.screenshot()  
            frame = np.array(img)  
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)  

            # MASK OUT THE UI
            if self.excluded_rect:
                x, y, w, h = self.excluded_rect
                max_y, max_x, _ = frame.shape
                
                # Ensure coordinates stay within screen bounds to prevent crashes
                x1, y1 = max(0, x), max(0, y)
                x2, y2 = min(max_x, x + w), min(max_y, y + h)
                
                if x1 < x2 and y1 < y2:
                    frame[y1:y2, x1:x2] = 0 # 0 makes the area black

            out.write(frame)  
            time.sleep(1 / fps) 
            
        out.release()

    def stop(self):
        self.recording = False

class ActionRecorderThread(QThread):
    """Handles pynput mouse and keyboard tracking in the background."""
    def exclude_region(self, coords):
        self.excluded_rect = coords # Tuple: (x, y, w, h)

    def on_click(self, x, y, button, pressed):
        if self.recording and pressed:
            # Check if click is inside the UI coordinates
            if self.excluded_rect:
                ex_x, ex_y, ex_w, ex_h = self.excluded_rect
                if ex_x <= x <= (ex_x + ex_w) and ex_y <= y <= (ex_y + ex_h):
                    return # Ignore this click!
                
    def __init__(self):
        super().__init__()
        self.actions = []
        self.recording = True
        self.typed_text = ""
        self.last_time = time.time()
        self.last_click_time = 0
        self.last_click_pos = (None, None)
        self.temp_filename = "temp_recording.json"
        self.excluded_rect = None

    def exclude_region(self, rect):
        self.excluded_rect = rect

    def add_action(self, action):
        current_time = time.time()
        delay = current_time - self.last_time
        self.last_time = current_time
        action["delay"] = delay
        self.actions.append(action)

    def flush_text(self):
        if self.typed_text:
            self.add_action({"action": "type", "text": self.typed_text})
            self.typed_text = ""

    def on_click(self, x, y, button, pressed):
        if self.recording and pressed:
            if self.excluded_rect is not None and self.excluded_rect.contains(x, y):
                return

            current_time = time.time()
            
            # Detect double click
            if (x, y) == self.last_click_pos and (current_time - self.last_click_time) < 0.5:
                self.add_action({"action": "double_click", "x": x, "y": y})
                self.last_click_pos = (None, None)
                self.last_click_time = 0
                return

            # Normal click
            self.add_action({"action": "click", "x": x, "y": y})
            self.last_click_pos = (x, y)
            self.last_click_time = current_time

    def on_press(self, key):
        try:
            self.typed_text += key.char
        except AttributeError:
            self.flush_text()
            self.add_action({"action": "press", "key": str(key)})

    def on_release(self, key):
        if not self.recording:
            return False  # Stop listener

    def run(self):
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.keyboard_listener.join()
        self.mouse_listener.stop()

        # Save temporary task safely
        with open(self.temp_filename, "w") as f:
            json.dump(self.actions, f, indent=4)

    def stop(self):
        self.recording = False
        self.flush_text()
        # Press a dummy key to release the listener safely
        keyboard.Controller().press(keyboard.Key.shift)
        keyboard.Controller().release(keyboard.Key.shift)


# ---------------- AI WORKER ----------------
class AIWorker(QThread):
    response_ready = Signal(str)

    def __init__(self, user_text):
        super().__init__()
        self.user_text = user_text

    def run(self):
        time.sleep(1.5)
        ai_response = f"I've processed your request regarding: '{self.user_text}'."
        self.response_ready.emit(ai_response)


# ---------------- MAIN WIDGET ----------------
class RecordingBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.dragging = False
        self.drag_position = QPoint()
        self.mode = "Manual Mode"
        self.is_locked = False
        
        self.is_recording = False
        self.waiting_for_task_name = False

        self.lock_timer = QTimer()
        self.lock_timer.setSingleShot(True)
        self.lock_timer.timeout.connect(self.pin_chat)

        self.init_ui()

    def init_ui(self):
        self.setFixedWidth(350)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(10)

        # -------- BAR --------
        self.bar_container = QFrame()
        self.bar_container.setFixedHeight(50)
        self.bar_container.setStyleSheet("""
            background-color: #f0f4f9;
            border-radius: 25px;
            border: none; 
        """)

        bar_layout = QHBoxLayout(self.bar_container)
        bar_layout.setContentsMargins(20, 0, 15, 0)

        self.status_label = QLabel(self.mode)
        self.status_label.setStyleSheet("color: #1f1f1f; font-family: 'Segoe UI'; font-weight: 500;")

        # Add Record Button here
        self.record_btn = QPushButton("⏺")
        self.record_btn.setFixedSize(24, 24)
        self.record_btn.setStyleSheet("color: red; border: none; font-size: 18px;")
        self.record_btn.clicked.connect(self.toggle_recording)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton { background: none; border: none; color: #444746; font-size: 20px; font-weight: bold; }
            QPushButton:hover { background-color: rgba(0, 0, 0, 0.05); border-radius: 12px; }
        """)
        close_btn.clicked.connect(self.unpin_and_hide)

        bar_layout.addWidget(self.status_label)
        bar_layout.addStretch()
        bar_layout.addWidget(self.record_btn)
        bar_layout.addWidget(close_btn)

        # -------- CHAT BUBBLE --------
        self.chat_bubble_container = QFrame()
        self.chat_bubble_container.setStyleSheet("""
            background-color: #ffffff; border-radius: 20px; border: 1px solid #dce1e7;
        """)

        chat_layout = QVBoxLayout(self.chat_bubble_container)

        self.history = QTextBrowser()
        self.history.setFixedHeight(200)
        self.history.setStyleSheet("border: none; background: transparent;")
        self.history.setHtml("""
            <div style="font-family:Segoe UI; font-size:13px;">
                <b>System (NanoClaw):</b> System active.
            </div>
        """) 

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Talk to Agent...")
        self.input_field.setStyleSheet("""
            QLineEdit { background-color: #f0f4f9; border-radius: 15px; padding: 8px; border: 1px solid #dce1e7; }
        """)
        self.input_field.returnPressed.connect(self.handle_send_message)

        chat_layout.addWidget(self.history)
        chat_layout.addWidget(self.input_field)
        self.chat_bubble_container.hide()

        self.main_layout.addWidget(self.bar_container)
        self.main_layout.addWidget(self.chat_bubble_container)

    # ---------------- RECORDING LOGIC ----------------
    def toggle_recording(self):
        if not self.is_recording:
            # Start Recording
            self.is_recording = True
            self.record_btn.setText("⏹")
            self.set_mode("Recording...")
            
            self.video_thread = VideoRecorderThread()
            self.action_thread = ActionRecorderThread()
            self.action_thread.exclude_region(self.frameGeometry())
            
            self.video_thread.start()
            self.action_thread.start()
            
            self.history.append("<i style='color:red;'>System (NanoClaw): Recording started...</i>")
            self.pin_chat() # Keep chat open to see status
        else:
            # Stop Recording
            self.is_recording = False
            self.record_btn.setText("⏺")
            self.set_mode("Manual Mode")
            
            self.video_thread.stop()
            self.action_thread.stop()
            
            self.waiting_for_task_name = True
            self.history.append("<b>System (NanoClaw):</b> Recording stopped. Please enter a task name:")

    # ---------------- CHAT LOGIC ----------------
    def handle_send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.history.append(f"<b>You:</b> {text}")
        self.input_field.clear()
        
        # Intercept chat if waiting for task name
        if self.waiting_for_task_name:
            task_name = text.lower().replace(" ", "_")
            
            # Wait briefly for threads to finish saving temp files
            time.sleep(0.5)
            
            avi_dest = f"record/{task_name}.avi"
            json_dest = f"tasks/{task_name}.json"
            
            try:
                os.rename("temp_recording.avi", avi_dest)
                os.rename("temp_recording.json", json_dest)
                self.history.append(f"<i style='color:green;'>System (NanoClaw): Task saved as {task_name}.avi and {task_name}.json</i>")
            except Exception as e:
                self.history.append(f"<i style='color:red;'>System (NanoClaw): Error saving files - {str(e)}</i>")
                
            self.waiting_for_task_name = False
            return

        # Normal AI Chat Logic
        self.set_mode("AI Processing...")
        self.worker = AIWorker(text)
        self.worker.response_ready.connect(self.on_ai_response)
        self.worker.start()

    def on_ai_response(self, response):
        self.history.append(f"<b>AI:</b> {response}")
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())
        self.set_mode("Manual Mode")
        
    def update_exclusion_zone(self):
        """Sends the current window coordinates to the background threads."""
        if self.is_recording:
            rect = self.geometry()
            # Convert QRect to a standard Python tuple
            coords = (rect.x(), rect.y(), rect.width(), rect.height())
            
            self.action_thread.exclude_region(coords)
            self.video_thread.exclude_region(coords)

    def resizeEvent(self, event):
        """Triggered automatically when the UI grows or shrinks."""
        self.update_exclusion_zone()
        super().resizeEvent(event)

    def moveEvent(self, event):
        """Triggered automatically when the user drags the UI."""
        self.update_exclusion_zone()
        super().moveEvent(event)

    # ---------------- UTILITY & EVENTS ----------------
    def set_mode(self, mode):
        self.mode = mode
        self.status_label.setText(mode)

    def pin_chat(self):
        self.is_locked = True

    def unpin_and_hide(self):
        self.is_locked = False
        self.chat_bubble_container.hide()
        self.adjustSize()

    def enterEvent(self, event):
        self.chat_bubble_container.show()
        self.adjustSize()
        if not self.is_locked:
            self.lock_timer.start(2000)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.lock_timer.stop()
        QTimer.singleShot(100, self.check_mouse_outside)
        super().leaveEvent(event)

    def check_mouse_outside(self):
        if not self.is_locked and not self.geometry().contains(QCursor.pos()):
            self.unpin_and_hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)

    def mouseReleaseEvent(self, event):
        self.dragging = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bar = RecordingBar()
    bar.show()
    sys.exit(app.exec())