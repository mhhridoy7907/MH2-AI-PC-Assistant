# MH2 AI PC Assistant - Single-file WhatsApp Web build (Chrome CDP / Playwright)
#
# SETUP (one time):
#   pip install playwright pygame pyaudio SpeechRecognition edge-tts imageio-ffmpeg
#   (no "playwright install" needed - your real Chrome is used)
#
# Chrome must be started with remote debugging. Either let this app launch it
# automatically, or create mh2_chrome.bat containing:
#   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\mh2_chrome_profile" --use-fake-ui-for-media-stream https://web.whatsapp.com/
#
# In that Chrome: chrome://settings/content/microphone -> choose "CABLE Output (VB-Audio Virtual Cable)"
# Log in to WhatsApp Web once (QR), then open the person's inbox and keep it open.
# In the app chat box type:  call   -> then type the message -> then type  yes
import os

if os.name != "nt":
    raise SystemExit("MH2 WhatsApp call module runs on Windows only.")

import argparse
import asyncio
import shutil
import array
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
from dataclasses import dataclass, fields
from enum import Enum

log = logging.getLogger("mh2_whatsapp_call")

NO_WINDOW = 0x08000000

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
    "confirm", "confirmed", "haan", "han", "ha", "yes please",
    # Common speech-recognition mishearings of the spoken word YES.
    "yess", "yea", "years", "year", "yas", "येस", "यस", "ইয়েস",
    "\u09b9\u09cd\u09af\u09be\u0981", "\u09b9\u09cd\u09af\u09be", "\u09b9\u09be\u0981",
    "\u09b9\u09be", "\u099c\u09bf", "\u09a0\u09bf\u0995",
    "\u0987\u09af\u09bc\u09c7\u09b8", "\u0987\u09df\u09c7\u09b8",
    "\u0987\u09df\u09c7\u09b8\u09c7\u09b8", "\u0987\u09af\u09bc\u09c7\u09b8\u09c7\u09b8",
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
    "contact_one": "I am going to call {name}. Speak clearly into your microphone. Say YES to place the call, or NO to cancel. If I hear nothing, I will not call.",
    "contact_many": "I found several contacts. {options} Say the number or the full name.",
    "contact_repeat": "Please say the number or the full name. {options}",
    "contact_confirm": "I am going to call {name}. Speak clearly into your microphone. Say YES to place the call, or NO to cancel. If I hear nothing, I will not call.",
    "contact_phone": "I will call the number {name}. Speak clearly into your microphone. Say YES to place the call, or NO to cancel. If I hear nothing, I will not call.",
    "yes_no": "I did not hear a clear answer. Speak clearly into the microphone. Say YES to place the call, or NO to cancel. Silence will cancel the call.",
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
        CallState.COLLECTING_MESSAGE, CallState.CALLING,
        CallState.ERROR, CallState.CANCELLED,
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
    # Force the physical microphone shown in --list-devices; never use Windows default/VB-CABLE.
    real_mic_name: str = "Microphone (High Definition Audio Device)"
    virtual_output_name: str = "CABLE Input"
    remote_monitor_name: str = ""
    ambient_seconds: float = 1.2
    post_speech_wait: float = 0.65
    phrase_limit: float = 25.0
    collect_timeout: float = 14.0
    confirm_timeout: float = 16.0
    max_retries: int = 3
    echo_guard_seconds: float = 0.8
    dedupe_seconds: float = 6.0
    max_message_chars: int = 900
    # auto: Bengali-script text uses Edge neural Bengali TTS; other text uses Windows speech.
    tts_backend: str = "auto"
    tts_voice: str = ""
    edge_tts_voice: str = "bn-BD-PradeepNeural"
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
    cdp_url: str = "http://127.0.0.1:9222"
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
    """Return yes/no only when the transcript contains an unambiguous answer."""
    for candidate in candidates:
        cleaned = normalize(candidate)
        tokens = set(cleaned.split())
        padded = f" {cleaned} "
        yes = bool(tokens & YES_WORDS)
        no = bool(tokens & NO_WORDS) or any(p in padded for p in NO_PHRASES)

        # ASR sometimes returns the prompt itself ("yes or no"). Never treat
        # a transcript containing both choices as consent.
        if yes and no:
            continue
        if yes:
            return "yes"
        if no:
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
        self.virtual_input = None
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
        recording = self.devices.find("CABLE Output", False)
        if recording is None:
            raise AudioDeviceError("VB-CABLE recording endpoint 'CABLE Output' was not found.")
        self.virtual_input = recording

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

        if self.custom is None and self.config.tts_backend not in ("auto", "powershell", "pyttsx3", "edge"):
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
        else:
            backend = self.config.tts_backend
            if backend == "auto":
                backend = "edge" if re.search(r"[\u0980-\u09FF]", text) else "powershell"

            if backend == "edge":
                self.render_edge_tts(text, path)
            elif backend == "pyttsx3":
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

    def render_edge_tts(self, text, path):
        """Render Bengali text with Edge neural TTS, then convert MP3 to WAV for the audio router."""
        edge_tts = import_optional("edge_tts")
        ffmpeg_module = import_optional("imageio_ffmpeg")
        if edge_tts is None or ffmpeg_module is None:
            raise TTSError(
                "Bangla neural voice needs dependencies. Run: "
                "pip install edge-tts imageio-ffmpeg"
            )

        voice = self.config.edge_tts_voice or "bn-BD-PradeepNeural"
        mp3_path = os.path.splitext(path)[0] + ".mp3"

        async def save_audio():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)

        try:
            # Run the async job in its own thread so it never clashes with an existing event loop.
            holder = {}

            def worker():
                try:
                    asyncio.run(save_audio())
                except Exception as exc:
                    holder["error"] = exc

            runner = threading.Thread(target=worker, daemon=True)
            runner.start()
            runner.join()
            if "error" in holder:
                raise holder["error"]

            ffmpeg = ffmpeg_module.get_ffmpeg_exe()
            result = subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", mp3_path,
                 "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", path],
                capture_output=True, text=True, timeout=60, check=False,
                creationflags=NO_WINDOW,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "unknown conversion error").strip()[:240]
                raise TTSError(f"Edge TTS audio conversion failed: {detail}")
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"Bangla neural TTS failed: {exc}") from exc
        finally:
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except OSError:
                log.warning("Could not remove temporary Edge TTS MP3 file.")

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
    """Controls WhatsApp Web in a Chrome started with --remote-debugging-port (CDP)."""

    def __init__(self, config, cancel_event):
        self.config = config
        self.cancel_event = cancel_event
        self.hwnd = None
        self._pw = None
        self._browser = None
        self.page = None

    def load(self):
        if import_optional("playwright.sync_api") is None:
            raise CallError("Playwright is required. Run: pip install playwright")

    def sleep(self, seconds):
        if self.cancel_event.wait(seconds):
            raise UserCancelled("Call cancelled.")

    def check(self):
        if self.cancel_event.is_set():
            raise UserCancelled("Call cancelled.")

    def close(self):
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            log.exception("Playwright could not be stopped.")
        self._pw = None
        self._browser = None
        self.page = None

    def launch_chrome(self):
        from urllib.parse import urlparse
        port = urlparse(self.config.cdp_url).port or 9222
        exe = next((p for p in (
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            shutil.which("chrome.exe")) if p and os.path.isfile(p)), None)
        if exe is None:
            raise CallError("Google Chrome could not be located.")
        profile = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "mh2_chrome_profile")
        subprocess.Popen([
            exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--use-fake-ui-for-media-stream", "--no-first-run", "https://web.whatsapp.com/",
        ])

    def connect(self):
        if self._browser is not None:
            return
        sync_playwright = import_optional("playwright.sync_api").sync_playwright
        if sync_playwright is None:
            raise CallError("Playwright is required. Run: pip install playwright")
        self._pw = sync_playwright().start()
        self.check()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self.config.cdp_url)
        except Exception as exc:
            self.close()
            raise CallError(
                "Could not attach to an existing Chrome session at "
                f"{self.config.cdp_url}. MH2 will not open Chrome or create a tab. "
                "The already-open Chrome must have remote debugging enabled, "
                "then WhatsApp Web and the target inbox must already be open."
            ) from exc

    def pages(self):
        found = []
        for ctx in self._browser.contexts:
            found.extend(ctx.pages)
        return found

    def wa_pages(self):
        return [p for p in self.pages() if "web.whatsapp.com" in (p.url or "")]

    def chat_page(self):
        pages = self.wa_pages()
        for selector in ("#main header", "#side"):
            for p in pages:
                try:
                    if p.locator(selector).count():
                        return p
                except Exception:
                    continue
        return pages[0] if pages else None

    def logged_out(self, page):
        try:
            return (page.locator("#side").count() == 0 and page.get_by_text(
                re.compile(r"Link with phone number|Log into WhatsApp|Scan the QR", re.I)).count() > 0)
        except Exception:
            return False

    def use_current_chat(self):
        self.check()
        self.connect()
        pages = self.wa_pages()
        if not pages:
            raise ContactError(
                "No existing WhatsApp Web tab was found in the current Chrome session. "
                "Open web.whatsapp.com yourself; MH2 will not open a new tab."
            )
        page = None
        for candidate in pages:
            self.check()
            try:
                if self.logged_out(candidate):
                    continue
                if candidate.locator("#main header").count() > 0:
                    page = candidate
                    break
            except Exception:
                continue
        if page is None:
            if all(self.logged_out(candidate) for candidate in pages):
                raise ContactError(
                    "WhatsApp Web is not logged in. Log in using the existing Chrome tab, "
                    "then open the target contact's inbox."
                )
            raise ContactError(
                "WhatsApp Web is open, but no contact inbox is open. "
                "Open the intended contact's conversation first; MH2 will not search, "
                "navigate, or create tabs."
            )
        self.page = page
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            text = page.locator("#main header").first.inner_text(timeout=4000)
            name = text.strip().split("\n")[0].strip()
        except Exception:
            name = ""
        return name or "the open chat"

    def header_labels(self):
        try:
            return self.page.evaluate("""() => Array.from(document.querySelectorAll(
                '#main header [aria-label], #main header [title], #main header [data-icon]'))
                .map(e => e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('data-icon'))
                .filter(Boolean)""")
        except Exception:
            return []

    def voice_button(self):
        header = self.page.locator("#main header")
        candidates = (
            header.get_by_role("button", name=re.compile(r"voice call|audio call", re.I)),
            header.locator("[aria-label*='voice call' i], [title*='voice call' i], "
                           "[aria-label*='audio call' i], [data-icon='audio-call'], [data-icon='voice-call']"),
        )
        for loc in candidates:
            if loc.count():
                return loc.first
        return None

    def start_voice_call(self):
        self.check()
        if self.page is None:
            raise CallError("WhatsApp chat is not ready.")
        self.page.bring_to_front()
        button = self.voice_button()
        if button is None:
            menu = self.page.locator("#main header").get_by_role(
                "button", name=re.compile(r"^call$|call options|start call", re.I))
            if menu.count():
                menu.first.click()
                self.sleep(0.8)
                item = self.page.get_by_role("menuitem", name=re.compile(r"voice|audio", re.I))
                if not item.count():
                    item = self.page.get_by_role("button", name=re.compile(r"voice|audio", re.I))
                if item.count():
                    button = item.first
        if button is None:
            raise CallError("Voice call button not found. Header labels: " + "; ".join(self.header_labels()[:15]))
        button.click(timeout=5000)

    def timer_text(self, page):
        try:
            return page.evaluate(r"""() => {
                const re = /^\d{1,2}:\d{2}(:\d{2})?$/;
                for (const el of document.querySelectorAll('span,div')) {
                    if (el.children.length === 0 && re.test((el.textContent || '').trim())
                        && !el.closest('#main') && !el.closest('#side')) return el.textContent.trim();
                }
                return null; }""")
        except Exception:
            return None

    def debug_text(self):
        try:
            for p in self.wa_pages():
                if p.locator("#main").count() == 0:
                    return "Call window text: " + " ".join(p.inner_text("body", timeout=1500).split())[:200]
        except Exception:
            pass
        return ""

    def call_snapshot(self):
        snap = {"in_call": False, "timer": None, "failure": None}
        for page in self.wa_pages():
            try:
                if page.get_by_role("button", name=END_RE).count():
                    snap["in_call"] = True
                    snap["timer"] = self.timer_text(page)
                fail = page.get_by_text(FAIL_RE)
                if fail.count() and fail.first.evaluate("e => !e.closest('#main')"):
                    snap["failure"] = fail.first.inner_text(timeout=500).strip()
            except Exception:
                continue
        return snap

    def wait_connected(self):
        start = time.monotonic()
        deadline = start + self.config.call_timeout
        seen, started, absent = [], False, 0
        while True:
            self.check()
            now = time.monotonic()
            if now >= deadline:
                raise CallTimeout("The call was not answered in time. " + self.debug_text())
            snap = self.call_snapshot()
            if snap["failure"]:
                raise CallFailed(f"The call failed: {snap['failure']}.")
            if snap["in_call"]:
                started, absent = True, 0
                timer = snap["timer"]
                if timer and timer not in seen:
                    seen.append(timer)
                    if len(seen) >= 2:
                        return True
            elif started:
                absent += 1
                if absent >= 3:
                    raise CallFailed("The call ended before it was answered.")
            elif now - start > self.config.call_start_grace:
                raise CallFailed("The WhatsApp call window did not appear. " + self.debug_text())
            self.sleep(self.config.connect_poll)

    def call_active(self):
        return bool(self.call_snapshot()["in_call"])

    def end_call(self):
        if self._browser is None:
            return False
        for page in self.wa_pages():
            try:
                button = page.get_by_role("button", name=END_RE)
                if button.count():
                    button.first.click(timeout=3000)
                    return True
            except Exception:
                continue
        return False

    # Only the already-open chat is supported in this build.
    def search_contacts(self, query):
        raise ContactError("Only the currently open chat is supported.")

    def open_contact(self, label, ordinal):
        raise ContactError("Only the currently open chat is supported.")

    def open_phone(self, digits):
        raise ContactError("Only the currently open chat is supported.")


class CallSession:

    def __init__(self, module, kind, value, message_text=None):
        self.module = module
        self.config = module.config
        self.kind = kind
        self.value = value
        self.typed_message = " ".join(str(message_text or "").split()).strip()
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
        self.playback_completed = False
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
        try:
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
            if self.typed_message:
                self.final_message = self.typed_message[:self.config.max_message_chars]
                self.final_locked = True
                self.message_path = self.tts.synthesize(self.final_message)
            else:
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
        if not self.typed_message:
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
        """Require a clearly recognized YES before any call can be placed.

        Silence or unclear speech never counts as consent. Retry with an explicit
        prompt, then cancel safely when the retry limit is reached.
        """
        for attempt in range(self.config.max_retries):
            self.speak_local(prompt if attempt == 0 else self.config.prompt("yes_no"))
            answers = self.listen(
                self.config.confirm_languages, self.config.confirm_timeout, 6.0
            )
            print(
                f"[VOICE CONFIRMATION] Heard: {answers if answers else 'nothing'}",
                flush=True,
            )
            decision = classify_answer(answers)

            if decision == "yes":
                print("[VOICE CONFIRMATION] YES recognized. Continuing.", flush=True)
                return

            if decision == "no":
                raise UserCancelled("NO recognized. The call was cancelled.")

            if attempt < self.config.max_retries - 1:
                print(
                    "[VOICE CONFIRMATION] No clear YES/NO detected; asking again.",
                    flush=True,
                )

        raise UserCancelled(
            "No clear YES was recognized after 3 attempts. The call was not placed."
        )

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
        if self.kind == "current":
            self.contact_label = self.whatsapp.use_current_chat()
            self.module.notify("heard", f"Calling {self.contact_label}")
            if not self.typed_message:
                self.require_yes(f"You have opened a WhatsApp chat with {self.contact_label}. Do you want to call this contact? Say yes or no.")
            return
        if self.kind == "phone":
            digits = self.value
            spoken = " ".join(digits.lstrip("+"))
            self.whatsapp.open_phone(digits)
            self.contact_label = digits
            self.require_yes(self.config.prompt("contact_phone", name=spoken))
            return

        candidates = self.whatsapp.search_contacts(self.value)[:5]

        if not candidates:
            raise ContactError(f"No WhatsApp contact matching {self.value} was found.")

        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            chosen = self.pick_contact(candidates)

        self.whatsapp.open_contact(chosen[0], chosen[1])
        self.contact_label = chosen[0]
        self.require_yes(self.config.prompt("contact_confirm", name=chosen[0]))

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
            print(f"[VOICE CONFIRMATION] Heard: {answers}", flush=True)
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
        if self.typed_message:
            return
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

        self.delivered = False
        self.playback_completed = True

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
            "done", f"WhatsApp call finished. TTS playback completed for {self.contact_label}; remote delivery is not verified."
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
            self.whatsapp.close()
        except Exception:
            log.exception("Browser connection could not be closed.")

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

    def start_call_to(self, kind, value, message_text=None):
        with self.guard:
            if self.session is not None:
                raise CallError("A WhatsApp call is already in progress.")

            if message_text is not None and not str(message_text).strip():
                raise CallError("The typed message is empty.")
            session = CallSession(self, kind, value, message_text=message_text)
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

    for name in ("speech_recognition", "pyaudio", "playwright"):
        report[name] = "ok" if import_optional(name) is not None else "missing"

    if config.tts_backend == "pyttsx3":
        report["pyttsx3"] = "ok" if import_optional("pyttsx3") is not None else "missing"
    if config.tts_backend in ("auto", "edge"):
        report["edge_tts"] = "ok" if import_optional("edge_tts") is not None else "missing (pip install edge-tts)"
        report["imageio_ffmpeg"] = "ok" if import_optional("imageio_ffmpeg") is not None else "missing (pip install imageio-ffmpeg)"

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


def cli_main(argv=None):
    """Optional command-line tools (not used by the Pygame UI)."""
    parser = argparse.ArgumentParser(description="MH2 WhatsApp call module")
    parser.add_argument("--config")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--mic-test", action="store_true")
    parser.add_argument("--say")
    parser.add_argument("--to-virtual", action="store_true")
    parser.add_argument("--call", nargs="?", const="__CURRENT_CHAT__")
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
            if args.call == "__CURRENT_CHAT__":
                module.start_call_to("current", "")
            else:
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


# ================= MH2 PYGAME ASSISTANT UI =================

import math
import random
import traceback

import pygame
import tkinter as tk

pygame.init()

TITLE = "MH2 AI PC Assistant"
FPS = 60
MIN_W, MIN_H = 800, 620
START_SIZE = (1180, 800)

BG = (3, 8, 16)
PANEL = (7, 18, 29)
CYAN = (0, 235, 255)
BLUE = (45, 115, 255)
GREEN = (60, 255, 164)
WHITE = (225, 250, 255)
MUTED = (85, 135, 158)
GRID = (8, 25, 38)
ORANGE = (255, 175, 65)
EDGE = (20, 65, 82)
FACE_DARK = (4, 21, 32)

BOOT_DURATION = 2.4
RAIN_CHARS = "01ABCDEF<>/|+-:=#"


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(current, target, rate, dt):
    return current + (target - current) * (1.0 - math.exp(-rate * dt))


def ease(x):
    x = clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def mix(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def scale_color(color, factor):
    return (
        int(clamp(color[0] * factor, 0, 255)),
        int(clamp(color[1] * factor, 0, 255)),
        int(clamp(color[2] * factor, 0, 255)),
    )


def get_clipboard_text():
    """Read Windows Unicode clipboard text without stealing app focus."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.GetClipboardData.restype = wintypes.HANDLE
            kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalUnlock.restype = wintypes.BOOL
            CF_UNICODETEXT = 13
            if not user32.OpenClipboard(None):
                return ""
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr) or ""
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            pass

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        value = root.clipboard_get()
        return value if isinstance(value, str) else ""
    except Exception:
        return ""
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


class AssistantBackend:
    name = "NONE"
    connected = False

    def start(self):
        return None

    def shutdown(self):
        return None

    def poll(self):
        return []

    def input_level(self):
        return 0.0

    def output_level(self):
        return 0.0

    def on_ai_toggle(self, active):
        return None

    def on_voice_toggle(self, enabled):
        return None

    def on_reboot(self):
        return None

    def on_chat_message(self, message):
        return None


class NullBackend(AssistantBackend):
    name = "NONE"
    connected = False


class WhatsAppTypedBackend(AssistantBackend):
    """Typed chat bridge to the WhatsApp call/TTS module."""
    name = "WHATSAPP TYPED CALL"
    connected = True

    def __init__(self):
        import queue
        callmod = sys.modules[__name__]
        self._queue = queue.Queue()
        self._threading = threading
        self._callmod = callmod
        self._module = None
        self._pending_call = False
        self._pending_message = None

    def start(self):
        return None

    def shutdown(self):
        if self._module is not None and self._module.is_active:
            self._module.cancel()

    def poll(self):
        events = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except Exception:
                break
        return events

    def on_chat_message(self, message):
        text = " ".join(str(message).split()).strip()
        lower = text.lower().strip(" .!?")
        if not self._pending_call and lower.startswith("call"):
            if self._module is not None and self._module.is_active:
                self._queue.put({"type": "status", "text": "A WhatsApp call is already running."})
                return "queued"
            self._pending_call = True
            self._pending_message = None
            self._queue.put({"type": "status", "text": "Type the message you want the AI to speak on the call."})
            return "queued"

        if self._pending_call and self._pending_message is None:
            if lower in {"cancel", "stop", "no"}:
                self._pending_call = False
                self._queue.put({"type": "status", "text": "Call cancelled."})
                return "queued"
            self._pending_message = text
            self._queue.put({"type": "status", "text": "Message preview: " + text[:180] + " | Type YES to place the call, or NO to cancel."})
            return "queued"

        if self._pending_call and self._pending_message is not None:
            if lower in {"yes", "y", "confirm"}:
                message = self._pending_message
                self._pending_call = False
                self._pending_message = None

                def notify(kind, detail=""):
                    self._queue.put({"type": "status", "text": f"{kind.upper()}: {detail}".strip()})

                def run_call():
                    try:
                        self._module = self._callmod.WhatsAppCallModule(
                            notifier=notify,
                            # Do not let cleanup's final IDLE transition overwrite the
                            # useful terminal status (ERROR / CALL_ENDED / CANCELLED).
                            on_state=lambda old, new: (
                                self._queue.put({"type": "status", "text": f"Call state: {new}"})
                                if new != "IDLE" else None
                            ),
                        )
                        self._module.start_call_to("current", "", message_text=message)
                        while not self._module.wait(0.4):
                            pass
                    except Exception as exc:
                        self._queue.put({"type": "status", "text": f"CALL ERROR: {exc}"})

                # Queue the startup notice BEFORE launching the worker so a fast
                # worker error cannot be overwritten by this late startup status.
                self._queue.put({"type": "status", "text": "Starting WhatsApp call. Connecting to Chrome and the open chat..."})
                self._threading.Thread(target=run_call, name="mh2-typed-whatsapp-call", daemon=True).start()
                return "queued"
            if lower in {"no", "cancel", "stop"}:
                self._pending_call = False
                self._pending_message = None
                self._queue.put({"type": "status", "text": "Call cancelled."})
                return "queued"
            self._queue.put({"type": "status", "text": "Type YES to confirm or NO to cancel."})
            return "queued"

        self._queue.put({"type": "status", "text": "To start: type 'call'."})
        return "queued"


class TextRenderer:
    def __init__(self):
        available = set(pygame.font.get_fonts())
        self.family = None
        for name in (
            "consolas",
            "couriernew",
            "dejavusansmono",
            "menlo",
            "liberationmono",
            "monospace",
        ):
            if name in available:
                self.family = name
                break
        self.fonts = {}
        self.cache = {}

    def font(self, size, bold=False):
        key = (size, bold)
        item = self.fonts.get(key)
        if item is None:
            item = pygame.font.SysFont(self.family, size, bold=bold)
            self.fonts[key] = item
        return item

    def render(self, value, size, color, bold=False):
        key = (value, size, color, bold)
        img = self.cache.get(key)
        if img is None:
            if len(self.cache) > 700:
                self.cache.clear()
            img = self.font(size, bold).render(value, True, color)
            self.cache[key] = img
        return img

    def width(self, value, size, bold=False):
        return self.font(size, bold).size(value)[0]

    def draw(self, surface, value, size, color, pos,
             anchor="topleft", bold=False):
        img = self.render(str(value), size, color, bold)
        rect = img.get_rect()
        setattr(rect, anchor, (int(pos[0]), int(pos[1])))
        surface.blit(img, rect)
        return rect


class GlowCache:
    def __init__(self):
        self.cache = {}

    def sprite(self, color, radius):
        quant = tuple((c // 16) * 16 for c in color)
        key = (quant, radius)
        img = self.cache.get(key)
        if img is None:
            if len(self.cache) > 140:
                self.cache.clear()
            size = radius * 2 + 1
            img = pygame.Surface((size, size), pygame.SRCALPHA)
            for i in range(radius, 0, -1):
                f = (1 - i / radius) ** 2 * 0.55
                c = (int(quant[0] * f), int(quant[1] * f), int(quant[2] * f), 255)
                pygame.draw.circle(img, c, (radius, radius), i)
            self.cache[key] = img
        return img

    def draw(self, surface, x, y, color, radius):
        radius = max(2, int(radius))
        img = self.sprite(color, radius)
        surface.blit(
            img,
            (int(x) - radius, int(y) - radius),
            special_flags=pygame.BLEND_RGB_ADD,
        )

    def dot(self, surface, x, y, color, radius=3):
        self.draw(surface, x, y, color, radius * 4)
        pygame.draw.circle(surface, color, (int(x), int(y)), max(1, radius))


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "r", "phase")

    def __init__(self, w, h):
        self.x = random.uniform(0, w)
        self.y = random.uniform(0, h)
        self.vx = random.uniform(-18, 18)
        self.vy = random.uniform(-13, 13)
        self.r = random.choice((1, 1, 2))
        self.phase = random.uniform(0, math.tau)


class Background:
    def __init__(self):
        self.w = 0
        self.h = 0
        self.static = None
        self.band = None
        self.particles = []
        self.columns = []
        self.glyphs = {}

    def resize(self, w, h, fresh=False):
        old_w, old_h = self.w, self.h
        self.w, self.h = w, h
        self.build_static()
        target = int(clamp(w * h / 11000, 50, 110))
        if fresh or not self.particles or not old_w:
            self.particles = [Particle(w, h) for _ in range(target)]
        else:
            sx = w / old_w
            sy = h / old_h
            for p in self.particles:
                p.x *= sx
                p.y *= sy
            while len(self.particles) > target:
                self.particles.pop()
            while len(self.particles) < target:
                self.particles.append(Particle(w, h))
        count = max(8, w // 42)
        self.columns = []
        for i in range(count):
            length = random.randint(7, 15)
            self.columns.append([
                (i + random.random() * 0.8) * (w / count),
                random.uniform(-h, h),
                random.uniform(35, 110),
                length,
                [random.choice(RAIN_CHARS) for _ in range(length)],
            ])

    def build_static(self):
        w, h = self.w, self.h
        base = pygame.Surface((w, h))
        base.fill(BG)
        grid = 44
        for x in range(0, w, grid):
            pygame.draw.line(base, GRID, (x, 0), (x, h))
        for y in range(0, h, grid):
            pygame.draw.line(base, GRID, (0, y), (w, y))
        for x in range(0, w, grid * 4):
            for y in range(0, h, grid * 4):
                pygame.draw.circle(base, (16, 52, 70), (x, y), 2)
        rng = random.Random(7)
        for _ in range(90):
            pygame.draw.circle(
                base,
                (24, 65, 82),
                (rng.randrange(max(1, w)), rng.randrange(max(1, h))),
                rng.choice((1, 1, 2)),
            )
        vig = pygame.Surface((48, 30), pygame.SRCALPHA)
        for yy in range(30):
            for xx in range(48):
                dx = (xx - 23.5) / 24
                dy = (yy - 14.5) / 15
                d = min(1.0, math.hypot(dx, dy) / 1.25)
                vig.set_at((xx, yy), (0, 0, 0, int(190 * d ** 2.3)))
        vig = pygame.transform.smoothscale(vig, (w, h))
        base.blit(vig, (0, 0))
        self.static = base.convert()
        band = pygame.Surface((w, 46))
        band.fill((0, 0, 0))
        for k in range(46):
            c = int(34 * math.sin(k / 45 * math.pi) ** 2)
            pygame.draw.line(band, (0, c, int(c * 1.2)), (0, k), (w, k))
        self.band = band.convert()

    def glyph(self, text, ch, level, act_q):
        key = (ch, level, act_q)
        img = self.glyphs.get(key)
        if img is None:
            base = mix(CYAN, GREEN, act_q / 4)
            color = mix((3, 8, 16), base, 0.05 + 0.07 * level)
            img = text.font(12).render(ch, True, color)
            self.glyphs[key] = img
        return img

    def draw(self, screen, glow, text, dt, t, act, mouse):
        w, h = self.w, self.h
        screen.blit(self.static, (0, 0))
        act_q = int(round(act * 4))
        for col in self.columns:
            col[1] += col[2] * dt * (1 + 0.8 * act)
            length = col[3]
            if col[1] - length * 14 > h:
                col[1] = random.uniform(-200, 0)
                col[2] = random.uniform(35, 110)
            if random.random() < dt * 9:
                col[4][random.randrange(length)] = random.choice(RAIN_CHARS)
            for j in range(length):
                y = col[1] - j * 14
                if y < -14 or y > h:
                    continue
                level = int((1 - j / length) * 5)
                screen.blit(self.glyph(text, col[4][j], level, act_q),
                            (int(col[0]), int(y)))

        band_y = int((t * 55) % (h + 120)) - 60
        screen.blit(self.band, (0, band_y), special_flags=pygame.BLEND_RGB_ADD)

        speed = 1.0 + 0.6 * act
        for p in self.particles:
            p.x += p.vx * dt * speed
            p.y += p.vy * dt * speed
            if p.x < 0:
                p.x = w
            elif p.x > w:
                p.x = 0
            if p.y < 0:
                p.y = h
            elif p.y > h:
                p.y = 0

        limit = 100.0
        limit_sq = limit * limit
        base_line = mix((0, 40, 55), (0, 70, 70), act)
        parts = self.particles
        for i, p in enumerate(parts):
            for q in parts[i + 1:]:
                dx, dy = p.x - q.x, p.y - q.y
                d2 = dx * dx + dy * dy
                if d2 < limit_sq:
                    f = 1 - d2 / limit_sq
                    pygame.draw.line(
                        screen,
                        (int(base_line[0] * f * 1.5),
                         int(base_line[1] * f * 1.5),
                         int(base_line[2] * f * 1.5)),
                        (int(p.x), int(p.y)), (int(q.x), int(q.y)),
                    )

        mx, my = mouse
        reach_sq = 150.0 ** 2
        mouse_color = mix(CYAN, GREEN, act)
        for p in parts:
            dx, dy = p.x - mx, p.y - my
            d2 = dx * dx + dy * dy
            if d2 < reach_sq:
                f = (1 - d2 / reach_sq) * 0.5
                pygame.draw.line(
                    screen,
                    (int(mouse_color[0] * f), int(mouse_color[1] * f),
                     int(mouse_color[2] * f)),
                    (int(p.x), int(p.y)), (mx, my),
                )

        color = mix(CYAN, GREEN, act)
        for p in parts:
            twinkle = 0.7 + 0.3 * math.sin(t * 2 + p.phase)
            if p.r == 2:
                glow.draw(screen, p.x, p.y, mix((0, 30, 40), color, 0.35), 7)
                pygame.draw.circle(screen, color, (int(p.x), int(p.y)), 2)
            else:
                pygame.draw.circle(
                    screen, (0, int(155 + 80 * twinkle), int(175 + 70 * twinkle)),
                    (int(p.x), int(p.y)), 1,
                )


class Face:
    def __init__(self):
        self.reset()

    def reset(self):
        self.blink_start = None
        self.double = False
        self.next_blink = 2.0
        self.gaze = [0.0, 0.0]

    def blink_amount(self, t):
        if self.blink_start is None:
            if t < self.next_blink:
                return 0.0
            self.blink_start = t
            self.double = random.random() < 0.22
        p = (t - self.blink_start) / 0.2
        if p < 0:
            return 0.0
        if p >= 1:
            if self.double:
                self.double = False
                self.blink_start = t + 0.07
                return 0.0
            self.blink_start = None
            self.next_blink = t + random.uniform(2.4, 5.6)
            return 0.0
        return math.sin(p * math.pi)


class Equalizer:
    def __init__(self, count=41):
        self.count = count
        self.reset()

    def reset(self):
        self.values = [0.0] * self.count
        self.peaks = [0.0] * self.count

    def update(self, dt, t, act, level):
        center = (self.count - 1) / 2
        for i in range(self.count):
            d = abs(i - center) / center
            env = 1 - 0.6 * d
            ambient = (0.07 + 0.04 * math.sin(t * 2.2 + i * 0.5)
                       + 0.05 * act * abs(math.sin(t * 1.7 + i * 0.31)))
            lively = level * env * (
                0.35 + 0.65 * abs(
                    math.sin(t * 7.5 + i * 0.9) *
                    math.cos(t * 3.3 + i * 0.37)
                )
            ) * 1.4
            target = clamp(ambient + lively, 0.0, 1.0)
            rate = 18 if target > self.values[i] else 7
            self.values[i] = smooth(self.values[i], target, rate, dt)
            self.peaks[i] = max(self.values[i], self.peaks[i] - dt * 0.45)

    def draw(self, screen, cx, cy, width, max_h, act):
        n = self.count
        gap = 3
        bar_w = max(2, (width - (n - 1) * gap) // n)
        total = n * bar_w + (n - 1) * gap
        start = int(cx - total / 2)
        dim = mix((0, 70, 85), (20, 100, 75), act)
        hot = mix(CYAN, GREEN, act)
        for i in range(n):
            v = self.values[i]
            hgt = max(3, int(max_h * v))
            rect = pygame.Rect(start + i * (bar_w + gap),
                               int(cy - hgt / 2), bar_w, hgt)
            pygame.draw.rect(screen, mix(dim, hot, v * 1.1),
                             rect, border_radius=2)
            cap = int(max_h * self.peaks[i]) // 2
            if cap > hgt // 2 + 2:
                pygame.draw.line(screen, hot, (rect.left, cy - cap),
                                 (rect.left + bar_w - 1, cy - cap))
                pygame.draw.line(screen, hot, (rect.left, cy + cap),
                                 (rect.left + bar_w - 1, cy + cap))


class Button:
    def __init__(self, hint, warning=False):
        self.rect = pygame.Rect(0, 0, 10, 10)
        self.hint = hint
        self.warning = warning
        self.hover = 0.0
        self.press = 0.0
        self.hot = False

    def update(self, mouse, dt, down):
        self.hot = self.rect.collidepoint(mouse)
        self.hover = smooth(self.hover, 1.0 if self.hot else 0.0, 14, dt)
        self.press = smooth(self.press,
                            1.0 if (self.hot and down) else 0.0, 26, dt)

    def draw(self, screen, text, label, selected):
        color = ORANGE if self.warning else (GREEN if selected else CYAN)
        rect = self.rect.inflate(-int(4 * self.press), -int(4 * self.press))
        fill = mix((5, 17, 28), color,
                   0.05 + 0.10 * self.hover + (0.07 if selected else 0.0))
        pygame.draw.rect(screen, fill, rect, border_radius=8)
        pygame.draw.rect(screen, mix(scale_color(color, 0.55), color, self.hover), rect, 1, border_radius=8)
        pygame.draw.line(screen, color, (rect.left + 9, rect.top + 9), (rect.left + 9, rect.bottom - 9), 2)
        bar = int((rect.w - 28) * self.hover)

        text.draw(screen, label, 13, WHITE if self.hot or selected else mix(WHITE, MUTED, 0.3),
                  rect.center, "center", True)
        text.draw(screen, self.hint, 9, MUTED, (rect.right - 8, rect.top + 6), "topright")

        if bar > 0:
            cx = rect.centerx
            pygame.draw.line(
                screen, color,
                (cx - bar // 2, rect.bottom - 4),
                (cx + bar // 2, rect.bottom - 4),
                2
            )


class App:
    def __init__(self, backend=None):
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode(START_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.text = TextRenderer()
        self.glow = GlowCache()
        self.background = Background()
        self.face = Face()
        self.equalizer = Equalizer()
        self.backend = backend or NullBackend()

        self.running = True
        self.active = False
        self.voice_mode = False
        self.act = 0.0
        self.voice_vis = 0.0
        self.level = 0.0
        self.input_level = 0.0
        self.output_level = 0.0

        self.t0 = time.perf_counter()
        self.t = 0.0
        self.dt = 1 / FPS

        self.w = 0
        self.h = 0
        self.L = {}
        self.scan = None
        self.boot_surface = None
        self.sweep_surface = None
        self.cursor_hand = False

        self.frame_ms = deque(maxlen=70)
        self.level_history = deque(maxlen=70)
        self.logs = deque(maxlen=40)

        # Compact bottom chat bar
        self.chat_text = ""
        self.chat_focused = False
        self.chat_messages = deque(maxlen=3)
        self.chat_rect = pygame.Rect(0, 0, 10, 10)
        self.chat_send_rect = pygame.Rect(0, 0, 10, 10)

        self.status = "BOOTING INTERFACE"
        self.status_at = 0.0
        self.status_until = 0.0

        self.buttons = {
            "activate": Button("SPACE"),
            "voice": Button("V"),
            "reboot": Button("R", warning=True),
        }

        self.booting = False
        self.boot_t0 = 0.0
        self.boot_queue = []

        self.safe_call(self.backend.start)
        self.sync_size()
        self.begin_boot()

    def safe_call(self, func, *args, default=None):
        try:
            return func(*args)
        except Exception as exc:
            self.log("BACKEND ERROR: " + type(exc).__name__)
            return default

    def log(self, message):
        self.logs.append((time.strftime("%H:%M:%S"), str(message)))

    def begin_boot(self):
        self.booting = True
        self.boot_t0 = self.t
        connected = bool(getattr(self.backend, "connected", False))
        self.boot_queue = [
            (0.25, "DISPLAY CONTEXT READY"),
            (0.80, "RENDER PIPELINE ONLINE"),
            (1.30, "BACKEND " + ("CONNECTED" if connected else "NOT CONNECTED")),
            (1.80, "INTERFACE READY"),
        ]
        self.set_status("BOOTING INTERFACE", 0)

    def idle_status(self):
        if self.active:
            return "AI CORE READY"
        if self.voice_mode:
            return "VOICE VISUALIZER ACTIVE"
        return "SYSTEM STANDBY"

    def set_status(self, message, duration=2.6):
        self.status = message
        self.status_at = self.t
        self.status_until = self.t + duration if duration else 0.0

    def set_active(self, value, notify=True):
        self.active = bool(value)
        if self.active:
            self.set_status("AI CORE ACTIVATED")
            self.log("AI STATE: ACTIVE")
        else:
            self.set_status("SYSTEM STANDBY")
            self.log("AI STATE: STANDBY")
        if notify:
            self.safe_call(self.backend.on_ai_toggle, self.active)

    def set_voice(self, value, notify=True):
        self.voice_mode = bool(value)
        if self.voice_mode:
            self.set_status("VOICE VISUALIZER ACTIVE")
            self.log("VOICE MODE: ON")
        else:
            self.set_status("VOICE MODE DISABLED")
            self.log("VOICE MODE: OFF")
        if notify:
            self.safe_call(self.backend.on_voice_toggle, self.voice_mode)

    def toggle_ai(self):
        self.set_active(not self.active)

    def toggle_voice(self):
        self.set_voice(not self.voice_mode)

    def reboot(self):
        self.active = False
        self.voice_mode = False
        self.background.resize(self.w, self.h, fresh=True)
        self.face.reset()
        self.equalizer.reset()
        self.log("SYSTEM REBOOT")
        self.safe_call(self.backend.on_reboot)
        self.begin_boot()

    def apply_backend_event(self, event):
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if kind == "status":
            self.set_status(str(event.get("text", "")))
        elif kind == "log":
            self.log(event.get("text", ""))
        elif kind == "active":
            self.set_active(event.get("value", False), notify=False)
        elif kind == "voice":
            self.set_voice(event.get("value", False), notify=False)

    def sync_size(self):
        surf = pygame.display.get_surface()
        w, h = surf.get_size()
        if w < MIN_W or h < MIN_H:
            surf = pygame.display.set_mode(
                (max(w, MIN_W), max(h, MIN_H)), pygame.RESIZABLE
            )
            w, h = surf.get_size()
        self.screen = surf
        if (w, h) != (self.w, self.h):
            self.w, self.h = w, h
            self.rebuild()

    def rebuild(self):
        w, h = self.w, self.h
        self.background.resize(w, h)
        self.scan = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 3):
            pygame.draw.line(self.scan, (0, 0, 0, 36), (0, y), (w, y))
        self.scan = self.scan.convert_alpha()
        self.boot_surface = pygame.Surface((w, h))
        self.boot_surface.fill((0, 0, 0))
        self.compute_layout()

    @staticmethod
    def panel_height(rows, spark):
        return 54 + rows * 27 + (40 if spark else 0) + 4

    def compute_layout(self):
        w, h = self.w, self.h
        cx = w // 2
        L = {}
        L["cx"] = cx
        L["header"] = pygame.Rect(18, 14, w - 36, 58)

        bs = int(clamp(h * 0.075, 42, 68))
        button_y = h - 150
        eq_y = button_y - 38
        status_y = eq_y - 32
        line2_y = status_y - 30
        line1_y = line2_y - 20
        brand_y = line1_y - 14 - bs // 2
        top_limit = 88
        bottom_limit = brand_y - bs // 2 - 12
        avail = max(120, bottom_limit - top_limit)
        radius = int(clamp(avail / 2 - 48, 48, 120))
        radius = int(min(radius, w * 0.14))
        core_y = top_limit + avail // 2

        L.update(bs=bs, button_y=button_y, eq_y=eq_y,
                 status_y=status_y, line1_y=line1_y, line2_y=line2_y,
                 brand_y=brand_y, radius=radius, core_y=core_y)

        bw = int(clamp((w - 70) / 3.3, 130, 180))
        bh = 42
        gap = 10
        total = bw * 3 + gap * 2
        sx = cx - total // 2
        for i, key in enumerate(("activate", "voice", "reboot")):
            self.buttons[key].rect = pygame.Rect(sx + i * (bw + gap),
                                                  button_y, bw, bh)

        L["side"] = w >= 1000
        pw = 200
        panel_top = max(96, core_y - 120)
        tel_h = self.panel_height(5, True)
        L["tel"] = pygame.Rect(24, panel_top, pw, tel_h)
        L["status_panel"] = pygame.Rect(w - 24 - pw, panel_top, pw, tel_h)

        log_top = panel_top + tel_h + 14
        log_h = min(176, button_y - 12 - log_top)
        L["log"] = pygame.Rect(24, log_top, pw, log_h) if log_h >= 96 else None
        ctl_h = self.panel_height(4, False)
        ctl_top = panel_top + tel_h + 14
        L["controls"] = (
            pygame.Rect(w - 24 - pw, ctl_top, pw, ctl_h)
            if ctl_top + ctl_h <= button_y - 12 else None
        )
        self.L = L

        chat_w = min(660, w - 48)
        chat_x = (w - chat_w) // 2
        chat_y = h - 82
        self.chat_rect = pygame.Rect(chat_x, chat_y, chat_w, 36)
        self.chat_send_rect = pygame.Rect(
            self.chat_rect.right - 72, chat_y + 4, 64, 28
        )

    def bracket(self, rect, color, size=10):
        s = self.screen
        x0, y0, x1, y1 = rect.left, rect.top, rect.right - 1, rect.bottom - 1
        for x, y, dx, dy in (
            (x0, y0, 1, 1), (x1, y0, -1, 1),
            (x0, y1, 1, -1), (x1, y1, -1, -1),
        ):
            pygame.draw.line(s, color, (x, y), (x + dx * size, y), 2)
            pygame.draw.line(s, color, (x, y), (x, y + dy * size), 2)

    def sparkline(self, rect, values, color, vmax):
        if len(values) < 2:
            return
        n = len(values)
        pts = []
        for i, v in enumerate(values):
            x = rect.left + rect.w * i / (n - 1)
            y = rect.bottom - rect.h * clamp(v / vmax, 0.0, 1.0)
            pts.append((x, y))
        poly = pts + [(rect.right, rect.bottom), (rect.left, rect.bottom)]
        pygame.draw.polygon(self.screen, scale_color(color, 0.18), poly)
        pygame.draw.lines(self.screen, color, False, pts, 1)

    def draw_panel(self, rect, title, rows, spark=None, spark_max=1.0):
        s = self.screen
        color = mix(CYAN, GREEN, self.act)
        pygame.draw.rect(s, PANEL, rect, border_radius=10)
        pygame.draw.rect(s, EDGE, rect, 1, border_radius=10)
        self.bracket(rect, scale_color(color, 0.8), 9)
        self.text.draw(s, title, 12, color, (rect.x + 14, rect.y + 14), bold=True)
        pygame.draw.line(s, EDGE, (rect.x + 12, rect.y + 38),
                         (rect.right - 12, rect.y + 38))
        for i, (label, value, vcolor) in enumerate(rows):
            yy = rect.y + 50 + i * 27
            self.text.draw(s, label, 11, MUTED, (rect.x + 14, yy))
            self.text.draw(s, value, 11, vcolor,
                           (rect.right - 14, yy), "topright", True)
        if spark is not None:
            area = pygame.Rect(rect.x + 14, rect.bottom - 40, rect.w - 28, 28)
            self.sparkline(area, spark, color, spark_max)

    def draw_log(self, rect):
        s = self.screen
        color = mix(CYAN, GREEN, self.act)
        pygame.draw.rect(s, PANEL, rect, border_radius=10)
        pygame.draw.rect(s, EDGE, rect, 1, border_radius=10)
        self.bracket(rect, scale_color(color, 0.8), 9)
        self.text.draw(s, "EVENT LOG", 12, color,
                       (rect.x + 14, rect.y + 14), bold=True)
        pygame.draw.line(s, EDGE, (rect.x + 12, rect.y + 38),
                         (rect.right - 12, rect.y + 38))
        line_h = 17
        capacity = max(1, (rect.h - 50) // line_h)
        entries = list(self.logs)[-capacity:]
        for i, (stamp, message) in enumerate(entries):
            line = stamp + " " + message
            while self.text.width(line, 10) > rect.w - 26 and len(line) > 12:
                line = line[:-2]
            age = len(entries) - 1 - i
            shade = mix(MUTED, WHITE, 0.55 if age == 0 else 0.0)
            self.text.draw(s, line, 10, shade,
                           (rect.x + 14, rect.y + 48 + i * line_h))

    def draw_ring(self, cx, cy, radius, angle, color,
                  segments=8, thickness=2, fraction=0.55):
        if radius <= 0:
            return
        rect = pygame.Rect(int(cx - radius), int(cy - radius),
                           int(radius * 2), int(radius * 2))
        for i in range(segments):
            start = angle + i * math.tau / segments
            end = start + math.tau / segments * fraction
            pygame.draw.arc(self.screen, color, rect, start, end, thickness)

    def draw_ticks(self, cx, cy, radius, color, rotation):
        dim = (20, 75, 90)
        for i in range(72):
            angle = rotation + i * math.tau / 72
            major = i % 6 == 0
            inner = radius - (12 if major else 5)
            ca, sa = math.cos(angle), math.sin(angle)
            pygame.draw.line(
                self.screen, color if major else dim,
                (cx + ca * inner, cy + sa * inner),
                (cx + ca * radius, cy + sa * radius),
                2 if major else 1,
            )

    def draw_core(self, cx, cy, base_r, mouse):
        s = self.screen
        t, act, dt = self.t, self.act, self.dt
        color = mix(CYAN, GREEN, act)
        pulse = 1 + 0.022 * math.sin(t * lerp(1.5, 3.2, act))
        r = int(base_r * pulse)
        self.glow.draw(s, cx, cy, mix((0, 44, 58), (8, 70, 52), act),
                       base_r + 60)

        size = (base_r + 64) * 2
        if self.sweep_surface is None or self.sweep_surface.get_width() != size:
            self.sweep_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        sw = self.sweep_surface
        sw.fill((0, 0, 0, 0))
        c = size // 2
        angle = t * 1.3
        rad = r + 32
        steps = 22
        for i in range(steps, 0, -1):
            a0 = angle - i * 0.045
            a1 = a0 + 0.05
            alpha = int(70 * (1 - i / steps) ** 1.6 * (0.45 + 0.55 * act))
            pts = [
                (c, c),
                (c + math.cos(a0) * rad, c + math.sin(a0) * rad),
                (c + math.cos(a1) * rad, c + math.sin(a1) * rad),
            ]
            pygame.draw.polygon(sw, (*color, alpha), pts)
        pygame.draw.line(sw, (*color, 190), (c, c),
                         (c + math.cos(angle) * rad, c + math.sin(angle) * rad), 1)
        s.blit(sw, (cx - c, cy - c))

        self.draw_ring(cx, cy, r + 35, t * 0.22, MUTED, 16, 1, 0.2)
        self.draw_ring(cx, cy, r + 24, -t * 0.45, BLUE, 8, 2)
        self.draw_ring(cx, cy, r + 10, t * 0.75, color, 5, 2)
        self.draw_ring(cx, cy, r - 6, -t * 0.4, GREEN, 3, 2)
        self.draw_ticks(cx, cy, r + 44, color, t * 0.08)

        for i in range(12):
            base = t * 0.5 + i * math.tau / 12
            orbit = r + (18 if i % 2 else 30)
            for k in (3, 2, 1):
                a = base - k * 0.05
                pygame.draw.circle(s, scale_color(color, 0.18 * (4 - k)),
                                   (int(cx + math.cos(a) * orbit),
                                    int(cy + math.sin(a) * orbit)), 1)
            self.glow.dot(s, cx + math.cos(base) * orbit,
                          cy + math.sin(base) * orbit,
                          GREEN if i % 3 == 0 else color,
                          3 if i % 3 == 0 else 2)

        fw, fh = int(r * 1.1), int(r * 1.2)
        face = pygame.Rect(0, 0, fw, fh)
        face.center = (cx, cy)
        rad_corner = max(14, int(r * 0.22))
        for side in (-1, 1):
            ear = pygame.Rect(0, 0, 8, int(r * 0.3))
            ear.centery = cy
            if side < 0:
                ear.right = face.left - 2
            else:
                ear.left = face.right + 2
            pygame.draw.rect(s, FACE_DARK, ear, border_radius=3)
            pygame.draw.rect(s, scale_color(color, 0.7), ear, 1, border_radius=3)

        pygame.draw.rect(s, FACE_DARK, face, border_radius=rad_corner)
        inner = face.inflate(-14, -14)
        pygame.draw.rect(s, (6, 28, 42), inner,
                         border_radius=max(10, rad_corner - 6))
        pygame.draw.rect(s, mix((15, 75, 91), color, 0.2),
                         face.inflate(4, 4), 1, border_radius=rad_corner + 2)
        pygame.draw.rect(s, color, face, 2, border_radius=rad_corner)

        for i in range(5):
            vx = cx - 32 + i * 16
            pygame.draw.line(s, (20, 90, 108),
                             (vx, face.top + 9), (vx + 8, face.top + 9))

        scan_pos = (t * 0.4) % 1.0
        scan_y = int(face.top + 18 + (face.h - 36) * scan_pos)
        pygame.draw.line(s, mix((6, 28, 42), color, 0.35),
                         (face.left + 14, scan_y), (face.right - 14, scan_y))

        f = self.face
        blink = f.blink_amount(t)
        openness = max(0.06, lerp(0.55, 1.0, act) * (1 - blink))
        mx, my = mouse
        tx = clamp((mx - cx) / max(1.0, self.w * 0.5), -1, 1)
        ty = clamp((my - cy) / max(1.0, self.h * 0.5), -1, 1)
        f.gaze[0] = smooth(f.gaze[0], tx + 0.25 * math.sin(t * 0.7), 5, dt)
        f.gaze[1] = smooth(f.gaze[1], ty * 0.8 + 0.15 * math.sin(t * 0.9 + 1), 5, dt)
        gx, gy = f.gaze[0] * r * 0.035, f.gaze[1] * r * 0.02

        eye_y = cy - r * 0.14
        eye_gap = r * 0.27
        eye_w = max(14, int(r * 0.27))
        eye_hmax = max(8, int(r * 0.16))
        eye_color = mix(color, WHITE, 0.1)
        for side in (-1, 1):
            ex = cx + side * eye_gap
            socket = pygame.Rect(0, 0, eye_w + 14, eye_hmax + 12)
            socket.center = (int(ex), int(eye_y))
            pygame.draw.rect(s, (2, 12, 20), socket, border_radius=9)
            pygame.draw.rect(s, (14, 60, 76), socket, 1, border_radius=9)
            eh = max(2, int(eye_hmax * openness))
            eye = pygame.Rect(0, 0, eye_w, eh)
            eye.center = (int(ex + gx), int(eye_y + gy))
            self.glow.draw(s, eye.centerx, eye.centery,
                           mix((0, 60, 70), (20, 90, 70), act), int(r * 0.28))
            pygame.draw.ellipse(s, eye_color, eye)
            if eh > 6:
                core = eye.inflate(-int(eye_w * 0.4), -int(eh * 0.4))
                pygame.draw.ellipse(s, mix(color, WHITE, 0.6), core)
                pygame.draw.circle(s, WHITE,
                                   (eye.centerx - eye_w // 5, eye.centery - eh // 5), 2)
            brow_y = eye_y - eye_hmax - 12
            tilt = lerp(1.0, 4.0, act)
            pygame.draw.line(s, scale_color(color, 0.8),
                             (ex - eye_w * 0.6, brow_y + side * tilt),
                             (ex + eye_w * 0.6, brow_y - side * tilt), 2)

        mouth_y = int(cy + r * 0.27)
        bars = 11
        bw = max(3, int(r * 0.035))
        gap = max(2, int(r * 0.025))
        total = bars * bw + (bars - 1) * gap
        start = int(cx - total / 2)
        level = self.level
        self.glow.draw(s, cx, mouth_y,
                       mix((0, 40, 50), (10, 60, 45), act),
                       int(r * (0.22 + 0.2 * level)))
        for i in range(bars):
            d = abs(i - (bars - 1) / 2) / ((bars - 1) / 2)
            env = 1 - 0.7 * d
            wave = (abs(math.sin(t * 9 + i * 0.8)) * 0.6
                    + abs(math.sin(t * 5.3 + i * 1.7)) * 0.4)
            hgt = 2 + int(1.5 * abs(math.sin(t * 2 + i * 0.5)) * (0.4 + act))
            hgt += int(r * 0.16 * level * env * wave * 1.3)
            rect = pygame.Rect(start + i * (bw + gap),
                               mouth_y - hgt // 2, bw, hgt)
            pygame.draw.rect(s, color, rect, border_radius=1)

        phase = int(t * 2.5) % 3
        for i in range(3):
            on = self.active and phase == i
            dot_color = color if on else (14, 60, 76)
            x, y = cx - 14 + i * 14, int(cy + r * 0.46)
            if on:
                self.glow.dot(s, x, y, dot_color, 2)
            else:
                pygame.draw.circle(s, dot_color, (x, y), 2)

    def draw_header(self):
        s = self.screen
        hd = self.L["header"]
        color = mix(CYAN, GREEN, self.act)
        pygame.draw.rect(s, (4, 14, 24), hd, border_radius=10)
        pygame.draw.rect(s, (18, 60, 78), hd, 1, border_radius=10)
        self.bracket(hd, scale_color(color, 0.8), 10)
        self.glow.dot(s, hd.left + 24, hd.centery, color, 4)
        self.text.draw(s, "MH2 // NEURAL INTERFACE", 16, WHITE,
                       (hd.left + 42, hd.top + 10), bold=True)
        self.text.draw(s, "PERSONAL AI SYSTEM  /  BUILD 2.7", 11, MUTED,
                       (hd.left + 43, hd.top + 32))
        self.text.draw(s, time.strftime("%H:%M:%S"), 16, WHITE,
                       (hd.right - 18, hd.top + 10), "topright", True)
        self.text.draw(s, "AI ACTIVE" if self.active else "SYSTEM STANDBY", 11,
                       GREEN if self.active else MUTED,
                       (hd.right - 18, hd.top + 32), "topright")
        if hd.w > 760:
            n = 28
            sx = hd.centerx - (n * 6) // 2
            for i in range(n):
                v = 0.25 + 0.75 * abs(
                    math.sin(self.t * 2.4 + i * 0.5) *
                    math.cos(self.t * 1.1 + i * 0.21)
                ) * (0.3 + 0.7 * max(self.act, self.level))
                hh = max(2, int(24 * v))
                pygame.draw.rect(s, mix((0, 70, 85), color, v),
                                 (sx + i * 6, hd.centery - hh // 2, 3, hh))

    def draw_branding(self):
        s, L = self.screen, self.L
        cx, bs = L["cx"], L["bs"]
        glow_color = mix((0, 50, 62), (10, 78, 55), self.act)
        self.glow.draw(s, cx, L["brand_y"], glow_color, bs)
        self.text.draw(s, "MH2", bs, WHITE, (cx, L["brand_y"]), "center", True)
        self.text.draw(s, "ARTIFICIAL INTELLIGENCE", 13, GREEN,
                       (cx, L["line1_y"]), "center", True)
        self.text.draw(s, "YOUR PERSONAL DIGITAL ASSISTANT", 10, MUTED,
                       (cx, L["line2_y"]), "center")

    def draw_status(self):
        s, L = self.screen, self.L
        cx, y = L["cx"], L["status_y"]
        color = mix(CYAN, GREEN, self.act)
        full = self.status
        width = self.text.width(full, 13, True)
        shown = int((self.t - self.status_at) * 55) + 1
        part = full[:shown]
        if shown <= len(full) and int(self.t * 6) % 2 == 0:
            part += "_"
        left = cx - width // 2
        self.glow.dot(s, left - 20, y, color, 3)
        if part:
            self.text.draw(s, part, 13, color, (left, y), "midleft", True)

    def draw_footer(self):
        s = self.screen
        w, h = self.w, self.h
        pygame.draw.line(s, (15, 45, 60), (22, h - 31), (w - 22, h - 31))
        self.text.draw(s, "MH2 SYSTEMS", 10, CYAN, (24, h - 23))
        self.text.draw(s, "NEURAL INTERFACE", 10, MUTED,
                       (self.L["cx"], h - 23), "midtop")
        self.text.draw(s, f"{self.clock.get_fps():.0f} FPS  |  {w}x{h}",
                       10, MUTED, (w - 24, h - 23), "topright")

    def draw_boot(self):
        if not self.booting:
            return
        bt = self.t - self.boot_t0
        alpha = int(255 * (1 - ease((bt - 0.9) / 1.3)))
        if alpha <= 0:
            return
        self.boot_surface.set_alpha(alpha)
        self.screen.blit(self.boot_surface, (0, 0))
        if alpha > 20:
            s = self.screen
            cx, cy = self.w // 2, self.h // 2
            self.text.draw(s, "BOOTING NEURAL INTERFACE", 16, CYAN,
                           (cx, cy - 18), "center", True)
            bar = pygame.Rect(0, 0, 280, 6)
            bar.center = (cx, cy + 12)
            pygame.draw.rect(s, (10, 34, 46), bar, border_radius=3)
            fill = bar.copy()
            fill.w = int(bar.w * clamp(bt / 2.0, 0.0, 1.0))
            pygame.draw.rect(s, CYAN, fill, border_radius=3)
            self.text.draw(s, f"{int(clamp(bt / 2.0, 0.0, 1.0) * 100):d}%",
                           11, MUTED, (cx, cy + 30), "center")

    def update_levels(self):
        bk, t = self.backend, self.t
        connected = bool(getattr(bk, "connected", False))
        target = 0.0
        if connected:
            out = clamp(float(self.safe_call(bk.output_level, default=0.0) or 0.0), 0.0, 1.0)
            inp = clamp(float(self.safe_call(bk.input_level, default=0.0) or 0.0), 0.0, 1.0)
            self.output_level = smooth(self.output_level, out, 14, self.dt)
            self.input_level = smooth(self.input_level, inp, 14, self.dt)
            target = max(out, inp)
        else:
            self.output_level = smooth(self.output_level, 0.0, 8, self.dt)
            self.input_level = smooth(self.input_level, 0.0, 8, self.dt)
            if self.voice_mode:
                target = 0.5 + 0.28 * math.sin(t * 2.3) * math.sin(t * 0.7 + 1)
        self.level = smooth(self.level, target, 10, self.dt)

    def update(self):
        dt, t = self.dt, self.t
        self.frame_ms.append(dt * 1000.0)
        events = self.safe_call(self.backend.poll, default=[]) or []
        for event in events:
            if isinstance(event, dict) and event.get("type") == "status":
                message = str(event.get("text", ""))
                # Keep failures visible long enough for the user to read them.
                persistent = any(token in message.upper() for token in ("ERROR", "FAILED", "NOT FOUND", "COULD NOT", "REQUIRES LOGIN", "LOGIN NEEDED"))
                self.set_status(message[:150], 15.0 if persistent else 6.0)
                self.log("AI: " + message[:180])
                continue
            self.apply_backend_event(event)

        self.act = smooth(self.act, 1.0 if self.active else 0.0, 4, dt)
        self.voice_vis = smooth(self.voice_vis, 1.0 if self.voice_mode else 0.0, 6, dt)
        self.update_levels()
        self.level_history.append(self.level)

        if self.booting:
            bt = t - self.boot_t0
            while self.boot_queue and bt >= self.boot_queue[0][0]:
                self.log(self.boot_queue.pop(0)[1])
            if bt >= BOOT_DURATION:
                self.booting = False
                self.set_status(self.idle_status(), 0)
        elif self.status_until and t > self.status_until:
            self.status = self.idle_status()
            self.status_at = t
            self.status_until = 0.0

        mouse = pygame.mouse.get_pos()
        down = pygame.mouse.get_pressed()[0]
        for button in self.buttons.values():
            button.update(mouse, dt, down)

        self.equalizer.update(dt, t, self.act, self.level)
        core_hover = (
            math.hypot(mouse[0] - self.L["cx"], mouse[1] - self.L["core_y"])
            <= self.L["radius"]
        )
        hand = core_hover or any(b.hot for b in self.buttons.values())
        if hand != self.cursor_hand:
            self.cursor_hand = hand
            try:
                pygame.mouse.set_cursor(
                    pygame.SYSTEM_CURSOR_HAND if hand else pygame.SYSTEM_CURSOR_ARROW
                )
            except pygame.error:
                pass

    def submit_chat(self):
        message = self.chat_text.strip()
        if not message:
            return
        self.chat_messages.append(message)
        self.log("YOU: " + message[:90])
        handled = self.safe_call(
            self.backend.on_chat_message, message, default=None
        )
        if handled is None:
            self.set_status("MESSAGE ADDED - CHAT BACKEND NOT CONNECTED")
        else:
            self.set_status("MESSAGE SENT TO AI")
        self.chat_text = ""

    def draw_chat(self):
        s = self.screen
        rect = self.chat_rect
        focused = self.chat_focused
        edge = GREEN if focused else CYAN

        shadow = rect.inflate(8, 8)
        pygame.draw.rect(s, (2, 9, 17), shadow, border_radius=12)
        pygame.draw.rect(s, (5, 17, 29), rect, border_radius=10)
        pygame.draw.rect(s, (18, 64, 82), rect, 1, border_radius=10)
        self.bracket(rect, edge, 7)

        icon_x, icon_y = rect.x + 17, rect.centery
        bubble = pygame.Rect(icon_x - 7, icon_y - 6, 14, 11)
        pygame.draw.rect(s, edge, bubble, 1, border_radius=3)
        pygame.draw.line(s, edge, (icon_x - 2, icon_y + 5),
                         (icon_x - 5, icon_y + 8), 1)

        input_left = rect.x + 32
        input_right = self.chat_send_rect.left - 10
        available = max(20, input_right - input_left)
        value = self.chat_text
        placeholder = "Message MH2..." if not value else value

        # Keep the newest characters visible as the user types.
        while value and self.text.width(placeholder, 13) > available:
            value = value[1:]
            placeholder = value
        color = WHITE if self.chat_text else MUTED
        self.text.draw(s, placeholder, 13, color,
                       (input_left, rect.centery), "midleft")

        if focused and int(self.t * 2) % 2 == 0:
            cursor_x = input_left + self.text.width(placeholder, 13) + 2
            if cursor_x < input_right:
                pygame.draw.line(s, GREEN, (cursor_x, rect.y + 10),
                                 (cursor_x, rect.bottom - 10), 1)

        send = self.chat_send_rect
        hovered = send.collidepoint(pygame.mouse.get_pos())
        send_fill = (8, 48, 56) if hovered else (5, 31, 42)
        pygame.draw.rect(s, send_fill, send, border_radius=7)
        pygame.draw.rect(s, edge, send, 1, border_radius=7)
        self.text.draw(s, "SEND", 10, edge, send.center, "center", True)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.TEXTINPUT and self.chat_focused:
                self.chat_text += event.text
            elif event.type == pygame.KEYDOWN:
                if self.chat_focused:
                    # Support Ctrl+V / Shift+Insert paste in the chat input.
                    paste_shortcut = (
                        (event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL))
                        or (event.key == pygame.K_INSERT and (event.mod & pygame.KMOD_SHIFT))
                    )
                    if paste_shortcut:
                        pasted = get_clipboard_text()
                        if pasted:
                            pasted = pasted.replace("\r", " ").replace("\n", " ")
                            self.chat_text += pasted
                    elif event.key == pygame.K_RETURN:
                        self.submit_chat()
                    elif event.key == pygame.K_BACKSPACE:
                        self.chat_text = self.chat_text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        self.chat_focused = False
                        pygame.key.stop_text_input()
                    continue
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self.toggle_ai()
                elif event.key == pygame.K_v:
                    self.toggle_voice()
                elif event.key == pygame.K_r:
                    self.reboot()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if self.chat_rect.collidepoint(pos):
                    if self.chat_send_rect.collidepoint(pos):
                        self.submit_chat()
                    else:
                        self.chat_focused = not self.chat_focused
                        if self.chat_focused:
                            pygame.key.start_text_input()
                        else:
                            pygame.key.stop_text_input()
                elif self.buttons["activate"].rect.collidepoint(pos):
                    self.toggle_ai()
                elif self.buttons["voice"].rect.collidepoint(pos):
                    self.toggle_voice()
                elif self.buttons["reboot"].rect.collidepoint(pos):
                    self.reboot()
                elif math.hypot(pos[0] - self.L["cx"], pos[1] - self.L["core_y"]) <= self.L["radius"]:
                    self.toggle_ai()

    def draw(self):
        s, L = self.screen, self.L
        mouse = pygame.mouse.get_pos()
        self.background.draw(s, self.glow, self.text, self.dt, self.t, self.act, mouse)
        self.draw_header()

        if L["side"]:
            fps = self.clock.get_fps()
            ms = self.frame_ms[-1] if self.frame_ms else 0.0
            up = int(self.t)
            self.draw_panel(
                L["tel"], "SYSTEM TELEMETRY",
                [
                    ("FPS", f"{fps:.0f}", GREEN if fps >= 50 else ORANGE),
                    ("FRAME", f"{ms:.1f} ms", CYAN),
                    ("UPTIME", f"{up // 60:02d}:{up % 60:02d}", CYAN),
                    ("DISPLAY", f"{self.w}x{self.h}", CYAN),
                    ("NODES", str(len(self.background.particles)), GREEN),
                ],
                list(self.frame_ms),
                max(20.0, max(self.frame_ms) if self.frame_ms else 20.0),
            )
            connected = bool(getattr(self.backend, "connected", False))
            backend_name = str(getattr(self.backend, "name", "BACKEND")).upper()[:10]
            self.draw_panel(
                L["status_panel"], "NEURAL STATUS",
                [
                    ("CORE", "ACTIVE" if self.active else "STANDBY",
                     GREEN if self.active else CYAN),
                    ("VOICE", "ACTIVE" if self.voice_mode else "STANDBY",
                     GREEN if self.voice_mode else CYAN),
                    ("BACKEND", backend_name if connected else "OFFLINE",
                     GREEN if connected else ORANGE),
                    ("INPUT", f"{int(self.input_level * 100)}%" if connected else "N/A",
                     GREEN if connected else MUTED),
                    ("OUTPUT", f"{int(self.output_level * 100)}%" if connected else "N/A",
                     GREEN if connected else MUTED),
                ],
                list(self.level_history), 1.0,
            )
            if L["log"] is not None:
                self.draw_log(L["log"])
            if L["controls"] is not None:
                self.draw_panel(
                    L["controls"], "CONTROLS",
                    [
                        ("SPACE", "AI ON/OFF", CYAN),
                        ("V", "VOICE", CYAN),
                        ("R", "REBOOT", ORANGE),
                        ("ESC", "EXIT", MUTED),
                    ],
                )

        self.draw_core(L["cx"], L["core_y"], L["radius"], mouse)
        self.draw_branding()
        self.draw_status()
        self.equalizer.draw(s, L["cx"], L["eq_y"], min(380, self.w - 100), 46, self.act)
        self.buttons["activate"].draw(
            s, self.text, "AI: ONLINE" if self.active else "ACTIVATE AI", self.active
        )
        self.buttons["voice"].draw(
            s, self.text, "VOICE: ON" if self.voice_mode else "VOICE MODE", self.voice_mode
        )
        self.buttons["reboot"].draw(s, self.text, "REBOOT SYSTEM", False)
        self.draw_chat()
        self.draw_footer()
        self.draw_boot()
        s.blit(self.scan, (0, 0))

    def run(self):
        while self.running:
            self.dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.t = time.perf_counter() - self.t0
            self.sync_size()
            self.handle_events()
            self.update()
            self.draw()
            pygame.display.flip()

    def close(self):
        self.safe_call(self.backend.shutdown)
        pygame.quit()


def main():
    app = App(backend=WhatsAppTypedBackend())
    try:
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            input("\nMH2 AI encountered an error. Press Enter to close...")
        except EOFError:
            pass
        pygame.quit()
        sys.exit(1)
