"""Selected XCvario polar definitions mirrored from upstream firmware."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XcvarioPolar:
    index: int
    name: str
    wingload_kg_m2: float
    speed1_kmh: float
    sink1_ms: float
    speed2_kmh: float
    sink2_ms: float
    speed3_kmh: float
    sink3_ms: float
    max_ballast_kg: float
    wingarea_m2: float

    @property
    def reference_weight_kg(self) -> float:
        return self.wingload_kg_m2 * self.wingarea_m2

    @property
    def empty_weight_kg(self) -> float:
        # Upstream XCVario assumes an 80 kg crew when deriving empty mass.
        return self.reference_weight_kg - 80.0

    def ballast_overload_factor(self, ballast_fill_fraction: float) -> float:
        if self.reference_weight_kg <= 0.0:
            return 1.0
        resolved_fill_fraction = max(0.0, min(1.0, float(ballast_fill_fraction)))
        ballast_kg = resolved_fill_fraction * self.max_ballast_kg
        ballast_overload_percent = (100.0 * (self.reference_weight_kg + ballast_kg) / self.reference_weight_kg) - 100.0
        return (ballast_overload_percent + 100.0) / 100.0


XCVARIO_POLARS: tuple[XcvarioPolar, ...] = (
    XcvarioPolar(1360, "DG 800B/15", 38.76, 97.4494, -0.6146, 130.0, -0.9312, 170.0, -1.5857, 100.0, 10.68),
    XcvarioPolar(1370, "DG 800S/15", 34.93, 92.4983, -0.5834, 130.0, -0.9720, 170.0, -1.6852, 150.0, 10.68),
    XcvarioPolar(1380, "DG 800B/18", 35.39, 84.7035, -0.5172, 130.0, -0.8367, 170.0, -1.5613, 100.0, 11.81),
    XcvarioPolar(1390, "DG 800S/18", 29.97, 77.9497, -0.4760, 130.0, -0.9192, 170.0, -1.7786, 150.0, 11.81),
)


def get_xcvario_polar(polar_name: str) -> XcvarioPolar:
    normalized_name = str(polar_name or "").strip().casefold()
    if not normalized_name:
        raise ValueError("xcvario.polar_name must be a non-empty string.")

    for polar in XCVARIO_POLARS:
        if polar.name.casefold() == normalized_name:
            return polar

    known_names = ", ".join(polar.name for polar in XCVARIO_POLARS)
    raise ValueError(f"Unknown xcvario.polar_name {polar_name!r}. Known values: {known_names}.")
