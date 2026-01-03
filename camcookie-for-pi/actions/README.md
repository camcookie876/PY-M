# 🍪 Camcookie Actions  
### Offline Voice Assistant for Raspberry Pi OS  
Camcookie Actions is a fully offline, privacy‑friendly voice assistant for Raspberry Pi OS.  
It uses **Vosk** for speech‑to‑text, **pyttsx3** for text‑to‑speech, and **PyAutoGUI** for real computer control — all without internet, accounts, or API keys.

Camcookie Actions can:

- Listen to your voice  
- Understand commands using a JSON rules file  
- Open apps  
- Move the mouse  
- Type text  
- Open websites  
- Speak responses  
- Show a GUI with a glowing Camcookie theme  

This project is designed to be simple, hackable, and fun.

---

## ⭐ Features
- **100% offline** (no cloud, no accounts)  
- **JSON‑based IF/THEN command system**  
- **Voice recognition using Vosk**  
- **Text‑to‑speech using pyttsx3**  
- **Mouse + keyboard automation**  
- **Blue‑glow Camcookie GUI**  
- **Easy to extend with your own commands**  

---

# 📦 Installation

## 1. Update your Raspberry Pi
```bash
sudo apt update && sudo apt full-upgrade -y
```

---

## 2. Install system dependencies
```bash
sudo apt install -y python3-full python3-venv python3-pip \
                 portaudio19-dev ffmpeg scrot unzip wget espeak-ng
```

These provide:
- Python environment tools  
- Audio input/output support  
- Screenshot support for PyAutoGUI  
- Offline TTS engine (espeak‑ng)  

---

## 3. Create the project folder
```bash
mkdir ~/camcookie-actions
cd ~/camcookie-actions
```

---

## 4. Create a Python virtual environment
```bash
python3 -m venv venv
```

---

## 5. Activate the environment
```bash
source venv/bin/activate
```

Your terminal should now show:

```
(venv) camcookie1@raspberrypi:~$
```

---

## 6. Install Python packages
```bash
pip install vosk pyttsx3 pyautogui speechrecognition pyaudio
```

---

## 7. Download the Vosk English model
```bash
mkdir models
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
cd ..
```

---

## 8. Create the command file (`actions.json`)
This file defines all voice commands.

```bash
nano actions.json
```

Paste:

```json
{
  "commands": [
    {
      "name": "open_browser",
      "triggers": ["open browser", "open chromium", "start browser"],
      "action": "open_chromium"
    },
    {
      "name": "go_to_youtube",
      "triggers": ["go to youtube", "open youtube", "youtube"],
      "action": "go_to_url",
      "params": {
        "url": "https://youtube.com"
      }
    },
    {
      "name": "go_to_google",
      "triggers": ["go to google", "open google", "google"],
      "action": "go_to_url",
      "params": {
        "url": "https://google.com"
      }
    },
    {
      "name": "move_mouse_center",
      "triggers": ["move mouse", "move the mouse"],
      "action": "move_mouse_center"
    },
    {
      "name": "say_hello",
      "triggers": ["say hello", "hello camcookie", "hi camcookie"],
      "action": "say_text",
      "params": {
        "text": "Hello, I am Camcookie Actions."
      }
    }
  ]
}
```

Save with **CTRL+O**, then **ENTER**, then **CTRL+X**.

---

## 9. Add the main program (`camcookie_actions.py`)
Create the file:

```bash
nano camcookie_actions.py
```
Paste the full Camcookie Actions code.

Code found at:
https://github.com/camcookie876/PY-M/tree/main/camcookie-for-pi/actions/camcookie_actions.py.txt

Save and exit.

---

# ▶️ Running Camcookie Actions

Activate the environment:

```bash
cd ~/camcookie-actions
source venv/bin/activate
```

Run the assistant:

```bash
python3 camcookie_actions.py
```

You will see:

- A glowing blue window  
- A “🎙 Listen” button  
- Voice recognition  
- JSON‑based commands  
- Real computer control  

---

# 🧩 Adding New Commands

Edit the JSON file:

```bash
nano actions.json
```

Add a new block:

```json
{
  "name": "open_file_manager",
  "triggers": ["open files", "open file manager", "show my files"],
  "action": "open_file_manager"
}
```

Then add the Python function in `camcookie_actions.py`:

```python
def open_file_manager():
    speak("Opening file manager.")
    os.system("pcmanfm &")
```

And register it:

```python
ACTION_MAP["open_file_manager"] = open_file_manager
```

Restart the app and the new command works instantly.

---

# 🎉 You're Ready to Use Camcookie Actions
You now have a real offline voice assistant running on Raspberry Pi OS.