#!/usr/bin/env python3
"""Growing-snake contribution animation.

Generates an animated SVG where the snake sweeps the contribution grid
and GROWS one segment each time it eats a contribution (like the real
snake game). Dark theme (GitHub dark palette). Stdlib only.

Usage: GITHUB_TOKEN=... python3 generate_snake.py <github_user> <output.svg>
"""
import json
import os
import sys
import urllib.request

# --- layout ---
CELL = 12          # cell size
GAP = 3            # gap between cells
PITCH = CELL + GAP
PAD = 10           # canvas padding
STEP_S = 0.09      # seconds per cell
END_PAUSE_S = 1.5  # pause before the loop restarts
MIN_LEN = 4        # starting snake length (head included)
MAX_LEN = 36       # cap so a heavy year doesn't fill the whole grid

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
    # grid[col][row] = contribution count
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


def cell_center(col, row):
    return (PAD + col * PITCH + CELL / 2, PAD + row * PITCH + CELL / 2)


def main():
    login = sys.argv[1] if len(sys.argv) > 1 else "VictorPimentaDev"
    out = sys.argv[2] if len(sys.argv) > 2 else "snake-growing-dark.svg"
    token = os.environ["GITHUB_TOKEN"]

    grid = fetch_grid(login, token)
    ncols = len(grid)

    # boustrophedon path: sweep each row, alternating direction
    path_cells = []
    for row in range(7):
        cols = range(ncols) if row % 2 == 0 else range(ncols - 1, -1, -1)
        path_cells.extend((c, row) for c in cols)

    n = len(path_cells)
    move_dur = n * STEP_S
    total = move_dur + END_PAUSE_S
    move_frac = move_dur / total

    # eat events: path index of every non-empty cell, in visit order
    eats = [i for i, (c, r) in enumerate(path_cells) if grid[c][r] > 0]
    growth = max(0, min(MAX_LEN, MIN_LEN + len(eats)) - MIN_LEN)
    eats_per_growth = max(1, -(-len(eats) // growth)) if growth else 1

    # spawn step for each segment (head=0). Base segments trail in as the
    # snake enters; grown segment k spawns when eat #(k*eats_per_growth) happens.
    length = MIN_LEN + growth
    spawn = {}
    for i in range(length):
        if i < MIN_LEN:
            spawn[i] = i  # visible once the head is i steps in
        else:
            eat_idx = min((i - MIN_LEN + 1) * eats_per_growth, len(eats)) - 1
            spawn[i] = max(eats[eat_idx], i)

    def frac(step):
        return step * STEP_S / total

    cx0, cy0 = cell_center(*path_cells[0])
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
    for i, (c, r) in enumerate(path_cells):
        lv = level(grid[c][r])
        x = PAD + c * PITCH
        y = PAD + r * PITCH
        color = EMPTY if lv == 0 else LEVELS[lv - 1]
        if lv == 0:
            svg.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}"/>')
        else:
            # pop when eaten: flash bright, burst outward and fade
            te = frac(i)
            t1 = min(te + 0.006, move_frac)   # burst peak
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

    # snake: head + body segments following the same path with a step delay
    def visibility(ts):
        return (
            f'<animate attributeName="opacity" values="0;0;1;1;0;0" '
            f'keyTimes="0;{ts:.4f};{min(ts + 0.002, 1):.4f};{move_frac:.4f};{min(move_frac + 0.01, 1):.4f};1" '
            f'dur="{total:.2f}s" repeatCount="indefinite"/>'
        )

    def motion(i):
        return (
            f'<animateMotion dur="{total:.2f}s" repeatCount="indefinite" '
            f'calcMode="linear" keyPoints="0;1;1" keyTimes="0;{move_frac:.4f};1" '
            f'begin="{-i * STEP_S:.2f}s"><mpath xlink:href="#p" href="#p"/></animateMotion>'
        )

    for i in range(length - 1, 0, -1):
        # body tapers towards the tail
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
    print(f"{out}: {n} cells, {len(eats)} contributions eaten, snake {MIN_LEN}->{length}")


if __name__ == "__main__":
    main()
