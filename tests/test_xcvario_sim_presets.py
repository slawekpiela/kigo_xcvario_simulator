import unittest

from kigo_xcvario_simulator.presets import (
    PRESET_CIRCLING,
    PRESET_FULL_FLIGHT,
    PRESET_GLIDER_LANDING,
    PRESET_GLIDER_LAUNCH,
    PRESET_ON_GROUND,
    PRESET_STRAIGHT,
    available_preset_ids,
    build_preset,
)
from kigo_xcvario_simulator.state import FlightPhase


class SimulatorPresetTests(unittest.TestCase):
    def test_available_presets_cover_mvp_set(self):
        self.assertEqual(
            available_preset_ids(),
            (
                PRESET_ON_GROUND,
                PRESET_GLIDER_LAUNCH,
                PRESET_CIRCLING,
                PRESET_STRAIGHT,
                PRESET_GLIDER_LANDING,
                PRESET_FULL_FLIGHT,
            ),
        )

    def test_on_ground_preset_keeps_glider_stationary_on_ground(self):
        preset = build_preset(PRESET_ON_GROUND, seed=7)

        self.assertEqual(len(preset.segments), 1)
        self.assertEqual(preset.segments[0].segment_id, "on_ground")
        self.assertEqual(preset.segments[0].phase, FlightPhase.GLIDER_LAUNCH)
        self.assertEqual(preset.segments[0].duration_s, None)
        self.assertAlmostEqual(preset.segments[0].target_speed_kmh, 0.0, places=6)
        self.assertAlmostEqual(preset.segments[0].sink_ms, 0.0, places=6)
        self.assertTrue(preset.segments[0].on_ground)

    def test_glider_launch_preset_contains_expected_segment_sequence(self):
        preset = build_preset(PRESET_GLIDER_LAUNCH, seed=7)

        self.assertEqual(preset.segments[0].segment_id, "ground_hold")
        self.assertTrue(preset.segments[0].on_ground)
        self.assertAlmostEqual(preset.segments[0].target_speed_kmh, 0.0, places=6)
        self.assertEqual(len(preset.segments), 153)
        self.assertEqual(preset.segments[1].segment_id, "launch_accel_001")
        self.assertAlmostEqual(preset.segments[1].target_speed_kmh, 120.0 / 150.0, places=6)
        self.assertEqual(preset.segments[120].segment_id, "launch_accel_120")
        self.assertAlmostEqual(preset.segments[120].target_speed_kmh, 96.0, places=6)
        self.assertAlmostEqual(preset.segments[120].climb_min_ms, 0.0, places=6)
        self.assertAlmostEqual(preset.segments[120].climb_max_ms, 0.0, places=6)
        self.assertEqual(preset.segments[121].segment_id, "launch_accel_121")
        self.assertAlmostEqual(preset.segments[121].climb_min_ms, 1.0, places=6)
        self.assertAlmostEqual(preset.segments[121].climb_max_ms, 1.0, places=6)
        self.assertEqual(preset.segments[-2].segment_id, "launch_climb_1ms")
        self.assertAlmostEqual(preset.segments[-2].duration_s, 2.0, places=6)
        self.assertAlmostEqual(preset.segments[-2].climb_min_ms, 1.0, places=6)
        self.assertEqual(preset.segments[-1].segment_id, "initial_climb")
        self.assertAlmostEqual(preset.segments[-1].target_speed_kmh, 120.0, places=6)
        self.assertAlmostEqual(preset.segments[-1].climb_min_ms, 4.0, places=6)
        self.assertAlmostEqual(preset.segments[-1].climb_max_ms, 4.0, places=6)
        self.assertEqual(preset.segments[-1].duration_s, None)
        self.assertEqual(preset.segments[-1].phase, FlightPhase.GLIDER_LAUNCH)

    def test_circling_preset_supports_right_turn_override(self):
        preset = build_preset(
            PRESET_CIRCLING,
            seed=3,
            overrides={
                "direction": "right",
                "turn_radius_m": 140.0,
                "speed_min_kmh": 75.0,
                "speed_max_kmh": 82.0,
            },
        )

        self.assertEqual(len(preset.segments), 1)
        self.assertEqual(preset.segments[0].phase, FlightPhase.CIRCLING_RIGHT)
        self.assertEqual(preset.segments[0].turn_radius_m, 140.0)
        self.assertEqual(preset.segments[0].speed_min_kmh, 75.0)
        self.assertEqual(preset.segments[0].speed_max_kmh, 82.0)

    def test_circling_preset_defaults_to_small_speed_band_around_target(self):
        preset = build_preset(PRESET_CIRCLING, seed=3)

        self.assertEqual(preset.segments[0].target_speed_kmh, 78.0)
        self.assertEqual(preset.segments[0].speed_min_kmh, 76.0)
        self.assertEqual(preset.segments[0].speed_max_kmh, 80.0)

    def test_straight_preset_applies_heading_override(self):
        preset = build_preset(PRESET_STRAIGHT, seed=99, overrides={"heading_deg": 135.0, "speed_kmh": 105.0})

        self.assertEqual(preset.segments[0].phase, FlightPhase.STRAIGHT)
        self.assertEqual(preset.segments[0].target_heading_deg, 135.0)
        self.assertEqual(preset.segments[0].target_speed_kmh, 105.0)

    def test_glider_landing_preset_ends_on_ground(self):
        preset = build_preset(PRESET_GLIDER_LANDING, seed=15)

        self.assertEqual([segment.segment_id for segment in preset.segments], ["approach", "flare", "rollout"])
        self.assertTrue(preset.segments[-1].on_ground)
        self.assertEqual(preset.segments[-1].phase, FlightPhase.GLIDER_LANDING)

    def test_full_flight_concatenates_mvp_phases(self):
        preset = build_preset(PRESET_FULL_FLIGHT, seed=15, overrides={"circling_direction": "right"})
        segment_ids = [segment.segment_id for segment in preset.segments]

        self.assertEqual(segment_ids[0], "ground_hold")
        self.assertEqual(segment_ids[-5:], ["initial_climb", "circling_core", "straight_leg", "approach", "flare", "rollout"][-5:])
        self.assertLess(segment_ids.index("initial_climb"), segment_ids.index("circling_core"))
        self.assertLess(segment_ids.index("circling_core"), segment_ids.index("straight_leg"))
        self.assertLess(segment_ids.index("straight_leg"), segment_ids.index("approach"))
        self.assertNotEqual(preset.segments[segment_ids.index("initial_climb")].duration_s, None)
        self.assertAlmostEqual(preset.segments[segment_ids.index("initial_climb")].duration_s, 36.25, places=6)
        self.assertEqual(preset.segments[segment_ids.index("circling_core")].phase, FlightPhase.CIRCLING_RIGHT)

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            build_preset("nope", seed=1)


if __name__ == "__main__":
    unittest.main()
