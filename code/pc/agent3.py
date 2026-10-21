import os

if os.name != "nt":
    raise SystemExit("MH2 PC Assistant agent runs on Windows only.")

import ctypes
import logging
import re
import subprocess
import time
import uuid
import winreg
from collections import OrderedDict
from ctypes import wintypes
from datetime import datetime, timezone
from urllib.parse import quote

import pyautogui
import pyperclip
import requests

try:
    import uiautomation
except Exception:
    uiautomation = None


APP_NAME = "MH2 PC Assistant"

DATABASE_URL = (
    "https://mh2***************************************************se.app"
)

AUTH_TOKEN = os.environ.get("MH2_AUTH_TOKEN", "").strip()

POLL_INTERVAL = 2
REQUEST_TIMEOUT = 15
COMMANDS_PATH = "commands"
CONFIRMATION_TIMEOUT = 60
COMMAND_MAX_AGE_SECONDS = 60
STALE_PROCESSING_SECONDS = 120
FETCH_LIMIT = 100
MAX_COMMAND_LENGTH = 2000
MAX_MOUSE_STEP = 2000
MAX_SCROLL_AMOUNT = 50
MOUSE_EDGE_MARGIN = 5
MOUSE_MOVE_DURATION = 0.25
MOUSE_STEP_PIXELS = 25
PROCESSED_CACHE_SIZE = 2000
MAX_BACKOFF = 30
WINDOW_WAIT_TIMEOUT = 15
WHATSAPP_LOAD_TIMEOUT = 40
WHATSAPP_SEARCH_DELAY = 1.8
MAX_CHROME_TABS_SCAN = 30
WHATSAPP_REQUIRE_VERIFICATION = True
MAX_SCAN_WORDS = 20

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
    "INCOGNITO", "SHUTDOWN", "RESTART", "REBOOT", "CLICK", "MINIMIZE",
    "MINIMISE", "MAXIMIZE", "MAXIMISE", "RESTORE",
}

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


class AgentError(Exception):
    pass


class NotUnderstood(AgentError):
    pass


NO_MATCH = object()


class CommandResult:

    def __init__(self, text, requires_confirmation=False, confirm_phrase=None):
        self.text = text
        self.requires_confirmation = requires_confirmation
        self.confirm_phrase = confirm_phrase


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value):
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def is_pending_record(record):
    if not isinstance(record, dict):
        return False

    status = str(record.get("status", "pending")).strip().lower()

    return status in ("", "pending", "queued", "new", "waiting")


class FirebaseREST:

    def __init__(self, database_url, token=""):
        self.database_url = database_url.rstrip("/")
        self.token = token.strip()
        self.session = requests.Session()

    def redact(self, value):
        text = str(value)

        if self.token:
            text = text.replace(self.token, "[hidden]")

        return re.sub(r"auth=[^&\s'\"]+", "auth=[hidden]", text)

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    def _url(self, path):
        return self.database_url + "/" + path.strip("/") + ".json"

    def _params(self):
        return {"auth": self.token} if self.token else {}

    @staticmethod
    def _raise_http(response):
        try:
            details = response.json()
        except ValueError:
            details = response.text[:300]

        raise AgentError(f"Firebase HTTP {response.status_code}: {details}")

    def request(self, method, path, data=None, params=None):
        merged = self._params()

        if params:
            merged.update(params)

        try:
            response = self.session.request(
                method=method,
                url=self._url(path),
                params=merged,
                json=data,
                timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise AgentError(
                f"Firebase connection failed: {self.redact(exc)}"
            ) from exc

        if not response.ok:
            self._raise_http(response)

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError:
            return response.text

    def get_commands(self):
        result = self.request(
            "GET",
            COMMANDS_PATH,
            params={
                "orderBy": '"$key"',
                "limitToLast": str(FETCH_LIMIT)
            }
        )

        return result if isinstance(result, dict) else {}

    def update_command(self, command_id, fields):
        safe_id = quote(str(command_id), safe="")
        self.request("PATCH", f"{COMMANDS_PATH}/{safe_id}", fields)

    def claim_command(self, command_id, agent_id):
        safe_id = quote(str(command_id), safe="")
        url = self._url(f"{COMMANDS_PATH}/{safe_id}")

        try:
            response = self.session.get(
                url,
                params=self._params(),
                headers={"X-Firebase-ETag": "true"},
                timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise AgentError(
                f"Firebase connection failed: {self.redact(exc)}"
            ) from exc

        if not response.ok:
            self._raise_http(response)

        try:
            record = response.json()
        except ValueError:
            return None

        if not is_pending_record(record):
            return None

        etag = response.headers.get("ETag")
        headers = {"if-match": etag} if etag else {}

        claimed = dict(record)
        claimed["status"] = "processing"
        claimed["claimedAt"] = timestamp()
        claimed["updatedAt"] = timestamp()
        claimed["agentId"] = agent_id

        try:
            put = self.session.put(
                url,
                params=self._params(),
                json=claimed,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise AgentError(
                f"Firebase connection failed: {self.redact(exc)}"
            ) from exc

        if put.status_code == 412:
            return None

        if not put.ok:
            self._raise_http(put)

        return claimed


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

    return hwnd


def foreground_window():
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        raise AgentError("There is no active window.")

    if window_class(hwnd) in SHELL_CLASSES:
        raise AgentError(
            "The desktop or taskbar is active. Focus an application window first."
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
            "Open the destination folder and send PASTE."
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

        patterns = [
            (r"^(?:GET[_ ])?STATUS$", self.cmd_status),
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
            (r"^(?:MOUSE[_ ]MOVE|MOVE[_ ]MOUSE|MOVE[_ ]CURSOR)(?:[_ ]TO)?\s+(?:TO\s+)?(?:X\s*[:=]?\s*)?(-?\d+)\s*[, ]\s*(?:Y\s*[:=]?\s*)?(-?\d+)$", self.cmd_mouse_move_to),
            (r"^(?:MOUSE[_ ]MOVE|MOVE[_ ]MOUSE|MOVE[_ ]CURSOR)\s+(LEFT|RIGHT|UP|DOWN)(?:\s+(\d+))?$", self.cmd_mouse_move),
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

    @staticmethod
    def key_of(text):
        return " ".join(str(text).replace("_", " ").split()).upper()

    @staticmethod
    def contains(key, phrase):
        pattern = r"(?<![A-Z0-9])" + re.escape(phrase) + r"(?![A-Z0-9])"
        return re.search(pattern, key) is not None

    def ask_confirmation(self, phrase, description, runner):
        self.pending = {
            "phrase": phrase,
            "runner": runner,
            "expires": time.time() + CONFIRMATION_TIMEOUT,
        }

        return CommandResult(
            f"Confirmation required to {description}. "
            f"Send {phrase} within {CONFIRMATION_TIMEOUT} seconds, "
            "or send CANCEL ACTION.",
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
        if any(self.contains(key, phrase) for phrase in SHUTDOWN_CANCEL_KEYS):
            return self.cancel_pending(True)

        pending = self.pending

        if key in CANCEL_KEYS or (
            pending and any(self.contains(key, phrase) for phrase in CANCEL_KEYS)
        ):
            return self.cancel_pending()

        if pending and self.contains(key, pending["phrase"]):
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

        if pending:
            log.info("Pending confirmation discarded by a new command.")
            self.pending = None

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

        return self.run_exact(text, command, self.key_of(command))

    def run_contained(self, text):
        words = text.split()
        total = len(words)

        if total < 2:
            return NO_MATCH

        limit = min(total, MAX_SCAN_WORDS)

        for start in range(1, limit):
            result = self.try_text(" ".join(words[start:]))

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

        return NO_MATCH

    def dispatch(self, raw):
        text = str(raw or "").strip()

        if not text:
            raise AgentError("Empty command.")

        if len(text) > MAX_COMMAND_LENGTH:
            raise AgentError("Command is too long.")

        if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
            raise AgentError("The command contains invalid control characters.")

        command = fix_transcription(clean_command(text))
        key = self.key_of(command)

        handled = self.handle_confirmation(key)

        if handled is not None:
            return handled

        self.unknown_note = None

        result = self.run_exact(text, command, key)

        if result is not NO_MATCH:
            return result

        result = self.run_contained(text)

        if result is not NO_MATCH:
            return result

        if self.unknown_note:
            raise AgentError(self.unknown_note)

        raise AgentError(
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
            "MH2 PC Assistant is running. "
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
            "Send CANCEL SHUTDOWN to abort."
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

    def __init__(self):
        self.firebase = FirebaseREST(DATABASE_URL, AUTH_TOKEN)
        self.dispatcher = PCCommandDispatcher()
        self.processed_ids = OrderedDict()
        self.agent_id = uuid.uuid4().hex

    @staticmethod
    def get_command_text(record):
        if not isinstance(record, dict):
            return ""

        for key in ("command", "text", "message", "input", "action"):
            value = record.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

        return ""

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

    def remember(self, command_id):
        self.processed_ids[command_id] = True

        while len(self.processed_ids) > PROCESSED_CACHE_SIZE:
            self.processed_ids.popitem(last=False)

    def finish(self, command_id, fields):
        for attempt in range(3):
            try:
                self.firebase.update_command(command_id, fields)
                return
            except AgentError as exc:
                log.warning(
                    "Could not update command %s (attempt %d): %s",
                    command_id,
                    attempt + 1,
                    exc
                )
                time.sleep(1)

        log.error("Giving up updating command %s.", command_id)

    @staticmethod
    def success_fields(result):
        if isinstance(result, CommandResult):
            text = result.text
            requires = result.requires_confirmation
            phrase = result.confirm_phrase
        else:
            text = str(result)
            requires = False
            phrase = None

        now = timestamp()

        return {
            "status": "completed",
            "response": text,
            "error": None,
            "requiresConfirmation": requires,
            "confirmPhrase": phrase,
            "confirmationTimeout": CONFIRMATION_TIMEOUT if requires else None,
            "updatedAt": now,
            "completedAt": now,
        }

    @staticmethod
    def failure_fields(message):
        return {
            "status": "failed",
            "response": message,
            "error": message,
            "requiresConfirmation": False,
            "confirmPhrase": None,
            "confirmationTimeout": None,
            "updatedAt": timestamp(),
        }

    def recover_stale(self, command_id, record):
        if record.get("agentId") == self.agent_id:
            return

        claimed = parse_iso(record.get("claimedAt"))

        if claimed is None:
            return

        age = (datetime.now(timezone.utc) - claimed).total_seconds()

        if age < STALE_PROCESSING_SECONDS:
            return

        log.warning("Command %s was interrupted earlier; marking failed.", command_id)
        self.remember(command_id)
        self.finish(
            command_id,
            self.failure_fields(
                "The command was interrupted when the PC agent stopped. "
                "It was not repeated. Please send it again."
            )
        )

    def process_one(self, command_id, record):
        command_id = str(command_id)

        if command_id in self.processed_ids:
            return

        if not isinstance(record, dict):
            return

        status = str(record.get("status", "pending")).strip().lower()

        if status == "processing":
            self.recover_stale(command_id, record)
            return

        if not is_pending_record(record):
            return

        command = self.get_command_text(record)

        if not command:
            return

        self.remember(command_id)

        created = record.get("createdAt")

        if isinstance(created, (int, float)) and not isinstance(created, bool):
            age = time.time() - created / 1000.0

            if age > COMMAND_MAX_AGE_SECONDS:
                log.warning("Command %s expired (%.0fs old).", command_id, age)
                self.finish(
                    command_id,
                    self.failure_fields(
                        "The command expired before the PC agent could run it."
                    )
                )
                return

        try:
            claimed = self.firebase.claim_command(command_id, self.agent_id)
        except AgentError as exc:
            log.error("Could not claim command %s: %s", command_id, exc)
            self.processed_ids.pop(command_id, None)
            return

        if not claimed:
            return

        log.info(
            "Processing command id=%s command=%s",
            command_id,
            self.describe(command)
        )

        try:
            result = self.dispatcher.dispatch(command)
            fields = self.success_fields(result)
            log.info("Command %s completed.", command_id)

        except AgentError as exc:
            log.warning("Command %s failed: %s", command_id, exc)
            fields = self.failure_fields(str(exc))

        except pyautogui.FailSafeException:
            log.warning("Command %s stopped by PyAutoGUI fail-safe.", command_id)
            fields = self.failure_fields(
                "PyAutoGUI fail-safe triggered because the mouse is in a "
                "screen corner. Move it away and try again."
            )

        except pyautogui.PyAutoGUIException as exc:
            log.warning("Command %s automation error: %s", command_id, exc)
            fields = self.failure_fields(f"Automation error: {exc}")

        except Exception as exc:
            log.exception("Unexpected error processing %s", command_id)
            fields = self.failure_fields(f"Unexpected error: {exc}")

        self.finish(command_id, fields)

    def run(self):
        log.info("%s starting.", APP_NAME)
        log.info("Database: %s", DATABASE_URL)
        log.info(
            "Polling /%s every %.1f seconds. Press Ctrl+C to stop.",
            COMMANDS_PATH,
            POLL_INTERVAL
        )

        failures = 0

        try:
            while True:
                delay = POLL_INTERVAL

                try:
                    commands = self.firebase.get_commands()
                    failures = 0

                    ordered = sorted(
                        (
                            (key, record)
                            for key, record in commands.items()
                            if isinstance(record, dict)
                        ),
                        key=lambda item: (
                            item[1].get("createdAt")
                            if isinstance(item[1].get("createdAt"), (int, float))
                            and not isinstance(item[1].get("createdAt"), bool)
                            else 0,
                            item[0]
                        )
                    )

                    for command_id, record in ordered:
                        self.process_one(command_id, record)

                except AgentError as exc:
                    failures += 1
                    log.error("%s", exc)
                    delay = min(MAX_BACKOFF, POLL_INTERVAL * (2 ** min(failures, 5)))

                except KeyboardInterrupt:
                    raise

                except Exception:
                    failures += 1
                    log.exception("Unexpected polling error.")
                    delay = min(MAX_BACKOFF, POLL_INTERVAL * (2 ** min(failures, 5)))

                time.sleep(delay)
        finally:
            self.firebase.close()


if __name__ == "__main__":
    try:
        MH2PCAssistantAgent().run()

    except KeyboardInterrupt:
        print("\nMH2 PC Assistant stopped.")

    except Exception:
        log.exception("Agent could not start.")
