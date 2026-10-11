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
