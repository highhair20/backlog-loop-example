from datetime import datetime, timedelta

import pytest

from gridwindow.core import (
    ForecastError,
    Slot,
    best_window,
    read_forecast,
    savings_grams,
    window_at,
)


def slots(start: str, step_minutes: int, intensities: list[float]) -> list[Slot]:
    t0 = datetime.fromisoformat(start)
    step = timedelta(minutes=step_minutes)
    return [Slot(t0 + i * step, v) for i, v in enumerate(intensities)]


def write_csv(tmp_path, text: str):
    path = tmp_path / "forecast.csv"
    path.write_text(text)
    return path


# --- read_forecast ---


def test_reads_rows_sorted_by_start(tmp_path):
    path = write_csv(tmp_path, "start,intensity\n2026-10-09T01:00,150\n2026-10-09T00:00,200\n")
    assert read_forecast(path) == [
        Slot(datetime(2026, 10, 9, 0), 200.0),
        Slot(datetime(2026, 10, 9, 1), 150.0),
    ]


def test_rejects_missing_columns(tmp_path):
    path = write_csv(tmp_path, "time,value\n2026-10-09T00:00,200\n")
    with pytest.raises(ForecastError, match="'start' and 'intensity'"):
        read_forecast(path)


def test_names_the_line_of_a_bad_row(tmp_path):
    path = write_csv(tmp_path, "start,intensity\n2026-10-09T00:00,200\n2026-10-09T01:00,lots\n")
    with pytest.raises(ForecastError, match=r"forecast\.csv:3"):
        read_forecast(path)


def test_rejects_an_empty_forecast(tmp_path):
    path = write_csv(tmp_path, "start,intensity\n")
    with pytest.raises(ForecastError, match="no rows"):
        read_forecast(path)


def test_rejects_a_negative_intensity(tmp_path):
    path = write_csv(tmp_path, "start,intensity\n2026-10-09T00:00,-5\n")
    with pytest.raises(ForecastError, match="negative"):
        read_forecast(path)


# --- best_window ---


def test_picks_the_lowest_mean_window():
    forecast = slots("2026-10-09T00:00", 60, [300, 100, 120, 400, 90])
    best = best_window(forecast, timedelta(hours=2))
    assert best.start == datetime(2026, 10, 9, 1)
    assert best.end == datetime(2026, 10, 9, 3)
    assert best.mean_intensity == pytest.approx(110)


def test_prefers_the_earliest_of_equal_windows():
    forecast = slots("2026-10-09T00:00", 60, [100, 100, 100])
    assert best_window(forecast, timedelta(hours=1)).start == datetime(2026, 10, 9, 0)


def test_infers_half_hour_slots():
    forecast = slots("2026-10-09T00:00", 30, [300, 50, 60, 400])
    best = best_window(forecast, timedelta(hours=1))
    assert best.start == datetime(2026, 10, 9, 0, 30)
    assert best.mean_intensity == pytest.approx(55)


def test_rejects_a_duration_that_is_not_whole_slots():
    forecast = slots("2026-10-09T00:00", 60, [100, 200, 300])
    with pytest.raises(ForecastError, match="whole number"):
        best_window(forecast, timedelta(minutes=90))


def test_rejects_a_run_longer_than_the_forecast():
    forecast = slots("2026-10-09T00:00", 60, [100, 200])
    with pytest.raises(ForecastError, match="shorter than the run"):
        best_window(forecast, timedelta(hours=3))


def test_needs_two_slots_to_know_the_slot_length():
    with pytest.raises(ForecastError, match="at least two"):
        best_window(slots("2026-10-09T00:00", 60, [100]), timedelta(hours=1))


# --- savings ---


def test_savings_compare_with_starting_now():
    forecast = slots("2026-10-09T00:00", 60, [300, 100, 100])
    duration = timedelta(hours=2)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    # now: mean 200; best: mean 100; 2 h at 1.5 kW = 3 kWh -> 300 g saved
    assert savings_grams(now, best, power_kw=1.5) == pytest.approx(300)
