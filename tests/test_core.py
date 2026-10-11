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


# --- best_window with a deadline ---

DEADLINE_FORECAST = [300, 100, 120, 400, 90]  # hourly from 00:00; best 2 h is 01:00-03:00


def test_a_deadline_moves_the_answer_to_an_earlier_window():
    forecast = slots("2026-10-09T00:00", 60, DEADLINE_FORECAST)
    best = best_window(forecast, timedelta(hours=1), deadline=datetime(2026, 10, 9, 3))
    # Without the deadline the 04:00 slot (90) wins; it ends at 05:00, too late.
    assert best.start == datetime(2026, 10, 9, 1)
    assert best.mean_intensity == pytest.approx(100)


def test_a_window_ending_exactly_at_the_deadline_counts():
    forecast = slots("2026-10-09T00:00", 60, DEADLINE_FORECAST)
    best = best_window(forecast, timedelta(hours=2), deadline=datetime(2026, 10, 9, 3))
    assert best.start == datetime(2026, 10, 9, 1)
    assert best.end == datetime(2026, 10, 9, 3)


def test_a_deadline_that_leaves_no_window_is_an_error():
    forecast = slots("2026-10-09T00:00", 60, DEADLINE_FORECAST)
    with pytest.raises(ForecastError, match="ends by"):
        best_window(forecast, timedelta(hours=2), deadline=datetime(2026, 10, 9, 1, 30))


def test_a_deadline_after_the_forecast_changes_nothing():
    forecast = slots("2026-10-09T00:00", 60, DEADLINE_FORECAST)
    duration = timedelta(hours=1)
    late = best_window(forecast, duration, deadline=datetime(2026, 10, 10))
    assert late == best_window(forecast, duration)


def test_an_aware_deadline_compares_across_offsets():
    forecast = slots("2026-10-09T00:00+00:00", 60, DEADLINE_FORECAST)
    # 04:00+01:00 is 03:00 UTC: same answer as the naive 03:00 case above.
    deadline = datetime.fromisoformat("2026-10-09T04:00+01:00")
    best = best_window(forecast, timedelta(hours=1), deadline=deadline)
    assert best.start == datetime.fromisoformat("2026-10-09T01:00+00:00")


@pytest.mark.parametrize(
    ("forecast_start", "deadline"),
    [
        ("2026-10-09T00:00", "2026-10-09T03:00+00:00"),
        ("2026-10-09T00:00+00:00", "2026-10-09T03:00"),
    ],
    ids=["aware-deadline-naive-forecast", "naive-deadline-aware-forecast"],
)
def test_a_deadline_and_forecast_must_agree_on_timezones(forecast_start, deadline):
    forecast = slots(forecast_start, 60, DEADLINE_FORECAST)
    with pytest.raises(ForecastError, match="timezone"):
        best_window(forecast, timedelta(hours=1), deadline=datetime.fromisoformat(deadline))


# --- gaps ---


def gappy(intensities: dict[str, float]) -> list[Slot]:
    return [Slot(datetime.fromisoformat(t), v) for t, v in intensities.items()]


# The issue's repro: 02:00 is missing.
GAP_AT_2AM = {
    "2026-10-09T00:00": 300,
    "2026-10-09T01:00": 100,
    "2026-10-09T03:00": 100,
    "2026-10-09T04:00": 300,
}
GAP_AT_2AM_MESSAGE = "gap: no slot between 2026-10-09 01:00 and 2026-10-09 03:00"


def test_best_window_avoids_a_gap():
    best = best_window(gappy(GAP_AT_2AM), timedelta(hours=2))
    # 01:00-03:00 (mean 100) spans the gap; 00:00 and 03:00 tie at 200, earliest wins.
    assert best.start == datetime(2026, 10, 9, 0)
    assert best.end == datetime(2026, 10, 9, 2)
    assert best.mean_intensity == pytest.approx(200)


def test_best_window_names_the_gap_when_no_window_fits():
    with pytest.raises(ForecastError, match=GAP_AT_2AM_MESSAGE):
        best_window(gappy(GAP_AT_2AM), timedelta(hours=3))


def test_a_deadline_still_avoids_a_gap():
    best = best_window(gappy(GAP_AT_2AM), timedelta(hours=2), deadline=datetime(2026, 10, 9, 3))
    # 01:00-03:00 (mean 100) ends by the deadline but spans the gap; 00:00-02:00 is left.
    assert best.start == datetime(2026, 10, 9, 0)
    assert best.mean_intensity == pytest.approx(200)


def test_a_window_across_a_gap_does_not_meet_a_deadline():
    forecast = gappy(
        {
            "2026-10-09T00:00": 100,
            "2026-10-09T02:00": 100,
            "2026-10-09T03:00": 100,
            "2026-10-09T04:00": 100,
        }
    )
    # 00:00-02:00 ends by 03:00 but spans the gap; every gap-free run ends later.
    with pytest.raises(ForecastError, match="ends by"):
        best_window(forecast, timedelta(hours=2), deadline=datetime(2026, 10, 9, 3))


def test_a_timezone_mismatch_is_reported_before_a_gap():
    deadline = datetime.fromisoformat("2026-10-09T03:00+00:00")
    with pytest.raises(ForecastError, match="timezone"):
        best_window(gappy(GAP_AT_2AM), timedelta(hours=3), deadline=deadline)


def test_window_at_refuses_a_window_across_a_gap():
    with pytest.raises(ForecastError, match=GAP_AT_2AM_MESSAGE):
        window_at(gappy(GAP_AT_2AM), 1, timedelta(hours=2))


def test_window_at_accepts_a_window_beside_a_gap():
    now = window_at(gappy(GAP_AT_2AM), 0, timedelta(hours=2))
    assert now.mean_intensity == pytest.approx(200)


def test_a_gap_between_the_first_two_slots_is_still_a_gap():
    forecast = gappy(
        {
            "2026-10-09T00:00": 100,
            "2026-10-09T02:00": 300,
            "2026-10-09T03:00": 300,
            "2026-10-09T04:00": 300,
        }
    )
    best = best_window(forecast, timedelta(hours=2))
    # Slots are 1 h (the smallest step), so 00:00 is a single 1 h slot, not a 2 h run.
    assert best.start == datetime(2026, 10, 9, 2)
    assert best.end == datetime(2026, 10, 9, 4)
    assert best.mean_intensity == pytest.approx(300)


def test_rejects_two_slots_with_the_same_start():
    forecast = gappy({"2026-10-09T00:00": 100, "2026-10-09T01:00": 100})
    duplicate = [*forecast, Slot(datetime(2026, 10, 9, 1), 200)]
    with pytest.raises(ForecastError, match="same start time"):
        best_window(duplicate, timedelta(hours=1))


# --- savings ---


def test_savings_compare_with_starting_now():
    forecast = slots("2026-10-09T00:00", 60, [300, 100, 100])
    duration = timedelta(hours=2)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    # now: mean 200; best: mean 100; 2 h at 1.5 kW = 3 kWh -> 300 g saved
    assert savings_grams(now, best, power_kw=1.5) == pytest.approx(300)
