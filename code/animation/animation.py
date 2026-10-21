import pygame
import math
import random
import sys
import time

pygame.init()

# Window setup
WIDTH, HEIGHT = 1000, 750
screen = pygame.display.set_mode(
    (WIDTH, HEIGHT), pygame.RESIZABLE
)
pygame.display.set_caption("MH2 AI Assistant")

clock = pygame.time.Clock()

# Colors
BG = (2, 8, 7)
CYAN = (0, 245, 255)
GREEN = (57, 255, 136)
WHITE = (235, 255, 255)
MUTED = (70, 130, 140)

active = False
start_time = time.time()
status = "AWAITING COMMAND"

particles = []

def create_particles():
    particles.clear()
    w, h = screen.get_size()

    for _ in range(100):
        particles.append({
            "x": random.uniform(0, w),
            "y": random.uniform(0, h),
            "vx": random.uniform(-0.5, 0.5),
            "vy": random.uniform(-0.5, 0.5),
            "size": random.randint(1, 3)
        })

create_particles()


def glow_circle(surface, color, pos, radius, strength=3):
    x, y = int(pos[0]), int(pos[1])

    for i in range(strength, 0, -1):
        glow_radius = radius + i * 5
        alpha = max(3, 18 // i)

        layer = pygame.Surface(
            (glow_radius * 2 + 4, glow_radius * 2 + 4),
            pygame.SRCALPHA
        )

        pygame.draw.circle(
            layer,
            (*color, alpha),
            (glow_radius + 2, glow_radius + 2),
            glow_radius,
            2
        )

        surface.blit(
            layer,
            (x - glow_radius - 2, y - glow_radius - 2)
        )

    pygame.draw.circle(surface, color, (x, y), radius)


def draw_text(text, size, color, pos, center=True):
    font = pygame.font.SysFont("consolas", size, bold=True)
    image = font.render(text, True, color)

    if center:
        rect = image.get_rect(center=pos)
    else:
        rect = image.get_rect(topleft=pos)

    screen.blit(image, rect)


def draw_background():
    screen.fill(BG)
    w, h = screen.get_size()

    # Digital grid
    for x in range(0, w, 40):
        pygame.draw.line(
            screen, (7, 24, 25), (x, 0), (x, h)
        )

    for y in range(0, h, 40):
        pygame.draw.line(
            screen, (7, 24, 25), (0, y), (w, y)
        )

    # Particles
    for p in particles:
        p["x"] += p["vx"] * (2 if active else 1)
        p["y"] += p["vy"] * (2 if active else 1)

        if p["x"] < 0 or p["x"] > w:
            p["vx"] *= -1

        if p["y"] < 0 or p["y"] > h:
            p["vy"] *= -1

        color = GREEN if active else CYAN

        pygame.draw.circle(
            screen,
            color,
            (int(p["x"]), int(p["y"])),
            p["size"]
        )

    # Connections
    for i, p in enumerate(particles):
        for q in particles[i + 1:]:
            dx = p["x"] - q["x"]
            dy = p["y"] - q["y"]
            distance = math.hypot(dx, dy)

            if distance < 100:
                pygame.draw.line(
                    screen,
                    (0, 55, 60),
                    (int(p["x"]), int(p["y"])),
                    (int(q["x"]), int(q["y"])),
                    1
                )


def draw_ai_core(cx, cy, radius, elapsed):
    color = GREEN if active else CYAN

    # Outer rotating rings
    for ring_radius, speed, offset, col in [
        (radius, 0.45, 0, color),
        (radius * 0.82, -0.8, 0.8, GREEN),
        (radius * 0.65, 0.25, 1.5, color),
    ]:
        rect = pygame.Rect(
            cx - ring_radius,
            cy - ring_radius,
            ring_radius * 2,
            ring_radius * 2
        )

        pygame.draw.arc(
            screen,
            col,
            rect,
            elapsed * speed + offset,
            elapsed * speed + offset + math.pi * 1.5,
            2
        )

        pygame.draw.arc(
            screen,
            (15, 80, 85),
            rect,
            elapsed * speed + offset + math.pi * 1.5,
            elapsed * speed + offset + math.tau,
            1
        )

    # Orbiting dots
    for i in range(8):
        angle = elapsed * 0.8 + i * math.tau / 8

        x = cx + math.cos(angle) * radius
        y = cy + math.sin(angle) * radius

        glow_circle(screen, color, (x, y), 3, 1)

    # AI face
    face_w = radius * 0.86
    face_h = radius * 0.92

    face_rect = pygame.Rect(
        cx - face_w / 2,
        cy - face_h / 2,
        face_w,
        face_h
    )

    pygame.draw.rect(
        screen, (3, 25, 29), face_rect, border_radius=35
    )

    pygame.draw.rect(
        screen, color, face_rect, 2, border_radius=35
    )

    # Eyes
    eye_y = cy - radius * 0.12
    eye_gap = radius * 0.26
    eye_width = max(5, int(radius * 0.15))
    eye_height = max(3, int(radius * 0.055))

    for eye_x in (cx - eye_gap, cx + eye_gap):
        eye_rect = pygame.Rect(
            int(eye_x - eye_width / 2),
            int(eye_y - eye_height / 2),
            eye_width,
            eye_height
        )

        pygame.draw.rect(
            screen, color, eye_rect, border_radius=5
        )

    # Animated mouth
    mouth_width = radius * (
        0.30 + 0.07 * math.sin(elapsed * 4)
    )

    mouth_rect = pygame.Rect(
        int(cx - mouth_width / 2),
        int(cy + radius * 0.25),
        int(mouth_width),
        max(3, int(radius * 0.045))
    )

    pygame.draw.rect(
        screen, GREEN, mouth_rect, border_radius=5
    )


def draw_button(rect, label, mouse_pos):
    hovered = rect.collidepoint(mouse_pos)

    color = GREEN if hovered else CYAN
    fill = (10, 45, 42) if hovered else (4, 20, 24)

    pygame.draw.rect(
        screen, fill, rect, border_radius=5
    )

    pygame.draw.rect(
        screen, color, rect, 1, border_radius=5
    )

    draw_text(
        label, 15, color, rect.center
    )


def main():
    global active, status, particles

    running = True

    while running:
        dt = clock.tick(60) / 1000
        elapsed = time.time() - start_time

        w, h = screen.get_size()
        cx = w // 2
        cy = int(h * 0.35)

        mouse_pos = pygame.mouse.get_pos()

        # Responsive layout
        radius = max(75, min(125, int(min(w, h) * 0.18)))

        activate_rect = pygame.Rect(
            cx - 190, int(h * 0.77), 175, 42
        )

        reboot_rect = pygame.Rect(
            cx + 15, int(h * 0.77), 175, 42
        )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                create_particles()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_SPACE:
                    active = not active
                    status = (
                        "AI CORE ACTIVATED"
                        if active else "AWAITING COMMAND"
                    )

                elif event.key == pygame.K_r:
                    active = False
                    status = "SYSTEM REBOOTED"
                    create_particles()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if activate_rect.collidepoint(event.pos):
                        active = not active
                        status = (
                            "AI CORE ACTIVATED"
                            if active else "AWAITING COMMAND"
                        )

                    elif reboot_rect.collidepoint(event.pos):
                        active = False
                        status = "SYSTEM REBOOTED"
                        create_particles()

                    elif math.hypot(
                        event.pos[0] - cx,
                        event.pos[1] - cy
                    ) < radius:
                        active = not active
                        status = (
                            "AI CORE ACTIVATED"
                            if active else "AWAITING COMMAND"
                        )

        # Draw scene
        draw_background()

        draw_text(
            "MH2 SYSTEM  |  AI CORE v1.0",
            13, GREEN, (18, 20), False
        )

        draw_text(
            time.strftime("%H:%M:%S"),
            13, CYAN, (w - 18, 20), False
        )

        draw_ai_core(cx, cy, radius, elapsed)

        # Brand
        brand_y = int(h * 0.58)

        draw_text(
            "MH2",
            max(42, min(76, int(w * 0.085))),
            WHITE,
            (cx, brand_y)
        )

        draw_text(
            "A I   A S S I S T A N T",
            15, GREEN, (cx, brand_y + 52)
        )

        # Status indicator
        status_color = GREEN if active else CYAN

        pygame.draw.circle(
            screen, status_color,
            (cx - 100, int(h * 0.69)), 4
        )

        draw_text(
            status, 13, status_color,
            (cx + 8, int(h * 0.69))
        )

        draw_button(
            activate_rect,
            "DEACTIVATE AI" if active else "ACTIVATE AI",
            mouse_pos
        )

        draw_button(
            reboot_rect, "REBOOT", mouse_pos
        )

        draw_text(
            "DESIGNED FOR MH2 AI SYSTEM",
            11, MUTED, (cx, h - 22)
        )

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
