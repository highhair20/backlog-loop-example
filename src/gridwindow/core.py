"""Find the cleanest time to run an appliance from a grid carbon-intensity forecast.

A forecast is a list of equal-length slots, each with the grid's expected carbon
intensity in gCO2/kWh. A run of a given duration covers consecutive slots; the best
window is the one with the lowest mean intensity.
"""

from __future__ import annotations

import csv
import math
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
    """Read a UTF-8 CSV with `start` (ISO 8601) and `intensity` (gCO2/kWh) columns.

    Start times must be unique, and either all carry a timezone or none do.
    """
    numbered = _read_rows(path)
    if not numbered:
        raise ForecastError(f"{path}: no rows")
    _check_timezones(path, numbered)
    ordered = sorted(numbered, key=lambda pair: pair[1].start)
    _check_duplicates(path, ordered)
    return [slot for _, slot in ordered]


def _read_rows(path: Path) -> list[tuple[int, Slot]]:
    """Each row's slot, paired with its line number in the file."""
    # utf-8-sig also reads a file saved with a byte-order mark, as Excel does.
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not set(COLUMNS) <= set(reader.fieldnames or ()):
                raise ForecastError(f"{path}: needs 'start' and 'intensity' columns")
            # line_num, not a row count: DictReader skips blank lines. Read after each row
            # is fetched, it is the row's last line (its only line unless a quoted field
            # spans lines).
            return [(reader.line_num, _parse_row(path, reader.line_num, row)) for row in reader]
    except UnicodeDecodeError as e:
        # e.start counts from the decoder's current chunk, not the file, so it is left out.
        raise ForecastError(f"{path}: not UTF-8 text ({e.reason})") from e
    except csv.Error as e:
        raise ForecastError(f"{path}: {e}") from e


def _parse_row(path: Path, line: int, row: dict[str, str]) -> Slot:
    try:
        slot = Slot(datetime.fromisoformat(row["start"]), float(row["intensity"]))
    except (TypeError, ValueError) as e:
        raise ForecastError(f"{path}:{line}: {e}") from e
    if not math.isfinite(slot.intensity):
        raise ForecastError(
            f"{path}:{line}: intensity must be a finite number, not {row['intensity']!r}"
        )
    if slot.intensity < 0:
        raise ForecastError(f"{path}:{line}: negative intensity {slot.intensity}")
    return slot


def _check_timezones(path: Path, numbered: list[tuple[int, Slot]]) -> None:
    """Start times with and without a timezone cannot be compared, so reject a mix."""
    first_is_aware = _is_aware(numbered[0][1].start)
    for line, slot in numbered:
        if _is_aware(slot.start) != first_is_aware:
            earlier = "a timezone" if first_is_aware else "no timezone"
            raise ForecastError(f"{path}:{line}: mixed timezones; earlier rows have {earlier}")


def _is_aware(moment: datetime) -> bool:
    return moment.utcoffset() is not None


def _check_duplicates(path: Path, ordered: list[tuple[int, Slot]]) -> None:
    """Reject a repeated start; the sort is stable, so the later line is the one named."""
    for (first_line, previous), (line, slot) in pairwise(ordered):
        if slot.start == previous.start:
            raise ForecastError(
                f"{path}:{line}: duplicate start {slot.start.isoformat()}, "
                f"the same time as line {first_line}"
            )


def slot_length(slots: list[Slot]) -> timedelta:
    """The forecast's slot length: the smallest step between consecutive slots.

    Any larger step is a gap in the forecast, wherever it falls. A forecast whose
    every step is equally wide (e.g. 00:00, 02:00, 04:00) reads as 2 h slots: with
    no other information, a missing slot there cannot be told from a longer one.
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
    return Window(covered[0].start, covered[0].start + duration, _mean(covered))


def _mean(covered: list[Slot]) -> float:
    """The mean intensity, which never overflows when every intensity is finite."""
    values = [s.intensity for s in covered]
    try:
        mean = _summed_mean(values)
    except ValueError:  # fsum of inf and -inf; only Slots built by hand can hold them
        mean = math.nan
    if not math.isfinite(mean):
        raise ForecastError(
            f"the result is out of range: the mean intensity from "
            f"{covered[0].start:{TIME}} is not a finite number"
        )
    return mean


def _summed_mean(values: list[float]) -> float:
    """Sum, then divide: exact for whole-number data, so equal means tie exactly.

    fsum is correctly rounded, so the result does not depend on the slots' order.
    """
    try:
        total = math.fsum(values)
    except OverflowError:  # finite values whose sum passes the float limit
        return _scaled_mean(values)
    return total / len(values)


def _scaled_mean(values: list[float]) -> float:
    """The mean of values whose sum overflows: divide each by 2n, sum, then double back.

    Halving is exact, so the sum keeps headroom even when rounding pushes it up (three
    of max/3 sum past the float limit). The true mean is never above the largest value,
    so doubling back is capped there.
    """
    n = len(values)
    return min(2 * math.fsum(v / (2 * n) for v in values), max(values))


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


def best_window(slots: list[Slot], duration: timedelta, deadline: datetime | None = None) -> Window:
    """The gap-free window of `duration` with the lowest mean intensity; the earliest on a tie.

    With a `deadline`, only windows that end at or before it are considered.
    """
    if deadline is not None:
        _check_same_timezone_kind(slots, deadline)
    step = slot_length(slots)
    count = _slot_count(slots, duration, step)
    runs = (slots[i : i + count] for i in range(len(slots) - count + 1))
    windows = [_window(run, duration) for run in runs if _first_gap(run, step) is None]
    if not windows:
        # Every run spans a gap, so the forecast has at least one.
        gap = _first_gap(slots, step)
        detail = _gap_message(gap) if gap is not None else "the forecast has a gap"
        raise ForecastError(f"no {duration} run fits between gaps; {detail}")
    if deadline is not None:
        windows = [w for w in windows if w.end <= deadline]
        if not windows:
            raise ForecastError(f"no {duration} run ends by {deadline.isoformat()}")
    return min(windows, key=lambda w: w.mean_intensity)


def _check_same_timezone_kind(slots: list[Slot], deadline: datetime) -> None:
    # Python cannot compare a naive datetime with an aware one; say so plainly.
    forecast_has_tz = slots[0].start.tzinfo is not None
    deadline_has_tz = deadline.tzinfo is not None
    if forecast_has_tz != deadline_has_tz:
        has, lacks = ("deadline", "forecast") if deadline_has_tz else ("forecast", "deadline")
        raise ForecastError(f"the {has} has a timezone but the {lacks} does not")


def savings_grams(now: Window, best: Window, power_kw: float) -> float:
    """CO2 saved, in grams, by running at `best` instead of `now` at `power_kw`."""
    hours = (now.end - now.start) / timedelta(hours=1)
    saved = (now.mean_intensity - best.mean_intensity) * power_kw * hours
    if not math.isfinite(saved):
        raise ForecastError(
            f"the result is out of range: the CO2 saving at {power_kw:g} kW is too large"
        )
    return saved
