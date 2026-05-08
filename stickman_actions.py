
import math
import sys
import threading

import pygame

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    np = None
    sd = None


WIDTH, HEIGHT = 900, 600
FPS = 60
GROUND_Y = 470
BG_COLOR = (245, 247, 255)
TEXT_COLOR = (30, 35, 50)
ACCENT = (70, 110, 220)
STICK_COLOR = (20, 20, 20)


class Stickman:
    def __init__(self):
        self.x = WIDTH // 2
        self.ground = GROUND_Y
        self.base_head_radius = 22
        self.t = 0.0
        self.action = "idle"
        self.vertical_offset = 0.0

    def set_action(self, action: str):
        self.action = action
        if action in {"jump", "hop"}:
            self.t = 0.0

    def update(self, dt: float):
        self.t += dt

        if self.action == "walk":
            self.x += 80 * dt
        elif self.action == "run":
            self.x += 180 * dt
        elif self.action == "crawl":
            self.x += 40 * dt
        elif self.action == "moonwalk":
            self.x -= 100 * dt
        elif self.action == "march":
            self.x += 60 * dt
        elif self.action == "dance":
            self.x += math.sin(self.t * 3.0) * 1.0

        if self.x > WIDTH + 40:
            self.x = -40
        if self.x < -40:
            self.x = WIDTH + 40

        if self.action == "jump":
            # One-shot jump arc
            jump_duration = 0.9
            p = min(self.t / jump_duration, 1.0)
            arc = 4 * p * (1 - p)
            self.vertical_offset = -arc * 150
            if p >= 1.0:
                self.action = "idle"
                self.vertical_offset = 0.0
                self.t = 0.0
        elif self.action == "hop":
            self.vertical_offset = -abs(math.sin(self.t * 6.0)) * 50
        else:
            self.vertical_offset = 0.0

    def draw(self, surface: pygame.Surface):
        cx = int(self.x)
        cy = int(self.ground + self.vertical_offset)

        phase = self.t * 5.0
        amp = 0.0
        speed = 1.0

        if self.action == "walk":
            amp = math.radians(30)
            speed = 4.5
        elif self.action == "run":
            amp = math.radians(55)
            speed = 8.0
        elif self.action == "march":
            amp = math.radians(40)
            speed = 5.0
        elif self.action == "dance":
            amp = math.radians(45)
            speed = 10.0
        elif self.action == "moonwalk":
            amp = math.radians(28)
            speed = 5.0
        elif self.action == "crawl":
            amp = math.radians(18)
            speed = 6.0

        leg_phase = phase * speed
        arm_phase = leg_phase + math.pi
        leg1 = math.sin(leg_phase) * amp
        leg2 = math.sin(leg_phase + math.pi) * amp
        arm1 = math.sin(arm_phase) * amp * 0.9
        arm2 = math.sin(arm_phase + math.pi) * amp * 0.9

        torso_len = 85
        thigh_len = 46
        shin_len = 46
        upper_arm_len = 38
        forearm_len = 36

        if self.action == "wave":
            arm1 = math.radians(-80)
            arm2 = math.radians(20)
            wave_bend = math.radians(35 + 25 * math.sin(self.t * 8))
        else:
            wave_bend = 0.0

        if self.action == "punch":
            punch = (math.sin(self.t * 12.0) + 1) / 2
            arm1 = math.radians(10)
            arm2 = math.radians(10 - 75 * punch)
        if self.action == "sit":
            torso_len = 70
            leg1 = math.radians(85)
            leg2 = math.radians(85)
        if self.action == "crawl":
            torso_len = 45

        hip = (cx, cy - 120)
        shoulder = (cx, hip[1] - torso_len)
        head_center = (cx, shoulder[1] - 35)

        pygame.draw.circle(surface, STICK_COLOR, head_center, self.base_head_radius, width=3)
        pygame.draw.line(surface, STICK_COLOR, shoulder, hip, width=4)

        left_shoulder = (shoulder[0] - 3, shoulder[1] + 4)
        right_shoulder = (shoulder[0] + 3, shoulder[1] + 4)
        left_hip = (hip[0] - 2, hip[1] + 2)
        right_hip = (hip[0] + 2, hip[1] + 2)

        self._draw_limb(surface, left_shoulder, upper_arm_len, forearm_len, arm1, bend=wave_bend)
        self._draw_limb(surface, right_shoulder, upper_arm_len, forearm_len, arm2)
        self._draw_limb(surface, left_hip, thigh_len, shin_len, leg1)
        self._draw_limb(surface, right_hip, thigh_len, shin_len, leg2)

    @staticmethod
    def _draw_limb(
        surface: pygame.Surface,
        start: tuple[int, int],
        upper_len: float,
        lower_len: float,
        theta: float,
        bend: float = 0.0,
    ):
        # theta=0 points down. Positive rotates right.
        upper_end = (
            int(start[0] + math.sin(theta) * upper_len),
            int(start[1] + math.cos(theta) * upper_len),
        )
        lower_theta = theta + bend
        lower_end = (
            int(upper_end[0] + math.sin(lower_theta) * lower_len),
            int(upper_end[1] + math.cos(lower_theta) * lower_len),
        )
        pygame.draw.line(surface, STICK_COLOR, start, upper_end, width=4)
        pygame.draw.line(surface, STICK_COLOR, upper_end, lower_end, width=4)


def normalize_command(text: str) -> str:
    return text.strip().lower()


def parse_voice_command(text: str) -> str:
    cmd = normalize_command(text)
    aliases = {
        "walking": "walk",
        "running": "run",
        "jumping": "jump",
        "hopping": "hop",
        "waving": "wave",
        "dancing": "dance",
        "sitting": "sit",
        "punching": "punch",
        "crawling": "crawl",
    }
    return aliases.get(cmd, cmd)


def listen_for_action() -> str:
    if sr is None:
        raise RuntimeError("SpeechRecognition package not installed.")

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = recognizer.listen(source, timeout=3, phrase_time_limit=3)
    except Exception:
        if np is None or sd is None:
            raise RuntimeError(
                "Microphone backend missing. Install: pip install sounddevice numpy"
            )

        sample_rate = 16000
        duration = 3
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        raw_pcm = np.asarray(recording).tobytes()
        audio = sr.AudioData(raw_pcm, sample_rate, 2)

    text = recognizer.recognize_google(audio)
    return parse_voice_command(text)


def main():
    pygame.init()
    pygame.display.set_caption("Animated Stickman Actions")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 24)
    small = pygame.font.SysFont("consolas", 18)

    stickman = Stickman()
    user_input = ""
    message = "Type action and press ENTER"
    listening = False
    voice_result = {"command": None, "error": None}
    valid_actions = {
        "idle",
        "walk",
        "run",
        "jump",
        "hop",
        "wave",
        "dance",
        "sit",
        "punch",
        "crawl",
        "moonwalk",
        "march",
    }

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        if voice_result["command"] is not None:
            cmd = voice_result["command"]
            voice_result["command"] = None
            if cmd in valid_actions:
                stickman.set_action(cmd)
                message = f"Voice action: {cmd}"
            else:
                message = f"Voice unknown: {cmd}"
            listening = False
        elif voice_result["error"] is not None:
            message = f"Voice error: {voice_result['error']}"
            voice_result["error"] = None
            listening = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_v:
                    if listening:
                        message = "Already listening..."
                    elif sr is None:
                        message = "Install voice package: pip install SpeechRecognition"
                    else:
                        listening = True
                        message = "Listening... say one action"

                        def worker():
                            try:
                                command = listen_for_action()
                                voice_result["command"] = command
                            except Exception as exc:
                                voice_result["error"] = str(exc)

                        threading.Thread(target=worker, daemon=True).start()
                elif event.key == pygame.K_BACKSPACE:
                    user_input = user_input[:-1]
                elif event.key == pygame.K_RETURN:
                    cmd = normalize_command(user_input)
                    if cmd in valid_actions:
                        stickman.set_action(cmd)
                        message = f"Action: {cmd}"
                    elif cmd == "":
                        message = "Please type an action."
                    else:
                        message = f"Unknown action: {cmd}"
                    user_input = ""
                else:
                    if event.unicode and event.unicode.isprintable():
                        user_input += event.unicode

        stickman.update(dt)

        screen.fill(BG_COLOR)
        pygame.draw.line(screen, (150, 160, 180), (0, GROUND_Y), (WIDTH, GROUND_Y), 2)
        stickman.draw(screen)

        help_text = "Actions: idle, walk, run, jump, hop, wave, dance, sit, punch, crawl, moonwalk, march"
        voice_help = "Press V for voice command"
        input_box = pygame.Rect(30, 520, WIDTH - 60, 50)
        pygame.draw.rect(screen, (220, 227, 245), input_box, border_radius=8)
        pygame.draw.rect(screen, ACCENT, input_box, width=2, border_radius=8)

        text_surface = font.render("> " + user_input, True, TEXT_COLOR)
        msg_surface = small.render(message, True, TEXT_COLOR)
        help_surface = small.render(help_text, True, (70, 80, 100))
        voice_surface = small.render(voice_help, True, (70, 80, 100))
        screen.blit(help_surface, (30, 20))
        screen.blit(voice_surface, (30, 45))
        screen.blit(msg_surface, (30, 70))
        screen.blit(text_surface, (42, 533))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
