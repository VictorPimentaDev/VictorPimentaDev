#!/usr/bin/env python3
"""Snake-game contribution animation.

The snake chases the nearest contribution (BFS, random tie-break and
neighbour order) and grows per meal up to a small cap. After the last
meal it follows the border back to the starting pose. Dark theme, stdlib
only. The daily seed (UTC date + GITHUB_RUN_ID) changes the route.

Usage: GITHUB_TOKEN=... python3 generate_snake.py <github_user> <output.svg>
"""
import json
import os
import heapq
import random
import sys
import urllib.request
from collections import deque
from itertools import count
from datetime import datetime, timezone

# --- layout ---
CELL = 12          # cell size
GAP = 3            # gap between cells
PITCH = CELL + GAP
PAD = 10           # canvas padding
TARGET_LOOP_S = 26.0  # whole loop length we aim for
MIN_STEP_S = 0.06    # fastest a cell may take (keeps motion readable)
MAX_STEP_S = 0.11    # slowest a cell may take (short routes stay lively)
MIN_LEN = 3        # starting snake length (head included)
MAX_LEN = 12       # grows while eating, never past this
GROW_SPAN = 0.7    # reach MAX_LEN after ~70% of the meals
START = ((-1, 0), (-1, -1), (0, -1))

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


def daily_seed():
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{day}:{run_id}" if run_id else day


def in_area(cell, ncols):
    col, row = cell
    return -1 <= col <= ncols and -1 <= row <= 7


def neighbors(cell, ncols, rng):
    col, row = cell
    options = [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
    rng.shuffle(options)
    return [option for option in options if in_area(option, ncols)]


def bfs_path(start, goals, blocked, ncols, rng, heading=None):
    """Shortest path from start to a goal, with as few turns as possible.

    Ties between equally short and equally straight routes, and between
    equally near goals, are broken at random so every run looks different.
    Staying straight matters: a staircase that turns every cell reads as
    jitter once the motion is interpolated.
    """
    goals = set(goals) - {start}
    if not goals:
        return []
    order = count()
    best = {}
    prev = {}
    heap = [(0, 0, rng.random(), next(order), start, heading)]
    best[(start, heading)] = (0, 0)
    prev[(start, heading)] = None
    found = None
    found_cost = None
    while heap:
        steps, turns, _, _, cur, direction = heapq.heappop(heap)
        if best.get((cur, direction)) != (steps, turns):
            continue
        if found_cost is not None and (steps, turns) > found_cost:
            break
        if cur in goals and cur != start:
            found, found_cost = (cur, direction), (steps, turns)
            break
        for nxt in neighbors(cur, ncols, rng):
            if nxt in blocked:
                # A dict maps body cells to the step they are vacated at.
                free_at = blocked[nxt] if isinstance(blocked, dict) else None
                if free_at is None or steps + 1 < free_at:
                    continue
            new_dir = (nxt[0] - cur[0], nxt[1] - cur[1])
            cost = (steps + 1, turns + (direction is not None and new_dir != direction))
            key = (nxt, new_dir)
            if key in best and best[key] <= cost:
                continue
            best[key] = cost
            prev[key] = (cur, direction)
            heapq.heappush(heap, (cost[0], cost[1], rng.random(), next(order), nxt, new_dir))
    if found is None:
        return []
    path = []
    state = found
    while prev[state] is not None:
        path.append(state[0])
        state = prev[state]
    path.reverse()
    return path


def border_loop(ncols):
    """Clockwise border from START[0], ending just before it (at START[1])."""
    cells = [(-1, row) for row in range(0, 8)]
    cells.extend((col, 7) for col in range(0, ncols + 1))
    cells.extend((ncols, row) for row in range(6, -2, -1))
    cells.extend((col, -1) for col in range(ncols - 1, -2, -1))
    return cells


def move(body, head, length):
    return (head,) + body[:length - 1]


def pose_path(start_body, goal, ncols, rng, shrink=True):
    """Shortest sequence of heads that takes the snake from start_body to goal."""
    start_body = tuple(start_body)
    goal = tuple(goal)
    if start_body == goal:
        return []
    prev = {start_body: None}
    queue = deque([start_body])
    found = None
    while queue:
        cur = queue.popleft()
        length = max(len(cur) - 1, MIN_LEN) if shrink else len(cur)
        for head in neighbors(cur[0], ncols, rng):
            if head in cur:
                continue
            nxt = move(cur, head, length)
            if nxt in prev:
                continue
            prev[nxt] = (cur, head)
            if nxt == goal:
                found = nxt
                queue.clear()
                break
            queue.append(nxt)
    if found is None:
        return []
    heads = []
    pose = found
    while prev[pose] is not None:
        pose, head = prev[pose]
        heads.append(head)
    heads.reverse()
    return heads


def grow_every(meals):
    """Meals per extra segment, so growth is spread across the whole hunt."""
    if meals <= 0:
        return 1
    return max(1, -(-int(meals * GROW_SPAN) // (MAX_LEN - MIN_LEN)))


# Final approach: along the top lane, then down into the starting pose.
HOME_LANE = [(1, -1), (0, -1), (-1, -1), (-1, 0)]


def shrink_schedule(length, steps):
    """Lengths for each return step: tail retracts evenly down to MIN_LEN."""
    extra = length - MIN_LEN
    return [length - round(extra * (i + 1) / steps) for i in range(steps)]


def build_frames(grid, seed=None, rng=None):
    """Chase every meal, then return outside the grid to the same pose.

    A long snake can, rarely, corner itself; then the route is re-rolled
    (still deterministic per seed) and, as a last resort, the cap lowered.
    """
    global MAX_LEN
    base = daily_seed() if seed is None else seed
    cap = MAX_LEN
    attempts = [(rng, cap)] + [(random.Random(f"{base}:retry{n}"), cap) for n in range(6)]
    attempts += [(random.Random(f"{base}:small{n}"), small)
                 for n, small in enumerate((9, 7, 5))]
    error = None
    try:
        for attempt_rng, attempt_cap in attempts:
            MAX_LEN = attempt_cap
            try:
                return _build_frames(grid, seed=base, rng=attempt_rng)
            except RuntimeError as exc:
                error = exc
    finally:
        MAX_LEN = cap
    raise error


def _build_frames(grid, seed=None, rng=None):
    ncols = len(grid)
    if not ncols or any(len(column) != 7 for column in grid):
        raise ValueError("Expected a nonempty contribution grid with seven rows")
    if rng is None:
        rng = random.Random(daily_seed() if seed is None else seed)

    foods = {(col, row) for col, column in enumerate(grid)
             for row, count in enumerate(column) if count > 0}
    body = START
    frames = [body]
    eats = {}
    loop = border_loop(ncols)
    cycle = loop + [START[0]]
    budget = 80 * (ncols + 8)

    def step_to(head, length):
        nonlocal body
        if head in body or not in_area(head, ncols):
            return False
        body = move(body, head, length)
        frames.append(body)
        return True

    plan = []

    def body_timeline(margin=1):
        # Segment i leaves its cell after len(body) - i moves; +1 in case
        # the snake grows on the way.
        return {cell: len(body) - i + margin for i, cell in enumerate(body)}

    def heading():
        return (body[0][0] - body[1][0], body[0][1] - body[1][1])

    def next_towards(goals):
        # Follow the committed route; re-planning every cell with a fresh
        # random tie-break is what made the snake zigzag.
        nonlocal plan
        if (not plan or plan[0] in body or plan[-1] not in goals
                or abs(plan[0][0] - body[0][0]) + abs(plan[0][1] - body[0][1]) != 1):
            plan = bfs_path(body[0], goals, body_timeline(), ncols, rng, heading())
        if plan and not safe(plan):
            plan = []
            tail_path = bfs_path(body[0], {body[-1]}, body_timeline(0), ncols, rng, heading())
            if tail_path:
                return tail_path[0]
        if not plan:
            return None
        return plan.pop(0)

    def safe(route):
        # After eating, the head must still be able to reach its own tail;
        # otherwise a long snake walls itself into a pocket.
        sim = body
        for head in route:
            grow = head in foods and len(sim) < MAX_LEN
            sim = move(sim, head, len(sim) + (1 if grow else 0))
        timeline = {cell: len(sim) - i for i, cell in enumerate(sim)}
        return bool(bfs_path(sim[0], {sim[-1]}, timeline, ncols, rng))

    def free_neighbor():
        options = [cell for cell in neighbors(body[0], ncols, rng) if cell not in body]
        return options[0] if options else None

    def next_home_step():
        if body[0] in loop:
            candidate = cycle[loop.index(body[0]) + 1]
            if candidate not in body:
                return candidate
        path = bfs_path(body[0], {START[2], START[1], START[0]} | set(loop),
                        set(body), ncols, rng, heading())
        return (path[0] if path else None) or free_neighbor()

    def home_route():
        """Fewest-turns route back, ending on the top lane into START."""
        lane = HOME_LANE
        if body[0] in lane or (2, -1) in body:
            return []
        path = bfs_path(body[0], {(2, -1)}, set(body) | set(lane), ncols, rng, heading())
        if not path:
            return []
        heads = path + lane
        if len(heads) < len(body) - MIN_LEN:
            return []
        sim = body
        for head, length in zip(heads, shrink_schedule(len(body), len(heads))):
            if head in sim or not in_area(head, ncols):
                return []
            sim = move(sim, head, length)
        return heads if sim == START else []

    stall = 0
    meals_eaten = 0
    every = grow_every(len(foods))
    while foods:
        nxt = next_towards(foods)
        if nxt is None:
            nxt = next_home_step()
            stall += 1
            if nxt is None or stall > budget or not step_to(nxt, len(body)):
                raise RuntimeError("Snake could not reach the remaining contributions")
            continue
        stall = 0
        if nxt in foods:
            foods.remove(nxt)
            eats[nxt] = len(frames)
            meals_eaten += 1
            grow = meals_eaten % every == 0 or meals_eaten <= 1
            length = min(len(body) + 1, MAX_LEN) if grow else len(body)
        else:
            length = len(body)
        if not step_to(nxt, length):
            raise RuntimeError("Snake crossed itself")

    if len(frames) == 1:
        for head in loop[1:] + [START[0]]:
            if not step_to(head, MIN_LEN):
                raise RuntimeError("Snake could not loop on an empty grid")
    elif body != START:
        heads = home_route()
        if heads:
            for head, length in zip(heads, shrink_schedule(len(body), len(heads))):
                if not step_to(head, length):
                    raise RuntimeError("Snake could not return to the start")
    if len(frames) > 1 and body != START:
        heads = pose_path(body, START, ncols, rng, shrink=True)
        if not heads:
            raise RuntimeError("Snake could not return to the start")
        for head in heads:
            if not step_to(head, max(len(body) - 1, MIN_LEN)):
                raise RuntimeError("Snake could not return to the start")

    if frames[-1] != frames[0]:
        raise RuntimeError("Snake loop did not close on the starting pose")
    return frames, eats


def cell_center(col, row):
    return (PAD + (col + 1) * PITCH + CELL / 2,
            PAD + (row + 1) * PITCH + CELL / 2)


def step_seconds(steps):
    """One constant speed per loop: no surges or brakes between cells."""
    if steps <= 0:
        return MAX_STEP_S
    return min(MAX_STEP_S, max(MIN_STEP_S, TARGET_LOOP_S / steps))


def step_durations(frames, grid=None):
    steps = len(frames) - 1
    return [step_seconds(steps)] * steps


def key_times(durations):
    total = sum(durations)
    acc = 0.0
    times = [0.0]
    for duration in durations:
        acc += duration
        times.append(acc / total)
    times[-1] = 1.0
    return times, total


def format_times(times):
    return ";".join(f"{time:.8f}" for time in times)


def render_svg(grid, seed=None, rng=None):
    frames, eat_steps = build_frames(grid, seed=seed, rng=rng)
    durations = step_durations(frames, grid)
    times, total = key_times(durations)
    keytimes = format_times(times)
    motion_timing = f'dur="{total:.2f}s" repeatCount="indefinite" calcMode="linear"'
    jump_timing = f'dur="{total:.2f}s" repeatCount="indefinite" calcMode="discrete"'
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
                eaten = times[eat_steps[(col, row)]]
                svg.append(f'<animate attributeName="fill" values="{color};{EMPTY};{EMPTY}" '
                           f'keyTimes="0;{eaten:.8f};1" {jump_timing}/>')
            svg.append('</rect>')

    steps = len(frames) - 1
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
                   f'values="{positions}" keyTimes="{keytimes}" {motion_timing}/>')
        svg.append(f'<animate attributeName="opacity" values="{visible}" '
                   f'keyTimes="{keytimes}" {jump_timing}/>')
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
    seed = daily_seed()

    grid = fetch_grid(login, token)
    frames, eats = build_frames(grid, seed=seed)
    with open(out, "w") as f:
        f.write(render_svg(grid, seed=seed))
    durations = step_durations(frames, grid)
    _, total = key_times(durations)
    print(f"{out}: seed={seed} loop={total:.2f}s steps={len(frames) - 1} meals={len(eats)}")


if __name__ == "__main__":
    main()
