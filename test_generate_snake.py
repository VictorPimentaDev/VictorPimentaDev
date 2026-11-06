import random
import unittest
import xml.etree.ElementTree as ET

from generate_snake import MAX_LEN, MIN_LEN, PITCH, build_frames, cell_center, render_svg


class SnakeTest(unittest.TestCase):
    def check_grid(self, grid, svg=None):
        frames, eats = build_frames(grid)
        self.assertEqual(frames[0], frames[-1])
        self.assertEqual(len(frames[0]), MIN_LEN)
        foods = {(c, r) for c, column in enumerate(grid)
                 for r, count in enumerate(column) if count > 0}
        self.assertEqual(set(eats), foods)
        for previous, frame in zip(frames, frames[1:]):
            self.assertEqual(len(set(frame)), len(frame))
            self.assertLessEqual(len(frame), MAX_LEN)
            self.assertGreaterEqual(len(frame), MIN_LEN)
            for a, b in [(previous[0], frame[0]), *zip(frame, frame[1:])]:
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
            self.assertEqual(frame[1:], previous[:len(frame) - 1])
            self.assertNotIn(frame[0], previous)
            if frame[0] in foods:
                self.assertEqual(len(frame), min(len(previous) + 1, MAX_LEN))
                foods.remove(frame[0])
            elif 0 <= frame[0][0] < len(grid) and 0 <= frame[0][1] < 7:
                self.assertEqual(len(frame), len(previous))
        self.assertFalse(foods)

        root = ET.fromstring(render_svg(grid) if svg is None else svg)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        rendered = [[] for _ in frames]
        groups = root.findall('s:g', ns)
        width, height = float(root.attrib['width']), float(root.attrib['height'])
        for group in reversed(groups):
            motion = group.find('s:animateTransform', ns)
            opacity = group.find('s:animate', ns)
            self.assertEqual(motion.attrib['calcMode'], 'discrete')
            self.assertEqual(opacity.attrib['calcMode'], 'discrete')
            self.assertNotIn('begin', motion.attrib)
            times = list(map(float, motion.attrib['keyTimes'].split(';')))
            self.assertEqual(len(times), len(frames))
            self.assertEqual(times[0], 0)
            self.assertEqual(times[-1], 1)
            for step, time in enumerate(times):
                self.assertAlmostEqual(time, step / (len(frames) - 1))
            self.assertEqual(motion.attrib['keyTimes'], opacity.attrib['keyTimes'])
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
        for animation in food_animations:
            self.assertEqual(animation.attrib['calcMode'], 'discrete')
            self.assertIn(round(float(animation.attrib['keyTimes'].split(';')[1]), 8),
                          {round(step / (len(frames) - 1), 8) for step in eats.values()})

    def test_empty_dense_and_sparse_grids(self):
        rng = random.Random(42)
        for width in (1, 2, 3, 52, 53, 54):
            for grid in ([[0] * 7 for _ in range(width)],
                         [[10] * 7 for _ in range(width)],
                         [[rng.choice([0, 0, 1, 5, 12]) for _ in range(7)]
                          for _ in range(width)]):
                with self.subTest(width=width, meals=sum(v > 0 for col in grid for v in col)):
                    self.check_grid(grid)

    def test_meal_at_last_cell_and_growth_reset(self):
        self.check_grid([[0] * 6 + [1]])
        frames, _ = build_frames([[1] * 7])
        self.assertEqual(max(map(len, frames)), MAX_LEN)
        self.assertEqual(len(frames[-1]), MIN_LEN)

    def test_invalid_grid(self):
        for grid in ([], [[]], [[0] * 6]):
            with self.assertRaises(ValueError):
                build_frames(grid)


if __name__ == '__main__':
    unittest.main()
