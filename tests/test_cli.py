from pathlib import Path

import pytest

from gridwindow.cli import main

FORECAST = "start,intensity\n2026-10-09T00:00,300\n2026-10-09T01:00,100\n2026-10-09T02:00,100\n"


def test_prints_the_best_start_and_the_saving(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text(FORECAST)
    assert main([str(path), "--hours", "2", "--power-kw", "1.5"]) == 0
    out = capsys.readouterr().out
    assert "Start at 2026-10-09 01:00" in out
    assert "100 gCO2/kWh" in out
    assert "Saves 300 g CO2" in out


def test_a_bad_forecast_exits_1_with_a_message(tmp_path, capsys):
    path = tmp_path / "f.csv"
    path.write_text("start,intensity\n")
    assert main([str(path), "--hours", "1"]) == 1
    assert "gridwindow: " in capsys.readouterr().err


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
    err = capsys.readouterr().err
    assert err.startswith("gridwindow: ")
    assert err.count("\n") == 1


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
    assert "--deadline" in capsys.readouterr().err
