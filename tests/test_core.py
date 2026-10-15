import math
import sys
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


HALF_HOURLY = [300, 280, 120, 90, 60, 250, 310]


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


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "NaN", "Infinity"])
def test_rejects_a_non_finite_intensity_with_its_line(tmp_path, value):
    path = write_csv(tmp_path, f"start,intensity\n2026-10-09T00:00,200\n2026-10-09T01:00,{value}\n")
    with pytest.raises(ForecastError, match=r"forecast\.csv:3: .*finite"):
        read_forecast(path)


def test_rejects_a_duplicate_first_start_with_its_line(tmp_path):
    path = write_csv(
        tmp_path,
        "start,intensity\n2026-10-09T00:00,300\n2026-10-09T00:00,100\n2026-10-09T01:00,100\n",
    )
    with pytest.raises(ForecastError, match=r"forecast\.csv:3: .*duplicate"):
        read_forecast(path)


def test_rejects_a_later_duplicate_start_with_its_line(tmp_path):
    path = write_csv(
        tmp_path,
        "start,intensity\n2026-10-09T00:00,300\n2026-10-09T01:00,100\n"
        "2026-10-09T02:00,100\n2026-10-09T01:00,50\n",
    )
    with pytest.raises(ForecastError, match=r"forecast\.csv:5: .*duplicate.*line 3"):
        read_forecast(path)


def test_rejects_the_same_instant_written_with_different_offsets(tmp_path):
    path = write_csv(
        tmp_path, "start,intensity\n2026-10-25T01:00+01:00,300\n2026-10-25T00:00+00:00,100\n"
    )
    with pytest.raises(ForecastError, match=r"forecast\.csv:3: .*line 2"):
        read_forecast(path)


def test_line_numbers_count_blank_lines(tmp_path):
    path = write_csv(tmp_path, "start,intensity\n2026-10-09T00:00,200\n\n\n2026-10-09T01:00,nan\n")
    with pytest.raises(ForecastError, match=r"forecast\.csv:5: "):
        read_forecast(path)


def test_rejects_mixed_timezones_with_the_line(tmp_path):
    path = write_csv(
        tmp_path, "start,intensity\n2026-10-09T00:00,300\n2026-10-09T01:00+00:00,100\n"
    )
    with pytest.raises(ForecastError, match=r"forecast\.csv:3: .*timezone"):
        read_forecast(path)


def test_rejects_a_row_without_a_timezone_after_rows_with_one(tmp_path):
    path = write_csv(
        tmp_path,
        "start,intensity\n2026-10-09T00:00+00:00,300\n2026-10-09T01:00+00:00,100\n"
        "2026-10-09T02:00,100\n",
    )
    with pytest.raises(ForecastError, match=r"forecast\.csv:4: .*earlier rows have a timezone"):
        read_forecast(path)


def test_accepts_rows_that_all_have_the_same_timezone(tmp_path):
    path = write_csv(
        tmp_path, "start,intensity\n2026-10-09T00:00+01:00,300\n2026-10-09T01:00+01:00,100\n"
    )
    assert [s.intensity for s in read_forecast(path)] == [300.0, 100.0]


def test_reads_a_file_with_a_utf8_byte_order_mark(tmp_path):
    path = tmp_path / "forecast.csv"
    path.write_bytes(b"\xef\xbb\xbfstart,intensity\n2026-10-09T00:00,200\n")
    assert read_forecast(path) == [Slot(datetime(2026, 10, 9, 0), 200.0)]


def test_reports_a_file_that_is_not_utf8(tmp_path):
    path = tmp_path / "forecast.csv"
    path.write_bytes("start,intensity\n2026-10-09T00:00,200 µ\n".encode("latin-1"))
    with pytest.raises(ForecastError, match=r"forecast\.csv: .*UTF-8"):
        read_forecast(path)


def test_reports_an_oversized_field(tmp_path):
    path = write_csv(tmp_path, "start,intensity\n2026-10-09T00:00," + "9" * 200_000 + "\n")
    with pytest.raises(ForecastError, match=r"forecast\.csv: .*field larger than field limit"):
        read_forecast(path)


def test_a_non_finite_intensity_message_stays_on_one_line(tmp_path):
    path = write_csv(tmp_path, 'start,intensity\n2026-10-09T00:00,"nan\n"\n')
    with pytest.raises(ForecastError) as caught:
        read_forecast(path)
    assert "\n" not in str(caught.value)


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


def test_finds_a_one_and_a_half_hour_window_in_half_hour_slots():
    forecast = slots("2026-10-09T00:00", 30, HALF_HOURLY)
    best = best_window(forecast, timedelta(hours=1.5))
    assert best.start == datetime(2026, 10, 9, 1)
    assert best.end == datetime(2026, 10, 9, 2, 30)
    assert best.mean_intensity == pytest.approx(90)  # (120 + 90 + 60) / 3


def test_rejects_a_run_that_is_not_whole_half_hour_slots():
    forecast = slots("2026-10-09T00:00", 30, HALF_HOURLY)
    with pytest.raises(ForecastError, match="whole number"):
        best_window(forecast, timedelta(minutes=45))


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


def test_savings_in_half_hour_slots_use_hours_not_slot_count():
    forecast = slots("2026-10-09T00:00", 30, HALF_HOURLY)
    duration = timedelta(hours=1.5)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    # now: mean 233.3; best: mean 90; 1.5 h (3 slots) at 2 kW = 3 kWh -> 430 g saved.
    # Counting slots as hours would give 860 g.
    assert savings_grams(now, best, power_kw=2) == pytest.approx(430)


# --- huge but finite values ---

# The issue's case 2: two values near the float limit, then an ordinary one.
HUGE = [1e308, 1e308, 1]


def test_a_mean_of_huge_values_does_not_overflow():
    forecast = slots("2026-10-09T00:00", 60, HUGE)
    duration = timedelta(hours=2)
    # Summing first would give 1e308 + 1e308 = inf.
    assert window_at(forecast, 0, duration).mean_intensity == pytest.approx(1e308)
    best = best_window(forecast, duration)
    assert best.start == datetime(2026, 10, 9, 1)
    assert best.mean_intensity == pytest.approx(5e307)


def test_the_saving_between_huge_means_is_finite():
    forecast = slots("2026-10-09T00:00", 60, HUGE)
    duration = timedelta(hours=2)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    assert savings_grams(now, best, power_kw=1) == pytest.approx(1e308)


def test_a_mean_at_the_float_limit_is_still_answered():
    biggest = sys.float_info.max
    forecast = slots("2026-10-09T00:00", 60, [biggest] * 3)
    assert best_window(forecast, timedelta(hours=3)).mean_intensity == pytest.approx(biggest)


@pytest.mark.parametrize(
    "intensities",
    [[math.inf, 100], [math.nan, 100], [math.inf, -math.inf]],
    ids=["inf", "nan", "inf-and-minus-inf"],
)
def test_a_non_finite_intensity_in_hand_built_slots_is_named(intensities):
    # read_forecast rejects these, so only a caller building Slots by hand can pass them.
    forecast = slots("2026-10-09T00:00", 60, intensities)
    with pytest.raises(ForecastError, match="slot at 2026-10-09 00:00 has a non-finite"):
        best_window(forecast, timedelta(hours=2))


def test_equal_means_tie_exactly_when_the_sum_overflows():
    q = 2.0**1020  # the float limit is just under 16q
    # 00:00 [4q, 14q, 12q] and 03:00 [10q, 10q, 10q] both average 10q; both sums overflow.
    forecast = slots("2026-10-09T00:00", 60, [4 * q, 14 * q, 12 * q, 10 * q, 10 * q, 10 * q])
    best = best_window(forecast, timedelta(hours=3))
    assert best.start == datetime(2026, 10, 9, 0)
    assert best.mean_intensity == 10 * q


def test_a_saving_is_answered_when_only_a_partial_product_overflows():
    forecast = slots("2026-10-09T00:00", 30, [1.5e308, 0, 0])
    duration = timedelta(minutes=30)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    # 1.5e308 * 2 kW overflows, but * 0.5 h brings the saving back to 1.5e308.
    assert savings_grams(now, best, power_kw=2) == pytest.approx(1.5e308)


def test_a_saving_that_overflows_raises():
    forecast = slots("2026-10-09T00:00", 60, [300, 100, 100])
    duration = timedelta(hours=2)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    # (200 - 100) gCO2/kWh * 1e308 kW * 2 h is past the float limit.
    with pytest.raises(ForecastError, match="out of range: the CO2 saving") as caught:
        savings_grams(now, best, power_kw=1e308)
    # The message names every factor, not only the power.
    assert "(100 gCO2/kWh at 1e+308 kW for 2 h)" in str(caught.value)


def test_a_saving_from_huge_intensities_at_ordinary_power_raises():
    forecast = slots("2026-10-09T00:00", 60, [1.7e308, 1.7e308, 0, 0])
    duration = timedelta(hours=2)
    now = window_at(forecast, 0, duration)
    best = best_window(forecast, duration)
    with pytest.raises(ForecastError, match=r"\(1\.7e\+308 gCO2/kWh at 1 kW for 2 h\)"):
        savings_grams(now, best, power_kw=1)


def test_windows_with_equal_means_still_tie_exactly():
    # 00:00 [1, 1, 4] and 03:00 [2, 2, 2] both average 2; dividing each value by 3 before
    # summing could round them apart and pick 03:00.
    forecast = slots("2026-10-09T00:00", 60, [1, 1, 4, 2, 2, 2])
    best = best_window(forecast, timedelta(hours=3))
    assert best.start == datetime(2026, 10, 9, 0)
    assert best.mean_intensity == 2


def test_ordinary_means_are_unchanged():
    forecast = slots("2026-10-09T00:00", 60, [100, 200, 300, 0, 0, 600])
    best = best_window(forecast, timedelta(hours=3))
    # 3 h windows from 00:00, 01:00, 02:00, 03:00 average 200, 166.7, 100, 200.
    assert best.start == datetime(2026, 10, 9, 2)
    assert best.mean_intensity == pytest.approx(100)
