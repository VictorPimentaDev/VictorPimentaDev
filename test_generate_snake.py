import random
import unittest
import xml.etree.ElementTree as ET

from generate_snake import (
    EMPTY_STEP_S,
    MAX_LEN,
    MIN_LEN,
    PITCH,
    START,
    STEP_S,
    build_frames,
    cell_center,
    key_times,
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
                self.assertEqual(len(frame), min(len(previous) + 1, MAX_LEN))
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
        for previous, frame, duration in zip(frames, frames[1:], durations):
            col, row = frame[0]
            meal = 0 <= col < len(grid) and 0 <= row < 7 and grid[col][row] > 0
            self.assertEqual(duration, STEP_S if meal else EMPTY_STEP_S)

        root = ET.fromstring(render_svg(grid, seed=seed) if svg is None else svg)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        rendered = [[] for _ in frames]
        groups = root.findall('s:g', ns)
        width, height = float(root.attrib['width']), float(root.attrib['height'])
        for group in reversed(groups):
            motion = group.find('s:animateTransform', ns)
            opacity = group.find('s:animate', ns)
            self.assertEqual(motion.attrib['calcMode'], 'linear')
            self.assertEqual(opacity.attrib['calcMode'], 'discrete')
            self.assertNotIn('begin', motion.attrib)
            times = list(map(float, motion.attrib['keyTimes'].split(';')))
            self.assertEqual(len(times), len(frames))
            self.assertEqual(times[0], 0)
            self.assertEqual(times[-1], 1)
            for previous, time in zip(times, times[1:]):
                self.assertGreater(time, previous)
            for step, time in enumerate(times):
                self.assertAlmostEqual(time, expected_times[step])
            self.assertEqual(motion.attrib['keyTimes'], opacity.attrib['keyTimes'])
            self.assertEqual(motion.attrib['dur'], f'{total:.2f}s')
            self.assertEqual(opacity.attrib['dur'], f'{total:.2f}s')
            positions = [tuple(map(float, p.split(',')))
                         for p in motion.attrib['values'].split(';')]
            visibility = opacity.attrib['values'].split(';')
            self.assertEqual(len(positions), len(frames))
            self.assertEqual(len(visibility), len(frames))
            self.assertEqual(positions[0], positions[-1])
            self.assertEqual(visibility[0], visibility[-1])
            for a, b in zip(positions, positions[1:]):
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), PITCH)
            for step, (position, visible) in enumerate(zip(positions, visibility)):
                x, y = position
                self.assertTrue(6 <= x <= width - 6 and 6 <= y <= height - 6)
                if visible == '1':
                    rendered[step].append(position)
        self.assertEqual(rendered, [[cell_center(*cell) for cell in frame] for frame in frames])

        food_animations = root.findall('s:rect/s:animate', ns)
        self.assertEqual(len(food_animations), len(eats))
        eat_times = {round(expected_times[step], 8) for step in eats.values()}
        for animation in food_animations:
            self.assertEqual(animation.attrib['calcMode'], 'discrete')
            self.assertIn(round(float(animation.attrib['keyTimes'].split(';')[1]), 8),
                          eat_times)

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
        self.assertEqual(max(map(len, frames)), MAX_LEN)
        self.assertEqual(len(frames[-1]), MIN_LEN)

    def test_variable_timing_makes_empty_cells_faster(self):
        grid = [[1] + [0] * 6]
        frames, _ = build_frames(grid, seed=0)
        durations = step_durations(frames, grid)
        times, total = key_times(durations)
        meals = sum(1 for duration in durations if duration == STEP_S)
        empties = sum(1 for duration in durations if duration == EMPTY_STEP_S)
        self.assertEqual(meals, 1)
        self.assertGreater(empties, 0)
        self.assertAlmostEqual(total, meals * STEP_S + empties * EMPTY_STEP_S)
        self.assertEqual(times[0], 0.0)
        self.assertEqual(times[-1], 1.0)
        self.assertLess(total, (len(frames) - 1) * 0.16)

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
