# DEVELOPMENT IN PROGRESS
# This project is currently under active development.
# New features, improvements, bug fixes, and performance optimizations are ongoing.
# The code is not yet considered a final stable release.

import os

if os.name != "nt":
    raise SystemExit("MH2 PC Assistant agent runs on Windows only.")

import ctypes
import logging
import math
import queue
import random
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
import winreg
from array import array
from collections import OrderedDict, deque
from ctypes import wintypes
from datetime import datetime
from urllib.parse import quote

import pyautogui
import pygame
import pyperclip

uiautomation = None


APP_NAME = "MH2 PC Assistant"

CONFIRMATION_TIMEOUT = 60
DUPLICATE_WINDOW = 2.0
MAX_COMMAND_LENGTH = 2000
MAX_MOUSE_STEP = 2000
MAX_SCROLL_AMOUNT = 50
MOUSE_EDGE_MARGIN = 5
MOUSE_MOVE_DURATION = 0.25
MOUSE_STEP_PIXELS = 25
WINDOW_WAIT_TIMEOUT = 15
WHATSAPP_LOAD_TIMEOUT = 40
WHATSAPP_SEARCH_DELAY = 1.8
MAX_CHROME_TABS_SCAN = 30
WHATSAPP_REQUIRE_VERIFICATION = True
MAX_SCAN_WORDS = 20

VOICE_ENABLED = True
VOICE_LANGUAGES = ("en-US",)
VOICE_GOOD_CONFIDENCE = 0.80
VOICE_PHRASE_LIMIT = 15
VOICE_PAUSE_THRESHOLD = 0.8
VOICE_QUEUE_SIZE = 4
VOICE_RETRY_SECONDS = 8
VOICE_MAX_RETRY_SECONDS = 30
VOICE_AMBIENT_SECONDS = 1.0
VOICE_MAX_CANDIDATES = 6

CLAP_ENABLED = True
CLAP_MIN_RMS = 1800.0
CLAP_MIN_PEAK = 6000
CLAP_NOISE_RATIO = 5.0
CLAP_ONSET_JUMP = 3.0
CLAP_MIN_ZCR = 0.04
CLAP_DECAY_WINDOW = 0.14
CLAP_DECAY_RATIO = 0.5
CLAP_COOLDOWN = 0.9

SCREENSHOT_DIR = os.path.join(
    os.path.expanduser("~"), "Pictures", "MH2 Screenshots"
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | mh2_agent | %(message)s"
)

log = logging.getLogger("mh2_agent")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
ole32 = ctypes.windll.ole32
dwmapi = ctypes.windll.dwmapi

try:
    user32.SetProcessDPIAware()
except (AttributeError, OSError):
    pass

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)

OWN_WINDOWS = set()


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


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
user32.GetWindowTextW.argtypes = [
    wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [
    wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [
    wintypes.DWORD, wintypes.DWORD, wintypes.BOOL
]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetConsoleWindow.restype = wintypes.HWND
kernel32.GetLogicalDrives.restype = wintypes.DWORD
kernel32.SetErrorMode.argtypes = [wintypes.UINT]
kernel32.SetErrorMode.restype = wintypes.UINT
shell32.SHEmptyRecycleBinW.argtypes = [
    wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD
]
shell32.SHEmptyRecycleBinW.restype = ctypes.c_long
shell32.SHGetKnownFolderPath.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    wintypes.HANDLE,
    ctypes.POINTER(ctypes.c_void_p),
]
shell32.SHGetKnownFolderPath.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.restype = None
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]

kernel32.SetErrorMode(0x0001)

SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
WM_CLOSE = 0x0010
DWMWA_CLOAKED = 14
SHERB_NOCONFIRMATION = 0x1
SHERB_NOPROGRESSUI = 0x2
SHERB_NOSOUND = 0x4

SHELL_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
}

EXPLORER_CLASSES = {"CabinetWClass", "ExploreWClass"}
CHROME_CLASS = "Chrome_WidgetWin_1"
ITEM_KINDS = {"ListItemControl", "DataItemControl", "TreeItemControl"}

KNOWN_FOLDER_IDS = {
    "DOWNLOADS": "374DE290-123F-4565-9164-39C4925E467B",
    "DESKTOP": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "DOCUMENTS": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "PICTURES": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "MUSIC": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "VIDEOS": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}

FOLDER_WORDS = {}

for _name in ("DOWNLOADS", "DESKTOP", "DOCUMENTS", "PICTURES", "MUSIC", "VIDEOS", "HOME"):
    FOLDER_WORDS[_name] = _name
    FOLDER_WORDS[_name + " FOLDER"] = _name

FOLDER_WORDS.update({
    "DOWNLOAD": "DOWNLOADS",
    "DOWNLOAD FOLDER": "DOWNLOADS",
    "DOCUMENT": "DOCUMENTS",
    "DOCUMENT FOLDER": "DOCUMENTS",
    "PICTURE": "PICTURES",
    "PICTURE FOLDER": "PICTURES",
    "IMAGES": "PICTURES",
    "PHOTOS": "PICTURES",
    "VIDEO": "VIDEOS",
    "VIDEO FOLDER": "VIDEOS",
})

SITE_URLS = {
    "YOUTUBE": "https://www.youtube.com",
    "GOOGLE": "https://www.google.com",
    "GITHUB": "https://github.com",
    "FACEBOOK": "https://www.facebook.com",
    "GMAIL": "https://mail.google.com",
}

SITE_KEYWORDS = {
    "YOUTUBE": "youtube",
    "GITHUB": "github",
    "FACEBOOK": "facebook",
    "GMAIL": "gmail",
}

SEARCH_URLS = {
    "YOUTUBE": "https://www.youtube.com/results?search_query=",
    "FACEBOOK": "https://www.facebook.com/search/top/?q=",
    "GOOGLE": "https://www.google.com/search?q=",
    "GITHUB": "https://github.com/search?q=",
}

BROWSER_ACTIONS = {
    "NEW_TAB": (("ctrl", "t"), "new tab opened"),
    "CLOSE_TAB": (("ctrl", "w"), "tab closed"),
    "NEXT_TAB": (("ctrl", "tab"), "switched to the next tab"),
    "PREVIOUS_TAB": (("ctrl", "shift", "tab"), "switched to the previous tab"),
    "REOPEN_TAB": (("ctrl", "shift", "t"), "reopened the last closed tab"),
    "RELOAD_PAGE": (("ctrl", "r"), "page reloaded"),
    "RELOAD_TAB": (("ctrl", "r"), "page reloaded"),
    "ADDRESS_BAR": (("ctrl", "l"), "address bar focused"),
    "NEW_WINDOW": (("ctrl", "n"), "new window opened"),
    "INCOGNITO": (("ctrl", "shift", "n"), "incognito window opened"),
}

BROWSER_PHRASES = {
    "NEW TAB": "NEW_TAB",
    "OPEN NEW TAB": "NEW_TAB",
    "OPEN A NEW TAB": "NEW_TAB",
    "CLOSE TAB": "CLOSE_TAB",
    "CLOSE THIS TAB": "CLOSE_TAB",
    "CLOSE THE TAB": "CLOSE_TAB",
    "CLOSE CURRENT TAB": "CLOSE_TAB",
    "NEXT TAB": "NEXT_TAB",
    "SWITCH TAB": "NEXT_TAB",
    "GO TO NEXT TAB": "NEXT_TAB",
    "SWITCH TO NEXT TAB": "NEXT_TAB",
    "PREVIOUS TAB": "PREVIOUS_TAB",
    "PREV TAB": "PREVIOUS_TAB",
    "LAST TAB": "PREVIOUS_TAB",
    "GO TO PREVIOUS TAB": "PREVIOUS_TAB",
    "SWITCH TO PREVIOUS TAB": "PREVIOUS_TAB",
    "REOPEN TAB": "REOPEN_TAB",
    "REOPEN CLOSED TAB": "REOPEN_TAB",
    "REOPEN LAST TAB": "REOPEN_TAB",
    "REOPEN THE TAB": "REOPEN_TAB",
    "RELOAD": "RELOAD_PAGE",
    "RELOAD PAGE": "RELOAD_PAGE",
    "RELOAD THE PAGE": "RELOAD_PAGE",
    "RELOAD TAB": "RELOAD_PAGE",
    "REFRESH": "RELOAD_PAGE",
    "REFRESH PAGE": "RELOAD_PAGE",
    "NEW WINDOW": "NEW_WINDOW",
    "OPEN NEW WINDOW": "NEW_WINDOW",
    "OPEN A NEW WINDOW": "NEW_WINDOW",
    "OPEN ADDRESS BAR": "ADDRESS_BAR",
    "ADDRESS BAR": "ADDRESS_BAR",
    "FOCUS ADDRESS BAR": "ADDRESS_BAR",
    "OPEN URL BAR": "ADDRESS_BAR",
    "INCOGNITO": "INCOGNITO",
    "OPEN INCOGNITO": "INCOGNITO",
    "NEW INCOGNITO WINDOW": "INCOGNITO",
}

KEY_NAMES = {
    "enter": "enter",
    "return": "enter",
    "space": "space",
    "spacebar": "space",
    "space bar": "space",
    "backspace": "backspace",
    "back space": "backspace",
    "delete": "delete",
    "del": "delete",
    "tab": "tab",
    "escape": "esc",
    "esc": "esc",
    "up": "up",
    "arrow up": "up",
    "up arrow": "up",
    "down": "down",
    "arrow down": "down",
    "down arrow": "down",
    "left": "left",
    "arrow left": "left",
    "left arrow": "left",
    "right": "right",
    "arrow right": "right",
    "right arrow": "right",
    "home": "home",
    "end": "end",
    "page up": "pageup",
    "pageup": "pageup",
    "pgup": "pageup",
    "page down": "pagedown",
    "pagedown": "pagedown",
    "pgdn": "pagedown",
    "pgdown": "pagedown",
    "insert": "insert",
}

MODIFIERS = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "win",
    "windows": "win",
}

SYMBOL_KEYS = set("/-=,.[]")

BLOCKED_COMBOS = {
    frozenset(("alt", "f4")),
    frozenset(("ctrl", "alt", "delete")),
    frozenset(("win", "r")),
}

PHRASE_COMBOS = {
    "SELECT ALL": "ctrl+a",
    "SELECT EVERYTHING": "ctrl+a",
    "COPY": "ctrl+c",
    "CUT": "ctrl+x",
    "PASTE": "ctrl+v",
    "UNDO": "ctrl+z",
    "REDO": "ctrl+y",
    "SAVE": "ctrl+s",
    "SAVE FILE": "ctrl+s",
    "SAVE DOCUMENT": "ctrl+s",
}

BARE_KEY_PHRASES = {
    "ENTER", "SPACE", "SPACEBAR", "SPACE BAR", "BACKSPACE", "BACK SPACE",
    "DELETE", "TAB", "ESCAPE", "ESC", "HOME", "END",
    "ARROW UP", "ARROW DOWN", "ARROW LEFT", "ARROW RIGHT",
    "UP ARROW", "DOWN ARROW", "LEFT ARROW", "RIGHT ARROW",
    "PAGE UP", "PAGE DOWN", "PAGEUP", "PAGEDOWN", "PGUP", "PGDN",
}

SINGLE_WORD_OK = {
    "STATUS", "SCREENSHOT", "LOCK", "MUTE", "UNMUTE", "RELOAD", "REFRESH",
    "INCOGNITO", "CLICK", "MINIMIZE", "MINIMISE", "MAXIMIZE", "MAXIMISE",
    "RESTORE",
}

DANGEROUS_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:SHUTDOWN|SHUT DOWN|TURN OFF|RESTART|REBOOT|DELETE|"
    r"EMPTY RECYCLE|CLEAR RECYCLE|SEND|DRAFT|PREPARE|TYPE|TYPING|HOTKEY)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE
)

COPY_ALL_WORDS = {"ALL", "EVERYTHING", "ALL FILES", "ALL ITEMS"}

APP_ALIASES = {
    "GOOGLE CHROME": "CHROME",
    "CHROME BROWSER": "CHROME",
    "BROWSER": "CHROME",
    "WHATS APP": "WHATSAPP",
    "WHATSAPP WEB": "WHATSAPP",
    "FILE EXPLORER": "FILE MANAGER",
    "WINDOWS EXPLORER": "FILE MANAGER",
    "EXPLORER": "FILE MANAGER",
    "THIS PC": "FILE MANAGER",
    "MY COMPUTER": "FILE MANAGER",
    "FILES": "FILE MANAGER",
    "CALC": "CALCULATOR",
    "MS WORD": "WORD",
    "MICROSOFT WORD": "WORD",
    "MS EXCEL": "EXCEL",
    "MICROSOFT EXCEL": "EXCEL",
    "MS POWERPOINT": "POWERPOINT",
    "MICROSOFT POWERPOINT": "POWERPOINT",
    "MICROSOFT EDGE": "EDGE",
    "MS PAINT": "PAINT",
    "TEXT EDITOR": "NOTEPAD",
}

LEADING_FILLER_RE = re.compile(
    r"^(?:(?:hey|ok|okay|please|kindly)\s+)+", re.IGNORECASE
)
LEADING_POLITE_RE = re.compile(
    r"^(?:can|could|would|will) you\s+(?:please\s+)?", re.IGNORECASE
)

TYPE_COMMAND_RE = re.compile(
    r"^(TYPE|ENTER TEXT)\s+(?!(?:IN|INTO)\s)(.+)$", re.IGNORECASE | re.DOTALL
)

SPOKEN_PUNCTUATION = (
    (re.compile(r"\s*\bquestion mark\b", re.IGNORECASE), "?"),
    (re.compile(r"\s*\bexclamation (?:mark|point)\b", re.IGNORECASE), "!"),
    (re.compile(r"\s*\bfull stop\b", re.IGNORECASE), "."),
    (re.compile(r"\s*\bperiod\b", re.IGNORECASE), "."),
    (re.compile(r"\s*\bcomma\b", re.IGNORECASE), ","),
)


def strip_leading_fillers(text):
    value = str(text).strip()
    value = LEADING_FILLER_RE.sub("", value)
    value = LEADING_POLITE_RE.sub("", value)

    return value.strip()


def format_dictation(body):
    value = body

    for pattern, symbol in SPOKEN_PUNCTUATION:
        value = pattern.sub(symbol, value)

    value = re.sub(r"([,.?!])(?=[A-Za-z0-9])", r"\1 ", value)
    value = re.sub(r"\bi\b", "I", value)
    value = re.sub(
        r"(^|[.?!]\s+)([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        value
    )

    return value.strip()


def normalize_voice(text):
    value = " ".join(str(text).split())

    if not value:
        return value

    stripped = strip_leading_fillers(value)
    match = TYPE_COMMAND_RE.match(stripped)

    if match:
        body = format_dictation(match.group(2))

        if body:
            return match.group(1).upper() + " " + body

        return stripped

    return value.strip(" .,!?;")


class AgentError(Exception):
    pass


class NotUnderstood(AgentError):
    pass


class UnsupportedCommand(AgentError):
    pass


NO_MATCH = object()


class CommandResult:

    def __init__(self, text, requires_confirmation=False, confirm_phrase=None):
        self.text = text
        self.requires_confirmation = requires_confirmation
        self.confirm_phrase = confirm_phrase


def register_own_window():
    try:
        handle = pygame.display.get_wm_info().get("window")
    except Exception:
        handle = None

    if handle:
        OWN_WINDOWS.add(int(handle))


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


def is_cloaked(hwnd):
    cloaked = wintypes.DWORD(0)

    try:
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked)
        )
    except OSError:
        return False

    return result == 0 and cloaked.value != 0


def list_windows():
    results = []

    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        if hwnd in OWN_WINDOWS:
            return True

        title = window_title(hwnd)

        if not title:
            return True

        cls = window_class(hwnd)

        if cls in SHELL_CLASSES or is_cloaked(hwnd):
            return True

        results.append((hwnd, title, cls))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)

    return results


def find_window(matcher):
    for hwnd, title, cls in list_windows():
        if matcher(title, cls):
            return hwnd, title

    return None


def wait_for_window(matcher, timeout=WINDOW_WAIT_TIMEOUT):
    deadline = time.time() + timeout

    while time.time() < deadline:
        found = find_window(matcher)

        if found:
            return found

        time.sleep(0.4)

    return None


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
            foreground_thread = user32.GetWindowThreadProcessId(
                foreground, None
            )

        attached = False

        if foreground_thread and foreground_thread != current_thread:
            attached = bool(
                user32.AttachThreadInput(
                    current_thread, foreground_thread, True
                )
            )

        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(
                    current_thread, foreground_thread, False
                )

        time.sleep(0.35)

        if user32.GetForegroundWindow() == hwnd:
            return True

    return False


def input_target():
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        raise AgentError("There is no active window.")

    if window_class(hwnd) in SHELL_CLASSES:
        raise AgentError(
            "The desktop or taskbar is active. Focus an application window first."
        )

    console = kernel32.GetConsoleWindow()

    if console and hwnd == console:
        raise AgentError(
            "The agent console is the active window. "
            "Focus the target application first."
        )

    if hwnd in OWN_WINDOWS:
        raise AgentError(
            "The MH2 interface window is the active window. "
            "Focus the target application first."
        )

    return hwnd


def foreground_window():
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        raise AgentError("There is no active window.")

    if window_class(hwnd) in SHELL_CLASSES:
        raise AgentError(
            "The desktop or taskbar is active. Focus an application window first."
        )

    if hwnd in OWN_WINDOWS:
        raise AgentError(
            "The MH2 interface window is the active window. "
            "Focus the target application first."
        )

    return hwnd


def require_explorer():
    hwnd = user32.GetForegroundWindow()

    if not hwnd or window_class(hwnd) not in EXPLORER_CLASSES:
        raise AgentError(
            "File Explorer must be the active window. "
            "Open the folder and select the files first."
        )

    return window_title(hwnd)


def explorer_active():
    hwnd = user32.GetForegroundWindow()
    return bool(hwnd) and window_class(hwnd) in EXPLORER_CLASSES


def match_chrome(title, cls):
    return cls == CHROME_CLASS and "google chrome" in title.lower()


def match_whatsapp(title, cls):
    return "whatsapp" in title.lower() and cls not in EXPLORER_CLASSES


def match_explorer(title, cls):
    return cls in EXPLORER_CLASSES


def match_notepad(title, cls):
    return cls != CHROME_CLASS and (
        cls == "Notepad" or "notepad" in title.lower()
    )


def match_word(title, cls):
    lowered = title.lower()
    return lowered.endswith("- word") or lowered == "word"


def match_excel(title, cls):
    lowered = title.lower()
    return lowered.endswith("- excel") or lowered == "excel"


def match_powerpoint(title, cls):
    return "powerpoint" in title.lower()


def match_edge(title, cls):
    return "microsoft edge" in title.lower() or "microsoft\u200b edge" in title.lower()


def match_calculator(title, cls):
    return title.lower() == "calculator"


def match_paint(title, cls):
    return cls != CHROME_CLASS and "paint" in title.lower()


def match_task_manager(title, cls):
    return title.lower() == "task manager"


def match_settings(title, cls):
    return title.lower() == "settings"


def match_recycle_bin(title, cls):
    return cls in EXPLORER_CLASSES and "recycle bin" in title.lower()


WINDOW_TARGETS = {
    "whatsapp": match_whatsapp,
    "word": match_word,
    "excel": match_excel,
    "powerpoint": match_powerpoint,
    "notepad": match_notepad,
    "chrome": match_chrome,
    "edge": match_edge,
    "calculator": match_calculator,
    "paint": match_paint,
    "file_manager": match_explorer,
    "recycle_bin": match_recycle_bin,
}

TARGET_ALIASES = {
    "browser": "chrome",
    "google_chrome": "chrome",
    "ms_word": "word",
    "microsoft_word": "word",
    "file_explorer": "file_manager",
    "explorer": "file_manager",
    "text_editor": "notepad",
    "whats_app": "whatsapp",
    "microsoft_edge": "edge",
    "calc": "calculator",
}

APP_SPECS = {
    "NOTEPAD": ("popen", ["notepad.exe"], match_notepad, "Notepad"),
    "CALCULATOR": ("popen", ["calc.exe"], match_calculator, "Calculator"),
    "PAINT": ("popen", ["mspaint.exe"], match_paint, "Paint"),
    "WORD": ("startfile", "winword.exe", match_word, "Word"),
    "EXCEL": ("startfile", "excel.exe", match_excel, "Excel"),
    "POWERPOINT": ("startfile", "powerpnt.exe", match_powerpoint, "PowerPoint"),
    "EDGE": ("startfile", "msedge.exe", match_edge, "Microsoft Edge"),
    "TASK MANAGER": ("popen", ["taskmgr.exe"], match_task_manager, "Task Manager"),
    "SETTINGS": ("startfile", "ms-settings:", match_settings, "Settings"),
}

SPECIAL_APPS = {"CHROME", "WHATSAPP", "FILE MANAGER"}

TRANSCRIPTION_FIXES = [
    (r"\bMOUSE (?:MOB|MOV|MOVED|MOOVE|MOVIE)\b", "MOUSE MOVE"),
    (r"\bWHATS APP\b", "WHATSAPP"),
    (r"\b(?:CROME|KROME|CHROM)\b", "CHROME"),
    (r"\bYOU TUBE\b", "YOUTUBE"),
    (r"\bFACE BOOK\b", "FACEBOOK"),
    (r"\bBACK SPACE\b", "BACKSPACE"),
    (r"\bSELECTOR\b", "SELECT ALL"),
    (r"\bSELECT AL\b", "SELECT ALL"),
    (r"\b(?:SCROL|SCROLE)\b", "SCROLL"),
    (r"\bNEW TAP\b", "NEW TAB"),
    (r"\bCLOSE TAP\b", "CLOSE TAB"),
    (r"\bNEXT TAP\b", "NEXT TAB"),
    (r"\bPREVIOUS TAP\b", "PREVIOUS TAB"),
    (r"\b(?:OPNE|OEPN|OPAN)\b", "OPEN"),
]


def clean_command(text):
    value = " ".join(str(text).split())
    value = value.strip(" .,!?;")

    if value.endswith(":") and not re.search(r"(?:^|\s)[A-Za-z]:$", value):
        value = value.rstrip(":").strip(" .,!?;")

    value = re.sub(
        r"^(?:(?:hey|ok|okay|please|kindly)\s+)+", "", value,
        flags=re.IGNORECASE
    )
    value = re.sub(
        r"^(?:can|could|would|will) you\s+(?:please\s+)?", "", value,
        flags=re.IGNORECASE
    )
    value = re.sub(
        r"(?:\s+(?:please|for me))+$", "", value, flags=re.IGNORECASE
    )

    return value.strip()


def fix_transcription(value):
    head = value[:32]
    tail = value[32:]

    for pattern, replacement in TRANSCRIPTION_FIXES:
        head = re.sub(pattern, replacement, head, flags=re.IGNORECASE)

    return head + tail


def looks_like_url(value):
    return bool(
        re.match(
            r"^(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?]\S*)?$",
            str(value).strip(),
            re.IGNORECASE
        )
    )


def make_guid(text):
    value = uuid.UUID(text)

    return GUID(
        value.time_low,
        value.time_mid,
        value.time_hi_version,
        (ctypes.c_ubyte * 8)(*value.bytes[8:])
    )


def known_folder(name):
    fallback = os.path.join(os.path.expanduser("~"), name.title())
    guid_text = KNOWN_FOLDER_IDS.get(name)

    if not guid_text:
        return fallback

    pointer = ctypes.c_void_p()

    try:
        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(make_guid(guid_text)), 0, None, ctypes.byref(pointer)
        )

        if result == 0 and pointer.value:
            return ctypes.wstring_at(pointer.value)
    except (OSError, ValueError):
        pass
    finally:
        if pointer.value:
            ole32.CoTaskMemFree(pointer)

    return fallback


def available_drives():
    mask = kernel32.GetLogicalDrives()

    return [chr(65 + index) for index in range(26) if mask & (1 << index)]


def drive_listing():
    drives = available_drives()
    return ", ".join(f"{letter}:" for letter in drives) or "none"


def find_chrome_exe():
    candidates = [
        os.path.expandvars(
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
        ),
        os.path.expandvars(
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
        ),
        os.path.expandvars(
            r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
        ),
    ]

    registry_path = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    )

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, registry_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
                candidates.insert(0, value)
        except OSError:
            continue

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    return None


def launch_chrome(url=None):
    executable = find_chrome_exe()

    if not executable:
        raise AgentError("Google Chrome was not found on this PC.")

    arguments = [executable]

    if url:
        arguments.append(url)

    try:
        subprocess.Popen(arguments)
    except OSError as exc:
        raise AgentError(f"Google Chrome could not be started: {exc}") from exc


def chrome_windows():
    return [
        (hwnd, title)
        for hwnd, title, cls in list_windows()
        if match_chrome(title, cls)
    ]


def cursor_position():
    point = wintypes.POINT()

    if not user32.GetCursorPos(ctypes.byref(point)):
        raise AgentError("The mouse position could not be read.")

    return point.x, point.y


def screen_bounds():
    left = user32.GetSystemMetrics(76)
    top = user32.GetSystemMetrics(77)
    width = user32.GetSystemMetrics(78)
    height = user32.GetSystemMetrics(79)

    if width <= 0 or height <= 0:
        left = 0
        top = 0
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)

    return left, top, left + width - 1, top + height - 1


def clamp_point(x, y):
    left, top, right, bottom = screen_bounds()
    x = int(x)
    y = int(y)

    clamped_x = min(max(x, left + MOUSE_EDGE_MARGIN), right - MOUSE_EDGE_MARGIN)
    clamped_y = min(max(y, top + MOUSE_EDGE_MARGIN), bottom - MOUSE_EDGE_MARGIN)

    return clamped_x, clamped_y, (clamped_x != x or clamped_y != y)


def smooth_move(x, y, duration=MOUSE_MOVE_DURATION, step=MOUSE_STEP_PIXELS):
    start_x, start_y = cursor_position()
    distance = max(abs(x - start_x), abs(y - start_y))
    steps = min(max(1, int(distance / max(1, step))), 200)
    delay = max(duration, 0) / steps

    for index in range(1, steps + 1):
        ratio = index / steps
        user32.SetCursorPos(
            int(start_x + (x - start_x) * ratio),
            int(start_y + (y - start_y) * ratio)
        )

        if delay:
            time.sleep(delay)

    user32.SetCursorPos(x, y)
    final_x, final_y = cursor_position()

    if abs(final_x - x) > 3 or abs(final_y - y) > 3:
        raise AgentError("Windows did not move the mouse to the requested position.")

    return final_x, final_y


def resolve_key(name):
    value = " ".join(str(name).lower().split())

    if value in KEY_NAMES:
        return KEY_NAMES[value]

    if re.fullmatch(r"f(?:[1-9]|1[0-2])", value):
        return value

    if len(value) == 1 and (value.isalnum() and value.isascii() or value in SYMBOL_KEYS):
        return value

    raise AgentError(f"Unknown or unsupported key: {name}")


def parse_combo(text):
    value = " ".join(
        str(text).replace("_", " ").lower().replace("+", " + ").split()
    )
    value = re.sub(r"\bplus\b", "+", value)
    parts = [part.strip() for part in value.split("+") if part.strip()]

    if not parts:
        raise AgentError("No key was specified.")

    if len(parts) == 1:
        words = parts[0].split()
        modifiers = []

        while len(words) > 1 and words[0] in MODIFIERS:
            modifiers.append(words.pop(0))

        if modifiers:
            parts = modifiers + [" ".join(words)]

    keys = []

    for index, part in enumerate(parts):
        if part in MODIFIERS and index < len(parts) - 1:
            mapped = MODIFIERS[part]

            if mapped not in keys:
                keys.append(mapped)
        else:
            keys.append(resolve_key(part))

    if len(keys) > 4:
        raise AgentError("Too many keys in one shortcut.")

    return keys


def uia_collect(hwnd, max_nodes=3000, max_seconds=10):
    if uiautomation is None:
        return None

    for attempt in range(2):
        try:
            root = uiautomation.ControlFromHandle(hwnd)
        except Exception:
            return None

        if root is None:
            return None

        deadline = time.time() + max_seconds
        stack = [(root, 0, False)]
        items = []
        count = 0

        while stack and count < max_nodes and time.time() < deadline:
            control, depth, inside = stack.pop()
            count += 1

            try:
                name = control.Name or ""
                kind = control.ControlTypeName or ""
                children = control.GetChildren() if depth < 40 else []
            except Exception:
                continue

            items.append((kind, name, inside))
            child_inside = inside or kind in ITEM_KINDS

            for child in reversed(children):
                stack.append((child, depth + 1, child_inside))

        if len(items) >= 30 or attempt == 1:
            return items

        time.sleep(1.0)

    return None


def focused_name():
    if uiautomation is None:
        return None

    try:
        control = uiautomation.GetFocusedControl()

        if control is None:
            return None

        return control.Name or ""
    except Exception:
        return None


def whatsapp_logged_out(items):
    for _, name, _ in items:
        lowered = name.lower()

        if "scan" in lowered and "qr" in lowered:
            return True

        if "link with phone number" in lowered:
            return True

    return False


class WindowsActions:

    @staticmethod
    def require_foreground(hwnd):
        if user32.GetForegroundWindow() != hwnd:
            raise AgentError("The target window lost focus. No keys were sent.")

    @staticmethod
    def read_clipboard():
        try:
            return pyperclip.paste()
        except pyperclip.PyperclipException:
            return None

    @staticmethod
    def write_clipboard(value):
        try:
            pyperclip.copy(value if value is not None else "")
        except pyperclip.PyperclipException:
            pass

    def paste_text(self, text, trailing_space=False, expected=None):
        if not text:
            raise AgentError("No text was provided.")

        if len(text) > MAX_COMMAND_LENGTH:
            raise AgentError("Text is too long.")

        target = input_target()

        if expected is not None and target != expected:
            raise AgentError(
                "The active window changed. Nothing was typed."
            )

        payload = str(text) + (" " if trailing_space else "")
        previous = self.read_clipboard()

        try:
            try:
                pyperclip.copy(payload)
            except pyperclip.PyperclipException as exc:
                raise AgentError("The clipboard is not available.") from exc

            time.sleep(0.15)
            self.require_foreground(target)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.45)
        finally:
            self.write_clipboard(previous)

        return f"Typed {len(text)} characters into: {window_title(target)[:60]}"

    def send_text_message(self, text):
        target = input_target()
        self.paste_text(text, expected=target)
        self.require_foreground(target)
        pyautogui.press("enter")

        return f"Text typed and Enter pressed in: {window_title(target)[:60]}"

    def send_keys(self, keys):
        keys = list(keys)

        if frozenset(keys) in BLOCKED_COMBOS:
            raise AgentError("This keyboard shortcut is blocked for safety.")

        if "win" not in keys:
            input_target()

        if "delete" in keys and explorer_active():
            raise AgentError(
                "Delete is blocked in File Explorer. "
                "Use DELETE SELECTED FILES, which asks for confirmation."
            )

        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

        label = "+".join(key.upper() for key in keys)

        return f"Pressed {label} in the active window."

    def press_text(self, text):
        cleaned = " ".join(str(text).replace("_", " ").upper().split())
        cleaned = re.sub(r"\s+KEY$", "", cleaned)
        combo = PHRASE_COMBOS.get(cleaned)

        keys = parse_combo(combo if combo else cleaned)

        return self.send_keys(keys)

    def activate_chrome(self, launch=True):
        hwnd = user32.GetForegroundWindow()

        if hwnd and match_chrome(window_title(hwnd), window_class(hwnd)):
            return hwnd

        windows = chrome_windows()

        if windows:
            target = windows[0][0]

            if not focus_window(target):
                raise AgentError("Windows did not allow focusing Google Chrome.")

            return target

        if not launch:
            raise AgentError("Google Chrome is not open.")

        launch_chrome()
        found = wait_for_window(match_chrome, WINDOW_WAIT_TIMEOUT)

        if not found:
            raise AgentError(
                "Google Chrome was started but its window did not appear."
            )

        if not focus_window(found[0]):
            raise AgentError("Windows did not allow focusing Google Chrome.")

        return found[0]

    def open_chrome(self):
        windows = chrome_windows()

        if windows:
            if not focus_window(windows[0][0]):
                raise AgentError("Windows did not allow focusing Google Chrome.")

            return "Reused the existing Google Chrome window."

        self.activate_chrome(True)

        return "Google Chrome opened."

    def open_in_chrome(self, url, description):
        existing = bool(chrome_windows())

        launch_chrome(url)

        if existing:
            time.sleep(1.0)
            return f"{description} in a new tab of the existing Chrome session."

        found = wait_for_window(match_chrome, WINDOW_WAIT_TIMEOUT)

        if not found:
            raise AgentError(
                "Google Chrome was started but its window did not appear."
            )

        return f"{description} (Chrome started)."

    def find_tab(self, keyword):
        keyword = keyword.lower()

        for hwnd, title, cls in list_windows():
            if cls == CHROME_CLASS and keyword in title.lower():
                return hwnd

        for hwnd, _ in chrome_windows():
            if not focus_window(hwnd):
                continue

            first = window_title(hwnd)

            for _ in range(MAX_CHROME_TABS_SCAN):
                if user32.GetForegroundWindow() != hwnd:
                    break

                pyautogui.hotkey("ctrl", "tab")
                time.sleep(0.3)
                current = window_title(hwnd)

                if keyword in current.lower():
                    return hwnd

                if current == first:
                    break

        return None

    def browser_shortcut(self, action):
        spec = BROWSER_ACTIONS.get(action)

        if not spec:
            raise AgentError("Unsupported browser action.")

        keys, label = spec
        launch = action in ("NEW_TAB", "NEW_WINDOW", "INCOGNITO")
        hwnd = self.activate_chrome(launch)
        self.require_foreground(hwnd)
        pyautogui.hotkey(*keys)
        time.sleep(0.2)

        return f"Chrome: {label}."

    def open_site(self, site):
        site = site.upper()
        url = SITE_URLS.get(site)

        if not url:
            raise AgentError("This website is not supported.")

        keyword = SITE_KEYWORDS.get(site)

        if keyword:
            hwnd = self.find_tab(keyword)

            if hwnd:
                if not focus_window(hwnd):
                    raise AgentError("Windows did not allow focusing Google Chrome.")

                return f"Switched to the existing {site.title()} tab."

        return self.open_in_chrome(url, f"Opened {site.title()}")

    def search_site(self, site, query):
        site = site.upper()
        query = " ".join(str(query).split())

        if site not in SEARCH_URLS:
            raise AgentError("Searching this website is not supported.")

        if not query:
            raise AgentError("Search text is missing.")

        if len(query) > 300:
            raise AgentError("Search text is too long.")

        url = SEARCH_URLS[site] + quote(query, safe="")

        return self.open_in_chrome(url, f"Searching {site.title()}")

    def open_website(self, target):
        value = str(target).strip()

        if not value or re.search(r"\s", value):
            raise AgentError("Website address is missing or invalid.")

        if not re.match(r"^https?://", value, re.IGNORECASE):
            value = "https://" + value

        if not looks_like_url(value):
            raise AgentError("This is not a valid website address.")

        return self.open_in_chrome(value, f"Opened {value}")

    def is_known_app(self, key):
        key = APP_ALIASES.get(key, key)

        return key in SPECIAL_APPS or key in APP_SPECS

    def open_app(self, name):
        key = " ".join(str(name).replace("_", " ").upper().split())
        key = re.sub(r"^(?:THE|MY)\s+", "", key)
        key = re.sub(r"\s+(?:APP|APPLICATION)$", "", key)
        key = APP_ALIASES.get(key, key)

        if key == "CHROME":
            return self.open_chrome()

        if key == "WHATSAPP":
            return self.open_whatsapp()

        if key == "FILE MANAGER":
            return self.open_file_manager()

        spec = APP_SPECS.get(key)

        if not spec:
            supported = ", ".join(
                sorted(list(SPECIAL_APPS) + list(APP_SPECS))
            ).title()
            raise AgentError(
                f"Application not supported: {str(name)[:60]}. "
                f"Supported: {supported}."
            )

        method, target, matcher, label = spec
        existing = find_window(matcher)

        if existing:
            if not focus_window(existing[0]):
                raise AgentError(
                    f"Windows did not allow focusing the existing {label} window."
                )

            return f"Reused the existing {label} window."

        try:
            if method == "popen":
                subprocess.Popen(target)
            else:
                os.startfile(target)
        except OSError as exc:
            raise AgentError(f"{label} could not be started: {exc}") from exc

        found = wait_for_window(matcher, WINDOW_WAIT_TIMEOUT)

        if not found:
            raise AgentError(f"{label} was started but its window did not appear.")

        focus_window(found[0])

        return f"{label} opened."

    def open_file_manager(self):
        existing = find_window(match_explorer)

        if existing:
            if focus_window(existing[0]):
                return "Reused the existing File Explorer window."

        try:
            os.startfile("shell:MyComputerFolder")
        except OSError as exc:
            raise AgentError(f"File Explorer could not be opened: {exc}") from exc

        found = wait_for_window(match_explorer, WINDOW_WAIT_TIMEOUT)

        if not found:
            raise AgentError("File Explorer was started but its window did not appear.")

        return "File Explorer opened."

    def confirm_explorer(self, needle, description):
        needle = needle.lower()

        found = wait_for_window(
            lambda title, cls: cls in EXPLORER_CLASSES and needle in title.lower(),
            6
        )

        if found:
            focus_window(found[0])
            return f"{description} opened."

        return (
            f"{description}: open was requested, "
            "but the Explorer window could not be confirmed."
        )

    def open_drive(self, letter):
        drives = available_drives()

        if not letter or (letter.upper() == "A" and "A" not in drives):
            try:
                os.startfile("shell:MyComputerFolder")
            except OSError as exc:
                raise AgentError(f"This PC could not be opened: {exc}") from exc

            return f"Opened This PC. Available drives: {drive_listing()}."

        letter = letter.upper()

        if letter not in drives:
            raise AgentError(
                f"Drive {letter}: is not available. "
                f"Available drives: {drive_listing()}."
            )

        path = letter + ":\\"

        if not os.path.isdir(path):
            raise AgentError(
                f"Drive {letter}: is present but not ready or not accessible."
            )

        try:
            os.startfile(path)
        except OSError as exc:
            raise AgentError(f"Drive {letter}: could not be opened: {exc}") from exc

        return self.confirm_explorer(letter + ":", f"Drive {letter}:")

    def folder_roots(self):
        roots = [known_folder(key) for key in KNOWN_FOLDER_IDS]
        roots.append(os.path.expanduser("~"))

        for letter in available_drives():
            roots.append(letter + ":\\")

        unique = []
        seen = set()

        for root in roots:
            norm = os.path.normcase(os.path.normpath(root))

            if norm in seen or not os.path.isdir(root):
                continue

            seen.add(norm)
            unique.append(root)

        return unique

    @staticmethod
    def child_dirs(path):
        try:
            with os.scandir(path) as entries:
                return [
                    entry.path
                    for entry in entries
                    if entry.is_dir(follow_symlinks=False)
                    and not entry.name.startswith(("$", "."))
                ]
        except OSError:
            return []

    def find_folder(self, name):
        needle = re.sub(r"\s+folder$", "", str(name).strip().lower())

        if len(needle) < 2:
            return None

        roots = self.folder_roots()
        known = [known_folder(key) for key in KNOWN_FOLDER_IDS]
        level_one = []

        for root in roots:
            level_one.extend(self.child_dirs(root))

        level_two = []

        for folder in known:
            for child in self.child_dirs(folder):
                level_two.extend(self.child_dirs(child))

        groups = [level_one, level_two]

        for group in groups:
            for path in group:
                if os.path.basename(path).lower() == needle:
                    return path

        for group in groups:
            for path in group:
                if needle in os.path.basename(path).lower():
                    return path

        return None

    def open_folder_path(self, path):
        if not os.path.isdir(path):
            if os.path.exists(path):
                raise AgentError("That path is a file, not a folder.")

            raise AgentError(f"Folder not found: {path}")

        try:
            os.startfile(path)
        except OSError as exc:
            raise AgentError(f"The folder could not be opened: {exc}") from exc

        needle = os.path.basename(path.rstrip("\\/")) or path[:2]

        return self.confirm_explorer(needle, f"Folder {path}")

    def open_folder(self, name):
        raw = str(name).strip().strip('"').strip("'").strip()

        if not raw:
            raise AgentError("The folder name or path is missing.")

        key = " ".join(raw.replace("_", " ").upper().split())
        key = FOLDER_WORDS.get(key, key)

        if key == "HOME":
            path = os.path.expanduser("~")
        elif key in KNOWN_FOLDER_IDS:
            path = known_folder(key)
        elif not re.search(r"[\\/:]", raw):
            path = self.find_folder(raw)

            if not path:
                raise AgentError(f"Folder not found: {raw[:60]}")
        else:
            if re.search(r'[<>"|?*\x00-\x1f]', raw):
                raise AgentError("The path contains invalid characters.")

            expanded = os.path.expandvars(os.path.expanduser(raw))

            if re.fullmatch(r"[A-Za-z]:", expanded):
                expanded += "\\"

            if not re.match(r"^[A-Za-z]:[\\/]", expanded) or ":" in expanded[2:]:
                raise AgentError(
                    "Give a full local path such as C:\\Users\\Name\\Documents, "
                    "or a name like Downloads."
                )

            path = os.path.normpath(expanded)
            drive = path[0].upper()

            if drive not in available_drives():
                raise AgentError(
                    f"Drive {drive}: is not available. "
                    f"Available drives: {drive_listing()}."
                )

        return self.open_folder_path(path)

    def open_recycle_bin(self):
        try:
            os.startfile("shell:RecycleBinFolder")
        except OSError as exc:
            raise AgentError(f"The Recycle Bin could not be opened: {exc}") from exc

        return self.confirm_explorer("recycle bin", "Recycle Bin")

    def explorer_select(self, name):
        title = require_explorer()
        name = " ".join(str(name).split())

        if not name:
            raise AgentError("The file or folder name is missing.")

        if len(name) > 100:
            raise AgentError("The file or folder name is too long.")

        if not name.isascii():
            raise AgentError(
                "Only English letters and numbers can be used to select by name."
            )

        hwnd = user32.GetForegroundWindow()
        pyautogui.press("home")
        time.sleep(0.25)
        self.require_foreground(hwnd)
        pyautogui.write(name, interval=0.03)
        time.sleep(0.5)

        return f"Selected by name: {name} in {title[:60]}."

    def explorer_copy(self, name=None):
        title = require_explorer()
        hwnd = user32.GetForegroundWindow()
        label = "the selected items"

        if name:
            clean = " ".join(str(name).split()).upper()

            if clean in COPY_ALL_WORDS:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.3)
                label = "all items"
            else:
                self.explorer_select(name)
                label = name

        self.require_foreground(hwnd)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.3)

        return (
            f"Copied {label} in {title[:60]}. "
            "Open the destination folder and say PASTE."
        )

    def locate_whatsapp(self, open_if_missing=True):
        found = find_window(match_whatsapp)
        hwnd = found[0] if found else None

        if hwnd is None:
            hwnd = self.find_tab("whatsapp")

        if hwnd is None:
            if not open_if_missing:
                raise AgentError("WhatsApp is not open.")

            self.open_in_chrome("https://web.whatsapp.com", "Opened WhatsApp Web")
            found = wait_for_window(match_whatsapp, WHATSAPP_LOAD_TIMEOUT)

            if not found:
                raise AgentError("WhatsApp Web did not open in Chrome.")

            hwnd = found[0]
            time.sleep(4)

        if not focus_window(hwnd):
            raise AgentError("Windows did not allow focusing WhatsApp.")

        return hwnd

    def open_whatsapp(self):
        hwnd = self.locate_whatsapp(True)

        return f"WhatsApp is open and focused: {window_title(hwnd)[:60]}"

    def open_whatsapp_contacts(self):
        hwnd = self.locate_whatsapp(True)
        self.require_foreground(hwnd)
        pyautogui.hotkey("ctrl", "alt", "n")
        time.sleep(0.4)

        return "WhatsApp focused and the new chat shortcut was sent."

    def whatsapp_open_first(self):
        current = user32.GetForegroundWindow()

        if current and match_whatsapp(window_title(current), window_class(current)):
            hwnd = current
        else:
            hwnd = self.locate_whatsapp(False)

        self.require_foreground(hwnd)
        pyautogui.press("down")
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1.4)

        return "The first WhatsApp search result was opened."

    def whatsapp_candidates(self, hwnd, query):
        items = uia_collect(hwnd)

        if items is None:
            return None

        needle = query.lower()
        labels = OrderedDict()

        for kind, name, _ in items:
            if kind not in ITEM_KINDS or needle not in name.lower():
                continue

            label = re.split(r"[\n\r]|,\s|\s{2,}", name.strip())[0].strip()

            if label and needle in label.lower():
                labels.setdefault(label.lower(), label)

        return list(labels.values())

    def whatsapp_chat_open(self, hwnd, label):
        items = uia_collect(hwnd, max_nodes=2500, max_seconds=8)

        if items is None:
            return False

        target = label.lower()

        for kind, name, inside in items:
            if inside or kind in ITEM_KINDS:
                continue

            if target in name.lower():
                return True

        return False

    def whatsapp_contact(self, name, message=None, send=False):
        name = " ".join(str(name).split()).strip(" \"'")

        if not name:
            raise AgentError("The contact name is missing.")

        if len(name) > 80:
            raise AgentError("The contact name is too long.")

        if message is not None:
            if not message.strip():
                raise AgentError("The message text is empty.")

            if len(message) > MAX_COMMAND_LENGTH:
                raise AgentError("The message is too long.")

        hwnd = self.locate_whatsapp(True)
        items = uia_collect(hwnd, max_nodes=1500, max_seconds=6)

        if items and whatsapp_logged_out(items):
            raise AgentError(
                "WhatsApp Web is not logged in. "
                "Scan the QR code on the screen, then try again."
            )

        self.require_foreground(hwnd)
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(0.7)
        self.require_foreground(hwnd)

        focus = focused_name()

        if focus is not None and "search" not in focus.lower():
            raise AgentError(
                "The WhatsApp search box could not be focused. Nothing was typed."
            )

        if focus is None and message is not None and WHATSAPP_REQUIRE_VERIFICATION:
            raise AgentError(
                "Sending needs the uiautomation package to verify the contact "
                "(pip install uiautomation). Nothing was typed or sent."
            )

        pyautogui.hotkey("ctrl", "a")
        self.paste_text(name, expected=hwnd)
        time.sleep(WHATSAPP_SEARCH_DELAY)

        candidates = self.whatsapp_candidates(hwnd, name)

        if message is None:
            if candidates is None:
                return (
                    f"Typed {name} into WhatsApp search. "
                    "Matching contacts could not be read automatically."
                )

            if not candidates:
                return (
                    f"Searched WhatsApp for {name}, "
                    "but no matching contact appeared in the results."
                )

            return (
                f"Searched WhatsApp for {name}. Matches: "
                + "; ".join(candidates[:8]) + "."
            )

        verified = candidates is not None

        if candidates is None and WHATSAPP_REQUIRE_VERIFICATION:
            raise AgentError(
                "The contact could not be verified. "
                "The name was typed into WhatsApp search, but nothing was opened or sent."
            )

        if verified and not candidates:
            raise AgentError(
                f"No WhatsApp contact matching {name} was found. Nothing was sent."
            )

        if verified and len(candidates) > 1:
            raise AgentError(
                f"Several contacts match {name}: "
                + "; ".join(candidates[:6])
                + ". Please say the full contact name. Nothing was sent."
            )

        label = candidates[0] if verified else name

        self.require_foreground(hwnd)
        pyautogui.press("down")
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1.6)

        if verified and not self.whatsapp_chat_open(hwnd, label):
            if WHATSAPP_REQUIRE_VERIFICATION:
                raise AgentError(
                    f"Could not confirm that the chat with {label} opened. "
                    "Nothing was sent."
                )

        focus = focused_name()

        if focus is not None and "search" in focus.lower():
            raise AgentError(
                "The chat did not open and the search box is still focused. "
                "Nothing was sent."
            )

        self.paste_text(message, expected=hwnd)

        if not send:
            return (
                f"Message prepared in the WhatsApp chat with {label}. "
                "It has not been sent."
            )

        self.require_foreground(hwnd)
        pyautogui.press("enter")
        time.sleep(0.5)

        return (
            f"Message submitted to {label} on WhatsApp "
            "(contact verified, Enter pressed)."
        )

    def mouse_position(self):
        x, y = cursor_position()
        left, top, right, bottom = screen_bounds()

        return (
            f"Mouse position: {x}, {y}. "
            f"Screen: {right - left + 1}x{bottom - top + 1}."
        )

    def mouse_move_to(self, x, y):
        target_x, target_y, clamped = clamp_point(x, y)
        final_x, final_y = smooth_move(target_x, target_y)
        note = " (adjusted to stay on screen)" if clamped else ""

        return f"Mouse moved to {final_x}, {final_y}{note}."

    def mouse_move(self, direction, amount):
        amount = min(max(int(amount), 1), MAX_MOUSE_STEP)
        x, y = cursor_position()

        deltas = {
            "LEFT": (-amount, 0),
            "RIGHT": (amount, 0),
            "UP": (0, -amount),
            "DOWN": (0, amount),
        }

        dx, dy = deltas[direction.upper()]
        target_x, target_y, clamped = clamp_point(x + dx, y + dy)
        final_x, final_y = smooth_move(target_x, target_y)
        note = " (stopped at the screen edge)" if clamped else ""

        return (
            f"Mouse moved {direction.lower()} {amount} pixels{note}. "
            f"Position: {final_x}, {final_y}."
        )

    def mouse_click(self, kind):
        kind = (kind or "left").lower()

        if kind == "double":
            pyautogui.doubleClick()
            return "Double-click performed."

        if kind == "right":
            pyautogui.rightClick()
            return "Right-click performed."

        if kind == "middle":
            pyautogui.middleClick()
            return "Middle-click performed."

        pyautogui.click()
        return "Left click performed."

    def ensure_cursor_in_active_window(self):
        hwnd = user32.GetForegroundWindow()

        if not hwnd or window_class(hwnd) in SHELL_CLASSES:
            return False

        rect = wintypes.RECT()

        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False

        x, y = cursor_position()

        if rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
            return False

        center_x, center_y, _ = clamp_point(
            (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        )
        smooth_move(center_x, center_y)

        return True

    def scroll(self, direction, amount=5):
        direction = direction.upper()
        amount = min(max(int(amount), 1), MAX_SCROLL_AMOUNT)

        if direction not in ("UP", "DOWN", "LEFT", "RIGHT"):
            raise AgentError("Use SCROLL UP, DOWN, LEFT or RIGHT.")

        moved = self.ensure_cursor_in_active_window()
        units = amount * 120

        if direction == "UP":
            pyautogui.scroll(units)
        elif direction == "DOWN":
            pyautogui.scroll(-units)
        elif direction == "LEFT":
            pyautogui.hscroll(-units)
        else:
            pyautogui.hscroll(units)

        note = " The pointer was moved into the active window." if moved else ""

        return f"Scrolled {direction.lower()} by {amount}.{note}"

    def focus_target(self, name):
        raw = " ".join(str(name).split())

        if not raw:
            raise AgentError("Window name is missing.")

        key = re.sub(r"[\s\-]+", "_", raw.lower())
        key = TARGET_ALIASES.get(key, key)

        if key == "desktop":
            raise AgentError(
                "Text cannot be typed on the desktop. Name an application window."
            )

        if key in ("address_bar", "url_bar"):
            hwnd = self.activate_chrome(False)
            self.require_foreground(hwnd)
            pyautogui.hotkey("ctrl", "l")
            return "Chrome address bar focused."

        if key in ("search", "search_box", "search_bar"):
            current = user32.GetForegroundWindow()

            if current and match_whatsapp(window_title(current), window_class(current)):
                pyautogui.hotkey("ctrl", "alt", "/")
                return "WhatsApp search box focused."

            hwnd = self.activate_chrome(False)
            self.require_foreground(hwnd)
            pyautogui.hotkey("ctrl", "e")
            return "Chrome search focused."

        if key == "whatsapp":
            hwnd = self.locate_whatsapp(False)
            return f"Focused WhatsApp: {window_title(hwnd)[:60]}"

        if key == "chrome":
            hwnd = self.activate_chrome(False)
            return f"Focused Google Chrome: {window_title(hwnd)[:60]}"

        matcher = WINDOW_TARGETS.get(key)

        if matcher is None:
            needle = raw.lower()

            if len(needle) < 3:
                raise AgentError("Window name is too short.")

            def matcher(title, cls):
                return needle in title.lower()

        found = find_window(matcher)

        if not found:
            raise AgentError(f"No open window found for: {raw[:60]}")

        hwnd, title = found

        if not focus_window(hwnd):
            raise AgentError(
                f"Windows did not allow focusing the window: {title[:60]}"
            )

        return f"Focused window: {title[:60]}"

    def set_window_state(self, action):
        hwnd = foreground_window()
        title = window_title(hwnd)

        states = {
            "MINIMIZE": (SW_MINIMIZE, "minimized"),
            "MAXIMIZE": (SW_MAXIMIZE, "maximized"),
            "RESTORE": (SW_RESTORE, "restored"),
        }

        flag, label = states[action]
        user32.ShowWindow(hwnd, flag)

        return f"Window {label}: {title[:60]}"

    def close_window(self):
        hwnd = input_target()
        title = window_title(hwnd)

        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

        return f"Close requested for: {title[:60]}"

    def snap_window(self, direction):
        input_target()
        pyautogui.hotkey("win", direction.lower())

        return f"Window snapped {direction.lower()}."

    def switch_window(self):
        pyautogui.hotkey("alt", "tab")
        return "Switched window (Alt+Tab)."

    def describe_windows(self):
        entries = list_windows()[:15]

        if not entries:
            return "No open windows were found."

        titles = [title[:60] for _, title, _ in entries]

        return "Open windows: " + "; ".join(titles)

    def volume(self, action, steps=5):
        steps = min(max(int(steps), 1), 25)

        if action == "MUTE":
            pyautogui.press("volumemute")
            return "Volume mute toggled."

        key = "volumeup" if action == "UP" else "volumedown"

        for _ in range(steps):
            pyautogui.press(key)

        return f"Volume {action.lower()} by {steps} steps."

    def screenshot(self):
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

        path = os.path.join(
            SCREENSHOT_DIR,
            datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
        )

        pyautogui.screenshot(path)

        if not os.path.isfile(path):
            raise AgentError("The screenshot file was not created.")

        return f"Screenshot saved: {path}"

    def lock_pc(self):
        if not user32.LockWorkStation():
            raise AgentError("Windows could not lock the workstation.")

        return "PC locked."

    def empty_recycle_bin(self):
        flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        result = shell32.SHEmptyRecycleBinW(None, None, flags) & 0xFFFFFFFF

        if result == 0:
            return "Recycle Bin emptied."

        if result == 0x8000FFFF:
            return "The Recycle Bin is already empty."

        raise AgentError(f"Recycle Bin could not be emptied (code 0x{result:08X}).")


SEP = r"(?:\s*:\s*|\s+)"

CANCEL_KEYS = {
    "CANCEL",
    "CANCEL ACTION",
    "CANCEL POWER ACTION",
    "CANCEL DELETE",
    "CANCEL DELETION",
    "NEVER MIND",
}

SHUTDOWN_CANCEL_KEYS = {
    "CANCEL SHUTDOWN",
    "CANCEL RESTART",
    "CANCEL REBOOT",
    "ABORT SHUTDOWN",
}


class PCCommandDispatcher:

    def __init__(self):
        self.actions = WindowsActions()
        self.pending = None
        self.shutdown_scheduled = False
        self.unknown_note = None
        self.contained = False

        flags = re.IGNORECASE | re.DOTALL
        wa = r"(?:WHATSAPP|WHATS ?APP)"

        raw_patterns = [
            (r"^TYPE_TARGET" + SEP + r"(.+)$", self.typing_target),
            (r"^(?:TYPE_END|TYPE END|TYPING END|STOP TYPING|FINISH TYPING|CANCEL_TYPING)[.!?]*$", self.typing_end),
            (r"^TYPE_SEND$", self.typing_send),
            (r"^SEND[_ ]MESSAGE" + SEP + r"(?!\s*TO\b)(.+)$", self.typing_send_message),
            (r"^TYPE_TEXT" + SEP + r"(.+)$", self.typing_text),
            (
                r"^(?:" + wa + r"\s+(?:SEARCH|FIND)|(?:SEARCH|FIND)\s+(?:FOR\s+)?CONTACT)"
                r"\s+(?:FOR\s+)?(.+?)(?:\s+(SEND|DRAFT|PREPARE|WRITE|TYPE)\s+(.+))?$",
                self.wa_search
            ),
            (
                r"^(?:SEARCH|FIND)\s+(?:FOR\s+)?(.+?)\s+(SEND|DRAFT|PREPARE)\s+(.+)$",
                self.wa_search
            ),
            (
                r"^(?:" + wa + r"\s+)?(SEND|DRAFT|PREPARE)\s+(?:A\s+)?(?:" + wa + r"\s+)?"
                r"(?:(?:MESSAGE|MSG)\s+)?TO\s+(.+?)\s*(?::|\bSAYING\b|\bSAYS\b|\bSAY\b)\s*(.+)$",
                self.wa_message
            ),
            (r"^OPEN[_ ](?:FOLDER|PATH)" + SEP + r"(.+)$", self.cmd_open_folder),
            (r"^(?:TYPE|TYPING|START TYPING)\s+(?:IN|INTO)\s+(.+)$", self.typing_target),
            (r"^(?:TYPE|ENTER TEXT)" + SEP + r"(?:TEXT" + SEP + r")?(.+)$", self.typing_plain),
        ]

        self.raw_routes = [
            (re.compile(pattern, flags), handler)
            for pattern, handler in raw_patterns
        ]

        site_names = r"(YOUTUBE|FACEBOOK|GOOGLE|GITHUB)"
        mouse_word = r"(?:MOUSE[_ ]MOVE|MOVE(?:[_ ]THE)?[_ ](?:MOUSE|CURSOR|POINTER))"

        patterns = [
            (r"^(?:(?:GET|SHOW)[_ ])?STATUS$", self.cmd_status),
            (r"^(?:SHUTDOWN|SHUT DOWN|TURN OFF)(?: PC| COMPUTER)?$", self.cmd_shutdown),
            (r"^(?:RESTART|REBOOT)(?: PC| COMPUTER)?$", self.cmd_restart),
            (r"^LOCK(?: PC| COMPUTER| SCREEN)?$", self.cmd_lock),
            (r"^DELETE[_ ]SELECTED(?:[_ ]FILES)?(?:[_ ]REQUEST)?$", self.cmd_delete_selected),
            (r"^(?:DELETE[_ ]ALL[_ ]FILES|DELETE EVERYTHING)(?:[_ ]REQUEST)?$", self.cmd_delete_all),
            (r"^(?:EMPTY|CLEAR)[_ ]RECYCLE[_ ]BIN(?:[_ ]REQUEST)?$", self.cmd_empty_recycle_bin),
            (r"^SELECT[_ ](?:ALL|EVERY)(?:[_ ]FILES?)?$", self.cmd_select_all),
            (r"^SELECT\s+(?:THE\s+)?(?:(?:FILE|FOLDER|ITEM)\s+)?(.+)$", self.cmd_select_name),
            (r"^COPY\s+(?:THE\s+)?(?:(?:FILE|FOLDER|ITEM)\s+)?(.+)$", self.cmd_copy_name),
            (r"^OPEN[_ ]APP" + SEP + r"(.+)$", self.cmd_open_app),
            (r"^(?:(?:OPEN|SHOW)[_ ])?WHATSAPP(?:[_ ](?:INBOX|OPEN|CHATS))?$", self.cmd_whatsapp_inbox),
            (r"^OPEN[_ ]WHATSAPP[_ ]CONTACTS$", self.cmd_whatsapp_contacts),
            (r"^(?:OPEN|SELECT)\s+(?:THE\s+)?(?:FIRST\s+)?(?:CHAT|RESULT|CONTACT)$", self.cmd_wa_open_first),
            (r"^(?:OPEN|SHOW)\s+(?:ANY\s+|ALL\s+|MY\s+|THE\s+)?DRIVES?$", self.cmd_open_any_drive),
            (r"^(?:OPEN|SHOW|GO TO)[_ ]DRIVE(?:\s+(?:LETTER\s+)?([A-Z]):?\\?)?$", self.cmd_open_drive),
            (r"^(?:OPEN|SHOW|GO TO)\s+LOCAL DISK\s+([A-Z]):?\\?$", self.cmd_open_drive),
            (r"^(?:OPEN|SHOW|GO TO)\s+([A-Z]):\\?$", self.cmd_open_drive),
            (r"^(?:OPEN|SHOW|GO TO)\s+([A-Z])\s+DRIVE$", self.cmd_open_drive),
            (r"^(?:OPEN|SHOW|GO TO)[_ ](?:THE\s+)?RECYCLE[_ ]BIN$", self.cmd_open_recycle_bin),
            (r"^OPEN[_ ]WEBSITE" + SEP + r"(.+)$", self.cmd_open_website),
            (r"^(?:GO TO|VISIT)\s+(.+)$", self.cmd_go_to),
            (r"^(?:SEARCH|FIND)\s+(?:ON\s+)?" + site_names + r"(?:\s*:\s*|\s+(?:FOR\s+)?)(.+)$", self.cmd_search_site),
            (r"^" + site_names + r"\s+SEARCH(?:\s*:\s*|\s+(?:FOR\s+)?)(.+)$", self.cmd_search_site),
            (r"^(?:SEARCH|FIND)\s+(?:FOR\s+)?(.+?)\s+(?:ON|IN)\s+" + site_names + r"$", self.cmd_search_site_reversed),
            (r"^(?:SEARCH|FIND)\s+" + site_names + r"$", self.cmd_search_site_only),
            (r"^GOOGLE(?:\s*:\s*|\s+)(.+)$", self.cmd_google),
            (r"^SEARCH\s*:\s*(.+)$", self.cmd_google),
            (r"^SEARCH\s+(?:FOR\s+)?(.+)$", self.cmd_search_bare),
            (r"^BROWSER[_ ]([A-Z_ ]+)$", self.cmd_browser),
            (r"^PRESS\s+(.+)$", self.cmd_press),
            (r"^HOTKEY\s+(.+)$", self.cmd_press),
            (r"^(?:CTRL|CONTROL|ALT|SHIFT|WIN|WINDOWS)\s*\+\s*.+$", self.cmd_press_whole),
            (r"^(?:MOUSE[_ ])?SCROLL\s+(UP|DOWN|LEFT|RIGHT)(?:\s+(\d+))?$", self.cmd_scroll),
            (r"^" + mouse_word + r"(?:[_ ]TO)?\s+(?:TO\s+)?(?:X\s*[:=]?\s*)?(-?\d+)\s*[, ]\s*(?:Y\s*[:=]?\s*)?(-?\d+)$", self.cmd_mouse_move_to),
            (r"^" + mouse_word + r"\s+(LEFT|RIGHT|UP|DOWN)(?:\s+(?:BY\s+)?(\d+)(?:\s+PIXELS?)?)?$", self.cmd_mouse_move),
            (r"^(?:MOUSE[_ ])?(?:(LEFT|RIGHT|MIDDLE|DOUBLE)[ _-])?CLICK$", self.cmd_click),
            (r"^(?:MOUSE|CURSOR)[_ ]POSITION$", self.cmd_mouse_position),
            (r"^(?:WHERE IS (?:THE |MY )?(?:MOUSE|CURSOR)|(?:GET|SHOW) MOUSE POSITION)$", self.cmd_mouse_position),
            (r"^(MINIMIZE|MINIMISE|MAXIMIZE|MAXIMISE|RESTORE)(?:[_ ]WINDOW)?$", self.cmd_window_state),
            (r"^CLOSE[_ ]WINDOW$", self.cmd_close_window),
            (r"^SNAP(?:[_ ]WINDOW)?\s+(LEFT|RIGHT)$", self.cmd_snap),
            (r"^(?:SWITCH[_ ]WINDOW|ALT TAB)$", self.cmd_switch_window),
            (r"^(?:LIST[_ ]WINDOWS|SHOW WINDOWS)$", self.cmd_list_windows),
            (r"^FOCUS[_ ]WINDOW" + SEP + r"(.+)$", self.cmd_focus),
            (r"^(?:FOCUS|SWITCH TO)\s+(.+)$", self.cmd_focus),
            (r"^VOLUME[_ ](UP|DOWN|MUTE)(?:\s+(\d+))?$", self.cmd_volume),
            (r"^(?:TAKE[_ ])?SCREENSHOT$", self.cmd_screenshot),
            (r"^(?:SEND[_ ]MESSAGE|SEND IT|SEND NOW)$", self.cmd_send_enter),
            (r"^(?:OPEN|LAUNCH|START)\s+(.+)$", self.cmd_open_generic),
        ]

        self.routes = [
            (re.compile(pattern, re.IGNORECASE), handler)
            for pattern, handler in patterns
        ]

        self.phrases = {}

        for phrase, action in BROWSER_PHRASES.items():
            self.phrases[phrase] = (
                lambda value=action: self.actions.browser_shortcut(value)
            )

        for phrase in BARE_KEY_PHRASES:
            self.phrases[phrase] = (
                lambda value=phrase: self.actions.press_text(value)
            )

        for phrase in PHRASE_COMBOS:
            self.phrases[phrase] = (
                lambda value=phrase: self.actions.press_text(value)
            )

        self.phrases.update({
            "SHOW DESKTOP": lambda: self.actions.send_keys(["win", "d"]),
            "MINIMIZE ALL": lambda: self.actions.send_keys(["win", "d"]),
            "MUTE": lambda: self.actions.volume("MUTE"),
            "UNMUTE": lambda: self.actions.volume("MUTE"),
            "OPEN SELECTED": lambda: self.actions.send_keys(["enter"]),
            "OPEN SELECTED FILE": lambda: self.actions.send_keys(["enter"]),
            "OPEN SELECTED FOLDER": lambda: self.actions.send_keys(["enter"]),
        })

        for phrase in (
            "INCREASE VOLUME", "RAISE VOLUME", "TURN UP VOLUME",
            "TURN UP THE VOLUME", "INCREASE THE VOLUME", "RAISE THE VOLUME",
            "VOLUME HIGHER", "LOUDER",
        ):
            self.phrases[phrase] = lambda: self.actions.volume("UP")

        for phrase in (
            "DECREASE VOLUME", "LOWER VOLUME", "REDUCE VOLUME",
            "TURN DOWN VOLUME", "TURN DOWN THE VOLUME", "LOWER THE VOLUME",
            "DECREASE THE VOLUME", "VOLUME LOWER", "QUIETER",
        ):
            self.phrases[phrase] = lambda: self.actions.volume("DOWN")

        for phrase in (
            "TAKE A SCREENSHOT", "CAPTURE SCREEN", "CAPTURE SCREENSHOT",
            "CAPTURE THE SCREEN", "TAKE SCREENSHOT",
        ):
            self.phrases[phrase] = lambda: self.actions.screenshot()

        for phrase in (
            "LOCK MY PC", "LOCK THE PC", "LOCK MY COMPUTER",
            "LOCK THE COMPUTER", "LOCK MY SCREEN", "LOCK THE SCREEN",
        ):
            self.phrases[phrase] = lambda: self.actions.lock_pc()

    @staticmethod
    def key_of(text):
        return " ".join(str(text).replace("_", " ").split()).upper()

    @staticmethod
    def contains(key, phrase):
        pattern = r"(?<![A-Z0-9])" + re.escape(phrase) + r"(?![A-Z0-9])"
        return re.search(pattern, key) is not None

    def phrase_match(self, key, phrase):
        return (
            self.contains(key, phrase)
            and len(key.split()) <= len(phrase.split()) + 2
        )

    def ask_confirmation(self, phrase, description, runner):
        self.pending = {
            "phrase": phrase,
            "runner": runner,
            "expires": time.time() + CONFIRMATION_TIMEOUT,
        }

        return CommandResult(
            f"Confirmation required to {description}. "
            f"Say {phrase} within {CONFIRMATION_TIMEOUT} seconds, "
            "or say CANCEL ACTION.",
            True,
            phrase.lower()
        )

    def abort_shutdown(self):
        try:
            result = subprocess.run(
                ["shutdown.exe", "/a"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
        except (OSError, subprocess.SubprocessError):
            return False

        self.shutdown_scheduled = False

        return result.returncode == 0

    def cancel_pending(self, force_shutdown=False):
        messages = []

        if self.pending:
            self.pending = None
            messages.append("Pending action cancelled.")

        if force_shutdown or self.shutdown_scheduled:
            if self.abort_shutdown():
                messages.append("Scheduled shutdown or restart cancelled.")
            elif force_shutdown:
                messages.append("No shutdown or restart is in progress.")

        return " ".join(messages) if messages else "Nothing is waiting to be cancelled."

    def handle_confirmation(self, key):
        key = key.replace("SHUT DOWN", "SHUTDOWN").replace("REBOOT", "RESTART")

        if any(self.phrase_match(key, phrase) for phrase in SHUTDOWN_CANCEL_KEYS):
            return self.cancel_pending(True)

        pending = self.pending

        if key in CANCEL_KEYS or (
            pending and any(self.phrase_match(key, phrase) for phrase in CANCEL_KEYS)
        ):
            return self.cancel_pending()

        if pending and self.phrase_match(key, pending["phrase"]):
            if time.time() > pending["expires"]:
                self.pending = None
                raise AgentError("Confirmation expired. Send the action again.")

            self.pending = None
            return pending["runner"]()

        wrong = re.search(
            r"(?<![A-Z0-9])CONFIRM\s+(?:SHUTDOWN|RESTART|DELETE|EMPTY RECYCLE BIN)",
            key
        )

        if key.startswith("CONFIRM ") or wrong:
            if not pending:
                raise AgentError("There is nothing waiting for confirmation.")

            raise AgentError(
                f"The pending action requires: {pending['phrase']}."
            )

        return None

    def run_exact(self, text, command, key):
        for pattern, handler in self.raw_routes:
            match = pattern.match(text)

            if match:
                try:
                    return handler(match)
                except NotUnderstood as exc:
                    if self.unknown_note is None:
                        self.unknown_note = str(exc)

        phrase_handler = self.phrases.get(key)

        if phrase_handler:
            return phrase_handler()

        for pattern, handler in self.routes:
            match = pattern.match(command)

            if match:
                try:
                    return handler(match)
                except NotUnderstood as exc:
                    if self.unknown_note is None:
                        self.unknown_note = str(exc)

        return NO_MATCH

    def try_text(self, text):
        command = fix_transcription(clean_command(text))

        if not command:
            return NO_MATCH

        if self.contained and DANGEROUS_RE.search(command):
            return NO_MATCH

        return self.run_exact(text, command, self.key_of(command))

    def run_contained(self, text):
        words = text.split()
        total = len(words)

        if total < 2:
            return NO_MATCH

        self.contained = True

        try:
            limit = min(total, MAX_SCAN_WORDS)

            for start in range(1, limit):
                span = words[start:]

                if len(span) == 1:
                    single = span[0].strip(" .,!?;:").upper()

                    if single not in SINGLE_WORD_OK:
                        continue

                result = self.try_text(" ".join(span))

                if result is not NO_MATCH:
                    return result

            if total > MAX_SCAN_WORDS:
                return NO_MATCH

            for start in range(total):
                for end in range(total - 1, start, -1):
                    span = words[start:end]

                    if len(span) == 1:
                        single = span[0].strip(" .,!?;:").upper()

                        if single not in SINGLE_WORD_OK:
                            continue

                    result = self.try_text(" ".join(span))

                    if result is not NO_MATCH:
                        return result
        finally:
            self.contained = False

        return NO_MATCH

    def dispatch(self, raw):
        text = str(raw or "").strip()

        if not text:
            raise AgentError("Empty command.")

        if len(text) > MAX_COMMAND_LENGTH:
            raise AgentError("Command is too long.")

        if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
            raise AgentError("The command contains invalid control characters.")

        text = strip_leading_fillers(text)

        if not text:
            raise AgentError("Empty command.")

        command = fix_transcription(clean_command(text))
        key = self.key_of(command)

        handled = self.handle_confirmation(key)

        if handled is not None:
            return handled

        self.unknown_note = None
        previous = self.pending

        result = self.run_exact(text, command, key)

        if result is NO_MATCH:
            result = self.run_contained(text)

        if result is not NO_MATCH:
            if previous is not None and self.pending is previous:
                self.pending = None

            return result

        if self.unknown_note:
            raise UnsupportedCommand(self.unknown_note)

        raise UnsupportedCommand(
            f"Unsupported command: {command[:100]}. "
            "Try OPEN_APP name, TYPE_TEXT text, SEARCH YOUTUBE query, "
            "WHATSAPP SEARCH name, OPEN_DRIVE D, MOUSE_MOVE 500 300, "
            "SCROLL DOWN 5, PRESS CTRL+C, FOCUS_WINDOW name, "
            "or another supported command."
        )

    def typing_target(self, match):
        return self.actions.focus_target(match.group(1)) + " Ready for text."

    def typing_end(self, match):
        return "Typing operation ended."

    def typing_send(self, match):
        return self.actions.press_text("enter")

    def typing_send_message(self, match):
        return self.actions.send_text_message(match.group(1))

    def typing_text(self, match):
        return self.actions.paste_text(match.group(1), trailing_space=True)

    def typing_plain(self, match):
        body = match.group(1)

        if not body.strip() or body.strip().lower() == "text":
            raise AgentError("No text was provided to type.")

        return self.actions.paste_text(body)

    def wa_search(self, match):
        name = match.group(1)
        verb = match.group(2)
        message = match.group(3)

        return self.actions.whatsapp_contact(
            name,
            message,
            bool(verb) and verb.upper() == "SEND"
        )

    def wa_message(self, match):
        verb = match.group(1)
        name = match.group(2)
        message = match.group(3)

        return self.actions.whatsapp_contact(
            name,
            message,
            verb.upper() == "SEND"
        )

    def cmd_status(self, match):
        verification = "available" if uiautomation is not None else "not installed"

        return (
            "MH2 PC Assistant is running locally. "
            f"Drives: {drive_listing()}. "
            f"Contact verification (uiautomation): {verification}."
        )

    def cmd_send_enter(self, match):
        return self.actions.press_text("enter")

    def cmd_open_app(self, match):
        return self.actions.open_app(match.group(1))

    def cmd_open_generic(self, match):
        target = match.group(1).strip()
        key = " ".join(target.replace("_", " ").upper().split())
        key = re.sub(r"^(?:THE|MY|A)\s+", "", key)

        if key in SITE_URLS:
            return self.actions.open_site(key)

        if key in FOLDER_WORDS:
            return self.actions.open_folder(FOLDER_WORDS[key])

        if self.actions.is_known_app(key):
            return self.actions.open_app(key)

        if looks_like_url(target):
            return self.actions.open_website(target)

        cleaned = re.sub(r"^(?:the|my|a)\s+", "", target, flags=re.IGNORECASE)
        path = self.actions.find_folder(cleaned)

        if path:
            return self.actions.open_folder_path(path)

        raise NotUnderstood(
            f"I don't know how to open: {target[:60]}. "
            "Use a supported app, drive, folder, or website."
        )

    def cmd_whatsapp_inbox(self, match):
        return self.actions.open_whatsapp()

    def cmd_whatsapp_contacts(self, match):
        return self.actions.open_whatsapp_contacts()

    def cmd_wa_open_first(self, match):
        return self.actions.whatsapp_open_first()

    def cmd_select_name(self, match):
        return self.actions.explorer_select(match.group(1))

    def cmd_copy_name(self, match):
        return self.actions.explorer_copy(match.group(1))

    def cmd_open_any_drive(self, match):
        return self.actions.open_drive(None)

    def cmd_open_drive(self, match):
        return self.actions.open_drive(match.group(1))

    def cmd_open_recycle_bin(self, match):
        return self.actions.open_recycle_bin()

    def cmd_open_folder(self, match):
        return self.actions.open_folder(match.group(1))

    def cmd_open_website(self, match):
        return self.actions.open_website(match.group(1))

    def cmd_go_to(self, match):
        target = match.group(1).strip()
        key = " ".join(target.replace("_", " ").upper().split())

        if key in SITE_URLS:
            return self.actions.open_site(key)

        if key in FOLDER_WORDS:
            return self.actions.open_folder(FOLDER_WORDS[key])

        if looks_like_url(target):
            return self.actions.open_website(target)

        raise NotUnderstood(
            f"I don't know how to go to: {target[:60]}. "
            "Use a supported website, folder, or drive."
        )

    def cmd_search_site(self, match):
        return self.actions.search_site(match.group(1), match.group(2))

    def cmd_search_site_reversed(self, match):
        return self.actions.search_site(match.group(2), match.group(1))

    def cmd_search_site_only(self, match):
        site = match.group(1).upper()
        result = self.actions.open_site(site)

        return f"{result} Say the search text to search {site.title()}."

    def cmd_google(self, match):
        return self.actions.search_site("GOOGLE", match.group(1))

    def cmd_search_bare(self, match):
        query = match.group(1)
        current = user32.GetForegroundWindow()

        if current and match_whatsapp(window_title(current), window_class(current)):
            return self.actions.whatsapp_contact(query)

        result = self.actions.search_site("GOOGLE", query)

        return result + ". For a WhatsApp contact, say WhatsApp search followed by the name."

    def cmd_browser(self, match):
        action = match.group(1).strip().upper().replace(" ", "_")

        return self.actions.browser_shortcut(action)

    def cmd_press(self, match):
        return self.actions.press_text(match.group(1))

    def cmd_press_whole(self, match):
        return self.actions.press_text(match.group(0))

    def cmd_scroll(self, match):
        return self.actions.scroll(match.group(1), match.group(2) or 5)

    def cmd_mouse_move_to(self, match):
        return self.actions.mouse_move_to(match.group(1), match.group(2))

    def cmd_mouse_move(self, match):
        return self.actions.mouse_move(match.group(1), match.group(2) or 100)

    def cmd_click(self, match):
        return self.actions.mouse_click(match.group(1))

    def cmd_mouse_position(self, match):
        return self.actions.mouse_position()

    def cmd_window_state(self, match):
        word = match.group(1).upper()

        if word.startswith("MINIM"):
            action = "MINIMIZE"
        elif word.startswith("MAXIM"):
            action = "MAXIMIZE"
        else:
            action = "RESTORE"

        return self.actions.set_window_state(action)

    def cmd_close_window(self, match):
        return self.actions.close_window()

    def cmd_snap(self, match):
        return self.actions.snap_window(match.group(1))

    def cmd_switch_window(self, match):
        return self.actions.switch_window()

    def cmd_list_windows(self, match):
        return self.actions.describe_windows()

    def cmd_focus(self, match):
        return self.actions.focus_target(match.group(1))

    def cmd_volume(self, match):
        return self.actions.volume(match.group(1).upper(), match.group(2) or 5)

    def cmd_screenshot(self, match):
        return self.actions.screenshot()

    def cmd_lock(self, match):
        return self.actions.lock_pc()

    def cmd_select_all(self, match):
        return self.actions.press_text("select all")

    def execute_power(self, action):
        flag = "/s" if action == "SHUTDOWN" else "/r"
        label = "shutdown" if action == "SHUTDOWN" else "restart"

        try:
            result = subprocess.run(
                ["shutdown.exe", flag, "/t", "30"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AgentError(f"Windows {label} could not be scheduled: {exc}") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:200]
            raise AgentError(f"Windows {label} could not be scheduled: {detail}")

        self.shutdown_scheduled = True

        return (
            f"Windows {label} scheduled in 30 seconds. "
            "Say CANCEL SHUTDOWN to abort."
        )

    def cmd_shutdown(self, match):
        return self.ask_confirmation(
            "CONFIRM SHUTDOWN",
            "shut down this PC",
            lambda: self.execute_power("SHUTDOWN")
        )

    def cmd_restart(self, match):
        return self.ask_confirmation(
            "CONFIRM RESTART",
            "restart this PC",
            lambda: self.execute_power("RESTART")
        )

    def request_delete(self, select_all):
        title = require_explorer()

        scope = "all items" if select_all else "the selected items"
        description = (
            f"delete {scope} in the File Explorer window \"{title}\" "
            "(Windows may still show its own prompt)"
        )

        def runner():
            current = require_explorer()

            if current != title:
                raise AgentError("The active window changed. Delete cancelled.")

            if select_all:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.3)

            pyautogui.press("delete")

            return "Delete key pressed in File Explorer."

        return self.ask_confirmation("CONFIRM DELETE", description, runner)

    def cmd_delete_selected(self, match):
        return self.request_delete(False)

    def cmd_delete_all(self, match):
        return self.request_delete(True)

    def cmd_empty_recycle_bin(self, match):
        return self.ask_confirmation(
            "CONFIRM EMPTY RECYCLE BIN",
            "permanently empty the Recycle Bin",
            self.actions.empty_recycle_bin
        )


class MH2PCAssistantAgent:

    def __init__(self, notifier=None):
        self.dispatcher = PCCommandDispatcher()
        self.notify_callback = notifier
        self.paused = False
        self.exec_lock = threading.RLock()
        self.last_command = None
        self.last_finished = 0.0

    def notify(self, kind, text=""):
        if self.notify_callback is None:
            return

        try:
            self.notify_callback(kind, text)
        except Exception:
            log.exception("Agent notifier failed.")

    @staticmethod
    def describe(command):
        parts = command.split()
        head = parts[0] if parts else ""

        if re.search(
            r"\b(TYPE|TYPING|SEND|WHATSAPP|WHATS|SEARCH|FIND|DRAFT|PREPARE|GOOGLE|YOUTUBE|FACEBOOK|OPEN_FOLDER|OPEN_PATH|FOLDER|GO|VISIT|ENTER|SELECT|COPY)\b",
            command,
            re.IGNORECASE
        ):
            return f"{head} ({len(command)} chars)"

        return command[:100]

    def attempt(self, command):
        try:
            result = self.dispatcher.dispatch(command)

            if isinstance(result, CommandResult):
                text = result.text
            else:
                text = str(result)

            return "done", text

        except UnsupportedCommand:
            return None

        except AgentError as exc:
            log.warning("Voice command failed: %s", exc)
            return "failed", str(exc)

        except pyautogui.FailSafeException:
            log.warning("Voice command stopped by PyAutoGUI fail-safe.")
            return "failed", (
                "PyAutoGUI fail-safe triggered because the mouse is in a "
                "screen corner. Move it away and try again."
            )

        except pyautogui.PyAutoGUIException as exc:
            log.warning("Voice command automation error: %s", exc)
            return "failed", f"Automation error: {exc}"

        except Exception as exc:
            log.exception("Unexpected error processing a voice command")
            return "failed", f"Unexpected error: {exc}"

    def run_voice(self, candidates):
        if self.paused:
            return

        commands = []

        for item in candidates:
            command = " ".join(str(item).split())[:MAX_COMMAND_LENGTH]

            if command and command not in commands:
                commands.append(command)

        if not commands:
            return

        now = time.monotonic()

        if (
            self.last_command is not None
            and now - self.last_finished < DUPLICATE_WINDOW
            and any(command.upper() == self.last_command for command in commands)
        ):
            log.info("Duplicate voice command ignored.")
            return

        log.info("Processing voice command=%s", self.describe(commands[0]))
        self.notify("command", self.describe(commands[0]))

        outcome = None
        used = commands[0]

        with self.exec_lock:
            for command in commands:
                outcome = self.attempt(command)

                if outcome is not None:
                    used = command
                    break

        if outcome is None:
            outcome = ("failed", "Unsupported command: " + commands[0][:100])

        status, text = outcome

        if status == "done":
            self.last_command = used.upper()
            self.last_finished = time.monotonic()
            log.info("Voice command completed.")

        self.notify("failed" if status == "failed" else "done", text)


class ClapDetector:
    """Detects a hand clap in raw 16-bit PCM audio chunks.

    A clap is a loud, broadband, sudden burst that dies away quickly.
    Sustained speech and slow loudness changes are rejected.
    """

    def __init__(self, on_clap):
        self.on_clap = on_clap
        self.failed = False
        self.floor = 150.0
        self.prev_rms = 0.0
        self.candidate = None
        self.last_clap = 0.0

    def reset(self):
        self.floor = 150.0
        self.prev_rms = 0.0
        self.candidate = None

    def feed(self, data, sample_rate):
        if self.failed or not data or sample_rate <= 0:
            return

        try:
            samples = array("h")
            samples.frombytes(data[:len(data) - (len(data) % 2)])

            if sys.byteorder == "big":
                samples.byteswap()

            count = len(samples)

            if count < 16:
                return

            rms = math.sqrt(sum(s * s for s in samples) / count)
            peak = max(max(samples), -min(samples))
            crossings = sum(
                1 for a, b in zip(samples, samples[1:]) if (a >= 0) != (b >= 0)
            )
            zcr = crossings / count
            duration = count / sample_rate
            now = time.monotonic()

            if self.candidate is not None:
                candidate = self.candidate
                candidate["elapsed"] += duration

                if candidate["elapsed"] < 0.05:
                    candidate["rms"] = max(candidate["rms"], rms)

                if candidate["elapsed"] >= CLAP_DECAY_WINDOW:
                    self.candidate = None
                    confirmed = rms <= candidate["rms"] * CLAP_DECAY_RATIO

                    if confirmed and now - self.last_clap >= CLAP_COOLDOWN:
                        self.last_clap = now
                        self.fire()

                self.prev_rms = rms
                return

            onset = (
                rms > max(self.floor * CLAP_NOISE_RATIO, CLAP_MIN_RMS)
                and rms > self.prev_rms * CLAP_ONSET_JUMP
                and peak >= CLAP_MIN_PEAK
                and zcr >= CLAP_MIN_ZCR
            )

            if onset and now - self.last_clap >= CLAP_COOLDOWN:
                self.candidate = {"rms": rms, "elapsed": 0.0}
            else:
                self.floor = min(4000.0, max(50.0, self.floor * 0.97 + rms * 0.03))

            self.prev_rms = rms
        except Exception:
            self.failed = True
            log.exception("Clap detection stopped after an error.")

    def fire(self):
        try:
            self.on_clap()
        except Exception:
            log.exception("Clap callback failed.")


class TappedStream:
    """Wraps the existing microphone stream so audio chunks can also be
    analysed for claps without opening a second input stream."""

    def __init__(self, inner, tap, sample_rate):
        self.inner = inner
        self.tap = tap
        self.sample_rate = sample_rate

    def read(self, size, *args, **kwargs):
        data = self.inner.read(size, *args, **kwargs)

        try:
            self.tap(data, self.sample_rate)
        except Exception:
            pass

        return data

    def close(self):
        return self.inner.close()

    def __getattr__(self, name):
        return getattr(self.inner, name)


class VoiceListener:

    def __init__(self, agent, report):
        self.agent = agent
        self.report = report
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.audio_queue = queue.Queue(maxsize=VOICE_QUEUE_SIZE)
        self.listen_thread = None
        self.work_thread = None
        self.recognizer = None
        self.sr = None
        self.listening = None
        self.network_ok = None
        self.clap = ClapDetector(self.on_clap) if CLAP_ENABLED else None

    def on_clap(self):
        self.report("clap", "")

    def attach_clap_tap(self, source):
        if self.clap is None:
            return

        try:
            stream = getattr(source, "stream", None)
            width = int(getattr(source, "SAMPLE_WIDTH", 2))
            rate = int(getattr(source, "SAMPLE_RATE", 0))

            if stream is None or width != 2 or rate <= 0:
                self.report("log", "CLAP DETECTION UNAVAILABLE")
                return

            self.clap.failed = False
            self.clap.reset()
            source.stream = TappedStream(stream, self.clap.feed, rate)
        except Exception:
            log.exception("Clap detection could not be attached.")
            self.report("log", "CLAP DETECTION UNAVAILABLE")

    def start(self):
        if self.listen_thread is not None and self.listen_thread.is_alive():
            return

        self.stop_event.clear()
        self.listen_thread = threading.Thread(
            target=self.listen_loop, name="mh2-voice-listen", daemon=True
        )
        self.work_thread = threading.Thread(
            target=self.work_loop, name="mh2-voice-work", daemon=True
        )
        self.listen_thread.start()
        self.work_thread.start()

    def stop(self):
        self.stop_event.set()

        for thread in (self.listen_thread, self.work_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.5)

    def load(self):
        try:
            import speech_recognition as sr
        except Exception as exc:
            log.warning("SpeechRecognition could not be imported: %s", exc)
            self.report("error", "SPEECHRECOGNITION MISSING - PIP INSTALL SPEECHRECOGNITION")
            return False

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 300
        recognizer.pause_threshold = VOICE_PAUSE_THRESHOLD
        recognizer.non_speaking_duration = min(0.5, VOICE_PAUSE_THRESHOLD)
        self.sr = sr
        self.recognizer = recognizer
        self.ready.set()

        return True

    def set_listening(self, state):
        if self.listening is state:
            return

        self.listening = state
        self.report("state", "1" if state else "0")

    def enqueue(self, audio):
        try:
            self.audio_queue.put_nowait(audio)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                self.audio_queue.put_nowait(audio)
            except queue.Full:
                pass

    @staticmethod
    def describe_error(exc):
        text = str(exc).lower()

        if "pyaudio" in text:
            return "PYAUDIO MISSING - PIP INSTALL PYAUDIO"

        if isinstance(exc, OSError) or "device" in text:
            return "NO MICROPHONE FOUND OR ACCESS DENIED"

        return "MICROPHONE NOT AVAILABLE"

    def listen_loop(self):
        if not self.load():
            return

        failures = 0
        last_error = None

        while not self.stop_event.is_set():
            try:
                microphone = self.sr.Microphone()
            except Exception as exc:
                failures += 1
                self.set_listening(False)
                message = self.describe_error(exc)

                if message != last_error:
                    last_error = message
                    self.report("error", message)

                log.warning("Microphone could not be opened: %s", exc)

                delay = min(
                    VOICE_MAX_RETRY_SECONDS,
                    VOICE_RETRY_SECONDS * min(failures, 4)
                )
                self.stop_event.wait(delay)
                continue

            last_error = None

            try:
                with microphone as source:
                    self.attach_clap_tap(source)
                    self.recognizer.adjust_for_ambient_noise(
                        source, duration=VOICE_AMBIENT_SECONDS
                    )
                    failures = 0
                    self.set_listening(True)

                    while not self.stop_event.is_set():
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=1.0,
                                phrase_time_limit=VOICE_PHRASE_LIMIT
                            )
                        except self.sr.WaitTimeoutError:
                            continue

                        if self.agent.paused:
                            continue

                        self.enqueue(audio)
            except Exception as exc:
                failures += 1
                log.warning("Microphone stream stopped: %s", exc)
                message = self.describe_error(exc)

                if message != last_error:
                    last_error = message
                    self.report("error", message)

            self.set_listening(False)

            if self.stop_event.is_set():
                break

            delay = min(
                VOICE_MAX_RETRY_SECONDS,
                VOICE_RETRY_SECONDS * min(max(failures, 1), 4)
            )
            self.stop_event.wait(delay)

    def transcribe(self, audio):
        scored = []

        for language in VOICE_LANGUAGES:
            if self.stop_event.is_set():
                break

            try:
                result = self.recognizer.recognize_google(
                    audio, language=language, show_all=True
                )
            except self.sr.UnknownValueError:
                continue

            alternatives = (
                result.get("alternative") if isinstance(result, dict) else None
            )

            if not alternatives:
                continue

            good = False

            for index, alternative in enumerate(alternatives[:3]):
                text = str(alternative.get("transcript", "")).strip()

                if not text:
                    continue

                try:
                    confidence = float(alternative.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5

                scored.append((confidence - 0.05 * index, text))

                if index == 0 and confidence >= VOICE_GOOD_CONFIDENCE:
                    good = True

            if good:
                break

        scored.sort(key=lambda item: item[0], reverse=True)

        candidates = []

        for _, text in scored:
            command = normalize_voice(text)

            if command and command not in candidates:
                candidates.append(command)

            if len(candidates) >= VOICE_MAX_CANDIDATES:
                break

        return candidates

    def work_loop(self):
        while not self.stop_event.is_set():
            if not self.ready.wait(0.5):
                continue

            try:
                audio = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self.agent.paused:
                continue

            try:
                candidates = self.transcribe(audio)
            except self.sr.RequestError as exc:
                if self.network_ok is not False:
                    self.network_ok = False
                    self.report("log", "VOICE RECOGNITION SERVICE OFFLINE")

                log.warning("Speech recognition request failed: %s", exc)
                self.stop_event.wait(1.0)
                continue
            except Exception:
                log.exception("Speech recognition failed.")
                self.stop_event.wait(0.5)
                continue

            if self.network_ok is False:
                self.network_ok = True
                self.report("log", "VOICE RECOGNITION SERVICE ONLINE")

            if not candidates:
                continue

            self.agent.notify("heard", candidates[0])

            try:
                self.agent.run_voice(candidates)
            except Exception:
                log.exception("Voice command execution failed.")


pygame.init()

TITLE = "MH2 AI | Neural Interface"
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

CLAP_DURATION = 2.2
CLAP_EFFECT_COOLDOWN = 0.6
CLAP_MAX_EFFECTS = 3
CLAP_MAX_PARTICLES = 240
CLAP_PARTICLE_COUNT = 70


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


class NullBackend(AssistantBackend):
    name = "NONE"
    connected = False


class AgentBackend(AssistantBackend):
    name = "LOCAL PC"

    def __init__(self):
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.connected = False
        self.busy = False
        self.input_at = 0.0
        self.output_at = 0.0
        self.agent = MH2PCAssistantAgent(self.on_agent_event)
        self.voice = VoiceListener(self.agent, self.on_voice_event)

    def push_log(self, text):
        self.events.put({"type": "log", "text": text})

    def push_status(self, text, duration=2.6):
        self.events.put({"type": "status", "text": text, "duration": duration})

    def push_active(self, value):
        self.events.put({"type": "active", "value": bool(value)})

    def on_voice_event(self, kind, text=""):
        text = " ".join(str(text).split()).upper()[:64]

        if kind == "state":
            if text == "1":
                self.push_log("MICROPHONE LISTENING")
                self.push_status("VOICE INPUT ONLINE")
            else:
                self.push_log("MICROPHONE OFFLINE")
                self.push_status("MICROPHONE OFFLINE", 4.0)
        elif kind == "error":
            self.push_log(text)
            self.push_status(text, 6.0)
        elif kind == "clap":
            self.push_log("HAND CLAP DETECTED")
            self.events.put({"type": "clap"})
        else:
            self.push_log(text)

    def on_agent_event(self, kind, text=""):
        text = " ".join(str(text).split()).upper()[:64]
        now = time.monotonic()

        if kind == "online":
            self.connected = True
            self.push_log("LOCAL AGENT READY")
            self.push_status("LOCAL COMMAND ENGINE READY")
        elif kind == "heard":
            self.push_log("HEARD " + text)
        elif kind == "command":
            self.busy = True
            self.input_at = now
            self.push_log("CMD " + text)
            self.push_status("EXECUTING COMMAND", 30.0)
        else:
            prefix = "FAILED: " if kind == "failed" else "DONE: "
            self.busy = False
            self.input_at = now
            self.output_at = now
            self.push_log(prefix + text)
            self.push_status((prefix + text)[:60], 4.0)

    def worker(self):
        global uiautomation

        try:
            import uiautomation as automation
            uiautomation = automation
        except Exception:
            uiautomation = None

        if uiautomation is None:
            self.push_log("CONTACT VERIFICATION UNAVAILABLE")

        self.on_agent_event("online")

        if VOICE_ENABLED and not self.stop_event.is_set():
            self.voice.start()
            self.push_log("VOICE INPUT STARTING")

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return None

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.worker, name="mh2-agent", daemon=True
        )
        self.thread.start()
        self.push_log("AGENT THREAD STARTED")
        self.push_active(True)

        return None

    def shutdown(self):
        self.stop_event.set()
        self.voice.stop()

        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=3.0)

        return None

    def poll(self):
        events = []

        while True:
            try:
                events.append(self.events.get_nowait())
            except queue.Empty:
                break

        return events

    def input_level(self):
        if self.busy:
            return 0.85

        age = time.monotonic() - self.input_at
        return max(0.0, 1.0 - age / 1.0) * 0.85

    def output_level(self):
        age = time.monotonic() - self.output_at
        return max(0.0, 1.0 - age / 1.6)

    def on_ai_toggle(self, active):
        self.agent.paused = not active
        self.push_log("COMMAND PROCESSING " + ("RESUMED" if active else "PAUSED"))
        return None

    def on_voice_toggle(self, enabled):
        if enabled:
            self.push_log("VOICE INPUT IS ALWAYS ACTIVE")
        return None

    def on_reboot(self):
        self.agent.dispatcher.pending = None
        self.agent.paused = False
        self.push_log("AGENT RESUMED AFTER REBOOT")
        self.push_active(True)
        return None


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
        pygame.draw.rect(screen, mix(scale_color(color, 0.55), color, self.hover),
                         rect, 1, border_radius=8)
        pygame.draw.line(screen, color, (rect.left + 9, rect.top + 9),
                         (rect.left + 9, rect.bottom - 9), 2)
        bar = int((rect.w - 28) * self.hover)

        if bar > 0:
            cx = rect.centerx
            pygame.draw.line(screen, color,
                             (cx - bar // 2, rect.bottom - 4),
                             (cx + bar // 2, rect.bottom - 4), 2)

        text.draw(screen, label, 13, color,
                  (rect.centerx + 4, rect.centery - 3), "center", True)
        text.draw(screen, self.hint, 9, mix(MUTED, color, 0.3),
                  (rect.centerx + 4, rect.bottom - 9), "center")


class App:
    def __init__(self, backend=None):
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode(START_SIZE, pygame.RESIZABLE)
        register_own_window()
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

        self.claps = []
        self.clap_particles = []
        self.last_clap_at = -10.0
        self.fx = None
        self.clap_sprite = self.build_clap_sprite()

        self.frame_ms = deque(maxlen=70)
        self.level_history = deque(maxlen=70)
        self.logs = deque(maxlen=40)

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

    @staticmethod
    def build_clap_sprite():
        radius = 200
        size = radius * 2 + 1
        sprite = pygame.Surface((size, size))
        sprite.fill((0, 0, 0))
        core = (60, 200, 255)
        for i in range(radius, 0, -1):
            f = (1 - i / radius) ** 2.2
            color = (int(core[0] * f), int(core[1] * f), int(core[2] * f))
            pygame.draw.circle(sprite, color, (radius, radius), i)
        return sprite.convert()

    def safe_call(self, func, *args, default=None):
        try:
            return func(*args)
        except Exception as exc:
            self.log("BACKEND ERROR: " + type(exc).__name__)
            return default

    def log(self, message):
        self.logs.append((time.strftime("%H:%M:%S"), str(message)))

    def backend_boot_message(self):
        connected = bool(getattr(self.backend, "connected", False))
        return "BACKEND " + ("CONNECTED" if connected else "NOT CONNECTED")

    def begin_boot(self):
        self.booting = True
        self.boot_t0 = self.t
        self.boot_queue = [
            (0.25, "DISPLAY CONTEXT READY"),
            (0.80, "RENDER PIPELINE ONLINE"),
            (1.30, self.backend_boot_message),
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
        self.claps = []
        self.clap_particles = []
        self.background.resize(self.w, self.h, fresh=True)
        self.face.reset()
        self.equalizer.reset()
        self.log("SYSTEM REBOOT")
        self.safe_call(self.backend.on_reboot)
        self.begin_boot()

    def trigger_clap(self):
        if self.t - self.last_clap_at < CLAP_EFFECT_COOLDOWN:
            return

        self.last_clap_at = self.t
        cx = self.L.get("cx", self.w // 2)
        cy = self.L.get("core_y", self.h // 2)
        base_r = self.L.get("radius", 80)

        self.claps.append({"t0": self.t})

        while len(self.claps) > CLAP_MAX_EFFECTS:
            self.claps.pop(0)

        for _ in range(CLAP_PARTICLE_COUNT):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(90, 420)
            start = base_r * random.uniform(0.9, 1.2)
            life = random.uniform(0.9, 1.8)
            self.clap_particles.append([
                cx + math.cos(angle) * start,
                cy + math.sin(angle) * start,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                0.0,
                life,
                random.choice((1, 2, 2, 3)),
                random.choice((0, 0, 1, 2)),
            ])

        if len(self.clap_particles) > CLAP_MAX_PARTICLES:
            self.clap_particles = self.clap_particles[-CLAP_MAX_PARTICLES:]

        self.set_status("CLAP DETECTED - ENERGY PULSE", 1.8)

    def update_claps(self, dt):
        if self.claps:
            self.claps = [
                c for c in self.claps if self.t - c["t0"] < CLAP_DURATION
            ]

        if self.clap_particles:
            drag = math.exp(-1.6 * dt)
            alive = []

            for p in self.clap_particles:
                p[4] += dt
                p[2] *= drag
                p[3] *= drag
                p[0] += p[2] * dt
                p[1] += p[3] * dt

                if p[4] < p[5]:
                    alive.append(p)

            self.clap_particles = alive

    @staticmethod
    def clap_envelope(age):
        p = age / CLAP_DURATION

        if p < 0.1:
            return ease(p / 0.1)

        return max(0.0, 1.0 - (p - 0.1) / 0.9) ** 1.6

    def blit_clap_halo(self, target, cx, cy, diameter, intensity):
        diameter = int(clamp(diameter, 8, 900))
        k = int(clamp(255 * intensity, 0, 255))

        if k <= 0:
            return

        halo = pygame.transform.smoothscale(
            self.clap_sprite, (diameter, diameter)
        )
        halo.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        target.blit(
            halo, (int(cx - diameter // 2), int(cy - diameter // 2)),
            special_flags=pygame.BLEND_RGB_ADD
        )

    def draw_claps(self, stage):
        if not self.claps and not self.clap_particles:
            return

        s = self.screen
        cx = self.L["cx"]
        cy = self.L["core_y"]
        base_r = self.L["radius"]

        if stage == "back" and self.claps and self.fx is not None:
            fx = self.fx
            fx.fill((0, 0, 0))
            max_r = math.hypot(self.w, self.h) * 0.55

            for clap in self.claps:
                age = self.t - clap["t0"]
                p = age / CLAP_DURATION
                env = self.clap_envelope(age)

                diameter = 2 * (base_r + 60) + 2 * (max_r * 0.5) * ease(
                    min(1.0, p * 1.4)
                )
                self.blit_clap_halo(fx, cx, cy, diameter, env * 0.8)

                for i in range(3):
                    local = (age - i * 0.14) / (CLAP_DURATION * 0.75)

                    if 0.0 < local < 1.0:
                        radius = int(base_r * 0.9 + max_r * ease(local))
                        fade = (1.0 - local) ** 1.4
                        ring_color = mix(BLUE, CYAN, 0.35 + 0.25 * i)
                        width = max(1, int(5 * (1.0 - local)) + 1)
                        pygame.draw.circle(
                            fx, scale_color(ring_color, fade), (cx, cy),
                            radius, width
                        )
                        pygame.draw.circle(
                            fx, scale_color(ring_color, fade * 0.35), (cx, cy),
                            max(1, radius - 7), 1
                        )

                wave = age / (CLAP_DURATION * 0.9)

                if 0.0 < wave < 1.0:
                    wave_r = base_r * 1.1 + max_r * 0.7 * ease(wave)
                    wobble = 5 + 10 * (1.0 - wave)
                    points = []

                    for i in range(96):
                        angle = i * math.tau / 96
                        rr = wave_r + wobble * math.sin(angle * 7 + self.t * 14)
                        points.append((cx + math.cos(angle) * rr,
                                       cy + math.sin(angle) * rr))

                    pygame.draw.lines(
                        fx, scale_color(CYAN, 0.55 * (1.0 - wave)), True,
                        points, 2
                    )

            s.blit(fx, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        elif stage == "front":
            for clap in self.claps:
                age = self.t - clap["t0"]
                env = self.clap_envelope(age)
                self.blit_clap_halo(
                    s, cx, cy, 2 * (base_r + 50), env * 0.45
                )

            tints = (CYAN, BLUE, WHITE)

            for p in self.clap_particles:
                fade = max(0.0, 1.0 - p[4] / p[5])
                color = scale_color(tints[p[7]], fade)
                self.glow.draw(s, p[0], p[1], color, 6)
                pygame.draw.circle(
                    s, color, (int(p[0]), int(p[1])),
                    max(1, int(p[6] * fade + 0.5))
                )

    def apply_backend_event(self, event):
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if kind == "status":
            self.set_status(str(event.get("text", "")),
                            event.get("duration", 2.6))
        elif kind == "log":
            self.log(event.get("text", ""))
        elif kind == "active":
            self.set_active(event.get("value", False), notify=False)
        elif kind == "voice":
            self.set_voice(event.get("value", False), notify=False)
        elif kind == "clap":
            self.trigger_clap()

    def sync_size(self):
        surf = pygame.display.get_surface()
        w, h = surf.get_size()
        if w < MIN_W or h < MIN_H:
            surf = pygame.display.set_mode(
                (max(w, MIN_W), max(h, MIN_H)), pygame.RESIZABLE
            )
            register_own_window()
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
        self.fx = pygame.Surface((w, h))
        self.fx.fill((0, 0, 0))
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
        button_y = h - 92
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
        self.text.draw(s, "PERSONAL AI SYSTEM  /  BUILD 2.6", 11, MUTED,
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
            self.apply_backend_event(event)

        self.act = smooth(self.act, 1.0 if self.active else 0.0, 4, dt)
        self.voice_vis = smooth(self.voice_vis, 1.0 if self.voice_mode else 0.0, 6, dt)
        self.update_levels()
        self.level_history.append(self.level)
        self.update_claps(dt)

        if self.booting:
            bt = t - self.boot_t0
            while self.boot_queue and bt >= self.boot_queue[0][0]:
                message = self.boot_queue.pop(0)[1]
                if callable(message):
                    message = message()
                self.log(message)
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

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
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
                if self.buttons["activate"].rect.collidepoint(pos):
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
        self.draw_claps("back")
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
        self.draw_claps("front")
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
    sys.setswitchinterval(0.002)
    backend = AgentBackend()
    app = App(backend) 
    try:
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
    except Exception:
        traceback.print_exc()
        try:
            input("\nMH2 AI encountered an error. Press Enter to close...")
        except EOFError:
            pass
        pygame.quit()
        sys.exit(1)
