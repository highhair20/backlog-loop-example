# gridwindow

**A worked example of [backlog-loop](https://github.com/highhair20/backlog-loop).**
Its issues were worked by Claude Code's backlog loop, and every PR was merged by a
person. Read the [closed issues](https://github.com/highhair20/backlog-loop-example/issues?q=is%3Aissue+is%3Aclosed)
and their PRs to see what the loop does: the premise and scope checks in each PR
body, the review comments, the labels, and the proposal gate.

## What the code does

`gridwindow` finds the cleanest time to run an appliance (a dishwasher, an EV
charge) from a forecast of the grid's carbon intensity, and says how much CO2 that
saves against starting now.

```console
$ gridwindow examples/sample-day.csv --hours 2 --power-kw 2
Start at 2026-10-09 13:00: 120 gCO2/kWh on average
Saves 340 g CO2 versus starting now (205 gCO2/kWh)
```

A forecast is a CSV with a `start` column (ISO 8601) and an `intensity` column
(gCO2/kWh), one row per slot. Slots are all the same length; it takes the length from
the first two rows. The sample in `examples/` uses made-up values. Real forecasts come
from grid operators, for example the [Carbon Intensity API](https://carbonintensity.org.uk/)
for Great Britain.

## Run it

```sh
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'
.venv/bin/gridwindow examples/sample-day.csv --hours 3
.venv/bin/pytest
```

## How this repo was made

1. Created with "Use this template" from backlog-loop, then `scripts/setup.sh --fix`.
2. The first version of `gridwindow` (PR #1) was written in an interactive Claude
   Code session, not by the loop, and turned the proposal gate on. It left gaps on
   purpose, so the loop would have real bugs to find.
3. Issues were filed with `/file-issue`, and the loop worked each one with
   `scripts/backlog-loop.sh`. A person reviewed and merged every PR.

The proposal gate is on because this repo is public: an issue from anyone becomes a
proposal for the maintainer to approve, never code. See backlog-loop's
[Security](https://github.com/highhair20/backlog-loop#security) section.

The `scripts/`, `.claude/` and `docs/` directories are backlog-loop's own files,
which every repo made from the template gets.

## License

MIT, see [LICENSE](LICENSE).
