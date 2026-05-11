"""Enums shared by simulator domain modules."""

from __future__ import annotations

from enum import Enum


class RuntimeState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class FlightPhase(str, Enum):
    GLIDER_LAUNCH = "glider_launch"
    STRAIGHT = "straight"
    CIRCLING_LEFT = "circling_left"
    CIRCLING_RIGHT = "circling_right"
    SINK = "sink"
    GLIDER_LANDING = "glider_landing"


class HealthState(str, Enum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPED = "stopped"
