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

BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

BN_LIGHT = {
    "করো", "করুন", "কর", "করেন", "করে", "দাও", "দিন", "নাও", "নিন",
    "চাপো", "চাপুন", "চাপ", "দেন",
}

BN_NAME_SUFFIXES = ("ে", "টা", "টি", "কে", "তে")

BN_OPEN_VERBS = (
    "ওপেন", "খোলো", "খুলো", "খোল", "খুলুন", "খোলুন", "খুলে", "চালু",
    "চালাও", "চালান", "চালিয়ে", "স্টার্ট", "লঞ্চ",
)

BN_SEARCH_VERBS = (
    "সার্চ", "খুঁজো", "খুঁজুন", "খোঁজো", "খুঁজে", "খুজো", "খুজে", "খোজো",
)

BN_TYPE_VERBS = ("টাইপ", "লেখো", "লিখো", "লিখুন", "লেখ")

BN_FILLERS = (
    "আমার", "আমাকে", "একটু", "একটা", "একটি", "প্লিজ", "দয়া করে", "এখন",
    "এবার", "তুমি", "ভাই", "এই", "ওই", "হ্যালো", "একবার",
)

BN_APPS = {
    "CHROME": (
        "ক্রোম", "গুগল ক্রোম", "ক্রোম ব্রাউজার", "ব্রাউজার", "ক্রোম্",
    ),
    "WHATSAPP": (
        "হোয়াটসঅ্যাপ", "হোয়াটস অ্যাপ", "হোয়াটসএপ", "হোয়াটস এপ",
        "হোয়াটসঅ্যাপ ওয়েব", "হোয়াটস্যাপ", "হোয়াটসাপ",
    ),
    "NOTEPAD": ("নোটপ্যাড", "নোট প্যাড", "টেক্সট এডিটর"),
    "CALCULATOR": (
        "ক্যালকুলেটর", "ক্যালকুলেটার", "ক্যাল্কুলেটর", "ক্যালকুলেটর অ্যাপ",
    ),
    "PAINT": ("পেইন্ট", "পেন্ট", "এমএস পেইন্ট"),
    "WORD": (
        "ওয়ার্ড", "মাইক্রোসফট ওয়ার্ড", "মাইক্রোসফ্ট ওয়ার্ড", "এমএস ওয়ার্ড",
    ),
    "EXCEL": ("এক্সেল", "মাইক্রোসফট এক্সেল", "এমএস এক্সেল"),
    "POWERPOINT": ("পাওয়ারপয়েন্ট", "পাওয়ার পয়েন্ট", "মাইক্রোসফট পাওয়ারপয়েন্ট"),
    "EDGE": ("এজ", "মাইক্রোসফট এজ", "মাইক্রোসফ্ট এজ"),
    "SETTINGS": ("সেটিংস", "সেটিং", "সেটিংস অ্যাপ"),
    "TASK MANAGER": ("টাস্ক ম্যানেজার",),
    "FILE MANAGER": (
        "ফাইল ম্যানেজার", "ফাইল এক্সপ্লোরার", "এক্সপ্লোরার", "দিস পিসি",
        "মাই কম্পিউটার", "ফাইল", "ফাইলস",
    ),
    "YOUTUBE": ("ইউটিউব", "ইউ টিউব", "ইউটিউভ"),
    "GOOGLE": ("গুগল", "গুগুল"),
    "FACEBOOK": ("ফেসবুক", "ফেইসবুক", "ফেস বুক"),
    "GITHUB": ("গিটহাব", "গিট হাব"),
    "GMAIL": ("জিমেইল", "জি মেইল", "জিমেল"),
    "DOWNLOADS": (
        "ডাউনলোড", "ডাউনলোডস", "ডাউনলোড ফোল্ডার", "ডাউনলোডস ফোল্ডার",
    ),
    "DESKTOP": ("ডেস্কটপ", "ডেস্কটপ ফোল্ডার"),
    "DOCUMENTS": (
        "ডকুমেন্ট", "ডকুমেন্টস", "ডকুমেন্ট ফোল্ডার", "ডকুমেন্টস ফোল্ডার",
    ),
    "PICTURES": ("ছবি", "ছবির ফোল্ডার", "ছবি ফোল্ডার", "পিকচার", "পিকচারস"),
    "MUSIC": ("গান", "গানের ফোল্ডার", "মিউজিক", "মিউজিক ফোল্ডার"),
    "VIDEOS": ("ভিডিও", "ভিডিওস", "ভিডিও ফোল্ডার"),
    "RECYCLE BIN": ("রিসাইকেল বিন",),
    "HOME": ("হোম ফোল্ডার", "হোম"),
    "DRIVE": ("ড্রাইভ",),
}

BN_DRIVES = {
    "সি": "C", "ডি": "D", "ই": "E", "এফ": "F", "জি": "G", "এইচ": "H",
}

BN_PHRASE_GROUPS = (
    ("SCREENSHOT", ("স্ক্রিনশট", "স্ক্রীনশট", "স্ক্রিন শট")),
    ("LOCK", ("লক", "পিসি লক", "কম্পিউটার লক", "স্ক্রিন লক", "লক স্ক্রিন")),
    ("VOLUME UP", (
        "ভলিউম বাড়াও", "ভলিউম বাড়ান", "ভলিউম বাড়িয়ে", "ভলিউম আপ",
        "সাউন্ড বাড়াও", "আওয়াজ বাড়াও", "শব্দ বাড়াও", "ভলিউম বাড়ানো",
    )),
    ("VOLUME DOWN", (
        "ভলিউম কমাও", "ভলিউম কমান", "ভলিউম কমিয়ে", "ভলিউম ডাউন",
        "সাউন্ড কমাও", "আওয়াজ কমাও", "শব্দ কমাও", "ভলিউম কমানো",
    )),
    ("MUTE", (
        "মিউট", "ভলিউম মিউট", "সাউন্ড মিউট", "আওয়াজ বন্ধ", "শব্দ বন্ধ",
    )),
    ("UNMUTE", ("আনমিউট",)),
    ("NEW TAB", ("নতুন ট্যাব", "নিউ ট্যাব")),
    ("CLOSE TAB", ("ট্যাব বন্ধ", "ট্যাব ক্লোজ", "ক্লোজ ট্যাব")),
    ("NEXT TAB", ("পরের ট্যাব", "পরবর্তী ট্যাব", "নেক্সট ট্যাব")),
    ("PREVIOUS TAB", ("আগের ট্যাব", "পূর্ববর্তী ট্যাব", "প্রিভিয়াস ট্যাব")),
    ("REOPEN TAB", ("রিওপেন ট্যাব",)),
    ("RELOAD", (
        "রিলোড", "রিফ্রেশ", "রিলোড পেজ", "পেজ রিলোড", "পেজ রিফ্রেশ",
        "রিফ্রেশ পেজ",
    )),
    ("NEW WINDOW", ("নতুন উইন্ডো", "নিউ উইন্ডো")),
    ("INCOGNITO", ("ইনকগনিটো", "ইনকগনিটো উইন্ডো", "ইনকগনিটো মোড")),
    ("ADDRESS BAR", ("অ্যাড্রেস বার", "এড্রেস বার", "ইউআরএল বার")),
    ("CLOSE WINDOW", ("উইন্ডো বন্ধ", "উইন্ডো ক্লোজ", "ক্লোজ উইন্ডো")),
    ("MINIMIZE", ("মিনিমাইজ", "মিনিমাইজ উইন্ডো")),
    ("MAXIMIZE", ("ম্যাক্সিমাইজ", "ম্যাক্সিমাইজ উইন্ডো")),
    ("RESTORE", ("রিস্টোর", "রিস্টোর উইন্ডো")),
    ("MINIMIZE ALL", ("সব মিনিমাইজ", "সব উইন্ডো মিনিমাইজ")),
    ("SHOW DESKTOP", ("ডেস্কটপ দেখাও", "ডেস্কটপ দেখান", "শো ডেস্কটপ")),
    ("SWITCH WINDOW", ("উইন্ডো পরিবর্তন", "উইন্ডো সুইচ", "সুইচ উইন্ডো")),
    ("LIST WINDOWS", ("উইন্ডো লিস্ট", "উইন্ডো তালিকা", "খোলা উইন্ডো")),
    ("SNAP LEFT", ("স্ন্যাপ বামে", "স্ন্যাপ লেফট", "উইন্ডো বামে")),
    ("SNAP RIGHT", ("স্ন্যাপ ডানে", "স্ন্যাপ রাইট", "উইন্ডো ডানে")),
    ("SCROLL DOWN", ("নিচে স্ক্রল", "স্ক্রল ডাউন", "স্ক্রল নিচে")),
    ("SCROLL UP", ("উপরে স্ক্রল", "স্ক্রল আপ", "স্ক্রল উপরে")),
    ("SCROLL RIGHT", ("ডানে স্ক্রল", "স্ক্রল ডানে")),
    ("SCROLL LEFT", ("বামে স্ক্রল", "স্ক্রল বামে")),
    ("MOUSE POSITION", ("মাউস পজিশন", "মাউসের পজিশন")),
    ("MOUSE MOVE UP", ("মাউস উপরে",)),
    ("MOUSE MOVE DOWN", ("মাউস নিচে",)),
    ("MOUSE MOVE LEFT", ("মাউস বামে",)),
    ("MOUSE MOVE RIGHT", ("মাউস ডানে",)),
    ("CLICK", ("ক্লিক",)),
    ("DOUBLE CLICK", ("ডাবল ক্লিক",)),
    ("RIGHT CLICK", ("রাইট ক্লিক",)),
    ("MIDDLE CLICK", ("মিডল ক্লিক",)),
    ("LEFT CLICK", ("লেফট ক্লিক",)),
    ("SELECT ALL", ("সব সিলেক্ট", "সিলেক্ট অল", "সবকিছু সিলেক্ট", "সব নির্বাচন")),
    ("COPY", ("কপি",)),
    ("CUT", ("কাট",)),
    ("PASTE", ("পেস্ট",)),
    ("UNDO", ("আনডু",)),
    ("REDO", ("রিডু",)),
    ("SAVE", ("সেভ",)),
    ("ENTER", ("এন্টার", "এন্টার কি")),
    ("SPACE", ("স্পেস", "স্পেসবার")),
    ("BACKSPACE", ("ব্যাকস্পেস",)),
    ("ESCAPE", ("এস্কেপ",)),
    ("PAGE UP", ("পেজ আপ",)),
    ("PAGE DOWN", ("পেজ ডাউন",)),
    ("SHUTDOWN", (
        "শাটডাউন", "পিসি শাটডাউন", "কম্পিউটার শাটডাউন", "কম্পিউটার বন্ধ",
        "পিসি বন্ধ",
    )),
    ("RESTART", ("রিস্টার্ট", "রিবুট", "পিসি রিস্টার্ট", "কম্পিউটার রিস্টার্ট")),
    ("CANCEL SHUTDOWN", ("শাটডাউন বাতিল", "রিস্টার্ট বাতিল", "শাটডাউন ক্যান্সেল")),
    ("CANCEL ACTION", ("বাতিল", "ক্যান্সেল", "ক্যানসেল", "থাক")),
    ("CONFIRM SHUTDOWN", ("কনফার্ম শাটডাউন", "শাটডাউন কনফার্ম", "নিশ্চিত শাটডাউন")),
    ("CONFIRM RESTART", (
        "কনফার্ম রিস্টার্ট", "রিস্টার্ট কনফার্ম", "নিশ্চিত রিস্টার্ট",
        "কনফার্ম রিবুট",
    )),
    ("CONFIRM DELETE", ("কনফার্ম ডিলিট", "ডিলিট কনফার্ম", "নিশ্চিত ডিলিট")),
    ("CONFIRM EMPTY RECYCLE BIN", (
        "কনফার্ম রিসাইকেল বিন খালি", "কনফার্ম খালি রিসাইকেল বিন",
    )),
    ("EMPTY RECYCLE BIN", (
        "রিসাইকেল বিন খালি", "রিসাইকেল বিন ক্লিয়ার", "খালি রিসাইকেল বিন",
    )),
    ("DELETE SELECTED", (
        "সিলেক্টেড ফাইল ডিলিট", "সিলেক্ট করা ফাইল ডিলিট", "সিলেক্টেড ডিলিট",
    )),
    ("DELETE ALL FILES", ("সব ফাইল ডিলিট",)),
    ("STATUS", ("স্ট্যাটাস", "স্ট্যাটাস দেখাও")),
    ("SEND IT", ("সেন্ড", "পাঠাও", "পাঠান")),
    ("SEND MESSAGE", ("মেসেজ পাঠাও", "মেসেজ সেন্ড")),
    ("FIRST CHAT", ("প্রথম চ্যাট", "প্রথম রেজাল্ট", "প্রথম কন্টাক্ট")),
)

BN_MESSAGE_RE = re.compile(
    r"^(?:হোয়াটস\s?(?:অ্যাপ|এপ)ে?\s+)?(.+?)\s*কে\s+"
    r"(?:হোয়াটস\s?(?:অ্যাপ|এপ)ে?\s+)?"
    r"(?:মেসেজ|ম্যাসেজ|মেসেজটা|বার্তা)\s+"
    r"(পাঠাও|পাঠান|পাঠিয়ে\s+দাও|লেখো|লিখো|লিখুন)\s*(.*)$"
)

SEARCH_SITES = {"YOUTUBE", "GOOGLE", "FACEBOOK", "GITHUB", "WHATSAPP"}

VOCAB = {}


def add_vocab(keys, kind, value, suffixes=False):
    for key in keys:
        variants = [key]

        if suffixes:
            variants.extend(
                key + suffix
                for suffix in BN_NAME_SUFFIXES
                if not key.endswith(suffix)
            )

        for variant in variants:
            VOCAB[tuple(variant.lower().split())] = (kind, value)


for _english, _keys in BN_APPS.items():
    add_vocab(_keys, "name", _english, True)

for _letter_bn, _letter in BN_DRIVES.items():
    add_vocab((_letter_bn + " ড্রাইভ",), "name", _letter + " DRIVE")

for _english, _keys in BN_PHRASE_GROUPS:
    add_vocab(_keys, "phrase", _english)

add_vocab(BN_OPEN_VERBS, "open", "")
add_vocab(("open", "launch", "start"), "open", "")
add_vocab(BN_SEARCH_VERBS, "search", "")
add_vocab(("search", "find"), "search", "")
add_vocab(BN_TYPE_VERBS, "type", "")
add_vocab(("type",), "type", "")
add_vocab(BN_FILLERS, "filler", "")

VOCAB_MAX = max(len(_key) for _key in VOCAB)


def bn_segments(value):
    tokens = value.split()
    lowered = [token.lower() for token in tokens]
    count = len(tokens)
    segments = []
    index = 0

    while index < count:
        size = 0
        entry = None

        for length in range(min(VOCAB_MAX, count - index), 0, -1):
            entry = VOCAB.get(tuple(lowered[index:index + length]))

            if entry is not None:
                size = length
                break

        if entry is None:
            segments.append(("raw", tokens[index], tokens[index]))
            index += 1
            continue

        end = index + size
        source = " ".join(tokens[index:end])

        while end < count and tokens[end] in BN_LIGHT:
            end += 1

        segments.append((entry[0], entry[1], source))
        index = end

    return segments


def bn_search_command(segments):
    site = None
    parts = []

    for kind, out, src in segments:
        if kind in ("search", "open", "type"):
            continue

        if site is None and kind == "name" and out in SEARCH_SITES:
            site = out
            continue

        parts.append(src)

    query = " ".join(parts).strip()

    if site == "WHATSAPP":
        return ("WHATSAPP SEARCH " + query) if query else "WHATSAPP"

    if site:
        return ("SEARCH " + site + " " + query).strip()

    return ("SEARCH " + query) if query else "SEARCH"


def bn_type_command(segments):
    position = next(
        index for index, segment in enumerate(segments) if segment[0] == "type"
    )
    allowed = ("raw", "name", "phrase", "filler")
    after = [segment for segment in segments[position + 1:] if segment[0] in allowed]
    before = [segment for segment in segments[:position] if segment[0] in allowed]
    chosen = after if after else before
    text = " ".join(segment[2] for segment in chosen).strip()

    return ("TYPE " + text) if text else "TYPE"


def normalize_voice(text):
    value = " ".join(
        str(text).replace("\u0964", " ").replace("\u0965", " ").split()
    ).strip(" .,!?;")

    if not value or not BENGALI_RE.search(value):
        return value

    value = value.translate(BN_DIGITS)
    value = " ".join(re.sub(r"[,;!?\"\u201c\u201d]", " ", value).split())

    message = BN_MESSAGE_RE.match(value)

    if message and message.group(3).strip():
        verb = "SEND" if message.group(2).startswith("পাঠ") else "DRAFT"
        return (
            f"{verb} MESSAGE TO {message.group(1).strip()} "
            f"SAYING {message.group(3).strip()}"
        )

    segments = bn_segments(value)
    kinds = {segment[0] for segment in segments}

    if "search" in kinds:
        return bn_search_command(segments)

    if "type" in kinds:
        return bn_type_command(segments)

    meaningful = [
        segment for segment in segments
        if segment[0] in ("name", "phrase", "raw")
    ]

    if "open" in kinds:
        parts = " ".join(segment[1] for segment in meaningful).strip()
        return ("OPEN " + parts) if parts else "OPEN"

    if len(meaningful) == 1 and meaningful[0][0] == "name":
        return "OPEN " + meaningful[0][1]

    return " ".join(segment[1] for segment in meaningful).strip() or value


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


        

# DEVELOPMENT IN PROGRESS
# This project is currently under active development.
# New features, improvements, bug fixes, and performance optimizations are ongoing.
# The code is not yet considered a final stable release.




