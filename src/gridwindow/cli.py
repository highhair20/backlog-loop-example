"""Command line: gridwindow <forecast.csv> --hours H [--power-kw P] [--deadline T]."""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

from gridwindow.core import ForecastError, best_window, read_forecast, savings_grams, window_at

# The longest run a timedelta can hold, in whole hours (about 2.4e10).
MAX_HOURS = timedelta.max // timedelta(hours=1)
# Above about 1e15 a float no longer holds every whole-number digit, so print 4 significant
# figures instead of a long run of meaningless ones.
LARGE = 1e15


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gridwindow",
        description="Find the cleanest time to run an appliance from a carbon-intensity forecast.",
    )
    p.add_argument("forecast", type=Path, help="CSV with start (ISO 8601) and intensity columns")
    p.add_argument("--hours", type=float, required=True, help="how long the appliance runs")
    p.add_argument("--power-kw", type=float, default=1.0, help="its average draw (default 1 kW)")
    p.add_argument(
        "--deadline",
        type=_iso_time,
        help="ISO 8601 time the run must finish by; a date alone means 00:00 "
        "(default: the end of the forecast)",
    )
    return p


def _iso_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"expected an ISO 8601 time such as 2026-10-09T07:00, got {value!r}"
        ) from e


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not math.isfinite(args.hours):
        return _fail("--hours must be a finite number")
    if args.hours <= 0:
        return _fail("--hours must be more than 0")
    if args.hours > MAX_HOURS:
        return _fail(f"--hours is too large (at most {MAX_HOURS})")
    if not math.isfinite(args.power_kw):
        return _fail("--power-kw must be a finite number")
    if args.power_kw <= 0:
        return _fail("--power-kw must be more than 0")
    duration = timedelta(hours=args.hours)
    if not duration:
        return _fail("--hours is too small (rounds to no time at all)")
    try:
        slots = read_forecast(args.forecast)
        best = best_window(slots, duration, args.deadline)
        now = window_at(slots, 0, duration)
        saved = savings_grams(now, best, args.power_kw)
    except (ForecastError, OSError) as e:
        return _fail(str(e))
    best_mean, now_mean = _amount(best.mean_intensity), _amount(now.mean_intensity)
    print(f"Start at {best.start:%Y-%m-%d %H:%M}: {best_mean} gCO2/kWh on average")
    print(f"Saves {_amount(saved)} g CO2 versus starting now ({now_mean} gCO2/kWh)")
    return 0


def _amount(value: float) -> str:
    """A whole number, or 4 significant figures once whole-number digits would be noise."""
    return f"{value:.4g}" if abs(value) >= LARGE else f"{value:.0f}"


def _fail(message: str) -> int:
    print(f"gridwindow: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
