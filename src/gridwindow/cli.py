"""Command line: gridwindow <forecast.csv> --hours H [--power-kw P]."""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from gridwindow.core import ForecastError, best_window, read_forecast, savings_grams, window_at


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gridwindow",
        description="Find the cleanest time to run an appliance from a carbon-intensity forecast.",
    )
    p.add_argument("forecast", type=Path, help="CSV with start (ISO 8601) and intensity columns")
    p.add_argument("--hours", type=float, required=True, help="how long the appliance runs")
    p.add_argument("--power-kw", type=float, default=1.0, help="its average draw (default 1 kW)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.hours <= 0:
        return _fail("--hours must be more than 0")
    if args.power_kw <= 0:
        return _fail("--power-kw must be more than 0")
    duration = timedelta(hours=args.hours)
    try:
        slots = read_forecast(args.forecast)
        best = best_window(slots, duration)
        now = window_at(slots, 0, duration)
    except (ForecastError, OSError) as e:
        return _fail(str(e))
    saved = savings_grams(now, best, args.power_kw)
    print(f"Start at {best.start:%Y-%m-%d %H:%M}: {best.mean_intensity:.0f} gCO2/kWh on average")
    print(f"Saves {saved:.0f} g CO2 versus starting now ({now.mean_intensity:.0f} gCO2/kWh)")
    return 0


def _fail(message: str) -> int:
    print(f"gridwindow: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
