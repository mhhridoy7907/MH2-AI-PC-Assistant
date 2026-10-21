import math
import random
import sys
import time
import traceback
from collections import deque

import pygame

pygame.init()

TITLE = "MH2 AI | PC ASSISTANT"
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
    app = App()
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
