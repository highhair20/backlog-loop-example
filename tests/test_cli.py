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
