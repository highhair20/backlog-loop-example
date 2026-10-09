"""Find the cleanest time to run an appliance from a grid carbon-intensity forecast.

A forecast is a list of equal-length slots, each with the grid's expected carbon
intensity in gCO2/kWh. A run of a given duration covers consecutive slots; the best
window is the one with the lowest mean intensity.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

COLUMNS = ("start", "intensity")


class ForecastError(ValueError):
    """A forecast that cannot be read, or a run it cannot answer."""


@dataclass(frozen=True)
class Slot:
    start: datetime
    intensity: float  # gCO2/kWh


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    mean_intensity: float  # gCO2/kWh


def read_forecast(path: Path) -> list[Slot]:
    """Read a CSV with `start` (ISO 8601) and `intensity` (gCO2/kWh) columns."""
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if not set(COLUMNS) <= set(reader.fieldnames or ()):
            raise ForecastError(f"{path}: needs 'start' and 'intensity' columns")
        slots = [_parse_row(path, line, row) for line, row in enumerate(reader, start=2)]
    if not slots:
        raise ForecastError(f"{path}: no rows")
    return sorted(slots, key=lambda s: s.start)


def _parse_row(path: Path, line: int, row: dict[str, str]) -> Slot:
    try:
        slot = Slot(datetime.fromisoformat(row["start"]), float(row["intensity"]))
    except (TypeError, ValueError) as e:
        raise ForecastError(f"{path}:{line}: {e}") from e
    if slot.intensity < 0:
        raise ForecastError(f"{path}:{line}: negative intensity {slot.intensity}")
    return slot


def slot_length(slots: list[Slot]) -> timedelta:
    """The forecast's slot length, taken from its first two slots."""
    if len(slots) < 2:
        raise ForecastError("a forecast needs at least two slots to show its slot length")
    return slots[1].start - slots[0].start


def _slot_count(slots: list[Slot], duration: timedelta) -> int:
    step = slot_length(slots)
    count, rest = divmod(duration, step)
    if rest or count < 1:
        raise ForecastError(f"a {duration} run is not a whole number of {step} slots")
    if count > len(slots):
        raise ForecastError(f"the forecast is shorter than the run ({duration})")
    return count


def window_at(slots: list[Slot], index: int, duration: timedelta) -> Window:
    """The window of `duration` that starts at slot `index`."""
    count = _slot_count(slots, duration)
    covered = slots[index : index + count]
    if len(covered) < count:
        raise ForecastError(f"the forecast ends before a {duration} run from slot {index}")
    mean = sum(s.intensity for s in covered) / count
    return Window(covered[0].start, covered[0].start + duration, mean)


def best_window(slots: list[Slot], duration: timedelta) -> Window:
    """The window of `duration` with the lowest mean intensity; the earliest on a tie."""
    count = _slot_count(slots, duration)
    windows = [window_at(slots, i, duration) for i in range(len(slots) - count + 1)]
    return min(windows, key=lambda w: w.mean_intensity)


def savings_grams(now: Window, best: Window, power_kw: float) -> float:
    """CO2 saved, in grams, by running at `best` instead of `now` at `power_kw`."""
    hours = (now.end - now.start) / timedelta(hours=1)
    return (now.mean_intensity - best.mean_intensity) * power_kw * hours
