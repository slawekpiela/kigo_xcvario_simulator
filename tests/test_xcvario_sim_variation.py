import unittest

from kigo_xcvario_simulator.variation import SeededRangeGenerator


class SimulatorVariationTests(unittest.TestCase):
    def test_same_seed_and_tick_are_stable(self):
        generator = SeededRangeGenerator(seed=42, minimum=2.0, maximum=3.0, salt="climb")

        self.assertAlmostEqual(generator.value_at(0), generator.value_at(0), places=12)
        self.assertAlmostEqual(generator.value_at(15), generator.value_at(15), places=12)

    def test_different_seed_changes_the_series(self):
        first = SeededRangeGenerator(seed=1, minimum=2.0, maximum=3.0, salt="climb")
        second = SeededRangeGenerator(seed=2, minimum=2.0, maximum=3.0, salt="climb")

        self.assertNotEqual(first.sequence(start_tick=0, count=6), second.sequence(start_tick=0, count=6))

    def test_generated_values_stay_inside_requested_range(self):
        generator = SeededRangeGenerator(seed=9, minimum=-3.0, maximum=-1.0, salt="sink")

        for value in generator.sequence(start_tick=0, count=25):
            self.assertGreaterEqual(value, -3.0)
            self.assertLessEqual(value, -1.0)

    def test_higher_smoothing_limits_per_tick_jumps(self):
        generator = SeededRangeGenerator(
            seed=11,
            minimum=-1.0,
            maximum=3.0,
            salt="circling",
            interpolation_ticks=24,
        )

        values = generator.sequence(start_tick=0, count=40)
        deltas = [abs(right - left) for left, right in zip(values, values[1:])]

        self.assertLess(max(deltas), 0.35)

    def test_count_and_tick_validation_is_enforced(self):
        generator = SeededRangeGenerator(seed=9, minimum=0.0, maximum=1.0)

        with self.assertRaises(ValueError):
            generator.value_at(-1)
        with self.assertRaises(ValueError):
            generator.sequence(start_tick=0, count=-1)


if __name__ == "__main__":
    unittest.main()
