"""Deterministic seeded range helpers for climb and sink variation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2s


@dataclass(frozen=True)
class SeededRangeGenerator:
    seed: int
    minimum: float
    maximum: float
    salt: str = ""
    interpolation_ticks: int = 5

    def value_at(self, tick_index: int) -> float:
        if tick_index < 0:
            raise ValueError("tick_index must be >= 0.")
        if self.maximum < self.minimum:
            raise ValueError("maximum must be >= minimum.")
        if self.maximum == self.minimum:
            return self.minimum

        smoothing = max(1, self.interpolation_ticks)
        anchor_index = tick_index // smoothing
        blend = _smoothstep((tick_index % smoothing) / smoothing)
        lower = self._anchor_value(anchor_index)
        upper = self._anchor_value(anchor_index + 1)
        return lower + (upper - lower) * blend

    def sequence(self, *, start_tick: int, count: int) -> tuple[float, ...]:
        if count < 0:
            raise ValueError("count must be >= 0.")
        return tuple(self.value_at(start_tick + offset) for offset in range(count))

    def _anchor_value(self, anchor_index: int) -> float:
        fraction = _hash_to_unit_interval(self.seed, anchor_index, self.salt)
        return self.minimum + (self.maximum - self.minimum) * fraction


def _hash_to_unit_interval(seed: int, tick_index: int, salt: str) -> float:
    payload = f"{seed}:{tick_index}:{salt}".encode("utf-8")
    digest = blake2s(payload, digest_size=8).digest()
    integer = int.from_bytes(digest, byteorder="big", signed=False)
    return integer / ((1 << 64) - 1)


def _smoothstep(value: float) -> float:
    clamped = min(1.0, max(0.0, float(value)))
    return clamped * clamped * (3.0 - 2.0 * clamped)
