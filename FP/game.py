#!/usr/bin/env python3
# Camcookie - DIRTBIKES
# Neon ASCII terminal racer with physics, bots, particles, overlays, and stats.
# Runs in any terminal; Windows users should install colorama for ANSI support.

import curses
import time
import random
import json
import os
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# Optional Windows ANSI support
try:
    from colorama import just_fix_windows_console  # type: ignore
    just_fix_windows_console()
except Exception:
    pass

STATS_FILE = "stats.json"

# Game constants
TRACK_LENGTH = 1200         # world units (columns in world space)
VIEW_WIDTH_MIN = 60         # min viewport columns
LANES = 5                   # number of lanes
GROUND_Y = 0                # ground baseline per lane, vertically stacked
TICK = 1.0 / 30.0           # seconds per tick (30 FPS)
GRAVITY = 36.0              # downward accel
JUMP_VEL = 16.0             # jump impulse
ACCEL = 28.0                # throttle accel
BRAKE = 36.0                # brake decel
FRICTION = 10.0             # passive decel
MAX_SPEED = 60.0            # cap speed
ENGINE_ON_ACCEL_FACTOR = 1.0
ENGINE_OFF_ACCEL_FACTOR = 0.25

# Obstacles
OBSTACLE_DENSITY = 0.008    # spawn per unit per lane
ROCK = "rock"
LOG = "log"
RAMP = "ramp"

# Colors (ANSI in curses via color pairs)
# We'll map logical colors to curses pairs once we know terminal capabilities.
COLOR_MAP = {
    "bg": (curses.COLOR_BLACK, curses.COLOR_BLACK),
    "track": (curses.COLOR_BLACK, curses.COLOR_BLACK),
    "neon1": (curses.COLOR_BLACK, curses.COLOR_MAGENTA),
    "neon2": (curses.COLOR_BLACK, curses.COLOR_CYAN),
    "neon3": (curses.COLOR_BLACK, curses.COLOR_GREEN),
    "hud": (curses.COLOR_BLACK, curses.COLOR_YELLOW),
    "danger": (curses.COLOR_BLACK, curses.COLOR_RED),
    "ghost": (curses.COLOR_BLACK, curses.COLOR_BLUE),
    "dust": (curses.COLOR_BLACK, curses.COLOR_WHITE),
    "confetti": (curses.COLOR_BLACK, curses.COLOR_GREEN),
}

# Visual characters
BIKE_PLAYER = "⟲"  # you can swap with 'A' if your font doesn't show this
BIKE_BOT = "∎"
GROUND_CHAR = "_"
ROCK_CHAR = "◼"
LOG_CHAR = "▭"
RAMP_CHAR = "⫸"
SPARK_CHAR = "*"
DUST_CHAR = "."
CONFETTI_CHAR = "✺"

# States
STATE_HOME = "home"
STATE_COUNTDOWN = "countdown"
STATE_RACE = "race"
STATE_PAUSE = "pause"
STATE_END = "end"

@dataclass
class Stats:
    total_races: int = 0
    wins: int = 0
    best_time: Optional[float] = None

    def load(self, path: str = STATS_FILE):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    self.total_races = int(data.get("total_races", 0))
                    self.wins = int(data.get("wins", 0))
                    bt = data.get("best_time", None)
                    self.best_time = float(bt) if bt is not None else None
            except Exception:
                pass

    def save(self, path: str = STATS_FILE):
        try:
            with open(path, "w") as f:
                json.dump({
                    "total_races": self.total_races,
                    "wins": self.wins,
                    "best_time": self.best_time
                }, f)
        except Exception:
            pass

@dataclass
class Obstacle:
    x: float     # world x
    lane: int
    kind: str

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    char: str
    color_key: str

@dataclass
class Racer:
    name: str
    is_player: bool
    lane: int
    x: float = 0.0
    y: float = 0.0            # vertical offset above ground
    vx: float = 0.0
    vy: float = 0.0
    finished: bool = False
    finish_time: Optional[float] = None
    engine_on: bool = True
    sparks_cooldown: float = 0.0

    # Bot AI params
    target_speed: float = field(default_factory=lambda: random.uniform(32.0, 52.0))
    lookahead: float = field(default_factory=lambda: random.uniform(10.0, 24.0))
    jump_bias: float = field(default_factory=lambda: random.uniform(0.35, 0.75))

class Track:
    def __init__(self, length: int, lanes: int):
        self.length = length
        self.lanes = lanes
        self.obstacles: List[Obstacle] = []
        self.generate()

    def generate(self):
        self.obstacles.clear()
        for lane in range(self.lanes):
            x = 20
            while x < self.length - 60:
                if random.random() < OBSTACLE_DENSITY:
                    kind = random.choice([ROCK, LOG, RAMP, ROCK, LOG])
                    self.obstacles.append(Obstacle(x=x, lane=lane, kind=kind))
                    x += random.randint(12, 28)
                else:
                    x += random.randint(4, 12)

    def obstacles_in_lane(self, lane: int) -> List[Obstacle]:
        return [o for o in self.obstacles if o.lane == lane]

class Game:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        self.h, self.w = stdscr.getmaxyx()
        self.w = max(self.w, VIEW_WIDTH_MIN)
        curses.start_color()
        curses.use_default_colors()
        self._init_color_pairs()

        self.state = STATE_HOME
        self.stats = Stats()
        self.stats.load()

        self.bot_count = 4
        self.reduced_motion = False

        self.track = Track(TRACK_LENGTH, LANES)
        self.racers: List[Racer] = []
        self.particles: List[Particle] = []
        self.camera_x = 0.0
        self.time_race = 0.0
        self.time_start_countdown = 0.0
        self.countdown_phase = 0  # 3,2,1,GO

    def _init_color_pairs(self):
        self.color_pairs = {}
        pair_id = 1
        for key, (fg, bg) in COLOR_MAP.items():
            curses.init_pair(pair_id, bg, fg)  # reverse to make neon foreground bright bg effect
            self.color_pairs[key] = pair_id
            pair_id += 1

    def run(self):
        last = time.time()
        while True:
            now = time.time()
            dt = max(0.001, min(0.06, now - last))
            last = now

            self._handle_input()

            if self.state == STATE_HOME:
                self._render_home()
            elif self.state == STATE_COUNTDOWN:
                self._update_countdown(dt)
                self._render_countdown()
            elif self.state == STATE_RACE:
                self._update_race(dt)
                self._render_race()
            elif self.state == STATE_PAUSE:
                self._render_pause()
            elif self.state == STATE_END:
                self._render_end()

            time.sleep(max(0.0, TICK - (time.time() - now)))

    # Input handling
    def _handle_input(self):
        self.stdscr.nodelay(True)
        try:
            ch = self.stdscr.getch()
        except Exception:
            ch = -1

        if ch == -1:
            return

        if self.state == STATE_HOME:
            if ch in (ord('\n'), curses.KEY_ENTER):
                self._start_countdown()
            elif ch in (ord('+'),):
                self.bot_count = min(12, self.bot_count + 1)
            elif ch in (ord('-'),):
                self.bot_count = max(0, self.bot_count - 1)
            elif ch in (ord('m'), ord('M')):
                self.reduced_motion = not self.reduced_motion
            elif ch in (ord('q'), ord('Q')):
                raise SystemExit

        elif self.state == STATE_COUNTDOWN:
            if ch in (ord('q'), ord('Q')):
                raise SystemExit
            # allow early pause
            if ch in (ord('p'), ord('P')):
                self.state = STATE_PAUSE

        elif self.state == STATE_RACE:
            player = self._player()
            if ch in (ord('q'), ord('Q')):
                raise SystemExit
            elif ch in (ord('p'), ord('P')):
                self.state = STATE_PAUSE
            elif ch in (ord('r'), ord('R')):
                self._rematch()
            elif ch in (ord('h'), ord('H')):
                self._to_home()
            elif ch in (ord('m'), ord('M')):
                self.reduced_motion = not self.reduced_motion
            elif ch in (ord('s'), ord('S')):
                player.engine_on = not player.engine_on
            elif ch in (ord('d'), ord('D')):
                # throttle pressed: handled in update via a flag? We'll nudge vx
                accel = ACCEL * (ENGINE_ON_ACCEL_FACTOR if player.engine_on else ENGINE_OFF_ACCEL_FACTOR)
                player.vx = min(MAX_SPEED, player.vx + accel * 0.06)
                self._dust(player)
            elif ch in (ord('a'), ord('A')):
                player.vx = max(0.0, player.vx - BRAKE * 0.08)
            elif ch == ord(' '):
                if abs(player.y) < 0.001:
                    player.vy = JUMP_VEL
                    self._dust(player, strong=True)

        elif self.state == STATE_PAUSE:
            if ch in (ord('p'), ord('P')):
                self.state = STATE_RACE
            elif ch in (ord('h'), ord('H')):
                self._to_home()
            elif ch in (ord('q'), ord('Q')):
                raise SystemExit
            elif ch in (ord('r'), ord('R')):
                self._rematch()

        elif self.state == STATE_END:
            if ch in (ord('\n'), curses.KEY_ENTER):
                self._rematch()
            elif ch in (ord('h'), ord('H')):
                self._to_home()
            elif ch in (ord('q'), ord('Q')):
                raise SystemExit

    # State transitions
    def _start_countdown(self):
        self.time_start_countdown = time.time()
        self.countdown_phase = 3
        self._spawn_race()
        self.state = STATE_COUNTDOWN

    def _spawn_race(self):
        self.track.generate()
        self.racers = []
        # place player in middle lane
        player_lane = LANES // 2
        self.racers.append(Racer(name="YOU", is_player=True, lane=player_lane))
        # bots
        for i in range(self.bot_count):
            lane = i % LANES
            self.racers.append(Racer(name=f"BOT-{i+1}", is_player=False, lane=lane))
        for r in self.racers:
            r.x = 0.0
            r.y = 0.0
            r.vx = 0.0
            r.vy = 0.0
            r.finished = False
            r.finish_time = None
            r.engine_on = True
        self.particles.clear()
        self.camera_x = 0.0
        self.time_race = 0.0

    def _rematch(self):
        self._start_countdown()

    def _to_home(self):
        self.state = STATE_HOME

    # Updates
    def _update_countdown(self, dt):
        elapsed = time.time() - self.time_start_countdown
        if elapsed < 1.0:
            self.countdown_phase = 3
        elif elapsed < 2.0:
            self.countdown_phase = 2
        elif elapsed < 3.0:
            self.countdown_phase = 1
        elif elapsed < 3.6:
            self.countdown_phase = 0  # GO flash
        else:
            self.state = STATE_RACE

    def _update_race(self, dt):
        self.time_race += dt
        # Physics and AI for each racer
        for r in self.racers:
            if r.finished:
                continue

            if r.is_player:
                # passive friction
                if r.vx > 0:
                    r.vx = max(0.0, r.vx - FRICTION * dt)
            else:
                self._bot_ai(r, dt)

            # gravity
            r.vy -= GRAVITY * dt
            r.y += r.vy * dt
            if r.y <= 0.0:
                r.y = 0.0
                r.vy = 0.0

            # speed clamp
            r.vx = max(0.0, min(MAX_SPEED, r.vx))
            r.x += r.vx * dt

            # collisions
            self._collisions(r, dt)

            # finish check
            if r.x >= TRACK_LENGTH:
                r.finished = True
                r.finish_time = self.time_race
                if r.is_player:
                    self._confetti_burst(r)

        # camera
        px = self._player().x
        target_cam = px - (self.w // 3)
        if self.reduced_motion:
            self.camera_x = max(0.0, min(TRACK_LENGTH, target_cam))
        else:
            self.camera_x = self._lerp(self.camera_x, target_cam, 0.12)

        # particles
        self._update_particles(dt)

        # all finished?
        if all(r.finished for r in self.racers):
            self._race_end()

    def _bot_ai(self, r: Racer, dt: float):
        # maintain target speed; slight variance
        accel = ACCEL if r.engine_on else ACCEL * ENGINE_OFF_ACCEL_FACTOR
        if r.vx < r.target_speed:
            r.vx = min(MAX_SPEED, r.vx + accel * dt)
        else:
            r.vx = max(0.0, r.vx - FRICTION * dt)

        # lookahead for obstacles
        ahead = r.x + r.lookahead
        lane_obs = self.track.obstacles_in_lane(r.lane)
        hazard = None
        for o in lane_obs:
            if r.x < o.x <= ahead:
                hazard = o
                break
        if hazard:
            # prefer jumping ramps; avoid rocks/logs
            jump_chance = r.jump_bias
            if hazard.kind == RAMP:
                jump_chance = max(0.65, jump_chance + 0.2)
            if r.y <= 0.001 and random.random() < jump_chance:
                r.vy = JUMP_VEL * random.uniform(0.9, 1.1)
                self._dust(r)
            # slight braking near hazard
            r.vx = max(0.0, r.vx - BRAKE * 0.2 * dt)

    def _collisions(self, r: Racer, dt: float):
        if r.y > 0.0:
            return
        lane_obs = self.track.obstacles_in_lane(r.lane)
        for o in lane_obs:
            if abs(r.x - o.x) < 0.9:
                if o.kind == ROCK:
                    r.vx = max(0.0, r.vx - 12.0)
                    self._sparks(r, count=random.randint(2, 5))
                elif o.kind == LOG:
                    r.vx = max(0.0, r.vx - 9.0)
                    self._sparks(r, count=random.randint(1, 4))
                elif o.kind == RAMP:
                    if r.y <= 0.001:
                        r.vy = JUMP_VEL * 1.2
                        self._dust(r, strong=True)

    def _race_end(self):
        # update stats, sort results, confetti for player if win
        self.state = STATE_END
        self.stats.total_races += 1
        # best time update if player finished
        player = self._player()
        if player.finish_time is not None:
            if self.stats.best_time is None or player.finish_time < self.stats.best_time:
                self.stats.best_time = player.finish_time
        # win check
        ordered = sorted(self.racers, key=lambda r: r.finish_time if r.finish_time is not None else 9e9)
        if ordered and ordered[0].is_player:
            self.stats.wins += 1
        self.stats.save()

    # Particles
    def _dust(self, r: Racer, strong: bool = False):
        n = random.randint(2, 5) + (4 if strong else 0)
        for _ in range(n):
            self.particles.append(Particle(
                x=r.x - random.uniform(0.5, 2.0),
                y=0.0,
                vx=-random.uniform(8.0, 16.0),
                vy=random.uniform(0.5, 2.0),
                ttl=random.uniform(0.2, 0.6),
                char=DUST_CHAR,
                color_key="dust"
            ))

    def _sparks(self, r: Racer, count: int = 3):
        if r.sparks_cooldown > 0.0:
            return
        r.sparks_cooldown = 0.2
        for _ in range(count):
            self.particles.append(Particle(
                x=r.x + random.uniform(-0.3, 0.3),
                y=0.2,
                vx=random.uniform(-6.0, 6.0),
                vy=random.uniform(2.0, 5.0),
                ttl=random.uniform(0.2, 0.5),
                char=SPARK_CHAR,
                color_key="danger"
            ))

    def _confetti_burst(self, r: Racer):
        for _ in range(25):
            self.particles.append(Particle(
                x=r.x,
                y=1.0,
                vx=random.uniform(-10.0, 10.0),
                vy=random.uniform(2.0, 8.0),
                ttl=random.uniform(0.4, 1.2),
                char=CONFETTI_CHAR,
                color_key=random.choice(["neon1", "neon2", "neon3", "confetti"])
            ))

    def _update_particles(self, dt: float):
        alive = []
        for p in self.particles:
            p.ttl -= dt
            if p.ttl <= 0:
                continue
            p.vy -= GRAVITY * 0.3 * dt
            p.x += p.vx * dt
            p.y = max(0.0, p.y + p.vy * dt)
            alive.append(p)
        self.particles = alive
        # cooldowns
        for r in self.racers:
            if r.sparks_cooldown > 0.0:
                r.sparks_cooldown = max(0.0, r.sparks_cooldown - dt)

    # Rendering helpers
    def _clr(self, key: str):
        return curses.color_pair(self.color_pairs.get(key, 0))

    def _render_home(self):
        self.stdscr.erase()
        midx = self.w // 2

        title = "Camcookie - DIRTBIKES"
        self.stdscr.attron(self._clr("neon2"))
        self._center_text(2, title)
        self.stdscr.attroff(self._clr("neon2"))

        self.stdscr.attron(self._clr("hud"))
        self._center_text(4, "Fast-paced neon ASCII dirt racing in your terminal.")
        self.stdscr.attroff(self._clr("hud"))

        # Stats
        s1 = f"Total races: {self.stats.total_races}"
        s2 = f"Wins: {self.stats.wins}"
        s3 = f"Best time: {self._fmt_time(self.stats.best_time) if self.stats.best_time else '--'}"
        self._center_text(6, s1)
        self._center_text(7, s2)
        self._center_text(8, s3)

        # Config
        self.stdscr.attron(self._clr("neon1"))
        self._center_text(10, f"Bots: {self.bot_count}   (+ / - to adjust)")
        self.stdscr.attroff(self._clr("neon1"))
        self.stdscr.attron(self._clr("neon3"))
        self._center_text(11, f"Reduced motion: {'ON' if self.reduced_motion else 'OFF'}   (M to toggle)")
        self.stdscr.attroff(self._clr("neon3"))

        self.stdscr.attron(self._clr("hud"))
        self._center_text(13, "Enter — Start   Q — Quit")
        self.stdscr.attroff(self._clr("hud"))

        self.stdscr.refresh()

    def _render_countdown(self):
        self.stdscr.erase()
        self._draw_track_base()
        self._draw_racers()
        self._draw_particles()

        msg = "3" if self.countdown_phase == 3 else "2" if self.countdown_phase == 2 else "1" if self.countdown_phase == 1 else "GO!"
        color = "danger" if self.countdown_phase in [3, 2, 1] else "neon3"
        self.stdscr.attron(self._clr(color))
        self._center_text(2, msg)
        self.stdscr.attroff(self._clr(color))

        self._draw_hud()
        self.stdscr.refresh()

    def _render_race(self):
        self.stdscr.erase()
        self._draw_track_base()
        self._draw_obstacles()
        self._draw_racers()
        self._draw_particles()
        self._draw_hud()
        self.stdscr.refresh()

    def _render_pause(self):
        self.stdscr.erase()
        self._draw_track_base()
        self._draw_obstacles()
        self._draw_racers()
        self._draw_particles()
        self._draw_hud()
        # Overlay
        self.stdscr.attron(self._clr("ghost"))
        self._center_text(3, "[PAUSED]")
        self._center_text(5, "P — Resume    R — Restart    H — Home")
        self.stdscr.attroff(self._clr("ghost"))
        self.stdscr.refresh()

    def _render_end(self):
        self.stdscr.erase()
        # Results sorted by time
        ordered = sorted(self.racers, key=lambda r: r.finish_time if r.finish_time is not None else 9e9)
        self.stdscr.attron(self._clr("neon2"))
        self._center_text(2, "Race Results")
        self.stdscr.attroff(self._clr("neon2"))

        y = 4
        for i, r in enumerate(ordered[:self.h - 10]):
            name = r.name if not r.is_player else "YOU"
            t = self._fmt_time(r.finish_time)
            line = f"{i+1:>2}. {name:<8}  time: {t:<10}"
            color = "neon3" if r.is_player else "hud"
            self.stdscr.attron(self._clr(color))
            self._center_text(y, line)
            self.stdscr.attroff(self._clr(color))
            y += 1

        self.stdscr.attron(self._clr("neon1"))
        self._center_text(y + 1, f"Total races: {self.stats.total_races}   Wins: {self.stats.wins}   Best: {self._fmt_time(self.stats.best_time) if self.stats.best_time else '--'}")
        self.stdscr.attroff(self._clr("neon1"))

        self.stdscr.attron(self._clr("hud"))
        self._center_text(y + 3, "Enter — Rematch    H — Home")
        self.stdscr.attroff(self._clr("hud"))

        self.stdscr.refresh()

    # Drawing primitives
    def _draw_track_base(self):
        # Draw lanes as ground lines with subtle neon
        for lane in range(LANES):
            row = min(self.h - 3, 6 + lane * 2)
            self.stdscr.attron(self._clr("track"))
            for col in range(self.w):
                self.stdscr.addstr(row, col, GROUND_CHAR, self._clr("track"))
            self.stdscr.attroff(self._clr("track"))

    def _draw_obstacles(self):
        for o in self.track.obstacles:
            col = int(o.x - self.camera_x)
            if 0 <= col < self.w:
                row = min(self.h - 3, 6 + o.lane * 2) - 1
                if o.kind == ROCK:
                    self.stdscr.addstr(row, col, ROCK_CHAR, self._clr("danger"))
                elif o.kind == LOG:
                    self.stdscr.addstr(row, col, LOG_CHAR, self._clr("hud"))
                elif o.kind == RAMP:
                    self.stdscr.addstr(row, col, RAMP_CHAR, self._clr("neon2"))

    def _draw_racers(self):
        for r in self.racers:
            col = int(r.x - self.camera_x)
            if 0 <= col < self.w:
                base_row = min(self.h - 3, 6 + r.lane * 2)
                row = base_row - (1 if r.y > 0.0 else 0) - int(min(2, r.y))
                ch = BIKE_PLAYER if r.is_player else BIKE_BOT
                color = "neon3" if r.is_player else "neon1"
                self.stdscr.addstr(row, col, ch, self._clr(color))

    def _draw_particles(self):
        for p in self.particles:
            col = int(p.x - self.camera_x)
            if 0 <= col < self.w:
                base_row = min(self.h - 3, 6 + (LANES // 2) * 2)
                row = base_row - int(p.y)
                if 0 <= row < self.h:
                    self.stdscr.addstr(row, col, p.char, self._clr(p.color_key))

    def _draw_hud(self):
        # HUD line
        player = self._player()
        hud = [
            f"Time: {self._fmt_time(self.time_race)}",
            f"Speed: {player.vx:05.1f}",
            f"Pos: {int(player.x):04d}/{TRACK_LENGTH}",
            f"Engine: {'ON' if player.engine_on else 'OFF'}",
            f"Motion: {'SMOOTH' if not self.reduced_motion else 'STEADY'}",
            f"Bots: {self.bot_count}"
        ]
        hud_str = "  ".join(hud)
        self.stdscr.attron(self._clr("hud"))
        self._left_text(self.h - 2, hud_str)
        self.stdscr.attroff(self._clr("hud"))

        # Controls hint (minimal)
        self.stdscr.attron(self._clr("ghost"))
        self._left_text(self.h - 1, "S engine  D throttle  A brake  Space jump  P pause  R restart  H home  Q quit")
        self.stdscr.attroff(self._clr("ghost"))

    # Utility
    def _player(self) -> Racer:
        for r in self.racers:
            if r.is_player:
                return r
        # fallback
        return self.racers[0]

    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def _fmt_time(self, t: Optional[float]) -> str:
        if t is None:
            return "--"
        return f"{t:0.2f}s"

    def _center_text(self, row: int, text: str):
        col = max(0, (self.w - len(text)) // 2)
        if 0 <= row < self.h:
            try:
                self.stdscr.addstr(row, col, text)
            except curses.error:
                pass

    def _left_text(self, row: int, text: str):
        if 0 <= row < self.h:
            try:
                self.stdscr.addstr(row, 1, text)
            except curses.error:
                pass

def main(stdscr):
    game = Game(stdscr)
    game.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass