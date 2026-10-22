import os

if os.name != "nt":  raise SystemExit("MH2 PC Assistant agent runs on Windows only.")

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
