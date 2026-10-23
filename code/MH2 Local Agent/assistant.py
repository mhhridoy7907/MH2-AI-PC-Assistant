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
