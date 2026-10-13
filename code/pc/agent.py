import ctypes
import logging
import os
import re
import subprocess
import time
import webbrowser
from collections import OrderedDict
from ctypes import wintypes
from datetime import datetime, timezone
from urllib.parse import quote

import pyautogui
import pyperclip
import requests


if os.name != "nt":
    raise SystemExit("MH2 PC Assistant agent runs on Windows only.")


APP_NAME = "MH2 PC Assistant"

DATABASE_URL = (
    "https://mh2p**********************************e.app"
)

AUTH_TOKEN = ""

POLL_INTERVAL = 2
REQUEST_TIMEOUT = 15
COMMANDS_PATH = "commands"
CONFIRMATION_TIMEOUT = 60
COMMAND_MAX_AGE_SECONDS = 60
FETCH_LIMIT = 100
MAX_COMMAND_LENGTH = 2000
MAX_MOUSE_STEP = 2000
MOUSE_EDGE_MARGIN = 5
PROCESSED_CACHE_SIZE = 2000

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
dwmapi = ctypes.windll.dwmapi

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
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
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
shell32.SHEmptyRecycleBinW.argtypes = [
    wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD
]
shell32.SHEmptyRecycleBinW.restype = ctypes.c_long
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]

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


class AgentError(Exception):
    pass


class CommandResult:

    def __init__(self, text, requires_confirmation=False, confirm_phrase=None):
        self.text = text
        self.requires_confirmation = requires_confirmation
        self.confirm_phrase = confirm_phrase


def timestamp():
    return datetime.now(timezone.utc).isoformat()


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
            raise AgentError(f"Firebase connection failed: {exc}") from exc

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

    def claim_command(self, command_id):
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
            raise AgentError(f"Firebase connection failed: {exc}") from exc

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

        try:
            put = self.session.put(
                url,
                params=self._params(),
                json=claimed,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise AgentError(f"Firebase connection failed: {exc}") from exc

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


def focus_window(hwnd):
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

    time.sleep(0.4)

    return user32.GetForegroundWindow() == hwnd


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


WINDOW_TARGETS = {
    "whatsapp": lambda t, c: "whatsapp" in t.lower(),
    "word": lambda t, c: t.lower().endswith("- word") or t.lower() == "word",
    "notepad": lambda t, c: "notepad" in t.lower(),
    "chrome": lambda t, c: "google chrome" in t.lower(),
    "edge": lambda t, c: "microsoft edge" in t.lower()
        or "microsoft\u200b edge" in t.lower(),
    "file_manager": lambda t, c: c in EXPLORER_CLASSES,
    "recycle_bin": lambda t, c: c in EXPLORER_CLASSES
        and "recycle bin" in t.lower(),
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
}



BROWSER_SHORTCUTS = {
    "NEW_TAB": ("ctrl", "t"),
    "CLOSE_TAB": ("ctrl", "w"),
    "CLOSE_ALL_TABS": ("ctrl", "shift", "w"),
    "NEXT_TAB": ("ctrl", "tab"),
    "PREVIOUS_TAB": ("ctrl", "shift", "tab"),
    "REOPEN_TAB": ("ctrl", "shift", "t"),
    "RELOAD_TAB": ("ctrl", "r"),
    "ADDRESS_BAR": ("ctrl", "l"),
    "NEW_WINDOW": ("ctrl", "n"),
    "INCOGNITO": ("ctrl", "shift", "n"),
}

ALLOWED_KEYS = {
    "ENTER": "enter",
    "RETURN": "enter",
    "ESC": "esc",
    "ESCAPE": "esc",
    "TAB": "tab",
    "SPACE": "space",
    "BACKSPACE": "backspace",
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "HOME": "home",
    "END": "end",
    "PAGEUP": "pageup",
    "PAGE UP": "pageup",
    "PAGEDOWN": "pagedown",
    "PAGE DOWN": "pagedown",
}

ALLOWED_HOTKEYS = {
    "CTRL+C": ("ctrl", "c"),
    "CTRL+V": ("ctrl", "v"),
    "CTRL+A": ("ctrl", "a"),
    "CTRL+S": ("ctrl", "s"),
    "CTRL+Z": ("ctrl", "z"),
    "CTRL+Y": ("ctrl", "y"),
    "CTRL+F": ("ctrl", "f"),
    "CTRL+P": ("ctrl", "p"),
    "CTRL+N": ("ctrl", "n"),
    "CTRL+O": ("ctrl", "o"),
    "CTRL+L": ("ctrl", "l"),
    "CTRL+E": ("ctrl", "e"),
    "CTRL+R": ("ctrl", "r"),
    "CTRL+T": ("ctrl", "t"),
    "CTRL+W": ("ctrl", "w"),
    "CTRL+TAB": ("ctrl", "tab"),
    "CTRL+SHIFT+TAB": ("ctrl", "shift", "tab"),
    "CTRL+SHIFT+T": ("ctrl", "shift", "t"),
    "CTRL+SHIFT+W": ("ctrl", "shift", "w"),
    "CTRL+SHIFT+N": ("ctrl", "shift", "n"),
    "CTRL+SHIFT+ESC": ("ctrl", "shift", "esc"),
    "ALT+TAB": ("alt", "tab"),
    "ALT+LEFT": ("alt", "left"),
    "ALT+RIGHT": ("alt", "right"),
    "WIN+D": ("win", "d"),
    "WIN+E": ("win", "e"),
    "WIN+L": ("win", "l"),
    "WIN+LEFT": ("win", "left"),
    "WIN+RIGHT": ("win", "right"),
    "WIN+UP": ("win", "up"),
    "WIN+DOWN": ("win", "down"),
    "WIN+SHIFT+S": ("win", "shift", "s"),
}

SHELL_APPS = {
    "WORD": "winword.exe",
    "EXCEL": "excel.exe",
    "POWERPOINT": "powerpnt.exe",
    "EDGE": "msedge.exe",
    "PAINT": "mspaint.exe",
    "TASK MANAGER": "taskmgr.exe",
    "SETTINGS": "ms-settings:",
}

APP_NAME_ALIASES = {
    "GOOGLE CHROME": "CHROME",
    "WHATS APP": "WHATSAPP",
    "WHATSAPP WEB": "WHATSAPP",
    "MS WORD": "WORD",
    "MICROSOFT WORD": "WORD",
    "MS EXCEL": "EXCEL",
    "MICROSOFT EXCEL": "EXCEL",
    "MS POWERPOINT": "POWERPOINT",
    "MICROSOFT POWERPOINT": "POWERPOINT",
    "CALC": "CALCULATOR",
    "MICROSOFT EDGE": "EDGE",
    "MS PAINT": "PAINT",
}

SITES = {
    "YOUTUBE": "https://www.youtube.com",
    "GOOGLE": "https://www.google.com",
    "GITHUB": "https://github.com",
    "FACEBOOK": "https://www.facebook.com",
    "GMAIL": "https://mail.google.com",
}


class WindowsActions:

    @staticmethod
    def paste_text(text, trailing_space=False):
        if not text:
            raise AgentError("No text was provided.")

        if len(text) > MAX_COMMAND_LENGTH:
            raise AgentError("Text is too long.")

        payload = str(text) + (" " if trailing_space else "")
        previous = None

        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            previous = None

        pyperclip.copy(payload)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.25)

        if previous is not None:
            try:
                pyperclip.copy(previous)
            except pyperclip.PyperclipException:
                pass

        return "Text pasted into the active window."

    @staticmethod
    def open_start_menu_app(app_name):
        app_name = app_name.strip()

        if not app_name:
            raise AgentError("Please specify an application name.")

        if len(app_name) > 100:
            raise AgentError("Application name is too long.")

        previous = None

        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            previous = None

        pyautogui.hotkey("win", "s")
        time.sleep(1.0)
        pyperclip.copy(app_name)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1.5)
        pyautogui.press("enter")

        if previous is not None:
            try:
                pyperclip.copy(previous)
            except pyperclip.PyperclipException:
                pass

        return f"Windows Search opened the app request: {app_name}"

    @staticmethod
    def open_notepad():
        subprocess.Popen(["notepad.exe"])
        return "Notepad opened."

    @staticmethod
    def open_calculator():
        subprocess.Popen(["calc.exe"])
        return "Calculator opened."

    @staticmethod
    def open_chrome():
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

        for executable in candidates:
            if os.path.isfile(executable):
                subprocess.Popen([executable])
                return "Google Chrome opened."

        webbrowser.open("https://www.google.com")
        return "Chrome was not found. Opened the default browser instead."

    @staticmethod
    def open_whatsapp():
        try:
            os.startfile("whatsapp:")
            return "WhatsApp launch requested."
        except OSError:
            webbrowser.open("https://web.whatsapp.com")
            return "Opened WhatsApp Web."

    @staticmethod
    def open_app(name):
        key = " ".join(str(name).upper().replace("_", " ").split())
        key = APP_NAME_ALIASES.get(key, key)

        if key == "NOTEPAD":
            return WindowsActions.open_notepad()

        if key == "CHROME":
            return WindowsActions.open_chrome()

        if key == "WHATSAPP":
            return WindowsActions.open_whatsapp()

        if key == "CALCULATOR":
            return WindowsActions.open_calculator()

        target = SHELL_APPS.get(key)

        if target:
            try:
                os.startfile(target)
                return f"{key.title()} opened."
            except OSError:
                return WindowsActions.open_start_menu_app(name)

        return WindowsActions.open_start_menu_app(name)

    @staticmethod
    def open_whatsapp_inbox():
        message = WindowsActions.open_whatsapp()
        time.sleep(2.0)

        found = find_window(WINDOW_TARGETS["whatsapp"])

        if found:
            focus_window(found[0])

        return message

    @staticmethod
    def open_whatsapp_contacts():
        WindowsActions.open_whatsapp()
        time.sleep(2.0)

        found = find_window(WINDOW_TARGETS["whatsapp"])

        if not found or not focus_window(found[0]):
            raise AgentError("The WhatsApp window could not be focused.")

        pyautogui.hotkey("ctrl", "n")

        return "WhatsApp focused and Ctrl+N (new chat) pressed."

    @staticmethod
    def open_this_pc():
        os.startfile("shell:MyComputerFolder")
        return "This PC opened."

    @staticmethod
    def open_folder(name):
        folders = {
            "DOWNLOADS": "Downloads",
            "DESKTOP": "Desktop",
            "DOCUMENTS": "Documents",
            "PICTURES": "Pictures",
            "MUSIC": "Music",
            "VIDEOS": "Videos",
        }

        raw = name.strip().strip('"')
        upper = raw.upper()
        home = os.path.expanduser("~")

        if upper == "HOME":
            path = home
        elif upper in folders:
            path = os.path.join(home, folders[upper])
        else:
            path = os.path.expandvars(os.path.expanduser(raw))

        if not os.path.isdir(path):
            raise AgentError(f"Folder not found: {path}")

        os.startfile(path)
        return f"Opened: {path}"

    @staticmethod
    def open_drive(letter):
        path = letter.upper() + ":\\"

        if not os.path.isdir(path):
            raise AgentError(f"Drive not found: {path}")

        os.startfile(path)
        return f"Opened drive {path}"

    @staticmethod
    def open_recycle_bin():
        os.startfile("shell:RecycleBinFolder")
        return "Recycle Bin opened."

    @staticmethod
    def open_website(url):
        url = url.strip()

        if not url:
            raise AgentError("Website URL is missing.")

        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url

        if not re.match(r"^https?://[^/\s]+", url, re.IGNORECASE):
            raise AgentError("Invalid website URL.")

        webbrowser.open(url)
        return f"Opening {url}"

    @staticmethod
    def search_google(query):
        query = query.strip()

        if not query:
            raise AgentError("Search text is missing.")

        webbrowser.open(
            "https://www.google.com/search?q=" + quote(query, safe="")
        )

        return f"Searching Google for: {query}"

    @staticmethod
    def browser_shortcut(action):
        keys = BROWSER_SHORTCUTS.get(action)

        if not keys:
            raise AgentError("Unsupported browser action.")

        pyautogui.hotkey(*keys)
        return f"Browser shortcut sent to the active window: {action}"

    @staticmethod
    def press_key(key):
        normalized = " ".join(key.strip().upper().split())

        if normalized in ALLOWED_KEYS:
            pyautogui.press(ALLOWED_KEYS[normalized])
            return f"Pressed {normalized}."

        if re.fullmatch(r"F(?:[1-9]|1[0-2])", normalized):
            pyautogui.press(normalized.lower())
            return f"Pressed {normalized}."

        if re.fullmatch(r"[A-Z0-9]", normalized):
            pyautogui.press(normalized.lower())
            return f"Pressed {normalized}."

        raise AgentError("This key is not in the allowed key list.")

    @staticmethod
    def hotkey(shortcut):
        key = "+".join(
            item.strip().upper() for item in shortcut.split("+")
        )

        if key not in ALLOWED_HOTKEYS:
            raise AgentError("This keyboard shortcut is not allowed.")

        pyautogui.hotkey(*ALLOWED_HOTKEYS[key])
        return f"Shortcut pressed: {key}"

    @staticmethod
    def clamp_point(x, y):
        width, height = pyautogui.size()

        return (
            min(max(int(x), MOUSE_EDGE_MARGIN), width - 1 - MOUSE_EDGE_MARGIN),
            min(max(int(y), MOUSE_EDGE_MARGIN), height - 1 - MOUSE_EDGE_MARGIN),
        )

    @staticmethod
    def mouse_move(direction, amount):
        amount = min(max(int(amount), 1), MAX_MOUSE_STEP)
        x, y = pyautogui.position()

        deltas = {
            "LEFT": (-amount, 0),
            "RIGHT": (amount, 0),
            "UP": (0, -amount),
            "DOWN": (0, amount),
        }

        dx, dy = deltas[direction.upper()]
        target_x, target_y = WindowsActions.clamp_point(x + dx, y + dy)

        pyautogui.moveTo(target_x, target_y, duration=0.2)

        return (
            f"Mouse moved {direction.lower()} toward {amount} pixels. "
            f"Position: {target_x}, {target_y}."
        )

    @staticmethod
    def mouse_move_to(x, y):
        target_x, target_y = WindowsActions.clamp_point(x, y)

        pyautogui.moveTo(target_x, target_y, duration=0.2)

        return f"Mouse moved to {target_x}, {target_y}."

    @staticmethod
    def mouse_click(kind):
        if kind == "double":
            pyautogui.doubleClick()
            return "Double-click performed."

        if kind == "right":
            pyautogui.rightClick()
            return "Right-click performed."

        pyautogui.click()
        return "Click performed."

    @staticmethod
    def scroll(direction, amount=5):
        direction = direction.upper()
        amount = min(max(int(amount), 1), 100)

        if direction == "UP":
            pyautogui.scroll(amount)
        elif direction == "DOWN":
            pyautogui.scroll(-amount)
        elif direction == "LEFT":
            pyautogui.hscroll(-amount)
        elif direction == "RIGHT":
            pyautogui.hscroll(amount)
        else:
            raise AgentError("Use SCROLL UP, DOWN, LEFT or RIGHT.")

        return f"Scrolled {direction.lower()} by {amount}."

    @staticmethod
    def focus_target(name):
        raw = str(name).strip()
        key = re.sub(r"[\s\-]+", "_", raw.lower())
        key = TARGET_ALIASES.get(key, key)

        if key in ("address_bar", "url_bar"):
            pyautogui.hotkey("ctrl", "l")
            return "Address bar focused (Ctrl+L)."

        if key in ("search", "search_box", "search_bar"):
            pyautogui.hotkey("ctrl", "e")
            return "Search box focused (Ctrl+E)."

        matcher = WINDOW_TARGETS.get(key)

        if matcher is None:
            needle = raw.lower()

            if not needle:
                raise AgentError("Window name is missing.")

            matcher = lambda title, cls: needle in title.lower()

        found = find_window(matcher)

        if not found:
            raise AgentError(f"No open window found for: {raw}")

        hwnd, title = found

        if not focus_window(hwnd):
            raise AgentError(
                f"Windows did not allow focusing the window: {title}"
            )

        return f"Focused window: {title}"

    @staticmethod
    def set_window_state(action):
        hwnd = foreground_window()
        title = window_title(hwnd)

        states = {
            "MINIMIZE": (SW_MINIMIZE, "minimized"),
            "MAXIMIZE": (SW_MAXIMIZE, "maximized"),
            "RESTORE": (SW_RESTORE, "restored"),
        }

        flag, label = states[action]
        user32.ShowWindow(hwnd, flag)

        return f"Window {label}: {title}"

    @staticmethod
    def close_window():
        hwnd = foreground_window()
        title = window_title(hwnd)

        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

        return f"Close requested for: {title}"

    @staticmethod
    def snap_window(direction):
        foreground_window()
        pyautogui.hotkey("win", direction.lower())

        return f"Window snapped {direction.lower()}."

    @staticmethod
    def switch_window():
        pyautogui.hotkey("alt", "tab")
        return "Switched window (Alt+Tab)."

    @staticmethod
    def describe_windows():
        entries = list_windows()[:15]

        if not entries:
            return "No open windows were found."

        titles = [title[:60] for _, title, _ in entries]

        return "Open windows: " + "; ".join(titles)

    @staticmethod
    def volume(action, steps=5):
        steps = min(max(int(steps), 1), 25)

        if action == "MUTE":
            pyautogui.press("volumemute")
            return "Volume mute toggled."

        key = "volumeup" if action == "UP" else "volumedown"

        for _ in range(steps):
            pyautogui.press(key)

        return f"Volume {action.lower()} by {steps} steps."

    @staticmethod
    def screenshot():
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

        path = os.path.join(
            SCREENSHOT_DIR,
            datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
        )

        pyautogui.screenshot(path)

        return f"Screenshot saved: {path}"

    @staticmethod
    def lock_pc():
        if not user32.LockWorkStation():
            raise AgentError("Windows could not lock the workstation.")

        return "PC locked."

    @staticmethod
    def empty_recycle_bin():
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

ALIASES = {
    "OPEN GOOGLE CHROME": "OPEN_APP CHROME",
    "OPEN CHROME": "OPEN_APP CHROME",
    "OPEN NOTEPAD": "OPEN_APP NOTEPAD",
    "OPEN WHATSAPP": "OPEN_APP WHATSAPP",
    "OPEN WHATSAPP WEB": "OPEN_APP WHATSAPP",
    "OPEN CALCULATOR": "OPEN_APP CALCULATOR",
    "OPEN WORD": "OPEN_APP WORD",
    "OPEN EXCEL": "OPEN_APP EXCEL",
    "OPEN POWERPOINT": "OPEN_APP POWERPOINT",
    "OPEN PAINT": "OPEN_APP PAINT",
    "OPEN EDGE": "OPEN_APP EDGE",
    "OPEN SETTINGS": "OPEN_APP SETTINGS",
    "OPEN TASK MANAGER": "OPEN_APP TASK MANAGER",
    "OPEN FILES": "OPEN_FILE_MANAGER",
    "NEW TAB": "BROWSER NEW_TAB",
    "CLOSE TAB": "BROWSER CLOSE_TAB",
    "CLOSE ALL TABS": "BROWSER CLOSE_ALL_TABS",
    "NEXT TAB": "BROWSER NEXT_TAB",
    "SWITCH TAB": "BROWSER NEXT_TAB",
    "PREVIOUS TAB": "BROWSER PREVIOUS_TAB",
    "LAST TAB": "BROWSER PREVIOUS_TAB",
    "REOPEN TAB": "BROWSER REOPEN_TAB",
    "RELOAD TAB": "BROWSER RELOAD_TAB",
    "NEW WINDOW": "BROWSER NEW_WINDOW",
    "OPEN INCOGNITO": "BROWSER INCOGNITO",
    "SHOW DESKTOP": "HOTKEY WIN+D",
    "MINIMIZE ALL": "HOTKEY WIN+D",
    "PAGE UP": "SCROLL UP",
    "PAGE DOWN": "SCROLL DOWN",
    "PRESS ESCAPE": "PRESS ESC",
    "MUTE": "VOLUME MUTE",
    "UNMUTE": "VOLUME MUTE",
}


class PCCommandDispatcher:

    def __init__(self):
        self.actions = WindowsActions()
        self.pending = None

        patterns = [
            (r"^(?:GET[_ ])?STATUS$", self.cmd_status),
            (r"^(?:SHUTDOWN|SHUT DOWN|TURN OFF)(?: PC| COMPUTER)?$", self.cmd_shutdown),
            (r"^(?:RESTART|REBOOT)(?: PC| COMPUTER)?$", self.cmd_restart),
            (r"^LOCK(?: PC| COMPUTER| SCREEN)?$", self.cmd_lock),
            (r"^CANCEL[_ ]SHUTDOWN$", self.cmd_cancel_shutdown),
            (r"^DELETE[_ ]SELECTED(?:[_ ]FILES)?(?:[_ ]REQUEST)?$", self.cmd_delete_selected),
            (r"^(?:DELETE[_ ]ALL[_ ]FILES|DELETE EVERYTHING)(?:[_ ]REQUEST)?$", self.cmd_delete_all),
            (r"^(?:EMPTY|CLEAR)[_ ]RECYCLE[_ ]BIN(?:[_ ]REQUEST)?$", self.cmd_empty_recycle_bin),
            (r"^SELECT[_ ]ALL(?:[_ ]FILES)?$", self.cmd_select_all),
            (r"^OPEN[_ ]APP" + SEP + r"(.+)$", self.cmd_open_app),
            (r"^OPEN[_ ](?:FILE[_ ]MANAGER|FILE[_ ]EXPLORER|WINDOWS[_ ]EXPLORER|EXPLORER|THIS[_ ]PC|MY[_ ]COMPUTER)$", self.cmd_open_this_pc),
            (r"^OPEN[_ ]WHATSAPP[_ ]INBOX$", self.cmd_whatsapp_inbox),
            (r"^OPEN[_ ]WHATSAPP[_ ]CONTACTS$", self.cmd_whatsapp_contacts),
            (r"^OPEN[_ ]DRIVE\s+([A-Z]):?\\?$", self.cmd_open_drive),
            (r"^OPEN\s+([A-Z])\s+DRIVE$", self.cmd_open_drive),
            (r"^OPEN[_ ]RECYCLE[_ ]BIN$", self.cmd_open_recycle_bin),
            (r"^OPEN[_ ]FOLDER" + SEP + r"(.+)$", self.cmd_open_folder),
            (r"^OPEN[_ ]PATH" + SEP + r"(.+)$", self.cmd_open_folder),
            (r"^OPEN (DOWNLOADS|DESKTOP|DOCUMENTS|PICTURES|MUSIC|VIDEOS|HOME)$", self.cmd_open_folder),
            (r"^OPEN[_ ]WEBSITE" + SEP + r"(.+)$", self.cmd_open_website),
            (r"^OPEN (YOUTUBE|GOOGLE|GITHUB|FACEBOOK|GMAIL)$", self.cmd_open_site),
            (r"^GO TO\s+(.+)$", self.cmd_open_website),
            (r"^(?:SEARCH|SEARCH GOOGLE|GOOGLE SEARCH)\s*:\s*(.+)$", self.cmd_search),
            (r"^SEARCH\s+(.+)$", self.cmd_search),
            (r"^BROWSER[_ ]([A-Z_ ]+)$", self.cmd_browser),
            (r"^PRESS\s+(.+)$", self.cmd_press),
            (r"^HOTKEY\s+(.+)$", self.cmd_hotkey),
            (r"^(?:MOUSE[_ ])?SCROLL\s+(UP|DOWN|LEFT|RIGHT)(?:\s+(\d+))?$", self.cmd_scroll),
            (r"^(?:MOUSE[_ ]MOVE[_ ]TO|MOVE MOUSE TO)\s+(?:X\s*)?(\d+)\s*,?\s*(?:Y\s*)?(\d+)$", self.cmd_mouse_move_to),
            (r"^(?:MOUSE[_ ]MOVE|MOVE MOUSE)\s+(LEFT|RIGHT|UP|DOWN)(?:\s+(\d+))?$", self.cmd_mouse_move),
            (r"^(?:MOUSE[_ ])?(?:LEFT[_ ])?CLICK$", self.cmd_click),
            (r"^(?:MOUSE[_ ])?DOUBLE[ _-]?CLICK$", self.cmd_double_click),
            (r"^(?:MOUSE[_ ])?RIGHT[ _-]?CLICK$", self.cmd_right_click),
            (r"^MOUSE[_ ]POSITION$", self.cmd_mouse_position),
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
            (r"^OPEN\s+(.+)$", self.cmd_open_generic),
        ]

        self.routes = [
            (re.compile(pattern, re.IGNORECASE), handler)
            for pattern, handler in patterns
        ]

        self.typing_routes = [
            (re.compile(r"^TYPE_TARGET" + SEP + r"(.+)$", re.IGNORECASE | re.DOTALL), self.typing_target),
            (re.compile(r"^(?:TYPE_END|TYPE END|TYPING END|STOP TYPING|CANCEL_TYPING)$", re.IGNORECASE), self.typing_end),
            (re.compile(r"^TYPE_SEND$", re.IGNORECASE), self.typing_send),
            (re.compile(r"^SEND_MESSAGE" + SEP + r"(.+)$", re.IGNORECASE | re.DOTALL), self.typing_send_message),
            (re.compile(r"^TYPE_TEXT" + SEP + r"(.+)$", re.IGNORECASE | re.DOTALL), self.typing_text),
            (re.compile(r"^TYPE(?:\s*:\s*|\s+)(.+)$", re.IGNORECASE | re.DOTALL), self.typing_plain),
        ]

    @staticmethod
    def key_of(text):
        return " ".join(
            str(text).replace("_", " ").split()
        ).upper().rstrip(".,!?;:")

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

    def handle_confirmation(self, key):
        if key in CANCEL_KEYS:
            if self.pending:
                self.pending = None
                return "Pending action cancelled."

            return "Nothing is waiting to be cancelled."

        if key.startswith("CONFIRM "):
            pending = self.pending

            if not pending:
                raise AgentError("There is nothing waiting for confirmation.")

            if time.time() > pending["expires"]:
                self.pending = None
                raise AgentError("Confirmation expired. Send the action again.")

            if key != pending["phrase"]:
                raise AgentError(
                    f"The pending action requires: {pending['phrase']}."
                )

            self.pending = None
            return pending["runner"]()

        if self.pending:
            log.info("Pending confirmation discarded by a new command.")
            self.pending = None

        return None

    def dispatch(self, raw):
        text = str(raw or "").strip()

        if not text:
            raise AgentError("Empty command.")

        if len(text) > MAX_COMMAND_LENGTH:
            raise AgentError("Command is too long.")

        key = self.key_of(text)
        handled = self.handle_confirmation(key)

        if handled is not None:
            return handled

        for pattern, handler in self.typing_routes:
            match = pattern.match(text)

            if match:
                return handler(match)

        command = " ".join(text.split()).rstrip(".,!?;:")
        command = ALIASES.get(key, command)

        for pattern, handler in self.routes:
            match = pattern.match(command)

            if match:
                return handler(match)

        raise AgentError(
            f"Unsupported command: {command}. "
            "Try OPEN_APP name, TYPE_TEXT text, SEARCH: query, "
            "MOUSE_CLICK, MOUSE_MOVE LEFT 100, SCROLL DOWN, "
            "HOTKEY CTRL+C, FOCUS_WINDOW name, or another supported command."
        )

    # ---------------- typing ----------------

    def typing_target(self, match):
        return self.actions.focus_target(match.group(1)) + " Ready for text."

    def typing_end(self, match):
        return "Typing operation ended."

    def typing_send(self, match):
        pyautogui.press("enter")
        return "Enter pressed."

    def typing_send_message(self, match):
        self.actions.paste_text(match.group(1))
        pyautogui.press("enter")
        return "Message pasted and Enter pressed."

    def typing_text(self, match):
        return self.actions.paste_text(match.group(1), trailing_space=True)

    def typing_plain(self, match):
        return self.actions.paste_text(match.group(1))

    # ---------------- general ----------------

    def cmd_status(self, match):
        return "MH2 PC Assistant is running."

    def cmd_send_enter(self, match):
        pyautogui.press("enter")
        return "Enter pressed."

    def cmd_open_app(self, match):
        return self.actions.open_app(match.group(1))

    def cmd_open_generic(self, match):
        return self.actions.open_start_menu_app(match.group(1))

    def cmd_open_this_pc(self, match):
        return self.actions.open_this_pc()

    def cmd_whatsapp_inbox(self, match):
        return self.actions.open_whatsapp_inbox()

    def cmd_whatsapp_contacts(self, match):
        return self.actions.open_whatsapp_contacts()

    def cmd_open_drive(self, match):
        return self.actions.open_drive(match.group(1))

    def cmd_open_recycle_bin(self, match):
        return self.actions.open_recycle_bin()

    def cmd_open_folder(self, match):
        return self.actions.open_folder(match.group(1))

    def cmd_open_website(self, match):
        return self.actions.open_website(match.group(1))

    def cmd_open_site(self, match):
        return self.actions.open_website(SITES[match.group(1).upper()])

    def cmd_search(self, match):
        return self.actions.search_google(match.group(1))

    def cmd_browser(self, match):
        action = match.group(1).strip().upper().replace(" ", "_")
        return self.actions.browser_shortcut(action)

    def cmd_press(self, match):
        return self.actions.press_key(match.group(1))

    def cmd_hotkey(self, match):
        return self.actions.hotkey(match.group(1))

    def cmd_scroll(self, match):
        return self.actions.scroll(match.group(1), match.group(2) or 5)

    def cmd_mouse_move_to(self, match):
        return self.actions.mouse_move_to(match.group(1), match.group(2))

    def cmd_mouse_move(self, match):
        return self.actions.mouse_move(match.group(1), match.group(2) or 100)

    def cmd_click(self, match):
        return self.actions.mouse_click("left")

    def cmd_double_click(self, match):
        return self.actions.mouse_click("double")

    def cmd_right_click(self, match):
        return self.actions.mouse_click("right")

    def cmd_mouse_position(self, match):
        x, y = pyautogui.position()
        width, height = pyautogui.size()
        return f"Mouse is at {x}, {y}. Screen size: {width}x{height}."

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
        pyautogui.hotkey("ctrl", "a")
        return "Select all (Ctrl+A) pressed in the active window."

    # ---------------- power and deletion ----------------

    def execute_power(self, action):
        if action == "SHUTDOWN":
            subprocess.Popen(["shutdown.exe", "/s", "/t", "30"])
            return (
                "Windows shutdown scheduled in 30 seconds. "
                "Send CANCEL SHUTDOWN to abort."
            )

        subprocess.Popen(["shutdown.exe", "/r", "/t", "30"])
        return (
            "Windows restart scheduled in 30 seconds. "
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

    def cmd_cancel_shutdown(self, match):
        result = subprocess.run(
            ["shutdown.exe", "/a"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )

        if result.returncode == 0:
            return "Scheduled shutdown or restart cancelled."

        return "No shutdown or restart is in progress."

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
        if re.match(r"^(TYPE|SEND_MESSAGE)", command, re.IGNORECASE):
            return f"{command.split()[0]} ({len(command)} chars)"

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

    def process_one(self, command_id, record):
        command_id = str(command_id)

        if command_id in self.processed_ids:
            return

        if not is_pending_record(record):
            return

        command = self.get_command_text(record)

        if not command:
            return

        self.remember(command_id)

        created = record.get("createdAt")

        if isinstance(created, (int, float)):
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
            claimed = self.firebase.claim_command(command_id)
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

        while True:
            try:
                commands = self.firebase.get_commands()

                ordered = sorted(
                    (
                        (key, record)
                        for key, record in commands.items()
                        if isinstance(record, dict)
                    ),
                    key=lambda item: (
                        item[1].get("createdAt")
                        if isinstance(item[1].get("createdAt"), (int, float))
                        else 0,
                        item[0]
                    )
                )

                for command_id, record in ordered:
                    self.process_one(command_id, record)

            except AgentError as exc:
                log.error("%s", exc)

            except KeyboardInterrupt:
                raise

            except Exception:  log.exception("Unexpected polling error.")

            time.sleep(POLL_INTERVAL)



if __name__ == "__main__":
    try:  MH2PCAssistantAgent().run()

    except KeyboardInterrupt:  print("\nMH2 PC Assistant stopped.")

    except Exception: log.exception("Agent could not start.")
