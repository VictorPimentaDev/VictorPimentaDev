import random
import unittest
import xml.etree.ElementTree as ET

from generate_snake import (
    MAX_LEN,
    MAX_STEP_S,
    MIN_LEN,
    PITCH,
    START,
    MIN_STEP_S,
    build_frames,
    cell_center,
    key_times,
    loop_times,
    route_geometry,
    render_svg,
    step_durations,
)


class SnakeTest(unittest.TestCase):
    def check_grid(self, grid, seed=0, svg=None):
        frames, eats = build_frames(grid, seed=seed)
        self.assertEqual(frames[0], frames[-1])
        self.assertEqual(frames[0], START)
        self.assertEqual(len(frames[0]), MIN_LEN)
        self.assertGreater(len(frames), 1)
        foods = {(c, r) for c, column in enumerate(grid)
                 for r, count in enumerate(column) if count > 0}
        self.assertEqual(set(eats), foods)
        pending = set(foods)
        hunting = True
        for previous, frame in zip(frames, frames[1:]):
            self.assertEqual(len(set(frame)), len(frame))
            self.assertLessEqual(len(frame), MAX_LEN)
            self.assertGreaterEqual(len(frame), MIN_LEN)
            for a, b in [(previous[0], frame[0]), *zip(frame, frame[1:])]:
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
            self.assertEqual(frame[1:], previous[:len(frame) - 1])
            self.assertNotIn(frame[0], previous)
            if frame[0] in pending:
                self.assertIn(len(frame), {len(previous), min(len(previous) + 1, MAX_LEN)})
                pending.remove(frame[0])
                if not pending:
                    hunting = False
            elif hunting:
                self.assertEqual(len(frame), len(previous))
            else:
                self.assertIn(len(frame), {len(previous), max(len(previous) - 1, MIN_LEN)})
        self.assertFalse(pending)

        durations = step_durations(frames, grid)
        expected_times, total = key_times(durations)
        self.assertGreater(total, 0)
        self.assertEqual(len(durations), len(frames) - 1)
        # One constant speed for the whole loop: no surges between cells.
        self.assertEqual(len(set(durations)), 1)
        self.assertTrue(MIN_STEP_S <= durations[0] <= MAX_STEP_S)

        svg = render_svg(grid, seed=seed) if svg is None else svg
        root = ET.fromstring(svg)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        _, cum, steps = route_geometry(frames)
        times = loop_times(frames)
        self.assertEqual(times[0], 0.0)
        self.assertEqual(times[-1], 1.0)
        for previous, time in zip(times, times[1:]):
            self.assertGreater(time, previous)
        # Constant speed: each step takes time proportional to its length.
        lap = cum[2 * steps] - cum[steps]
        for k in range(steps):
            self.assertAlmostEqual(times[k + 1] - times[k],
                                   (cum[steps + k + 1] - cum[steps + k]) / lap)

        # Cost must not scale with the snake's length or the meal count.
        animations = [el for el in root.iter()
                      if el.tag.split('}')[1] in ('animate', 'animateMotion', 'animateTransform', 'set')]
        self.assertLessEqual(len(animations), 4)

        body = root.find('s:path[@id="route"]', ns)
        dash_anim, offset_anim = body.findall('s:animate', ns)
        self.assertEqual(dash_anim.attrib['attributeName'], 'stroke-dasharray')
        self.assertEqual(offset_anim.attrib['attributeName'], 'stroke-dashoffset')
        for anim in (dash_anim, offset_anim):
            self.assertEqual(anim.attrib['calcMode'], 'linear')
            self.assertEqual(anim.attrib['dur'], f'{total:.2f}s')
            self.assertEqual(anim.attrib['keyTimes'], dash_anim.attrib['keyTimes'])
            self.assertEqual(len(anim.attrib['values'].split(';')), len(frames))
        dashes = [float(v.split()[0]) for v in dash_anim.attrib['values'].split(';')]
        tails = [-float(v) for v in offset_anim.attrib['values'].split(';')]
        self.assertEqual(dashes[0], dashes[-1])
        for k, frame in enumerate(frames):
            head = cum[steps + k]
            tail = cum[steps + k - (len(frame) - 1)]
            self.assertAlmostEqual(tails[k], tail, places=1)
            self.assertAlmostEqual(dashes[k] + tails[k], head, places=1)
        # The tail never jumps: it holds still while growing and moves at
        # most two cells per step while shrinking.
        for k in range(steps):
            if k + 1 == steps:
                break
            self.assertGreaterEqual(tails[k + 1] - tails[k], -0.01)
            self.assertLessEqual(tails[k + 1] - tails[k], 2 * PITCH + 0.01)

        motion = root.find('s:g[@id="head"]/s:animateMotion', ns)
        self.assertEqual(motion.attrib['calcMode'], 'linear')
        self.assertEqual(motion.attrib['keyTimes'], '0;1')
        self.assertEqual(motion.attrib['dur'], f'{total:.2f}s')
        start, end = map(float, motion.attrib['keyPoints'].split(';'))
        self.assertAlmostEqual(start, cum[steps] / cum[-1], places=5)
        self.assertAlmostEqual(end, cum[2 * steps] / cum[-1], places=5)

        wipe = root.find('s:mask/s:path/s:animate', ns)
        self.assertEqual(wipe.attrib['keyTimes'], dash_anim.attrib['keyTimes'])
        trail = [tuple(map(float, p.split(','))) for p in
                 root.find('s:mask/s:path', ns).attrib['d'][1:].split(' L')]
        self.assertEqual(trail, [cell_center(*frame[0]) for frame in frames])
        wiped = [float(v.split()[0]) for v in wipe.attrib['values'].split(';')]
        for previous, value in zip(wiped, wiped[1:]):
            self.assertGreater(value, previous)
        foods_drawn = root.findall('s:g[@mask]/s:rect', ns)
        self.assertEqual(len(foods_drawn), len(eats))
        for step in eats.values():
            # Wiped just as the head reaches the cell, not before.
            self.assertAlmostEqual(wiped[step], step * PITCH + 6)

    def test_empty_dense_and_sparse_grids(self):
        rng = random.Random(42)
        for width in (1, 2, 3, 52, 53, 54):
            for grid in ([[0] * 7 for _ in range(width)],
                         [[10] * 7 for _ in range(width)],
                         [[rng.choice([0, 0, 1, 5, 12]) for _ in range(7)]
                          for _ in range(width)]):
                with self.subTest(width=width, meals=sum(v > 0 for col in grid for v in col)):
                    self.check_grid(grid, seed=0)

    def test_meal_at_last_cell_and_growth_reset(self):
        self.check_grid([[0] * 6 + [1]], seed=0)
        frames, _ = build_frames([[1] * 7], seed=0)
        self.assertEqual(max(map(len, frames)), MIN_LEN + 7)
        self.assertEqual(len(frames[-1]), MIN_LEN)

    def test_grows_while_eating_up_to_the_cap(self):
        rng = random.Random(11)
        grid = [[0] * 7 for _ in range(30)]
        grid += [[rng.choice([0, 1, 1, 5, 12]) for _ in range(7)] for _ in range(23)]
        for seed in range(4):
            frames, eats = build_frames(grid, seed=seed)
            lengths = [len(frame) for frame in frames]
            last_meal = max(eats.values())
            hunt = lengths[:last_meal + 1]
            # Never shrinks while hunting, grows one segment at a time.
            for a, b in zip(hunt, hunt[1:]):
                self.assertIn(b - a, (0, 1))
            self.assertEqual(max(lengths), MAX_LEN)
            self.assertGreater(MAX_LEN, MIN_LEN + 5)
            # Growth is spread out: the cap is reached well into the hunt,
            # and the snake keeps growing visibly before that.
            first_cap = lengths.index(MAX_LEN)
            self.assertGreater(first_cap, last_meal * 0.3)
            self.assertLess(first_cap, last_meal)
            # The return trip retracts the tail at most one segment per step.
            back = lengths[last_meal:]
            for a, b in zip(back, back[1:]):
                self.assertIn(a - b, (0, 1))
            self.assertEqual(lengths[-1], MIN_LEN)

    def test_constant_speed_and_reasonable_loop(self):
        rng = random.Random(7)
        grid = [[rng.choice([0, 0, 0, 1, 5, 12]) for _ in range(7)] for _ in range(53)]
        frames, _ = build_frames(grid, seed=3)
        durations = step_durations(frames, grid)
        times, total = key_times(durations)
        self.assertEqual(len(set(durations)), 1)
        self.assertEqual(times[0], 0.0)
        self.assertEqual(times[-1], 1.0)
        self.assertTrue(15 <= total <= 35, total)

    def test_route_mostly_runs_straight(self):
        # Real profiles cluster contributions in recent weeks.
        rng = random.Random(5)
        grid = [[0] * 7 for _ in range(30)]
        grid += [[rng.choice([0, 1, 1, 5, 12]) for _ in range(7)] for _ in range(23)]
        for seed in range(4):
            frames, _ = build_frames(grid, seed=seed)
            heads = [frame[0] for frame in frames]
            moves = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(heads, heads[1:])]
            turns = sum(1 for a, b in zip(moves, moves[1:]) if a != b)
            # A random-tie-break staircase turns on ~half the cells.
            self.assertLess(turns / len(moves), 0.35, (seed, turns, len(moves)))

    def test_same_seed_is_deterministic(self):
        rng = random.Random(1)
        grid = [[rng.choice([0, 0, 1, 5]) for _ in range(7)] for _ in range(12)]
        first = build_frames(grid, seed=42)
        second = build_frames(grid, seed=42)
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        # And the SVG, which would otherwise reshuffle the path.
        self.assertEqual(render_svg(grid, seed=42), render_svg(grid, seed=42))

    def test_different_seeds_change_the_route(self):
        rng = random.Random(1)
        grid = [[rng.choice([0, 0, 1, 5, 12]) for _ in range(7)] for _ in range(16)]
        paths = {tuple(frame[0] for frame in build_frames(grid, seed=seed)[0])
                 for seed in range(8)}
        self.assertGreater(len(paths), 1)

    def test_chase_does_not_sweep_every_cell(self):
        grid = [[0] * 7 for _ in range(20)]
        grid[19][6] = 1
        frames, eats = build_frames(grid, seed=0)
        visited = {frame[0] for frame in frames if 0 <= frame[0][0] < 20 and 0 <= frame[0][1] < 7}
        self.assertEqual(set(eats), {(19, 6)})
        self.assertLess(len(visited), 20 * 7)

    def test_invalid_grid(self):
        for grid in ([], [[]], [[0] * 6]):
            with self.assertRaises(ValueError):
                build_frames(grid, seed=0)


if __name__ == '__main__':
    unittest.main()
