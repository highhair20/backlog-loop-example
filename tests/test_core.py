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
