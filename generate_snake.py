#!/usr/bin/env python3
"""Snake-game contribution animation.

The snake chases the nearest contribution (BFS pathfinding, so the route
looks organic instead of a row sweep), eats it head-first with a burst
effect, and grows a segment per meal up to a small cap. Dark theme,
stdlib only.

Usage: GITHUB_TOKEN=... python3 generate_snake.py <github_user> <output.svg>
"""
import json
import os
import random
import sys
import urllib.request
from collections import deque

# --- layout ---
CELL = 12          # cell size
GAP = 3            # gap between cells
PITCH = CELL + GAP
PAD = 10           # canvas padding
STEP_S = 0.16      # seconds per cell, unhurried on purpose
END_PAUSE_S = 2.0  # pause before the loop restarts
MIN_LEN = 3        # starting snake length (head included)
MAX_LEN = 7        # she stays a comfortable size

# --- GitHub dark palette ---
BG = "#0d1117"
EMPTY = "#161b22"
LEVELS = ["#0e4429", "#006d32", "#26a641", "#39d353"]
SNAKE_BODY = "#8957e5"
SNAKE_HEAD = "#bc8cff"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { contributionCount weekday } }
      }
    }
  }
}
"""


def fetch_grid(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    grid = []
    for w in weeks:
        col = [0] * 7
        for d in w["contributionDays"]:
            col[d["weekday"]] = d["contributionCount"]
        grid.append(col)
    return grid


def level(count):
    if count == 0:
        return 0
    if count < 3:
        return 1
    if count < 6:
        return 2
    if count < 10:
        return 3
    return 4


def bfs_path(ncols, start, goals):
    """Shortest path from start to the nearest goal, with shuffled neighbour
    order so the route bends organically instead of tracing an L."""
    prev = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur in goals:
            path = []
            while cur != start:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]
        c, r = cur
        neigh = [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]
        random.shuffle(neigh)
        for n in neigh:
            if 0 <= n[0] < ncols and 0 <= n[1] < 7 and n not in prev:
                prev[n] = cur
                queue.append(n)
    return []


def build_path(grid, ncols):
    """Greedy chase: keep routing to the nearest uneaten contribution.
    Returns (path_cells, eat_steps) where eat_steps maps cell -> step index."""
    foods = {(c, r) for c in range(ncols) for r in range(7) if grid[c][r] > 0}
    start = (0, 0)
    path = [start]
    eats = {}
    if start in foods:
        foods.discard(start)
        eats[start] = 0
    while foods:
        for cell in bfs_path(ncols, path[-1], foods):
            path.append(cell)
            if cell in foods:
                foods.discard(cell)
                eats[cell] = len(path) - 1
    return path, eats


def cell_center(col, row):
    return (PAD + col * PITCH + CELL / 2, PAD + row * PITCH + CELL / 2)


def main():
    login = sys.argv[1] if len(sys.argv) > 1 else "VictorPimentaDev"
    out = sys.argv[2] if len(sys.argv) > 2 else "snake-growing-dark.svg"
    token = os.environ["GITHUB_TOKEN"]

    grid = fetch_grid(login, token)
    ncols = len(grid)

    path_cells, eat_steps = build_path(grid, ncols)
    n = len(path_cells)
    move_dur = n * STEP_S
    total = move_dur + END_PAUSE_S
    move_frac = move_dur / total

    # growth: one segment per meal, spread across the run, capped at MAX_LEN
    eat_order = sorted(eat_steps.values())
    slots = MAX_LEN - MIN_LEN
    spawn = {i: i for i in range(MIN_LEN)}
    for j in range(slots):
        if not eat_order:
            break
        idx = min(round((j + 1) * len(eat_order) / (slots + 1)), len(eat_order) - 1)
        spawn[MIN_LEN + j] = max(eat_order[idx], MIN_LEN + j)
    length = len(spawn)

    def frac(step):
        return step * STEP_S / total

    points = " ".join(
        f"{x},{y}" for x, y in (cell_center(c, r) for c, r in path_cells)
    )

    width = PAD * 2 + ncols * PITCH - GAP
    height = PAD * 2 + 7 * PITCH - GAP

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    )
    svg.append(f'<rect width="{width}" height="{height}" rx="6" fill="{BG}"/>')
    svg.append(f'<path id="p" d="M {points.replace(" ", " L ")}" fill="none"/>')

    # dots
    dur = f'dur="{total:.2f}s" repeatCount="indefinite"'
    for c in range(ncols):
        for r in range(7):
            lv = level(grid[c][r])
            x = PAD + c * PITCH
            y = PAD + r * PITCH
            color = EMPTY if lv == 0 else LEVELS[lv - 1]
            if lv == 0:
                svg.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}"/>')
            else:
                # pop when the head arrives: flash bright, burst outward, fade
                te = frac(eat_steps[(c, r)])
                t1 = min(te + 0.006, move_frac)
                kt = f"0;{te:.4f};{t1:.4f};1"
                grow = 6
                svg.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}">')
                svg.append(f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="{kt}" {dur}/>')
                svg.append(f'<animate attributeName="fill" values="{color};{color};#fff8c5;#fff8c5" keyTimes="{kt}" {dur}/>')
                svg.append(f'<animate attributeName="x" values="{x};{x};{x - grow / 2};{x - grow / 2}" keyTimes="{kt}" {dur}/>')
                svg.append(f'<animate attributeName="y" values="{y};{y};{y - grow / 2};{y - grow / 2}" keyTimes="{kt}" {dur}/>')
                svg.append(f'<animate attributeName="width" values="{CELL};{CELL};{CELL + grow};{CELL + grow}" keyTimes="{kt}" {dur}/>')
                svg.append(f'<animate attributeName="height" values="{CELL};{CELL};{CELL + grow};{CELL + grow}" keyTimes="{kt}" {dur}/>')
                svg.append('</rect>')

    # snake: positive begin so each segment TRAILS the head (head eats first)
    def visibility(ts):
        return (
            f'<animate attributeName="opacity" values="0;0;1;1;0;0" '
            f'keyTimes="0;{ts:.4f};{min(ts + 0.002, 1):.4f};0.985;0.995;1" '
            f'{dur}/>'
        )

    def motion(i):
        return (
            f'<animateMotion dur="{total:.2f}s" repeatCount="indefinite" '
            f'calcMode="linear" keyPoints="0;1;1" keyTimes="0;{move_frac:.4f};1" '
            f'begin="{i * STEP_S:.2f}s"><mpath xlink:href="#p" href="#p"/></animateMotion>'
        )

    for i in range(length - 1, 0, -1):
        size = CELL - 1 - round(3 * i / length)
        ts = min(frac(spawn[i]), move_frac - 0.004)
        svg.append(f'<rect x="{-size / 2}" y="{-size / 2}" width="{size}" height="{size}" rx="3.5" fill="{SNAKE_BODY}" opacity="0">')
        svg.append(visibility(ts))
        svg.append(motion(i))
        svg.append("</rect>")

    # head: eyes + constant chomping pulse (scale on an inner group so it
    # pulses around the head centre, not the canvas origin)
    hs = CELL + 3
    svg.append('<g opacity="0">')
    svg.append(visibility(0.0))
    svg.append(motion(0))
    svg.append("<g>")
    svg.append(
        f'<animateTransform attributeName="transform" type="scale" '
        f'values="1;1.2;1" dur="{STEP_S * 2:.2f}s" repeatCount="indefinite"/>'
    )
    svg.append(f'<rect x="{-hs / 2}" y="{-hs / 2}" width="{hs}" height="{hs}" rx="4.5" fill="{SNAKE_HEAD}"/>')
    svg.append(f'<circle cx="-3" cy="-2.5" r="1.8" fill="{BG}"/>')
    svg.append(f'<circle cx="3" cy="-2.5" r="1.8" fill="{BG}"/>')
    svg.append("</g>")
    svg.append("</g>")

    svg.append("</svg>")
    with open(out, "w") as f:
        f.write("\n".join(svg))
    print(f"{out}: {n} steps, {len(eat_steps)} meals, snake {MIN_LEN}->{length}, loop {total:.0f}s")


if __name__ == "__main__":
    main()
