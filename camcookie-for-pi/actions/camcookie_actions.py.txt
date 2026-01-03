import json
import os
import queue
import threading
import time

import pyautogui
import pyttsx3
import tkinter as tk
from tkinter import ttk

from vosk import Model, KaldiRecognizer
import pyaudio

# ---------- Paths and config ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_JSON = os.path.join(BASE_DIR, "actions.json")
VOSK_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-model-small-en-us-0.15")

# ---------- Text-to-speech ----------

tts_engine = pyttsx3.init()

def speak(text: str):
    print(f"[SAY] {text}")
    tts_engine.say(text)
    tts_engine.runAndWait()

# ---------- Load actions from JSON ----------

class ActionDefinition:
    def __init__(self, name, triggers, action, params=None):
        self.name = name
        self.triggers = [t.lower() for t in triggers]
        self.action = action
        self.params = params or {}

def load_actions():
    with open(ACTIONS_JSON, "r") as f:
        data = json.load(f)

    actions = []
    for cmd in data.get("commands", []):
        actions.append(
            ActionDefinition(
                name=cmd.get("name"),
                triggers=cmd.get("triggers", []),
                action=cmd.get("action"),
                params=cmd.get("params", {})
            )
        )
    return actions

actions = load_actions()

def find_matching_action(text: str):
    text = text.lower()
    for action_def in actions:
        for trigger in action_def.triggers:
            if trigger in text:
                return action_def
    return None

# ---------- System actions (hands of Camcookie) ----------

def open_chromium():
    speak("Opening Chromium.")
    # If chromium-browser is named differently, adjust here
    os.system("chromium-browser &")

def go_to_url(url: str):
    speak(f"Going to {url}.")
    time.sleep(2)  # give the browser time to open
    pyautogui.hotkey("ctrl", "l")
    pyautogui.typewrite(url + "\n", interval=0.05)

def move_mouse_center():
    speak("Moving mouse to the center.")
    screen_width, screen_height = pyautogui.size()
    pyautogui.moveTo(screen_width // 2, screen_height // 2, duration=0.5)

def say_text(text: str):
    speak(text)

# Map action names (from JSON) to Python functions
ACTION_MAP = {
    "open_chromium": open_chromium,
    "go_to_url": go_to_url,
    "move_mouse_center": move_mouse_center,
    "say_text": say_text,
}

def execute_action(action_def: ActionDefinition):
    func = ACTION_MAP.get(action_def.action)
    if not func:
        speak(f"I don't know how to perform action {action_def.action}.")
        return

    params = action_def.params or {}
    try:
        func(**params)
    except TypeError:
        # If params don't match, try calling without them
        func()

# ---------- Vosk STT (ears of Camcookie) ----------

if not os.path.exists(VOSK_MODEL_PATH):
    raise RuntimeError(f"Vosk model not found at {VOSK_MODEL_PATH}. Download and unzip it first.")

model = Model(VOSK_MODEL_PATH)

# We'll use a background thread and queue for audio
recognizer_queue = queue.Queue()

def stt_worker():
    while True:
        task = recognizer_queue.get()
        if task is None:
            break  # allow clean exit

        # Single utterance recognition
        result_text = recognize_once_vosk()
        task["callback"](result_text)

def recognize_once_vosk() -> str:
    recognizer = KaldiRecognizer(model, 16000)
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16,
                     channels=1,
                     rate=16000,
                     input=True,
                     frames_per_buffer=8000)
    stream.start_stream()

    print("[LISTEN] Listening...")
    speak("Listening.")

    # Collect ~3 seconds of audio
    start_time = time.time()
    while time.time() - start_time < 3.0:
        data = stream.read(4000, exception_on_overflow=False)
        if recognizer.AcceptWaveform(data):
            break

    stream.stop_stream()
    stream.close()
    pa.terminate()

    final = recognizer.FinalResult()
    # final is a JSON string like {"text": "open browser"}
    try:
        import json as _json
        parsed = _json.loads(final)
        text = parsed.get("text", "")
    except Exception:
        text = ""

    print(f"[HEARD] {text}")
    return text

stt_thread = threading.Thread(target=stt_worker, daemon=True)
stt_thread.start()

# ---------- GUI (blue glow) ----------

root = tk.Tk()
root.title("Camcookie Actions")

# Outer frame = blue glow border
root.configure(bg="#001a33")  # dark blue

outer_frame = tk.Frame(root, bg="#3388ff", padx=10, pady=10)
outer_frame.pack(fill="both", expand=True)

inner_frame = tk.Frame(outer_frame, bg="#f0f6ff", padx=20, pady=20)
inner_frame.pack(fill="both", expand=True)

title_label = tk.Label(inner_frame,
                       text="Camcookie Actions",
                       font=("Arial", 18, "bold"),
                       bg="#f0f6ff",
                       fg="#003366")
title_label.pack(pady=(0, 10))

status_label = tk.Label(inner_frame,
                        text="Idle",
                        font=("Arial", 10),
                        bg="#f0f6ff")
status_label.pack()

heard_label = tk.Label(inner_frame,
                       text="Heard: (nothing yet)",
                       font=("Arial", 10),
                       bg="#f0f6ff",
                       wraplength=400,
                       justify="left")
heard_label.pack(pady=(10, 10))

def on_stt_result(text: str):
    if not text:
        status_label.config(text="Didn't catch that.")
        heard_label.config(text="Heard: (could not understand)")
        speak("Sorry, I did not catch that.")
        return

    heard_label.config(text=f"Heard: {text}")
    status_label.config(text="Matching command...")

    action_def = find_matching_action(text)
    if action_def:
        status_label.config(text=f"Running: {action_def.name}")
        execute_action(action_def)
        status_label.config(text="Idle")
    else:
        status_label.config(text="No matching command.")
        speak("I did not understand that command.")

def listen_button_pressed():
    status_label.config(text="Listening...")
    root.update_idletasks()
    recognizer_queue.put({"callback": on_stt_result})

style = ttk.Style()
style.configure("Camcookie.TButton",
                font=("Arial", 12),
                padding=10)

listen_button = ttk.Button(inner_frame,
                           text="🎙 Listen",
                           style="Camcookie.TButton",
                           command=listen_button_pressed)
listen_button.pack(pady=(10, 0))

def on_close():
    recognizer_queue.put(None)
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

root.geometry("500x260")
root.mainloop()