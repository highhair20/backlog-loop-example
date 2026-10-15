from pathlib import Path

import pytest

from gridwindow.cli import MAX_HOURS, _amount, main

FORECAST = "start,intensity\n2026-10-09T00:00,300\n2026-10-09T01:00,100\n2026-10-09T02:00,100\n"


def assert_one_line_error(capsys, *fragments: str) -> None:
    assert_one_line_error_text(capsys.readouterr().err, *fragments)


def assert_one_line_error_text(err: str, *fragments: str) -> None:
    assert err.startswith("gridwindow: ")
    assert err.count("\n") == 1
    assert "Traceback" not in err
    for fragment in fragments:
        assert fragment in err


def test_prints_the_best_start_and_the_saving(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "2", "--power-kw", "1.5"]) == 0
    out = capsys.readouterr().out
    assert "Start at 2026-10-09 01:00" in out
    assert "100 gCO2/kWh" in out
    assert "Saves 300 g CO2" in out


def test_a_half_hourly_forecast_takes_a_one_and_a_half_hour_run(tmp_path, capsys):
    # Timestamps as GB's Carbon Intensity API writes them, with a Z offset.
    rows = zip(
        ["00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00"],
        [300, 280, 120, 90, 60, 250, 310],
        strict=True,
    )
    path = tmp_path / "f.csv"
    path.write_text("start,intensity\n" + "".join(f"2026-10-09T{t}Z,{v}\n" for t, v in rows))
    assert main([str(path), "--hours", "1.5", "--power-kw", "2"]) == 0
    out = capsys.readouterr().out
    assert "Start at 2026-10-09 01:00: 90 gCO2/kWh" in out
    assert "Saves 430 g CO2" in out


def test_a_bad_forecast_exits_1_with_a_message(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text("start,intensity\n")
    assert main([str(path), "--hours", "1"]) == 1
    assert "gridwindow: " in capsys.readouterr().err


def test_a_gap_that_leaves_no_window_exits_1_naming_it(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(
        "start,intensity\n"
        "2026-10-09T00:00,300\n2026-10-09T01:00,100\n"
        "2026-10-09T03:00,100\n2026-10-09T04:00,300\n"
    )
    assert main([str(path), "--hours", "3"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "gap: no slot between 2026-10-09 01:00 and 2026-10-09 03:00" in captured.err


def test_a_gap_in_the_starting_now_window_exits_1_naming_it(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(
        "start,intensity\n"
        "2026-10-09T00:00,300\n2026-10-09T02:00,100\n"
        "2026-10-09T03:00,100\n2026-10-09T04:00,300\n"
    )
    # 02:00-04:00 is a clean window, but "starting now" (00:00-02:00) spans the gap.
    assert main([str(path), "--hours", "2"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "gap: no slot between 2026-10-09 00:00 and 2026-10-09 02:00" in captured.err


def test_a_missing_file_exits_1_with_a_message(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv"), "--hours", "1"]) == 1
    assert "nope.csv" in capsys.readouterr().err


def test_rejects_a_non_positive_power(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "1", "--power-kw", "0"]) == 1
    assert "--power-kw" in capsys.readouterr().err


def test_rejects_a_non_positive_duration(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "-1"]) == 1
    assert "--hours" in capsys.readouterr().err


def test_a_deadline_limits_the_start_time(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "1", "--deadline", "2026-10-09T01:00"]) == 0
    assert "Start at 2026-10-09 00:00" in capsys.readouterr().out


def test_the_readme_deadline_example(capsys):
    root = Path(__file__).parent.parent
    flags = ["--hours", "2", "--deadline", "2026-10-09T07:00"]
    assert main([str(root / "examples" / "sample-day.csv"), *flags]) == 0
    example = f"$ gridwindow examples/sample-day.csv {' '.join(flags)}\n{capsys.readouterr().out}"
    assert example in (root / "README.md").read_text()


def test_a_deadline_with_no_fitting_window_exits_1(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "2", "--deadline", "2026-10-09T01:00"]) == 1
    assert_one_line_error(capsys, "ends by 2026-10-09T01:00")


def test_a_deadline_timezone_mismatch_exits_1(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "1", "--deadline", "2026-10-09T02:00+00:00"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("gridwindow: ")
    assert "timezone" in err
    assert err.count("\n") == 1


def test_a_malformed_deadline_is_a_usage_error(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    with pytest.raises(SystemExit) as exc:
        main([str(path), "--hours", "1", "--deadline", "tomorrow"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--deadline" in err
    assert "ISO 8601" in err
    assert "fromisoformat" not in err


# --- bad input: one line on stderr, exit 1, never a traceback ---


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        pytest.param(
            "2026-10-09T00:00,300\n2026-10-09T00:00,100\n2026-10-09T01:00,100\n",
            "f.csv:3",
            id="duplicate-first-start",
        ),
        pytest.param(
            "2026-10-09T00:00,300\n2026-10-09T01:00,100\n2026-10-09T02:00,100\n2026-10-09T01:00,50\n",
            "f.csv:5",
            id="duplicate-later-start",
        ),
        pytest.param("2026-10-09T00:00,nan\n2026-10-09T01:00,100\n", "f.csv:2", id="nan-intensity"),
        pytest.param("2026-10-09T00:00,300\n2026-10-09T01:00,inf\n", "f.csv:3", id="inf-intensity"),
        pytest.param(
            "2026-10-09T00:00,300\n2026-10-09T01:00+00:00,100\n", "f.csv:3", id="mixed-timezones"
        ),
    ],
)
def test_a_bad_row_exits_1_naming_its_line(tmp_path, capsys, body, fragment):
    path = tmp_path / "f.csv"
    path.write_text("start,intensity\n" + body)
    assert main([str(path), "--hours", "1"]) == 1
    assert_one_line_error(capsys, fragment)


def test_a_file_that_is_not_utf8_exits_1(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_bytes("start,intensity\n2026-10-09T00:00,200 µ\n".encode("latin-1"))
    assert main([str(path), "--hours", "1"]) == 1
    assert_one_line_error(capsys, "UTF-8")


def test_an_oversized_field_exits_1(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text("start,intensity\n2026-10-09T00:00," + "9" * 200_000 + "\n")
    assert main([str(path), "--hours", "1"]) == 1
    assert_one_line_error(capsys, "f.csv")


def test_a_byte_order_mark_is_read(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_bytes(b"\xef\xbb\xbf" + FORECAST.encode())
    assert main([str(path), "--hours", "2", "--power-kw", "1.5"]) == 0
    assert "Start at 2026-10-09 01:00" in capsys.readouterr().out


@pytest.mark.parametrize("hours", ["nan", "inf", "-inf", "1e12"])
def test_rejects_a_non_finite_or_too_large_duration(tmp_path, capsys, hours):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    # `--hours=` form: argparse would read a bare "-inf" as an option.
    assert main([str(path), f"--hours={hours}"]) == 1
    assert_one_line_error(capsys, "--hours")


def test_hours_at_the_limit_passes_the_flag_check(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), f"--hours={MAX_HOURS}"]) == 1
    assert_one_line_error(capsys, "shorter than the run")


def test_rejects_hours_just_over_the_limit(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), f"--hours={MAX_HOURS + 1}"]) == 1
    assert_one_line_error(capsys, "--hours is too large")


def test_rejects_hours_too_small_to_measure(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "1e-300"]) == 1
    assert_one_line_error(capsys, "--hours is too small")


@pytest.mark.parametrize("power", ["nan", "inf", "-inf"])
def test_rejects_a_non_finite_power(tmp_path, capsys, power):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "1", f"--power-kw={power}"]) == 1
    assert_one_line_error(capsys, "--power-kw")


# --- huge but finite values: a readable answer or one line, never inf ---


def test_a_saving_too_large_to_compute_exits_1(capsys):
    sample = Path(__file__).parent.parent / "examples" / "sample-day.csv"
    assert main([str(sample), "--hours", "2", "--power-kw", "1e308"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert_one_line_error_text(captured.err, "out of range")


def test_huge_means_print_in_a_readable_form(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(
        "start,intensity\n2026-10-09T00:00,1e308\n2026-10-09T01:00,1e308\n2026-10-09T02:00,1\n"
    )
    assert main([str(path), "--hours", "2"]) == 0
    out = capsys.readouterr().out
    assert out == (
        "Start at 2026-10-09 01:00: 5e+307 gCO2/kWh on average\n"
        "Saves 1e+308 g CO2 versus starting now (1e+308 gCO2/kWh)\n"
    )


def test_ordinary_values_still_print_as_whole_numbers(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    # (200 - 100) gCO2/kWh * 1e9 kW * 2 h = 2e11 g, below the readable-form threshold.
    assert main([str(path), "--hours", "2", "--power-kw", "1e9"]) == 0
    out = capsys.readouterr().out
    assert "Saves 200000000000 g CO2 versus starting now (200 gCO2/kWh)" in out


@pytest.mark.parametrize(
    ("power", "saving"),
    [("4.99e12", "Saves 998000000000000 g"), ("5e12", "Saves 1e+15 g")],
    ids=["just-under-1e15", "at-1e15"],
)
def test_the_readable_form_starts_at_1e15(tmp_path, capsys, power, saving):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    # (200 - 100) gCO2/kWh * power * 2 h
    assert main([str(path), "--hours", "2", "--power-kw", power]) == 0
    assert saving in capsys.readouterr().out


@pytest.mark.parametrize(
    ("value", "text"),
    [(999999999999999.4, "999999999999999"), (999999999999999.6, "1e+15")],
    ids=["rounds-down-below", "rounds-up-to-1e15"],
)
def test_a_value_that_rounds_up_to_1e15_takes_the_readable_form(value, text):
    assert _amount(value) == text
