#   I haven’t even started yet. 
import os

if os.name != "nt":
    raise SystemExit("MH2 WhatsApp call module runs on Windows only.")

import argparse
import array
import ctypes
import importlib
import json
import logging
import re
import string
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections import OrderedDict, deque
from ctypes import wintypes
from dataclasses import dataclass, fields
from enum import Enum

log = logging.getLogger("mh2_whatsapp_call")

NO_WINDOW = 0x08000000

ITEM_KINDS = {"ListItemControl", "DataItemControl", "TreeItemControl"}
BUTTON_KINDS = ("ButtonControl", "SplitButtonControl", "MenuItemControl")
SECTION_NAMES = {
    "chats", "contacts", "messages", "groups", "contacts in groups",
    "not in your contacts",
}

VOICE_RE = re.compile(r"^(?:start\s+)?(?:voice|audio)\s+call$", re.IGNORECASE)
CALL_MENU_RE = re.compile(r"^(?:call|start\s+call|call\s+options)$", re.IGNORECASE)
VOICE_ITEM_RE = re.compile(r"voice|audio", re.IGNORECASE)
END_RE = re.compile(r"^(?:end\s+call|hang\s*up|leave\s+call)\b", re.IGNORECASE)
TIMER_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
FAIL_RE = re.compile(
    r"^(?:busy|declined|no\s+answer|not\s+answered|unavailable|call\s+failed|"
    r"couldn.?t\s+connect)$",
    re.IGNORECASE
)

PUNCT_TABLE = str.maketrans({c: " " for c in string.punctuation + "\u0964\u0965\u2018\u2019\u201c\u201d\u2026"})

YES_WORDS = {
    "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "correct", "right",
    "confirm", "confirmed", "haan", "han", "ha",
    "\u09b9\u09cd\u09af\u09be\u0981", "\u09b9\u09cd\u09af\u09be", "\u09b9\u09be\u0981",
    "\u09b9\u09be", "\u099c\u09bf", "\u09a0\u09bf\u0995",
}

NO_WORDS = {
    "no", "nope", "nah", "not", "nothing", "done", "finish", "finished",
    "\u09a8\u09be", "\u09a8\u09be\u09b9", "\u09a8\u09c7\u0987", "\u09a5\u09be\u0995",
}

NO_PHRASES = (" that is all ", " that s all ", " no more ", " thats all ")

CANCEL_PHRASES = {
    "cancel", "cancel call", "cancel the call", "cancel action", "never mind",
    "nevermind", "stop call", "stop the call", "hang up", "end call",
    "end the call", "disconnect",
}

ORDINALS = {
    "1": 0, "one": 0, "first": 0,
    "2": 1, "two": 1, "second": 1,
    "3": 2, "three": 2, "third": 2,
    "4": 3, "four": 3, "fourth": 3,
    "5": 4, "five": 4, "fifth": 4,
}

IGNORED_TARGETS = {"me", "back", "it", "him", "her", "them", "us", "you"}

FILLER_RE = re.compile(r"^(?:(?:hey|ok|okay|please|kindly)\s+)+", re.IGNORECASE)

CALL_PATTERNS = (
    re.compile(
        r"^(?:(?:can|could|would|will)\s+you\s+)?(?:make\s+(?:a\s+)?)?"
        r"(?:(?:whats\s?app|voice)\s+)*call\s+(?:to\s+)?(?P<t>.+?)"
        r"(?:\s+(?:on|in|using|via|through)\s+whats\s?app)?$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:ring|phone)\s+(?P<t>.+?)\s+on\s+whats\s?app$",
        re.IGNORECASE
    ),
)

DEFAULT_PROMPTS = {
    "contact_one": "I found {name}. Do you want to call this contact? Say yes or no.",
    "contact_many": "I found several contacts. {options} Say the number or the full name.",
    "contact_repeat": "Please say the number or the full name. {options}",
    "contact_confirm": "Calling {name}. Say yes to confirm or no to cancel.",
    "contact_phone": "I will call the number {name}. Say yes to confirm or no to cancel.",
    "yes_no": "Please say yes or no.",
    "start_collect": "Please say your message now.",
    "not_heard": "I did not hear anything. Please say your message.",
    "ask_more": "Do you want to say anything else?",
}


class CallError(Exception):
    code = "CALL_ERROR"


class ContactError(CallError):
    code = "CONTACT_ERROR"


class AudioDeviceError(CallError):
    code = "AUDIO_DEVICE_ERROR"


class MicrophoneError(CallError):
    code = "MICROPHONE_ERROR"


class TTSError(CallError):
    code = "TTS_ERROR"


class CallTimeout(CallError):
    code = "CALL_TIMEOUT"


class CallFailed(CallError):
    code = "CALL_FAILED"


class InvalidTransition(CallError):
    code = "INVALID_TRANSITION"


class UserCancelled(Exception):
    code = "USER_CANCELLED"


class CallState(Enum):
    IDLE = "IDLE"
    COLLECTING_MESSAGE = "COLLECTING_MESSAGE"
    CONFIRMING_MESSAGE = "CONFIRMING_MESSAGE"
    CONTACT_CONFIRMATION = "CONTACT_CONFIRMATION"
    CALLING = "CALLING"
    CONNECTED = "CONNECTED"
    SPEAKING_MESSAGE = "SPEAKING_MESSAGE"
    CALL_ENDED = "CALL_ENDED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {CallState.CALL_ENDED, CallState.ERROR, CallState.CANCELLED}

TRANSITIONS = {
    CallState.IDLE: {
        CallState.CONTACT_CONFIRMATION, CallState.ERROR, CallState.CANCELLED,
    },
    CallState.CONTACT_CONFIRMATION: {
        CallState.COLLECTING_MESSAGE, CallState.ERROR, CallState.CANCELLED,
    },
    CallState.COLLECTING_MESSAGE: {
        CallState.CONFIRMING_MESSAGE, CallState.ERROR, CallState.CANCELLED,
    },
    CallState.CONFIRMING_MESSAGE: {
        CallState.COLLECTING_MESSAGE, CallState.CALLING,
        CallState.ERROR, CallState.CANCELLED,
    },
    CallState.CALLING: {
        CallState.CONNECTED, CallState.CALL_ENDED,
        CallState.ERROR, CallState.CANCELLED,
    },
    CallState.CONNECTED: {
        CallState.SPEAKING_MESSAGE, CallState.CALL_ENDED,
        CallState.ERROR, CallState.CANCELLED,
    },
    CallState.SPEAKING_MESSAGE: {
        CallState.CALL_ENDED, CallState.ERROR, CallState.CANCELLED,
    },
    CallState.CALL_ENDED: {CallState.IDLE},
    CallState.ERROR: {CallState.IDLE},
    CallState.CANCELLED: {CallState.IDLE},
}


@dataclass
class CallConfig:
    message_languages: tuple = ("en-US",)
    confirm_languages: tuple = ("en-US",)
    real_mic_index: object = None
    real_mic_name: str = ""
    virtual_output_name: str = "CABLE Input"
    remote_monitor_name: str = ""
    ambient_seconds: float = 0.8
    post_speech_wait: float = 0.8
    phrase_limit: float = 25.0
    collect_timeout: float = 14.0
    confirm_timeout: float = 10.0
    max_retries: int = 3
    echo_guard_seconds: float = 0.5
    dedupe_seconds: float = 6.0
    max_message_chars: int = 900
    tts_backend: str = "powershell"
    tts_voice: str = ""
    tts_rate: int = 0
    whatsapp_launch_timeout: float = 30.0
    search_delay: float = 1.8
    call_start_grace: float = 20.0
    call_timeout: float = 60.0
    connect_poll: float = 0.7
    connected_settle_seconds: float = 1.2
    repeat_message: int = 1
    repeat_gap_seconds: float = 1.5
    hangup_after_message: bool = True
    post_message_delay: float = 1.5
    max_call_seconds: float = 600.0
    input_switch_args: tuple = ()
    input_restore_args: tuple = ()
    prompts: object = None

    def prompt(self, key, **values):
        custom = self.prompts if isinstance(self.prompts, dict) else {}
        text = custom.get(key) or DEFAULT_PROMPTS[key]

        if values:
            return text.format(**values)

        return text

    @classmethod
    def load(cls, path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            raise CallError(f"The configuration file could not be read: {exc}") from exc

        if not isinstance(data, dict):
            raise CallError("The configuration file must contain a JSON object.")

        names = {item.name for item in fields(cls)}
        values = {}

        for key, value in data.items():
            if key not in names:
                raise CallError(f"Unknown configuration setting: {key}")

            if isinstance(value, list):
                value = tuple(value)

            values[key] = value

        return cls(**values)


def import_optional(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def normalize(text):
    value = str(text).lower().translate(PUNCT_TABLE)

    return " ".join(value.split())


def classify_answer(candidates):
    for candidate in candidates:
        cleaned = normalize(candidate)
        tokens = set(cleaned.split())
        padded = f" {cleaned} "
        yes = bool(tokens & YES_WORDS)
        no = bool(tokens & NO_WORDS) or any(p in padded for p in NO_PHRASES)

        if yes and not no:
            return "yes"

        if no and not yes:
            return "no"

    return None


def choose_index(candidates, labels):
    for candidate in candidates:
        cleaned = normalize(candidate)

        for token in cleaned.split():
            index = ORDINALS.get(token)

            if index is not None and index < len(labels):
                return index

        if len(cleaned) < 3:
            continue

        hits = []

        for index, label in enumerate(labels):
            label_norm = normalize(label)

            if label_norm and (label_norm in cleaned or cleaned in label_norm):
                hits.append(index)

        if len(hits) == 1:
            return hits[0]

    return None


def parse_target(text):
    target = " ".join(str(text).split()).strip(" .,!?;:\"'")

    if not target or target.lower() in IGNORED_TARGETS or len(target) > 80:
        return None

    compact = re.sub(r"[\s\-().]", "", target)

    if re.fullmatch(r"\+?\d{7,15}", compact):
        return ("phone", compact)

    return ("name", target)


def parse_call_request(text):
    value = " ".join(str(text).split()).strip(" .,!?;:")
    value = FILLER_RE.sub("", value)

    for pattern in CALL_PATTERNS:
        match = pattern.match(value)

        if match:
            parsed = parse_target(match.group("t"))

            if parsed:
                return parsed

    return None


def is_virtual_name(name):
    lowered = str(name).lower()

    return any(word in lowered for word in ("cable", "vb-audio", "virtual", "voicemeeter"))


def contact_label(name):
    return re.split(r"[\n\r]|,\s|\s{2,}", str(name).strip())[0].strip()


def pcm_level(data):
    samples = array.array("h")
    samples.frombytes(data[:len(data) - (len(data) % 2)])

    if sys.byteorder == "big":
        samples.byteswap()

    if not samples:
        return 0.0

    mean = sum(abs(s) for s in samples) / len(samples)

    return max(0.0, min(1.0, mean / 32768.0 * 6.0))


def run_args(args):
    if not args:
        return

    try:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=NO_WINDOW
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AudioDeviceError(f"Audio routing command failed: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:200]
        raise AudioDeviceError(f"Audio routing command failed: {detail}")


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

SW_RESTORE = 9


def window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)

    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)

    return buffer.value


def window_class(hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)

    return buffer.value


def list_windows():
    results = []

    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        title = window_title(hwnd)

        if title:
            results.append((hwnd, title, window_class(hwnd)))

        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)

    return results


def is_whatsapp_desktop(title, cls):
    normalized = title.strip().lower()
    if normalized in ("whatsapp", "whatsapp beta") and cls != "Chrome_WidgetWin_1":
        return True
    is_chrome_window = cls == "Chrome_WidgetWin_1" or "chrome" in normalized or "chromium" in normalized
    return is_chrome_window and ("whatsapp" in normalized or "whatsapp business" in normalized)


def whatsapp_windows():
    windows = []
    for hwnd, title, cls in list_windows():
        if is_whatsapp_desktop(title, cls):
            windows.append((hwnd, title))
    windows.sort(key=lambda item: ("chrome" not in item[1].lower(), "business" not in item[1].lower()))
    return windows


def focus_window(hwnd, attempts=3):
    for _ in range(attempts):
        if not user32.IsWindow(hwnd):
            return False

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        current_thread = kernel32.GetCurrentThreadId()
        foreground = user32.GetForegroundWindow()
        foreground_thread = 0

        if foreground:
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None)

        attached = False

        if foreground_thread and foreground_thread != current_thread:
            attached = bool(
                user32.AttachThreadInput(current_thread, foreground_thread, True)
            )

        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, foreground_thread, False)

        time.sleep(0.35)

        if user32.GetForegroundWindow() == hwnd:
            return True

    return False


def walk(root, max_nodes=4000, max_seconds=8.0, max_depth=40):
    if root is None:
        return

    deadline = time.monotonic() + max_seconds
    stack = [(root, 0, False)]
    count = 0

    while stack and count < max_nodes and time.monotonic() < deadline:
        control, depth, inside = stack.pop()
        count += 1

        try:
            name = control.Name or ""
            kind = control.ControlTypeName or ""
            children = control.GetChildren() if depth < max_depth else []
        except Exception:
            continue

        yield control, kind, name, inside

        child_inside = inside or kind in ITEM_KINDS

        for child in reversed(children):
            stack.append((child, depth + 1, child_inside))


class StateMachine:

    def __init__(self, on_change=None):
        self.lock = threading.RLock()
        self.state = CallState.IDLE
        self.on_change = on_change

    def move(self, new_state):
        with self.lock:
            old_state = self.state

            if new_state == old_state:
                return False

            if new_state not in TRANSITIONS[old_state]:
                raise InvalidTransition(
                    f"Invalid state change: {old_state.value} to {new_state.value}"
                )

            self.state = new_state

        if self.on_change is not None:
            try:
                self.on_change(old_state, new_state)
            except Exception:
                log.exception("State change callback failed.")

        return True

    def is_terminal(self):
        return self.state in TERMINAL_STATES


class CommandLock:

    def __init__(self, on_lock=None, on_unlock=None):
        self.on_lock = on_lock
        self.on_unlock = on_unlock
        self.guard = threading.Lock()
        self.locked = False

    def lock(self):
        with self.guard:
            if self.locked:
                return False

            self.locked = True

        self.fire(self.on_lock)

        return True

    def unlock(self):
        with self.guard:
            if not self.locked:
                return False

            self.locked = False

        self.fire(self.on_unlock)

        return True

    @staticmethod
    def fire(callback):
        if callback is None:
            return

        try:
            callback()
        except Exception:
            log.exception("Command lock callback failed.")


class AudioDevices:

    def __init__(self):
        self.pyaudio = None
        self.pa = None
        self.cache = None

    def open(self):
        if self.pa is not None:
            return

        module = import_optional("pyaudio")

        if module is None:
            raise AudioDeviceError("PyAudio is not installed. Run: pip install pyaudio")

        try:
            self.pa = module.PyAudio()
        except Exception as exc:
            raise AudioDeviceError(f"The audio system could not be opened: {exc}") from exc

        self.pyaudio = module
        self.cache = None

    def close(self):
        pa = self.pa
        self.pa = None
        self.cache = None

        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                log.exception("PyAudio could not be terminated cleanly.")

    def devices(self):
        self.open()

        if self.cache is not None:
            return self.cache

        found = []

        for index in range(self.pa.get_device_count()):
            try:
                info = self.pa.get_device_info_by_index(index)
                host = self.pa.get_host_api_info_by_index(info["hostApi"])["name"]
            except Exception:
                continue

            found.append({
                "index": index,
                "name": str(info["name"]),
                "inputs": int(info["maxInputChannels"]),
                "outputs": int(info["maxOutputChannels"]),
                "host": str(host),
                "rate": int(info["defaultSampleRate"]),
            })

        self.cache = found

        return found

    def info(self, index):
        for item in self.devices():
            if item["index"] == index:
                return item

        return None

    def find(self, needle, output):
        needle = str(needle).lower().strip()

        if not needle:
            return None

        key = "outputs" if output else "inputs"
        matches = [
            item for item in self.devices()
            if item[key] > 0 and needle in item["name"].lower()
        ]

        if not matches:
            return None

        matches.sort(key=lambda item: 0 if "mme" in item["host"].lower() else 1)

        return matches[0]


def resolve_real_mic(config, devices):
    if config.real_mic_index is not None:
        try:
            info = devices.info(int(config.real_mic_index))
        except (TypeError, ValueError) as exc:
            raise MicrophoneError("real_mic_index must be a number.") from exc
    elif config.real_mic_name:
        info = devices.find(config.real_mic_name, False)
    else:
        try:
            default = devices.pa.get_default_input_device_info()
        except (OSError, IOError) as exc:
            raise MicrophoneError("No default microphone was found.") from exc

        info = devices.info(int(default["index"]))

    if info is None or info["inputs"] <= 0:
        raise MicrophoneError("The configured real microphone was not found.")

    if is_virtual_name(info["name"]):
        raise MicrophoneError(
            "The selected microphone is a virtual device. "
            "Set real_mic_name to the physical microphone."
        )

    return info["index"]


class AudioRouter:

    def __init__(self, config, devices):
        self.config = config
        self.devices = devices
        self.virtual_output = None
        self.remote_device = None
        self.applied = False

    def validate(self):
        output = self.devices.find(self.config.virtual_output_name, True)

        if output is None:
            raise AudioDeviceError(
                f"Virtual audio output device '{self.config.virtual_output_name}' "
                "was not found. Install VB-CABLE or set virtual_output_name."
            )

        self.virtual_output = output

        if self.config.remote_monitor_name:
            monitor = self.devices.find(self.config.remote_monitor_name, False)

            if monitor is None:
                raise AudioDeviceError(
                    f"Remote audio monitor device '{self.config.remote_monitor_name}' "
                    "was not found."
                )

            self.remote_device = monitor

    def apply(self):
        if self.config.input_switch_args and not self.applied:
            run_args(self.config.input_switch_args)
            self.applied = True

    def restore(self):
        if not self.applied:
            return

        self.applied = False

        try:
            run_args(self.config.input_restore_args)
        except CallError:
            log.exception("The default audio input could not be restored.")


class WavPlayer:

    def __init__(self, devices):
        self.devices = devices

    def play(self, path, device_index, stop_event):
        self.devices.open()
        pa = self.devices.pa
        stream = None

        try:
            with wave.open(path, "rb") as source:
                width = source.getsampwidth()
                channels = source.getnchannels()
                rate = source.getframerate()
                options = {
                    "format": pa.get_format_from_width(width),
                    "channels": channels,
                    "rate": rate,
                    "output": True,
                }

                if device_index is not None:
                    options["output_device_index"] = int(device_index)

                stream = pa.open(**options)
                data = source.readframes(1024)

                while data:
                    if stop_event.is_set():
                        return False

                    stream.write(data)
                    data = source.readframes(1024)

                stream.write(b"\x00" * int(rate * width * channels * 0.25))
                stream.stop_stream()

            return True
        except (OSError, wave.Error, ValueError) as exc:
            raise AudioDeviceError(f"Audio playback failed: {exc}") from exc
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    log.exception("Playback stream could not be closed.")


class TTSAdapter:

    def __init__(self, config, custom=None):
        self.config = config
        self.custom = custom
        self.directory = None
        self.cache = {}
        self.guard = threading.Lock()

    def prepare(self):
        with self.guard:
            if self.directory is None:
                self.directory = tempfile.mkdtemp(prefix="mh2_wa_tts_")

        if self.custom is None and self.config.tts_backend == "pyttsx3":
            if import_optional("pyttsx3") is None:
                raise TTSError("pyttsx3 is not installed. Run: pip install pyttsx3")

        if self.custom is None and self.config.tts_backend not in ("powershell", "pyttsx3"):
            raise TTSError(f"Unknown TTS backend: {self.config.tts_backend}")

    def synthesize(self, text):
        text = " ".join(str(text).split())

        if not text:
            raise TTSError("There is no text to speak.")

        self.prepare()

        with self.guard:
            cached = self.cache.get(text)

            if cached and os.path.isfile(cached):
                return cached

            path = os.path.join(self.directory, f"tts_{time.time_ns()}.wav")

        if self.custom is not None:
            try:
                self.custom(text, path)
            except Exception as exc:
                raise TTSError(f"The custom TTS function failed: {exc}") from exc
        elif self.config.tts_backend == "pyttsx3":
            self.render_pyttsx3(text, path)
        else:
            self.render_powershell(text, path)

        if not os.path.isfile(path) or os.path.getsize(path) <= 44:
            raise TTSError("The TTS engine did not produce an audio file.")

        with self.guard:
            self.cache[text] = path

        return path

    def render_powershell(self, text, path):
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "if ($env:MH2_TTS_VOICE) { $s.SelectVoice($env:MH2_TTS_VOICE) }; "
            "$s.Rate = [int]$env:MH2_TTS_RATE; "
            "$s.SetOutputToWaveFile($env:MH2_TTS_PATH); "
            "$s.Speak($env:MH2_TTS_TEXT); "
            "$s.Dispose()"
        )
        environment = os.environ.copy()
        environment["MH2_TTS_TEXT"] = text
        environment["MH2_TTS_PATH"] = path
        environment["MH2_TTS_VOICE"] = self.config.tts_voice
        environment["MH2_TTS_RATE"] = str(int(self.config.tts_rate))

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                creationflags=NO_WINDOW
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TTSError(f"Windows speech synthesis could not run: {exc}") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:200]
            raise TTSError(f"Windows speech synthesis failed: {detail}")

    def render_pyttsx3(self, text, path):
        module = import_optional("pyttsx3")

        try:
            engine = module.init()
        except Exception as exc:
            raise TTSError(f"pyttsx3 could not start: {exc}") from exc

        try:
            if self.config.tts_voice:
                needle = self.config.tts_voice.lower()

                for voice in engine.getProperty("voices"):
                    if needle in str(voice.name).lower() or needle in str(voice.id).lower():
                        engine.setProperty("voice", voice.id)
                        break

            if self.config.tts_rate:
                engine.setProperty("rate", engine.getProperty("rate") + int(self.config.tts_rate))

            engine.save_to_file(text, path)
            engine.runAndWait()
        except Exception as exc:
            raise TTSError(f"pyttsx3 synthesis failed: {exc}") from exc
        finally:
            try:
                engine.stop()
            except Exception:
                log.exception("pyttsx3 engine could not be stopped.")

    def cleanup(self):
        with self.guard:
            directory = self.directory
            files = list(self.cache.values())
            self.directory = None
            self.cache = {}

        for path in files:
            try:
                os.remove(path)
            except OSError:
                continue

        if directory:
            try:
                for name in os.listdir(directory):
                    os.remove(os.path.join(directory, name))

                os.rmdir(directory)
            except OSError:
                log.warning("Temporary TTS directory could not be fully removed.")


class MicListener:

    def __init__(self, config, stop_event):
        self.config = config
        self.stop_event = stop_event
        self.sr = None
        self.recognizer = None
        self.device_index = None

    def prepare(self, device_index):
        module = import_optional("speech_recognition")

        if module is None:
            raise MicrophoneError(
                "SpeechRecognition is not installed. Run: pip install SpeechRecognition"
            )

        recognizer = module.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 300
        recognizer.pause_threshold = self.config.post_speech_wait
        recognizer.non_speaking_duration = min(0.5, self.config.post_speech_wait)

        try:
            with module.Microphone(device_index=device_index) as source:
                recognizer.adjust_for_ambient_noise(
                    source, duration=self.config.ambient_seconds
                )
        except Exception as exc:
            raise MicrophoneError(f"The microphone could not be opened: {exc}") from exc

        self.sr = module
        self.recognizer = recognizer
        self.device_index = device_index

    def listen(self, languages, total_timeout, phrase_limit):
        if self.recognizer is None:
            raise MicrophoneError("The microphone is not prepared.")

        deadline = time.monotonic() + total_timeout
        audio = None

        try:
            with self.sr.Microphone(device_index=self.device_index) as source:
                while audio is None:
                    if self.stop_event.is_set():
                        raise UserCancelled("Call cancelled.")

                    if time.monotonic() >= deadline:
                        return []

                    try:
                        audio = self.recognizer.listen(
                            source, timeout=1.0, phrase_time_limit=phrase_limit
                        )
                    except self.sr.WaitTimeoutError:
                        continue
        except UserCancelled:
            raise
        except Exception as exc:
            raise MicrophoneError(f"Microphone input failed: {exc}") from exc

        if self.stop_event.is_set():
            raise UserCancelled("Call cancelled.")

        return self.transcribe(audio, languages)

    def transcribe(self, audio, languages):
        for language in languages:
            try:
                result = self.recognizer.recognize_google(
                    audio, language=language, show_all=True
                )
            except self.sr.UnknownValueError:
                continue
            except self.sr.RequestError as exc:
                raise MicrophoneError(f"Speech recognition service failed: {exc}") from exc

            alternatives = result.get("alternative") if isinstance(result, dict) else None

            if not alternatives:
                continue

            scored = []

            for index, alternative in enumerate(alternatives[:3]):
                text = " ".join(str(alternative.get("transcript", "")).split())

                if not text:
                    continue

                try:
                    confidence = float(alternative.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5

                scored.append((confidence - 0.05 * index, text))

            if scored:
                scored.sort(key=lambda item: item[0], reverse=True)

                return [text for _, text in scored]

        return []


class RemoteMonitor:

    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.level = 0.0
        self.error = ""
        self.device = None

    def start(self, device):
        if device is None:
            return False

        self.device = device
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.loop, name="mh2-remote-monitor", daemon=True
        )
        self.thread.start()

        return True

    def loop(self):
        module = import_optional("pyaudio")
        pa = None
        stream = None

        try:
            pa = module.PyAudio()
            channels = 2 if self.device["inputs"] >= 2 else 1
            stream = pa.open(
                format=module.paInt16,
                channels=channels,
                rate=int(self.device["rate"]),
                input=True,
                input_device_index=self.device["index"],
                frames_per_buffer=1024
            )

            while not self.stop_event.is_set():
                data = stream.read(1024, exception_on_overflow=False)
                self.level = pcm_level(data)
        except Exception as exc:
            self.error = str(exc)
            log.warning("Remote audio monitor stopped: %s", exc)
        finally:
            self.level = 0.0

            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    log.exception("Monitor stream could not be closed.")

            if pa is not None:
                try:
                    pa.terminate()
                except Exception:
                    log.exception("Monitor audio system could not be closed.")

    def stop(self):
        self.stop_event.set()

        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        self.thread = None


class WhatsAppDesktop:

    def __init__(self, config, cancel_event):
        self.config = config
        self.cancel_event = cancel_event
        self.uia = None
        self.pyautogui = None
        self.pyperclip = None
        self.hwnd = None
        self.last_query = ""

    def load(self):
        self.uia = import_optional("uiautomation")
        self.pyautogui = import_optional("pyautogui")
        self.pyperclip = import_optional("pyperclip")

        if self.uia is None:
            raise CallError("uiautomation is required. Run: pip install uiautomation")

        if self.pyautogui is None:
            raise CallError("pyautogui is required. Run: pip install pyautogui")

        if self.pyperclip is None:
            raise CallError("pyperclip is required. Run: pip install pyperclip")

    def sleep(self, seconds):
        if self.cancel_event.wait(seconds):
            raise UserCancelled("Call cancelled.")

    def check(self):
        if self.cancel_event.is_set():
            raise UserCancelled("Call cancelled.")

    @staticmethod
    def walk(root, max_nodes=4000, max_seconds=8.0):
        return walk(root, max_nodes, max_seconds)

    def fresh_root(self, hwnd=None):
        target = hwnd or self.hwnd

        if target is None:
            raise CallError("WhatsApp Desktop is not ready.")

        try:
            root = self.uia.ControlFromHandle(target)
        except Exception as exc:
            raise CallError(f"WhatsApp Desktop could not be inspected: {exc}") from exc

        if root is None:
            raise CallError("WhatsApp Desktop could not be inspected.")

        return root

    def require_foreground(self):
        if user32.GetForegroundWindow() != self.hwnd:
            raise CallError("WhatsApp lost focus. Nothing was typed.")

    def hotkey(self, *keys):
        try:
            self.pyautogui.hotkey(*keys)
        except Exception as exc:
            raise CallError(f"Keyboard automation failed: {exc}") from exc

    def paste(self, text):
        self.require_foreground()
        previous = None

        try:
            previous = self.pyperclip.paste()
        except Exception:
            previous = None

        try:
            try:
                self.pyperclip.copy(text)
            except Exception as exc:
                raise CallError("The clipboard is not available.") from exc

            self.sleep(0.15)
            self.require_foreground()
            self.hotkey("ctrl", "v")
            self.sleep(0.45)
        finally:
            try:
                self.pyperclip.copy(previous if previous is not None else "")
            except Exception:
                log.warning("The clipboard could not be restored.")

    def activate(self, control):
        try:
            pattern = control.GetInvokePattern()

            if pattern is not None:
                pattern.Invoke()
                return
        except Exception:
            log.debug("Invoke pattern unavailable, falling back to click.")

        try:
            control.Click(simulateMove=False)
        except Exception as exc:
            raise CallError(f"A WhatsApp control could not be activated: {exc}") from exc

    def ensure_ready(self):
        windows = whatsapp_windows()

        if not windows:
            try:
                os.startfile("whatsapp:")
            except OSError as exc:
                raise CallError(
                    "No WhatsApp Desktop or Chrome WhatsApp Web window was found. "
                    "Open WhatsApp Web in Chrome and keep that window open."
                ) from exc

            deadline = time.monotonic() + self.config.whatsapp_launch_timeout
            while not windows and time.monotonic() < deadline:
                self.sleep(0.6)
                windows = whatsapp_windows()

            if not windows:
                raise CallError("No WhatsApp window appeared. Open WhatsApp Web in Chrome and log in.")
            self.sleep(2.0)

        hwnd = windows[0][0]

        if not focus_window(hwnd):
            raise CallError("Windows did not allow focusing WhatsApp Desktop.")

        self.hwnd = hwnd
        root = self.fresh_root()

        for _, _, name, _ in self.walk(root, 1500, 6.0):
            lowered = name.lower()

            if ("scan" in lowered and "qr" in lowered) or "link with phone number" in lowered:
                raise CallError("WhatsApp Desktop is not logged in. Log in and try again.")

        return hwnd

    def find_search_box(self):
        for control, kind, name, _ in self.walk(self.fresh_root(), 2500, 6.0):
            if kind == "EditControl" and "search" in name.lower():
                return control

        return None

    def scan_candidates(self, query):
        needle = query.lower().strip()
        section = ""
        counts = {}
        results = []

        for control, kind, name, inside in self.walk(self.fresh_root(), 4500, 10.0):
            if not inside:
                lowered = name.strip().lower()

                if lowered in SECTION_NAMES:
                    section = lowered
                    continue

            if kind not in ITEM_KINDS or section == "messages":
                continue

            label = contact_label(name)

            if not label or needle not in label.lower():
                continue

            key = label.lower()
            ordinal = counts.get(key, 0)
            counts[key] = ordinal + 1
            results.append((label, ordinal, control))

        return results

    def search_contacts(self, query):
        self.ensure_ready()
        self.last_query = query
        self.require_foreground()
        box = self.find_search_box()
        focused = False

        if box is not None:
            try:
                box.SetFocus()
                focused = True
            except Exception:
                focused = False

        if not focused:
            self.hotkey("ctrl", "f")

        self.sleep(0.5)
        self.require_foreground()
        self.hotkey("ctrl", "a")
        self.paste(query)
        self.sleep(self.config.search_delay)

        return [(label, ordinal) for label, ordinal, _ in self.scan_candidates(query)]

    def chat_open(self, label):
        target = label.lower()
        has_call = False
        has_header = False

        for _, kind, name, inside in self.walk(self.fresh_root(), 3500, 8.0):
            if inside:
                continue

            text = name.strip()

            if not text:
                continue

            if kind in BUTTON_KINDS and (VOICE_RE.match(text) or CALL_MENU_RE.match(text)):
                has_call = True
            elif kind != "EditControl" and target in text.lower():
                has_header = True

        return has_call and has_header

    def open_contact(self, label, ordinal):
        self.ensure_ready()
        selected = None

        for found_label, found_ordinal, control in self.scan_candidates(self.last_query):
            if found_label.lower() == label.lower() and found_ordinal == ordinal:
                selected = control
                break

        if selected is None:
            raise ContactError(f"The contact {label} is no longer in the search results.")

        try:
            selected.Click(simulateMove=False)
        except Exception as exc:
            raise ContactError(f"The contact {label} could not be opened: {exc}") from exc

        self.sleep(1.6)

        if not self.chat_open(label):
            raise ContactError(
                f"Could not confirm that the chat with {label} opened. No call was started."
            )

    def open_phone(self, digits):
        number = digits.strip()
        normalized_number = number.lstrip("+").replace(" ", "").replace("-", "")
        windows = whatsapp_windows()
        browser_window = next(
            ((hwnd, title) for hwnd, title in windows if "chrome" in title.lower()),
            None,
        )

        if browser_window is not None:
            self.ensure_ready()
            candidates = self.search_contacts(number)[:10]
            exact = [
                (label, ordinal) for label, ordinal in candidates
                if normalized_number in label.replace(" ", "").replace("-", "").replace("+", "")
            ]
            matches = exact or candidates
            if not matches:
                raise ContactError(
                    f"No WhatsApp Web search result matched {number}. "
                    "Search the number manually in WhatsApp Web and try again."
                )
            if len(matches) != 1:
                raise ContactError(
                    f"More than one result matched {number}. Use the contact name instead."
                )
            self.open_contact(matches[0][0], matches[0][1])
            return

        try:
            os.startfile(f"whatsapp://send?phone={normalized_number}")
        except OSError as exc:
            raise ContactError(f"WhatsApp could not open the number: {exc}") from exc

        deadline = time.monotonic() + self.config.whatsapp_launch_timeout
        windows = whatsapp_windows()
        while not windows and time.monotonic() < deadline:
            self.sleep(0.6)
            windows = whatsapp_windows()
        if not windows:
            raise ContactError("The WhatsApp Desktop window did not appear.")

        self.sleep(2.0)
        self.hwnd = windows[0][0]
        if not focus_window(self.hwnd):
            raise CallError("Windows did not allow focusing WhatsApp.")
        if self.find_named(VOICE_RE, BUTTON_KINDS) is None and self.find_named(CALL_MENU_RE, BUTTON_KINDS) is None:
            raise ContactError("The chat for this number did not open. No call was started.")

    def find_named(self, regex, kinds):
        for control, kind, name, inside in self.walk(self.fresh_root(), 4000, 8.0):
            if inside or kind not in kinds:
                continue

            if regex.search(name.strip()):
                return control

        return None

    def start_voice_call(self):
        self.check()

        if user32.GetForegroundWindow() != self.hwnd and not focus_window(self.hwnd):
            raise CallError("Windows did not allow focusing WhatsApp Desktop.")

        button = self.find_named(VOICE_RE, BUTTON_KINDS)

        if button is None:
            menu = self.find_named(CALL_MENU_RE, BUTTON_KINDS)

            if menu is None:
                raise CallError("The WhatsApp voice call button was not found.")

            self.activate(menu)
            self.sleep(0.7)
            button = self.find_named(VOICE_ITEM_RE, ("MenuItemControl", "ButtonControl"))

            if button is None:
                raise CallError("The WhatsApp voice call option was not found.")

        self.activate(button)

    def call_snapshot(self):
        snapshot = {"in_call": False, "timer": None, "failure": None}

        for hwnd, _ in whatsapp_windows():
            try:
                root = self.uia.ControlFromHandle(hwnd)
            except Exception:
                continue

            window_in_call = False
            window_timer = None

            for _, kind, name, inside in self.walk(root, 2500, 3.0):
                text = name.strip()

                if not text:
                    continue

                if kind in BUTTON_KINDS and END_RE.match(text):
                    window_in_call = True
                elif kind == "TextControl" and not inside:
                    if TIMER_RE.match(text):
                        window_timer = text
                    elif FAIL_RE.match(text):
                        snapshot["failure"] = text

            if window_in_call:
                snapshot["in_call"] = True
                snapshot["timer"] = window_timer

        return snapshot

    def wait_connected(self):
        start = time.monotonic()
        deadline = start + self.config.call_timeout
        seen = []
        started = False
        absent = 0

        while True:
            self.check()
            now = time.monotonic()

            if now >= deadline:
                raise CallTimeout("The call was not answered in time.")

            snapshot = self.call_snapshot()

            if snapshot["failure"]:
                raise CallFailed(f"The call failed: {snapshot['failure']}.")

            if snapshot["in_call"]:
                started = True
                absent = 0
                timer = snapshot["timer"]

                if timer and timer not in seen:
                    seen.append(timer)

                    if len(seen) >= 2:
                        return True
            elif started:
                absent += 1

                if absent >= 3:
                    raise CallFailed("The call ended before it was answered.")
            elif now - start > self.config.call_start_grace:
                raise CallFailed("The WhatsApp call window did not appear.")

            self.sleep(self.config.connect_poll)

    def call_active(self):
        return bool(self.call_snapshot()["in_call"])

    def end_call(self):
        if self.uia is None:
            return False

        for hwnd, _ in whatsapp_windows():
            try:
                root = self.uia.ControlFromHandle(hwnd)
            except Exception:
                continue

            for control, kind, name, _ in self.walk(root, 2500, 3.0):
                if kind in BUTTON_KINDS and END_RE.match(name.strip()):
                    self.activate(control)
                    return True

        return False


class CallSession:

    def __init__(self, module, kind, value):
        self.module = module
        self.config = module.config
        self.kind = kind
        self.value = value
        self.cancel_event = threading.Event()
        self.listeners_stop = threading.Event()
        self.done_event = threading.Event()
        self.machine = StateMachine(self.on_state)
        self.devices = AudioDevices()
        self.router = AudioRouter(self.config, self.devices)
        self.tts = TTSAdapter(self.config, module.tts_function)
        self.player = WavPlayer(self.devices)
        self.mic = MicListener(self.config, self.cancel_event)
        self.whatsapp = WhatsAppDesktop(self.config, self.cancel_event)
        self.monitor = RemoteMonitor()
        self.thread = None
        self.hangup_thread = None
        self.segments = []
        self.last_norm = ""
        self.last_time = 0.0
        self.spoken = deque(maxlen=8)
        self.final_message = ""
        self.final_locked = False
        self.message_path = None
        self.real_mic_index = None
        self.contact_label = ""
        self.call_started = False
        self.call_ended = False
        self.delivered = False
        self.clean_guard = threading.Lock()
        self.cleaned = False

    @property
    def alive(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        self.thread = threading.Thread(
            target=self.run, name="mh2-whatsapp-call", daemon=True
        )
        self.thread.start()

    def cancel(self):
        self.cancel_event.set()

    def on_state(self, old_state, new_state):
        log.info("WhatsApp call state: %s -> %s", old_state.value, new_state.value)
        self.module.emit_state(old_state, new_state)

    def run(self):
        uia = import_optional("uiautomation")
        initializer = getattr(uia, "UIAutomationInitializerInThread", None) if uia else None

        try:
            if initializer is not None:
                with initializer():
                    self.execute()
            else:
                self.execute()
        except Exception:
            log.exception("The WhatsApp call session crashed.")
        finally:
            self.cleanup()
            self.done_event.set()

    def execute(self):
        try:
            self.module.lock.lock()
            self.module.notify("command", "WHATSAPP CALL")
            self.prepare()
            self.machine.move(CallState.CONTACT_CONFIRMATION)
            self.confirm_contact()
            self.collect_message()
            self.place_call()
            self.deliver_message()
            self.finish_call()
        except UserCancelled as exc:
            self.conclude(CallState.CANCELLED, str(exc) or "Call cancelled.")
        except CallError as exc:
            self.conclude(CallState.ERROR, str(exc))
        except Exception as exc:
            log.exception("Unexpected WhatsApp call error.")
            self.conclude(CallState.ERROR, f"Unexpected error: {exc}")
        finally:
            self.cleanup()

    def conclude(self, state, text):
        if self.machine.is_terminal():
            return

        try:
            self.machine.move(state)
        except InvalidTransition:
            log.exception("Final state could not be set.")

        if state == CallState.ERROR:
            self.module.notify("failed", text)
        else:
            self.module.notify("done", text)

    def check_cancel(self):
        if self.cancel_event.is_set():
            raise UserCancelled("Call cancelled.")

    def sleep(self, seconds):
        if self.cancel_event.wait(seconds):
            raise UserCancelled("Call cancelled.")

    def prepare(self):
        self.devices.open()
        self.router.validate()
        self.real_mic_index = resolve_real_mic(self.config, self.devices)
        self.mic.prepare(self.real_mic_index)
        self.tts.prepare()
        self.whatsapp.load()

    def remember_spoken(self, text):
        self.spoken.append(normalize(text))

    def is_echo(self, text):
        cleaned = normalize(text)

        if not cleaned:
            return True

        for spoken in self.spoken:
            if not spoken:
                continue

            if len(cleaned.split()) >= 2 and cleaned in spoken:
                return True

            if len(spoken.split()) >= 3 and spoken in cleaned:
                return True

        return False

    def speak_local(self, text):
        self.check_cancel()
        path = self.tts.synthesize(text)
        self.remember_spoken(text)
        self.player.play(path, None, self.cancel_event)
        self.sleep(self.config.echo_guard_seconds)

    def listen(self, languages, timeout, limit):
        self.check_cancel()
        answers = self.mic.listen(languages, timeout, limit)
        self.check_cancel()
        answers = [text for text in answers if not self.is_echo(text)]

        for text in answers:
            if normalize(text) in CANCEL_PHRASES:
                raise UserCancelled("Cancelled by voice command.")

        return answers

    def require_yes(self, prompt):
        for attempt in range(self.config.max_retries):
            self.speak_local(prompt if attempt == 0 else self.config.prompt("yes_no"))
            answers = self.listen(
                self.config.confirm_languages, self.config.confirm_timeout, 6.0
            )
            decision = classify_answer(answers)

            if decision == "yes":
                return

            if decision == "no":
                raise UserCancelled("The contact was not confirmed.")

        raise UserCancelled("No confirmation was received. The call was not placed.")

    def pick_contact(self, candidates):
        options = " ".join(
            f"{index + 1}, {label}." for index, (label, _) in enumerate(candidates)
        )
        labels = [label for label, _ in candidates]

        for attempt in range(self.config.max_retries):
            if attempt == 0:
                prompt = self.config.prompt("contact_many", options=options)
            else:
                prompt = self.config.prompt("contact_repeat", options=options)

            self.speak_local(prompt)
            answers = self.listen(
                self.config.confirm_languages, self.config.confirm_timeout, 8.0
            )
            index = choose_index(answers, labels)

            if index is not None:
                return candidates[index]

        raise UserCancelled("No contact was chosen. The call was not placed.")

    def confirm_contact(self):
        if self.kind == "phone":
            digits = self.value
            spoken = " ".join(digits.lstrip("+"))
            self.require_yes(self.config.prompt("contact_phone", name=spoken))
            self.contact_label = digits
            self.whatsapp.open_phone(digits)
            return

        candidates = self.whatsapp.search_contacts(self.value)[:5]

        if not candidates:
            raise ContactError(f"No WhatsApp contact matching {self.value} was found.")

        if len(candidates) == 1:
            chosen = candidates[0]
            self.require_yes(self.config.prompt("contact_one", name=chosen[0]))
        else:
            chosen = self.pick_contact(candidates)
            self.require_yes(self.config.prompt("contact_confirm", name=chosen[0]))

        self.contact_label = chosen[0]
        self.whatsapp.open_contact(chosen[0], chosen[1])

    def add_segment(self, text):
        if self.final_locked:
            return False

        text = " ".join(str(text).split())
        cleaned = normalize(text)

        if not cleaned:
            return False

        now = time.monotonic()

        if cleaned == self.last_norm and now - self.last_time < self.config.dedupe_seconds:
            return False

        self.last_norm = cleaned
        self.last_time = now
        self.segments.append(text)
        self.module.notify("heard", text[:64])

        return True

    def ask_more(self):
        self.speak_local(self.config.prompt("ask_more"))

        for attempt in range(self.config.max_retries):
            answers = self.listen(
                self.config.confirm_languages, self.config.confirm_timeout, 6.0
            )
            decision = classify_answer(answers)

            if decision in ("yes", "no"):
                return decision

            if attempt < self.config.max_retries - 1:
                self.speak_local(self.config.prompt("yes_no"))

        raise UserCancelled("No confirmation was received. The call was not placed.")

    def collect_message(self):
        self.machine.move(CallState.COLLECTING_MESSAGE)
        self.speak_local(self.config.prompt("start_collect"))
        silent = 0

        while True:
            answers = self.listen(
                self.config.message_languages,
                self.config.collect_timeout,
                self.config.phrase_limit
            )

            if not answers:
                silent += 1

                if silent < self.config.max_retries:
                    self.speak_local(self.config.prompt("not_heard"))
                    continue

                if not self.segments:
                    raise UserCancelled("No message was heard. The call was not placed.")

                silent = 0
                self.machine.move(CallState.CONFIRMING_MESSAGE)

                if self.ask_more() == "no":
                    break

                self.machine.move(CallState.COLLECTING_MESSAGE)
                continue

            silent = 0

            if not self.add_segment(answers[0]):
                continue

            self.machine.move(CallState.CONFIRMING_MESSAGE)

            if self.ask_more() == "no":
                break

            self.machine.move(CallState.COLLECTING_MESSAGE)

        message = " ".join(self.segments).strip()

        if not message:
            raise UserCancelled("No message was collected. The call was not placed.")

        self.final_message = message[:self.config.max_message_chars]
        self.final_locked = True
        self.message_path = self.tts.synthesize(self.final_message)

    def place_call(self):
        self.check_cancel()

        if not self.final_locked or not self.message_path:
            raise CallError("The final message is not ready.")

        self.machine.move(CallState.CALLING)
        self.router.apply()
        self.monitor.start(self.router.remote_device)
        self.start_hangup_listener()
        self.whatsapp.start_voice_call()
        self.call_started = True
        self.whatsapp.wait_connected()
        self.machine.move(CallState.CONNECTED)

    def start_hangup_listener(self):
        self.hangup_thread = threading.Thread(
            target=self.hangup_loop, name="mh2-call-control", daemon=True
        )
        self.hangup_thread.start()

    def hangup_loop(self):
        listener = MicListener(self.config, self.listeners_stop)
        failures = 0

        try:
            listener.prepare(self.real_mic_index)
        except CallError as exc:
            self.module.notify("failed", f"Call voice control unavailable: {exc}")
            return

        while not self.listeners_stop.is_set():
            try:
                answers = listener.listen(self.config.confirm_languages, 2.0, 5.0)
                failures = 0
            except UserCancelled:
                return
            except CallError as exc:
                failures += 1

                if failures >= 3:
                    self.module.notify("failed", f"Call voice control stopped: {exc}")
                    return

                self.listeners_stop.wait(1.5)
                continue

            for answer in answers:
                if normalize(answer) in CANCEL_PHRASES:
                    self.cancel_event.set()
                    return

    def deliver_message(self):
        self.sleep(self.config.connected_settle_seconds)

        if not self.final_locked or not self.final_message or not self.message_path:
            raise CallError("The approved message is not available.")

        if not self.whatsapp.call_active():
            raise CallFailed("The call is no longer active. The message was not played.")

        self.machine.move(CallState.SPEAKING_MESSAGE)
        index = self.router.virtual_output["index"]

        for repeat in range(max(1, int(self.config.repeat_message))):
            if repeat:
                self.sleep(self.config.repeat_gap_seconds)

            completed = self.player.play(self.message_path, index, self.cancel_event)

            if not completed:
                raise UserCancelled("Call cancelled.")

        self.delivered = True

    def finish_call(self):
        self.sleep(self.config.post_message_delay)

        if self.config.hangup_after_message:
            if not self.whatsapp.end_call():
                raise CallError("The call could not be ended automatically.")

            self.call_ended = True
            self.sleep(1.0)
        else:
            deadline = time.monotonic() + self.config.max_call_seconds

            while self.whatsapp.call_active() and time.monotonic() < deadline:
                self.sleep(1.0)

            self.call_ended = True

        self.machine.move(CallState.CALL_ENDED)
        self.module.notify(
            "done", f"WhatsApp call finished. Message delivered to {self.contact_label}."
        )

    def cleanup(self):
        with self.clean_guard:
            if self.cleaned:
                return

            self.cleaned = True

        self.cancel_event.set()
        self.listeners_stop.set()

        if self.call_started and not self.call_ended:
            try:
                self.call_ended = bool(self.whatsapp.end_call())
            except Exception:
                log.exception("The call could not be ended during cleanup.")

        try:
            self.monitor.stop()
        except Exception:
            log.exception("The remote audio monitor could not be stopped.")

        thread = self.hangup_thread

        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=4.0)

        try:
            self.router.restore()
        except Exception:
            log.exception("Audio routing could not be restored.")

        try:
            self.tts.cleanup()
        except Exception:
            log.exception("TTS files could not be removed.")

        try:
            self.devices.close()
        except Exception:
            log.exception("The audio system could not be closed.")

        try:
            self.machine.move(CallState.IDLE)
        except InvalidTransition:
            log.warning("The session could not return to IDLE.")

        self.module.session_finished(self)


class WhatsAppCallModule:

    def __init__(
        self,
        config=None,
        notifier=None,
        tts_function=None,
        on_lock=None,
        on_unlock=None,
        on_restore=None,
        on_state=None
    ):
        self.config = config or CallConfig()
        self.notifier = notifier
        self.tts_function = tts_function
        self.lock = CommandLock(on_lock, on_unlock)
        self.on_restore = on_restore
        self.on_state = on_state
        self.guard = threading.RLock()
        self.session = None
        self.agent = None
        self.original_run_voice = None

    @property
    def state(self):
        with self.guard:
            session = self.session

        return session.machine.state if session is not None else CallState.IDLE

    @property
    def is_active(self):
        with self.guard:
            return self.session is not None

    def status(self):
        with self.guard:
            session = self.session

        return {
            "state": self.state.value,
            "locked": self.lock.locked,
            "contact": session.contact_label if session else "",
            "message_ready": bool(session and session.final_locked),
        }

    def notify(self, kind, text=""):
        if self.notifier is None:
            return

        try:
            self.notifier(kind, text)
        except Exception:
            log.exception("The call notifier failed.")

    def emit_state(self, old_state, new_state):
        if self.on_state is None:
            return

        try:
            self.on_state(old_state.value, new_state.value)
        except Exception:
            log.exception("The state callback failed.")

    def start_call(self, target_text):
        parsed = parse_call_request(target_text) or parse_target(target_text)

        if parsed is None:
            raise CallError("The contact name or phone number is missing.")

        return self.start_call_to(parsed[0], parsed[1])

    def start_call_to(self, kind, value):
        with self.guard:
            if self.session is not None:
                raise CallError("A WhatsApp call is already in progress.")

            session = CallSession(self, kind, value)
            self.session = session

        session.start()

        return session

    def cancel(self):
        with self.guard:
            session = self.session

        if session is None:
            return False

        session.cancel()

        return True

    def wait(self, timeout=None):
        with self.guard:
            session = self.session

        if session is None:
            return True

        return session.done_event.wait(timeout)

    def session_finished(self, session):
        with self.guard:
            if self.session is session:
                self.session = None

        self.lock.unlock()

        if self.on_restore is not None:
            try:
                self.on_restore()
            except Exception:
                log.exception("The restore callback failed.")

    def handle_voice(self, candidates):
        with self.guard:
            session = self.session

        if session is not None:
            for candidate in candidates:
                if normalize(candidate) in CANCEL_PHRASES:
                    session.cancel()
                    break

            return True

        if self.agent is not None and getattr(self.agent, "paused", False):
            return False

        for candidate in candidates:
            request = parse_call_request(candidate)

            if request is None:
                continue

            try:
                self.start_call_to(request[0], request[1])
            except CallError as exc:
                self.notify("failed", str(exc))

            return True

        return False

    def install(self, agent):
        with self.guard:
            if self.agent is not None:
                return self

            original = getattr(agent, "run_voice", None)

            if not callable(original):
                raise CallError("The assistant agent has no run_voice method.")

            if self.notifier is None and callable(getattr(agent, "notify", None)):
                self.notifier = agent.notify

            def hooked(candidates):
                if self.handle_voice(candidates):
                    return None

                return original(candidates)

            self.agent = agent
            self.original_run_voice = original
            agent.run_voice = hooked

        return self

    def uninstall(self):
        with self.guard:
            if self.agent is None:
                return

            self.agent.run_voice = self.original_run_voice
            self.agent = None
            self.original_run_voice = None

    def shutdown(self, timeout=15.0):
        self.cancel()
        self.wait(timeout)
        self.uninstall()


def check_environment(config):
    report = OrderedDict()

    for name in ("speech_recognition", "pyaudio", "uiautomation", "pyautogui", "pyperclip"):
        report[name] = "ok" if import_optional(name) is not None else "missing"

    if config.tts_backend == "pyttsx3":
        report["pyttsx3"] = "ok" if import_optional("pyttsx3") is not None else "missing"

    report["whatsapp_window"] = "found" if whatsapp_windows() else "not open"
    devices = AudioDevices()

    try:
        devices.open()
        router = AudioRouter(config, devices)

        try:
            router.validate()
            report["virtual_output"] = router.virtual_output["name"]

            if config.remote_monitor_name:
                report["remote_monitor"] = router.remote_device["name"]
        except CallError as exc:
            report["virtual_output"] = str(exc)

        try:
            index = resolve_real_mic(config, devices)
            report["real_microphone"] = devices.info(index)["name"]
        except CallError as exc:
            report["real_microphone"] = str(exc)
    except CallError as exc:
        report["audio"] = str(exc)
    finally:
        devices.close()

    return report


def list_devices():
    devices = AudioDevices()

    try:
        for item in devices.devices():
            print(
                f"[{item['index']:>3}] in={item['inputs']} out={item['outputs']} "
                f"rate={item['rate']} host={item['host']} | {item['name']}"
            )
    finally:
        devices.close()


def run_mic_test(config):
    devices = AudioDevices()

    try:
        devices.open()
        index = resolve_real_mic(config, devices)
        print("Using microphone:", devices.info(index)["name"])
        stop = threading.Event()
        listener = MicListener(config, stop)
        listener.prepare(index)
        print("Speak now...")
        answers = listener.listen(config.message_languages, 12.0, config.phrase_limit)
        print("Heard:", answers if answers else "nothing")
    finally:
        devices.close()


def run_say(config, text, to_virtual):
    devices = AudioDevices()
    tts = TTSAdapter(config, None)

    try:
        devices.open()
        tts.prepare()
        index = None

        if to_virtual:
            router = AudioRouter(config, devices)
            router.validate()
            index = router.virtual_output["index"]
            print("Playing to:", router.virtual_output["name"])

        path = tts.synthesize(text)
        WavPlayer(devices).play(path, index, threading.Event())
    finally:
        tts.cleanup()
        devices.close()


def run_lock_test():
    events = []
    lock = CommandLock(lambda: events.append("locked"), lambda: events.append("unlocked"))
    lock.lock()
    lock.lock()
    locked_state = lock.locked
    lock.unlock()
    lock.unlock()

    ok = events == ["locked", "unlocked"] and locked_state and not lock.locked
    print("Command lock test:", "OK" if ok else "FAILED", events)

    return ok


def console_notifier(kind, text=""):
    print(f"[{kind.upper()}] {text}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="MH2 WhatsApp call module")
    parser.add_argument("--config")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--mic-test", action="store_true")
    parser.add_argument("--say")
    parser.add_argument("--to-virtual", action="store_true")
    parser.add_argument("--call")
    parser.add_argument("--lock-test", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | mh2_whatsapp_call | %(message)s"
    )

    try:
        config = CallConfig.load(args.config) if args.config else CallConfig()

        if args.list_devices:
            list_devices()
            return 0

        if args.check:
            for key, value in check_environment(config).items():
                print(f"{key}: {value}")

            return 0

        if args.lock_test:
            return 0 if run_lock_test() else 1

        if args.mic_test:
            run_mic_test(config)
            return 0

        if args.say:
            run_say(config, args.say, args.to_virtual)
            return 0

        if args.call:
            module = WhatsAppCallModule(
                config,
                notifier=console_notifier,
                on_lock=lambda: print("[LOCK] PC voice commands locked"),
                on_unlock=lambda: print("[LOCK] PC voice commands restored"),
                on_state=lambda old, new: print(f"[STATE] {old} -> {new}")
            )
            module.start_call(args.call)

            try:
                while not module.wait(0.5):
                    continue
            except KeyboardInterrupt:
                module.cancel()
                module.wait(30.0)

            return 0

        parser.print_help()

        return 0
    except CallError as exc:
        print(f"ERROR: {exc}")

        return 1


if __name__ == "__main__":
    sys.exit(main())
