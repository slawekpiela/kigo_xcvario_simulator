import unittest

from kigo_xcvario_simulator.config import (
    ControlApiConfig,
    EndpointConfig,
    HomePosition,
    SchedulerConfig,
    SimulatorRuntimeConfig,
    XcvarioConfig,
)
from kigo_xcvario_simulator.baro import qnh_hpa_for_static_pressure, static_pressure_hpa_for_altitude
from kigo_xcvario_simulator.contracts import ManualModeInput, PresetRequest
from kigo_xcvario_simulator.orchestrator import ScenarioOrchestrator
from kigo_xcvario_simulator.state import FlightPhase, HealthState, RuntimeState
from kigo_xcvario_simulator.traffic_database import FLARM_TRAFFIC_AIRCRAFT


def _runtime_config() -> SimulatorRuntimeConfig:
    return SimulatorRuntimeConfig(
        session_id="xcvario-sim",
        seed=321,
        device_qnh_hpa=1013.25,
        home_position=HomePosition(latitude_deg=49.83833, longitude_deg=19.00202, gps_altitude_m=401.0),
        control_api=ControlApiConfig(),
        xcvario=XcvarioConfig(port=4353, polar_name="DG 800B/15"),
        flarm=EndpointConfig(port=4354),
        scheduler=SchedulerConfig(),
    )


class ScenarioOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = ScenarioOrchestrator(_runtime_config())

    def test_start_pause_and_reset_are_idempotent(self):
        first_start = self.orchestrator.start()
        second_start = self.orchestrator.start()
        paused = self.orchestrator.pause()
        second_pause = self.orchestrator.pause()
        reset = self.orchestrator.reset()

        self.assertEqual(first_start.runtime_state, RuntimeState.RUNNING)
        self.assertEqual(second_start.runtime_state, RuntimeState.RUNNING)
        self.assertEqual(paused.runtime_state, RuntimeState.PAUSED)
        self.assertEqual(second_pause.runtime_state, RuntimeState.PAUSED)
        self.assertEqual(reset.runtime_state, RuntimeState.PAUSED)
        self.assertAlmostEqual(reset.sim_time_s, 0.0, places=6)

    def test_preset_autostart_and_completion_stop_runtime(self):
        snapshot = self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=5, autostart=True))
        self.assertEqual(snapshot.runtime_state, RuntimeState.RUNNING)

        completed = self.orchestrator.tick(500.0)

        self.assertEqual(completed.runtime_state, RuntimeState.STOPPED)
        self.assertEqual(completed.preset_id, "straight")
        self.assertAlmostEqual(completed.sim_time_s, 240.0, places=6)

    def test_manual_override_replaces_active_preset_without_resetting_progress(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="circling", seed=7, autostart=True))
        before_override = self.orchestrator.tick(5.0)

        override = self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.STRAIGHT,
                heading_deg=135.0,
                speed_kmh=100.0,
            )
        )
        after_override = self.orchestrator.tick(5.0)

        self.assertEqual(override.preset_id, None)
        self.assertEqual(after_override.runtime_state, RuntimeState.RUNNING)
        self.assertGreater(after_override.sim_time_s, before_override.sim_time_s)
        self.assertGreater(after_override.ownship.longitude_deg, before_override.ownship.longitude_deg)
        self.assertEqual(after_override.ownship.phase, FlightPhase.STRAIGHT)

    def test_manual_circling_uses_configured_speed_limits(self):
        self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.CIRCLING_LEFT,
                speed_min_kmh=90.0,
                speed_max_kmh=110.0,
                climb_min_ms=2.0,
                climb_max_ms=2.0,
            )
        )
        self.orchestrator.start()

        samples = []
        for _ in range(100):
            samples.append(self.orchestrator.tick(0.1).ownship.speed_kmh)

        self.assertAlmostEqual(min(samples), 90.0, places=6)
        self.assertAlmostEqual(max(samples), 110.0, places=6)
        self.assertAlmostEqual(samples[0], 90.0, places=6)
        self.assertAlmostEqual(samples[48], 110.0, places=6)
        self.assertAlmostEqual(samples[96], 90.0, places=6)

    def test_manual_straight_sets_configured_altitude_for_gps_and_pressure(self):
        immediate = self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.STRAIGHT,
                heading_deg=90.0,
                speed_kmh=100.0,
                baro_altitude_m=900.0,
            )
        )
        self.orchestrator.start()

        snapshot = self.orchestrator.tick(1.0)

        self.assertEqual(immediate.ownship.phase, FlightPhase.STRAIGHT)
        self.assertAlmostEqual(immediate.ownship.track_deg, 90.0, places=6)
        self.assertAlmostEqual(immediate.ownship.speed_kmh, 100.0, places=6)
        self.assertAlmostEqual(immediate.ownship.gps_altitude_m, 900.0, places=6)
        self.assertAlmostEqual(immediate.ownship.vertical_speed_ms, 0.0, places=6)
        self.assertAlmostEqual(snapshot.ownship.gps_altitude_m, 900.0, places=6)
        self.assertAlmostEqual(snapshot.ownship.vertical_speed_ms, 0.0, places=6)
        self.assertAlmostEqual(
            snapshot.ownship.static_pressure_hpa,
            static_pressure_hpa_for_altitude(900.0, qnh_hpa=_runtime_config().device_qnh_hpa),
            places=6,
        )

    def test_manual_circling_and_sink_update_snapshot_immediately(self):
        circling = self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.CIRCLING_LEFT,
                heading_deg=45.0,
                speed_min_kmh=70.0,
                speed_max_kmh=72.0,
                turn_radius_m=80.0,
                climb_min_ms=1.1,
                climb_max_ms=1.1,
            )
        )

        self.assertEqual(circling.ownship.phase, FlightPhase.CIRCLING_LEFT)
        self.assertAlmostEqual(circling.ownship.track_deg, 45.0, places=6)
        self.assertAlmostEqual(circling.ownship.speed_kmh, 70.0, places=6)
        self.assertAlmostEqual(circling.ownship.vertical_speed_ms, 1.1, places=6)

        self.orchestrator.start()
        first_tick = self.orchestrator.tick(0.1)
        self.assertAlmostEqual(first_tick.ownship.speed_kmh, 70.0, places=6)

        sink = self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.SINK,
                heading_deg=222.0,
                speed_kmh=99.0,
                sink_ms=-3.3,
            )
        )

        self.assertEqual(sink.ownship.phase, FlightPhase.SINK)
        self.assertAlmostEqual(sink.ownship.track_deg, 222.0, places=6)
        self.assertAlmostEqual(sink.ownship.speed_kmh, 99.0, places=6)
        self.assertAlmostEqual(sink.ownship.vertical_speed_ms, -3.3, places=6)

    def test_manual_on_ground_resets_to_home_position(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=7, autostart=True))
        before_on_ground = self.orchestrator.tick(10.0)

        snapshot = self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.GLIDER_LAUNCH,
                on_ground=True,
            )
        )

        self.assertGreater(before_on_ground.ownship.longitude_deg, snapshot.ownship.longitude_deg)
        self.assertEqual(snapshot.preset_id, None)
        self.assertAlmostEqual(snapshot.sim_time_s, 0.0, places=6)
        self.assertTrue(snapshot.ownship.on_ground)
        self.assertAlmostEqual(snapshot.ownship.speed_kmh, 0.0, places=6)
        self.assertAlmostEqual(snapshot.ownship.latitude_deg, _runtime_config().home_position.latitude_deg, places=6)
        self.assertAlmostEqual(snapshot.ownship.longitude_deg, _runtime_config().home_position.longitude_deg, places=6)

    def test_wind_state_is_normalized_and_persists_across_reset(self):
        changed = self.orchestrator.set_wind(450.0, 25.5)
        reset = self.orchestrator.reset()

        self.assertAlmostEqual(changed.wind.direction_deg, 90.0, places=6)
        self.assertAlmostEqual(changed.wind.speed_kmh, 25.5, places=6)
        self.assertAlmostEqual(reset.wind.direction_deg, 90.0, places=6)
        self.assertAlmostEqual(reset.wind.speed_kmh, 25.5, places=6)

    def test_manual_glider_launch_holds_then_accelerates_to_target_speed(self):
        self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.GLIDER_LAUNCH,
                heading_deg=135.0,
                speed_kmh=100.0,
            )
        )
        self.orchestrator.start()

        hold = self.orchestrator.tick(3.0)
        level_roll = self.orchestrator.tick(11.0)
        low_climb_acceleration = self.orchestrator.tick(4.0)
        low_climb_tail = self.orchestrator.tick(1.5)
        high_climb = self.orchestrator.tick(1.5)

        self.assertAlmostEqual(hold.ownship.speed_kmh, 0.0, places=6)
        self.assertAlmostEqual(hold.ownship.gps_altitude_m, 401.0, places=6)
        self.assertTrue(hold.ownship.on_ground)
        self.assertEqual(hold.preset_id, None)
        self.assertGreater(level_roll.ownship.speed_kmh, 0.0)
        self.assertLess(level_roll.ownship.speed_kmh, 100.0)
        self.assertAlmostEqual(level_roll.ownship.gps_altitude_m, 401.0, places=6)
        self.assertAlmostEqual(level_roll.ownship.vertical_speed_ms, 0.0, places=6)
        self.assertFalse(level_roll.ownship.on_ground)
        self.assertAlmostEqual(low_climb_acceleration.ownship.speed_kmh, 100.0, places=6)
        self.assertAlmostEqual(low_climb_acceleration.ownship.gps_altitude_m, 404.0, places=6)
        self.assertAlmostEqual(low_climb_acceleration.ownship.vertical_speed_ms, 1.0, places=6)
        self.assertAlmostEqual(low_climb_tail.ownship.gps_altitude_m, 405.5, places=6)
        self.assertAlmostEqual(low_climb_tail.ownship.vertical_speed_ms, 1.0, places=6)
        self.assertAlmostEqual(high_climb.ownship.gps_altitude_m, 410.0, places=6)
        self.assertAlmostEqual(high_climb.ownship.vertical_speed_ms, 4.0, places=6)

    def test_glider_launch_preset_switches_to_straight_after_reaching_150m_agl(self):
        launched = self.orchestrator.load_preset(
            PresetRequest(preset_id="glider_launch", seed=5, autostart=True),
        )
        completed_launch = self.orchestrator.tick(56.3)

        self.assertEqual(launched.preset_id, "glider_launch")
        self.assertEqual(completed_launch.preset_id, "straight")
        self.assertEqual(completed_launch.ownship.phase, FlightPhase.STRAIGHT)
        self.assertGreaterEqual(completed_launch.ownship.gps_altitude_m, 551.0)
        self.assertAlmostEqual(completed_launch.ownship.speed_kmh, 120.0, places=6)

    def test_manual_glider_launch_switches_to_straight_after_reaching_150m_agl(self):
        self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.GLIDER_LAUNCH,
                heading_deg=135.0,
                speed_kmh=100.0,
            )
        )
        self.orchestrator.start()

        completed_launch = self.orchestrator.tick(56.3)

        self.assertEqual(completed_launch.preset_id, None)
        self.assertEqual(completed_launch.ownship.phase, FlightPhase.STRAIGHT)
        self.assertGreaterEqual(completed_launch.ownship.gps_altitude_m, 551.0)
        self.assertAlmostEqual(completed_launch.ownship.speed_kmh, 100.0, places=6)

    def test_write_side_qnh_updates_device_setting_without_changing_pressure(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=5, autostart=True))
        before = self.orchestrator.tick(5.0)

        changed = self.orchestrator.set_device_qnh_hpa(995.5)

        self.assertAlmostEqual(changed.ownship.device_qnh_hpa, 995.5, places=4)
        self.assertAlmostEqual(changed.ownship.static_pressure_hpa, before.ownship.static_pressure_hpa, places=6)
        self.assertAlmostEqual(changed.ownship.gps_altitude_m, before.ownship.gps_altitude_m, places=6)

    def test_device_altitude_change_recalculates_qnh_without_changing_pressure(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=5, autostart=True))
        before = self.orchestrator.tick(5.0)

        changed = self.orchestrator.set_device_altitude_m(875.0)
        expected_qnh = qnh_hpa_for_static_pressure(before.ownship.static_pressure_hpa, 875.0)

        self.assertAlmostEqual(changed.ownship.device_altitude_m or 0.0, 875.0, places=6)
        self.assertAlmostEqual(changed.ownship.device_qnh_hpa, expected_qnh, places=6)
        self.assertAlmostEqual(changed.ownship.static_pressure_hpa, before.ownship.static_pressure_hpa, places=6)
        self.assertAlmostEqual(changed.ownship.gps_altitude_m, before.ownship.gps_altitude_m, places=6)

    def test_traffic_config_populates_snapshot_without_degrading_ownship(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=5, autostart=True))
        self.orchestrator.set_traffic_config(
            True,
            2,
            collision_course=True,
            motion_mode="straight",
            circling_radius_min_m=300.0,
            circling_radius_max_m=500.0,
        )

        snapshot = self.orchestrator.tick(1.0)

        self.assertEqual(len(snapshot.traffic), 2)
        self.assertEqual(snapshot.health, HealthState.READY)
        self.assertEqual(snapshot.ownship.phase, FlightPhase.STRAIGHT)
        self.assertTrue(snapshot.traffic[0].aircraft_id)
        self.assertEqual(self.orchestrator.get_traffic_config().collision_course, True)
        self.assertEqual(self.orchestrator.get_traffic_config().motion_mode, "straight")
        self.assertEqual(self.orchestrator.get_traffic_config().circling_radius_min_m, 300.0)
        self.assertEqual(self.orchestrator.get_traffic_config().circling_radius_max_m, 500.0)

    def test_default_traffic_config_populates_all_contacts(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=5, autostart=True))

        snapshot = self.orchestrator.tick(1.0)

        self.assertEqual(len(snapshot.traffic), len(FLARM_TRAFFIC_AIRCRAFT))
        self.assertEqual(self.orchestrator.get_traffic_config().contact_count, len(FLARM_TRAFFIC_AIRCRAFT))
        self.assertEqual(self.orchestrator.get_traffic_config().motion_mode, "orbit")
        self.assertEqual(self.orchestrator.get_traffic_config().circling_radius_min_m, 100.0)
        self.assertEqual(self.orchestrator.get_traffic_config().circling_radius_max_m, 700.0)

    def test_traffic_config_reset_restarts_contacts_from_start_anchor(self):
        self.orchestrator.load_preset(PresetRequest(preset_id="straight", seed=5, autostart=True))
        self.orchestrator.set_traffic_config(True, 1)
        first = self.orchestrator.tick(1.0)
        moved = self.orchestrator.tick(10.0)
        self.assertNotAlmostEqual(first.traffic[0].relative_north_m, moved.traffic[0].relative_north_m, delta=0.1)

        self.orchestrator.set_traffic_config(
            True,
            1,
            reset_traffic=True,
            traffic_anchor_position=HomePosition(latitude_deg=49.85833, longitude_deg=19.00202, gps_altitude_m=501.0),
        )
        restarted = self.orchestrator.tick(1.0)

        self.assertAlmostEqual(
            restarted.traffic[0].relative_north_m,
            first.traffic[0].relative_north_m + 0.02 * 111320.0,
            delta=0.1,
        )
        self.assertAlmostEqual(restarted.traffic[0].relative_altitude_m, first.traffic[0].relative_altitude_m + 100.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
