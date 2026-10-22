# DEVELOPMENT IN PROGRESS

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
VOICE_LANGUAGES = ("en-US", "bn-BD")
VOICE_GOOD_CONFIDENCE = 0.80
VOICE_PHRASE_LIMIT = 15
VOICE_PAUSE_THRESHOLD = 0.8
VOICE_QUEUE_SIZE = 4
VOICE_RETRY_SECONDS = 8
VOICE_MAX_RETRY_SECONDS = 30
VOICE_AMBIENT_SECONDS = 1.0
VOICE_MAX_CANDIDATES = 6

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

# DEVELOPMENT IN PROGRESS
# This project is currently under active development.
# New features, improvements, bug fixes, and performance optimizations are ongoing.
# The code is not yet considered a final stable release.
