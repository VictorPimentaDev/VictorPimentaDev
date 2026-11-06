#!/usr/bin/env python3
"""Snake-game contribution animation.

The snake follows a closed, non-intersecting route and grows per meal up
to a small cap. The empty return lane resets its length before the next
loop. Dark theme, stdlib only.

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
STEP_S = 0.16      # seconds per cell, unhurried on purpose
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


def build_frames(grid):
    """Sweep every cell once, then return outside the grid to the same pose."""
    ncols = len(grid)
    if not ncols or any(len(column) != 7 for column in grid):
        raise ValueError("Expected a nonempty contribution grid with seven rows")
    cycle = [(-1, 0)]
    for row in range(7):
        columns = range(ncols) if row % 2 == 0 else reversed(range(ncols))
        cycle.extend((col, row) for col in columns)
    cycle.extend((ncols, row) for row in range(6, -2, -1))
    cycle.extend((col, -1) for col in range(ncols - 1, -2, -1))

    length = MIN_LEN
    frames = [tuple(cycle[-i] for i in range(length))]
    eats = {}
    for step in range(1, len(cycle) + 1):
        col, row = cycle[step % len(cycle)]
        if 0 <= col < ncols and 0 <= row < 7 and grid[col][row] > 0:
            eats[(col, row)] = step
            length = min(length + 1, MAX_LEN)
        elif step > 7 * ncols:
            # Retract only on the empty return lane so the loop starts at MIN_LEN.
            length = max(length - 1, MIN_LEN)
        frames.append(tuple(cycle[(step - i) % len(cycle)] for i in range(length)))
    return frames, eats


def cell_center(col, row):
    return (PAD + (col + 1) * PITCH + CELL / 2,
            PAD + (row + 1) * PITCH + CELL / 2)


def render_svg(grid):
    frames, eat_steps = build_frames(grid)
    steps = len(frames) - 1
    total = steps * STEP_S
    timing = f'dur="{total:.2f}s" repeatCount="indefinite" calcMode="discrete"'
    key_times = ";".join(f"{step / steps:.8f}" for step in range(steps + 1))
    width = PAD * 2 + (len(grid) + 2) * PITCH - GAP
    height = PAD * 2 + 9 * PITCH - GAP
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">',
        '<title id="title">Snake growing as it eats GitHub contributions</title>',
        f'<rect width="{width}" height="{height}" rx="6" fill="{BG}"/>',
    ]
    for col, column in enumerate(grid):
        for row, count in enumerate(column):
            lv = level(count)
            x, y = cell_center(col, row)
            color = EMPTY if lv == 0 else LEVELS[lv - 1]
            svg.append(f'<rect x="{x - CELL / 2}" y="{y - CELL / 2}" '
                       f'width="{CELL}" height="{CELL}" rx="2.5" fill="{color}">')
            if lv:
                eaten = eat_steps[(col, row)] / steps
                svg.append(f'<animate attributeName="fill" values="{color};{EMPTY};{EMPTY}" '
                           f'keyTimes="0;{eaten:.8f};1" {timing}/>')
            svg.append('</rect>')

    for segment in reversed(range(max(map(len, frames)))):
        # Hidden segments keep their own cell position on the same closed route.
        positions = ";".join(
            f"{x},{y}" for x, y in (
                cell_center(*frames[(step - segment) % steps][0])
                for step in range(steps + 1)
            )
        )
        visible = ";".join("1" if segment < len(frame) else "0" for frame in frames)
        size = CELL if segment == 0 else CELL - 2
        color = SNAKE_HEAD if segment == 0 else SNAKE_BODY
        x, y = positions.split(";")[0].split(",")
        svg.append(f'<g id="segment-{segment}" transform="translate({x},{y})" '
                   f'opacity="{visible[0]}">')
        svg.append(f'<animateTransform attributeName="transform" type="translate" '
                   f'values="{positions}" keyTimes="{key_times}" {timing}/>')
        svg.append(f'<animate attributeName="opacity" values="{visible}" '
                   f'keyTimes="{key_times}" {timing}/>')
        svg.append(f'<rect x="{-size / 2}" y="{-size / 2}" width="{size}" '
                   f'height="{size}" rx="3" fill="{color}"/>')
        if segment == 0:
            svg.append(f'<circle cx="-2.5" cy="-2" r="1.5" fill="{BG}"/>')
            svg.append(f'<circle cx="2.5" cy="-2" r="1.5" fill="{BG}"/>')
        svg.append('</g>')
    svg.append('</svg>')
    return "\n".join(svg)


def main():
    login = sys.argv[1] if len(sys.argv) > 1 else "VictorPimentaDev"
    out = sys.argv[2] if len(sys.argv) > 2 else "snake-growing-dark.svg"
    token = os.environ["GITHUB_TOKEN"]

    grid = fetch_grid(login, token)
    with open(out, "w") as f:
        f.write(render_svg(grid))
    print(f"{out}: generated a closed snake loop")


if __name__ == "__main__":
    main()
