
import ctypes
import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

import pyautogui
import pyperclip
import speech_recognition as sr


# =========================================================
# MH2 PC ASSISTANT — ONLINE VOICE
# Windows | Bengali + English | Allowlisted commands only
# =========================================================

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15

COMMANDS = {
    # Applications
    "open notepad": ("app", "notepad"),
    "start notepad": ("app", "notepad"),
    "নোটপ্যাড খোলো": ("app", "notepad"),
    "নোটপ্যাড চালু করো": ("app", "notepad"),

    "open calculator": ("app", "calc"),
    "ক্যালকুলেটর খোলো": ("app", "calc"),

    "open word": ("app", "winword"),
    "open ms word": ("app", "winword"),
    "ms word": ("app", "winword"),
    "microsoft word": ("app", "winword"),
    "এমএস ওয়ার্ড": ("app", "winword"),
    "ওয়ার্ড খোলো": ("app", "winword"),

    "open excel": ("app", "excel"),
    "open ms excel": ("app", "excel"),
    "ms excel": ("app", "excel"),
    "open xl": ("app", "excel"),
    "open x l": ("app", "excel"),
    "ওপেন এক্সেল": ("app", "excel"),
    "এক্সেল খোলো": ("app", "excel"),
    "ওপেন এক্সএল": ("app", "excel"),
    "এক্সেল চালু করো": ("app", "excel"),

    # Websites
    "open chrome": ("chrome_site", "https://www.google.com/"),
    "ক্রোম খোলো": ("chrome_site", "https://www.google.com/"),

    "open youtube": ("site", "https://www.youtube.com/"),
    "ইউটিউব খোলো": ("site", "https://www.youtube.com/"),

    "open google": ("site", "https://www.google.com/"),
    "গুগল খোলো": ("site", "https://www.google.com/"),

    "open gmail": ("site", "https://mail.google.com/"),
    "জিমেইল খোলো": ("site", "https://mail.google.com/"),

    "open whatsapp": ("chrome_site", "https://web.whatsapp.com/"),
    "open whatsapp web": ("chrome_site", "https://web.whatsapp.com/"),
    "whatsapp on chrome": ("chrome_site", "https://web.whatsapp.com/"),
    "হোয়াটসঅ্যাপ খোলো": ("chrome_site", "https://web.whatsapp.com/"),
    "হোয়াটসঅ্যাপ চালু করো": ("chrome_site", "https://web.whatsapp.com/"),

    # Close applications/windows
    "close notepad": ("close_app", "notepad"),
    "ক্লোজ নোটপ্যাড": ("close_app", "notepad"),
    "নোটপ্যাড বন্ধ করো": ("close_app", "notepad"),

    "close this window": ("hotkey", ("alt", "f4")),
    "close window": ("hotkey", ("alt", "f4")),
    "এই উইন্ডো বন্ধ করো": ("hotkey", ("alt", "f4")),
    "উইন্ডো বন্ধ করো": ("hotkey", ("alt", "f4")),

    # Show desktop rather than forcibly closing every app.
    "close all windows": ("show_desktop", ""),
    "show desktop": ("show_desktop", ""),
    "সব উইন্ডো বন্ধ করো": ("show_desktop", ""),
    "ডেস্কটপ দেখাও": ("show_desktop", ""),

    "minimize window": ("hotkey", ("win", "down")),
    "মিনিমাইজ করো": ("hotkey", ("win", "down")),
    "maximize window": ("hotkey", ("win", "up")),
    "ম্যাক্সিমাইজ করো": ("hotkey", ("win", "up")),

    # Switch apps/windows
    "switch window": ("hotkey", ("alt", "tab")),
    "switch app": ("hotkey", ("alt", "tab")),
    "next window": ("hotkey", ("alt", "tab")),
    "অ্যাপ চেঞ্জ করো": ("hotkey", ("alt", "tab")),
    "উইন্ডো চেঞ্জ করো": ("hotkey", ("alt", "tab")),

    # Browser tabs
    "new tab": ("hotkey", ("ctrl", "t")),
    "open new tab": ("hotkey", ("ctrl", "t")),
    "নতুন ট্যাব খোলো": ("hotkey", ("ctrl", "t")),

    "close tab": ("hotkey", ("ctrl", "w")),
    "ট্যাব বন্ধ করো": ("hotkey", ("ctrl", "w")),

    "next tab": ("hotkey", ("ctrl", "tab")),
    "পরের ট্যাবে যাও": ("hotkey", ("ctrl", "tab")),

    "previous tab": ("hotkey", ("ctrl", "shift", "tab")),
    "আগের ট্যাবে যাও": ("hotkey", ("ctrl", "shift", "tab")),

    # Mouse movement: move in 100-pixel increments
    "move mouse left": ("mouse", (-100, 0)),
    "move mouse right": ("mouse", (100, 0)),
    "move mouse up": ("mouse", (0, -100)),
    "move mouse down": ("mouse", (0, 100)),
    "মাউস বামে নাও": ("mouse", (-100, 0)),
    "মাউস ডানে নাও": ("mouse", (100, 0)),
    "মাউস উপরে নাও": ("mouse", (0, -100)),
    "মাউস নিচে নাও": ("mouse", (0, 100)),

    "mouse click": ("click", "left"),
    "left click": ("click", "left"),
    "মাউস ক্লিক": ("click", "left"),
    "right click": ("click", "right"),
    "রাইট ক্লিক": ("click", "right"),

    "scroll up": ("scroll", 4),
    "scroll down": ("scroll", -4),
    "উপরে স্ক্রল করো": ("scroll", 4),
    "নিচে স্ক্রল করো": ("scroll", -4),

    # WhatsApp message workflow
    "dictate message": ("dictate", ""),
    "type message": ("dictate", ""),
    "write message": ("dictate", ""),
    "মেসেজ লেখো": ("dictate", ""),
    "মেসেজ টাইপ করো": ("dictate", ""),

    "send message": ("send", ""),
    "send whatsapp message": ("send", ""),
    "মেসেজ পাঠাও": ("send", ""),
    "মেসেজ সেন্ড করো": ("send", ""),

    # Power commands
    "shut down pc": ("power", "shutdown"),
    "shutdown pc": ("power", "shutdown"),
    "কম্পিউটার বন্ধ করো": ("power", "shutdown"),
    "পিসি বন্ধ করো": ("power", "shutdown"),

    "restart pc": ("power", "restart"),
    "restart computer": ("power", "restart"),
    "কম্পিউটার রিস্টার্ট করো": ("power", "restart"),
    "পিসি রিস্টার্ট করো": ("power", "restart"),

    "sleep pc": ("power", "sleep"),
    "put pc to sleep": ("power", "sleep"),
    "কম্পিউটার স্লিপ করো": ("power", "sleep"),
    "পিসি স্লিপ করো": ("power", "sleep"),

    "cancel shutdown": ("cancel_shutdown", ""),
    "shutdown cancel করো": ("cancel_shutdown", ""),

    # Voice control
    "stop listening": ("stop", ""),
    "ভয়েস বন্ধ করো": ("stop", ""),
    "শোনা বন্ধ করো": ("stop", ""),
}


def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"[.!?,;:'\"।]+", "", text)
    return re.sub(r"\s+", " ", text)


def find_chrome():
    """Find common Chrome installation paths on Windows."""
    found = shutil.which("chrome.exe")
    if found:
        return found

    locations = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",

        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",

        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google/Chrome/Application/chrome.exe",
    ]

    for path in locations:
        if path.is_file():
            return str(path)

    return None


def find_office_app(app_name):
    """Find Word/Excel in common Microsoft Office installation folders."""
    found = shutil.which(app_name + ".exe")
    if found:
        return found

    folders = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft Office/root/Office16",

        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft Office/root/Office16",

        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft Office/Office16",

        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft Office/Office16",
    ]

    for folder in folders:
        candidate = folder / (app_name + ".exe")
        if candidate.is_file():
            return str(candidate)

    return None


def confirm_action(prompt, expected):
    """Require explicit keyboard confirmation for sensitive actions."""
    print("\nCONFIRMATION REQUIRED")
    print(prompt)
    answer = input(f"Type {expected} to confirm: ").strip()
    return answer == expected


def execute_action(action):
    kind, value = action

    try:
        if kind == "stop":
            print("Voice mode stopped.")
            return True

        if kind == "app":
            if value in ("winword", "excel"):
                executable = find_office_app(value)
                if not executable:
                    print(
                        f"Could not find {value}.exe. "
                        "Check whether Microsoft Office is installed."
                    )
                    return False
            else:
                executable = shutil.which(value + ".exe") or (value + ".exe")

            subprocess.Popen([executable], shell=False)
            print(f"Application launch requested: {value}")
            return False

        if kind == "site":
            webbrowser.open(value)
            print("Website opened in the default browser.")
            return False

        if kind == "chrome_site":
            chrome = find_chrome()
            if chrome:
                subprocess.Popen([chrome, value], shell=False)
                print("Opened in Chrome.")
            else:
                webbrowser.open(value)
                print("Chrome not found; opened in the default browser.")
            return False

        if kind == "close_app":
            if value == "notepad":
                result = subprocess.run(
                    ["taskkill", "/IM", "notepad.exe", "/T"],
                    shell=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print("Notepad close command sent.")
                else:
                    print("Notepad may not be running.")
            return False

        if kind == "hotkey":
            pyautogui.hotkey(*value)
            print("Keyboard shortcut executed.")
            return False

        if kind == "show_desktop":
            pyautogui.hotkey("win", "d")
            print("Desktop shown. Open applications remain running.")
            return False

        if kind == "mouse":
            dx, dy = value
            pyautogui.moveRel(dx, dy, duration=0.2)
            print("Mouse moved.")
            return False

        if kind == "click":
            pyautogui.click(button=value)
            print(f"{value.capitalize()} click executed.")
            return False

        if kind == "scroll":
            pyautogui.scroll(value)
            print("Scrolled.")
            return False

        if kind == "dictate":
            print(
                "Dictation mode is available in /voice mode. "
                "Say your message in the next turn."
            )
            return False

        if kind == "send":
            print(
                "Make sure the correct WhatsApp chat and message box "
                "are active before sending."
            )
            if confirm_action(
                "This will press Enter in the currently focused window.",
                "SEND",
            ):
                pyautogui.press("enter")
                print("Enter pressed.")
            else:
                print("Sending cancelled.")
            return False

        if kind == "power":
            prompts = {
                "shutdown": (
                    "The PC will shut down after a 30-second countdown.",
                    ["shutdown", "/s", "/t", "30"],
                ),
                "restart": (
                    "The PC will restart after a 30-second countdown.",
                    ["shutdown", "/r", "/t", "30"],
                ),
                "sleep": (
                    "The PC will enter Windows sleep/suspend mode.",
                    None,
                ),
            }

            prompt, command = prompts[value]
            if not confirm_action(prompt, "YES"):
                print("Power action cancelled.")
                return False

            if value == "sleep":
                ctypes.windll.powrprof.SetSuspendState(False, True, False)
            else:
                subprocess.run(command, shell=False, check=False)
                print("Power command sent. Use 'cancel shutdown' to abort a countdown.")
            return False

        if kind == "cancel_shutdown":
            subprocess.run(
                ["shutdown", "/a"],
                shell=False,
                capture_output=True,
                text=True,
            )
            print("Shutdown/restart countdown cancellation requested.")
            return False

    except (OSError, RuntimeError, pyautogui.FailSafeException) as error:
        print("Action failed:", error)

    return False


def execute(command):
    action = COMMANDS.get(normalize(command))

    if action is None:
        print("Command not matched exactly. No action taken.")
        return False

    return execute_action(action)


def listen_once(recognizer, microphone):
    with microphone as source:
        print("\nListening...")
        return recognizer.listen(
            source,
            timeout=6,
            phrase_time_limit=10,
        )


def recognize_text(recognizer, audio):
    """Try Bengali first, then English."""
    for language in ("bn-BD", "en-US"):
        try:
            text = recognizer.recognize_google(audio, language=language)
            print(f"Heard [{language}]: {text}")
            return text
        except sr.UnknownValueError:
            continue
        except sr.RequestError:
            raise

    return None


def paste_dictated_message(recognizer, microphone):
    print("Dictation: say the message you want typed.")
    print("The message will be typed but NOT sent automatically.")

    try:
        audio = listen_once(recognizer, microphone)
        text = recognize_text(recognizer, audio)

        if not text:
            print("Speech not understood. Nothing typed.")
            return

        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        print("Message typed into the focused text field.")
        print("Review it, then say 'send message' if you want to send it.")

    except sr.WaitTimeoutError:
        print("No speech detected. Dictation cancelled.")
    except sr.RequestError as error:
        print("Online recognition error:", error)
    except (OSError, RuntimeError, pyautogui.FailSafeException) as error:
        print("Dictation failed:", error)


def voice_mode():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.7

    try:
        microphone = sr.Microphone()
    except Exception as error:
        print("Microphone error:", error)
        return

    print("\nMH2 Online Voice Mode — Bengali + English")
    print("Internet is required for speech recognition.")
    print("Say 'stop listening' to exit.")
    print("For WhatsApp: open a chat, focus its message box,")
    print("say 'dictate message', speak the text, review it,")
    print("then say 'send message' to request sending.")
    print("Power actions require typing YES in the terminal.")

    with microphone as source:
        print("Adjusting microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    while True:
        try:
            audio = listen_once(recognizer, microphone)

            # A separate utterance is used for message dictation.
            # It is pasted only; it is never automatically sent.
            if dictation_requested(recognizer, audio):
                paste_dictated_message(recognizer, microphone)
                continue

            # Try both recognizers on the same audio.
            matches = []

            for language in ("bn-BD", "en-US"):
                try:
                    text = recognizer.recognize_google(
                        audio,
                        language=language,
                    )
                    print(f"Heard [{language}]: {text}")

                    action = COMMANDS.get(normalize(text))
                    if action is not None:
                        matches.append(action)

                except sr.UnknownValueError:
                    pass

            unique_matches = set(matches)

            if len(unique_matches) == 1:
                action = next(iter(unique_matches))

                if action[0] == "dictate":
                    paste_dictated_message(recognizer, microphone)
                    continue

                if execute_action(action):
                    return

            elif len(unique_matches) > 1:
                print("Ambiguous result. No action taken.")
            else:
                print("Command not matched exactly. No action taken.")

        except sr.WaitTimeoutError:
            print("No speech detected. Try again.")
        except sr.RequestError as error:
            print("Online recognition error:", error)
            print("Check your internet connection.")
            return
        except KeyboardInterrupt:
            print("\nVoice mode stopped.")
            return


def dictation_requested(recognizer, audio):
    """Detect only exact dictation-start commands."""
    recognized_actions = []

    for language in ("bn-BD", "en-US"):
        try:
            text = recognizer.recognize_google(audio, language=language)
            print(f"Heard [{language}]: {text}")
            action = COMMANDS.get(normalize(text))
            if action is not None:
                recognized_actions.append(action)
        except sr.UnknownValueError:
            pass
        except sr.RequestError:
            raise

    unique = set(recognized_actions)
    return len(unique) == 1 and next(iter(unique))[0] == "dictate"


def main():
    print("=" * 58)
    print("MH2 PC ASSISTANT — ONLINE VOICE")
    print("No Firebase or database connection.")
    print("Type /voice, /help, or /quit.")
    print("=" * 58)

    while True:
        try:
            command = input("MH2> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if command.lower() == "/quit":
            break

        if command.lower() == "/help":
            print("""
APPLICATIONS:
  Open Notepad, Open Calculator, Open Word, Open Excel

BROWSER:
  Open Chrome, Open YouTube, Open Google, Open Gmail
  Open WhatsApp, New Tab, Close Tab, Next Tab, Previous Tab

WINDOWS:
  Close This Window, Switch Window, Minimize Window
  Maximize Window, Close All Windows (shows desktop only)

MOUSE:
  Move Mouse Left/Right/Up/Down, Mouse Click, Right Click
  Scroll Up, Scroll Down

WHATSAPP:
  Open WhatsApp
  Select a chat and click its message box.
  Say 'dictate message', then speak your message.
  Review the typed message and say 'send message'.
  Sending requires typing SEND in the terminal.

POWER:
  Shut Down PC, Restart PC, Sleep PC
  Power actions require typing YES in the terminal.
  Cancel Shutdown cancels a pending shutdown/restart countdown.

VOICE:
  /voice
  Stop Listening
""")
            continue

        if command.lower() == "/voice":
            voice_mode()
            continue

        if command:
            execute(command)

    print("Goodbye!")


if __name__ == "__main__":
    main()
