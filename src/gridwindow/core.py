"""Find the cleanest time to run an appliance from a grid carbon-intensity forecast.

A forecast is a list of equal-length slots, each with the grid's expected carbon
intensity in gCO2/kWh. A run of a given duration covers consecutive slots; the best
window is the one with the lowest mean intensity.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path

COLUMNS = ("start", "intensity")
TIME = "%Y-%m-%d %H:%M"  # how messages show a slot's start


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
    """The forecast's slot length: the smallest step between consecutive slots.

    Any larger step is a gap in the forecast, wherever it falls.
    """
    if len(slots) < 2:
        raise ForecastError("a forecast needs at least two slots to show its slot length")
    step = min(b.start - a.start for a, b in pairwise(slots))
    if step <= timedelta(0):
        raise ForecastError("the forecast has two slots with the same start time")
    return step


def _slot_count(slots: list[Slot], duration: timedelta, step: timedelta) -> int:
    count, rest = divmod(duration, step)
    if rest or count < 1:
        raise ForecastError(f"a {duration} run is not a whole number of {step} slots")
    if count > len(slots):
        raise ForecastError(f"the forecast is shorter than the run ({duration})")
    return count


def _first_gap(slots: list[Slot], step: timedelta) -> tuple[datetime, datetime] | None:
    """The first pair of consecutive starts more than `step` apart, if any."""
    pairs = pairwise(slots)
    return next(((a.start, b.start) for a, b in pairs if b.start - a.start != step), None)


def _gap_message(gap: tuple[datetime, datetime]) -> str:
    before, after = gap
    return f"the forecast has a gap: no slot between {before:{TIME}} and {after:{TIME}}"


def _window(covered: list[Slot], duration: timedelta) -> Window:
    mean = sum(s.intensity for s in covered) / len(covered)
    return Window(covered[0].start, covered[0].start + duration, mean)


def window_at(slots: list[Slot], index: int, duration: timedelta) -> Window:
    """The window of `duration` that starts at slot `index`; it may not span a gap."""
    step = slot_length(slots)
    count = _slot_count(slots, duration, step)
    covered = slots[index : index + count]
    if len(covered) < count:
        raise ForecastError(f"the forecast ends before a {duration} run from slot {index}")
    gap = _first_gap(covered, step)
    if gap is not None:
        raise ForecastError(_gap_message(gap))
    return _window(covered, duration)


def best_window(slots: list[Slot], duration: timedelta) -> Window:
    """The gap-free window of `duration` with the lowest mean intensity; the earliest on a tie."""
    step = slot_length(slots)
    count = _slot_count(slots, duration, step)
    runs = (slots[i : i + count] for i in range(len(slots) - count + 1))
    windows = [_window(run, duration) for run in runs if _first_gap(run, step) is None]
    if not windows:
        # Every run spans a gap, so the forecast has at least one.
        gap = _first_gap(slots, step)
        raise ForecastError(f"no {duration} run fits between gaps; {_gap_message(gap)}")
    return min(windows, key=lambda w: w.mean_intensity)


def savings_grams(now: Window, best: Window, power_kw: float) -> float:
    """CO2 saved, in grams, by running at `best` instead of `now` at `power_kw`."""
    hours = (now.end - now.start) / timedelta(hours=1)
    return (now.mean_intensity - best.mean_intensity) * power_kw * hours
