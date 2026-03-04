# CLAUDE.md

## Project Overview

Baseball Lineup Cards is a Python CLI tool that generates formatted lineup cards
for MLB games using real-time data from the MLB Stats API and Statcast (Baseball
Savant). It outputs 80-character-wide ASCII cards or structured JSON.

## Architecture

Three-layer separation of concerns:

- **`lineup_data.py`** — Data layer. Fetches from MLB Stats API and Statcast,
  returns JSON-serializable dicts.
- **`lineup_formatter.py`** — Presentation layer. Converts structured data into
  80-char ASCII lineup cards.
- **`lineup_html.py`** — Presentation layer. Converts structured data into a
  self-contained HTML file with sortable tables.
- **`team_lineup.py`** — CLI entry point. Argument parsing and output routing.
- **`pitch_workload.py`** — Standalone module for bullpen 3-day pitch workload.

## Commands

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the tool

```bash
# Print lineup cards for both teams to terminal
python team_lineup.py NYM 2024-06-15

# Save to auto-named text files
python team_lineup.py NYM 2024-06-15 -o

# Save with custom filename prefix
python team_lineup.py NYM 2024-06-15 -o my_cards

# Output as JSON
python team_lineup.py NYM 2024-06-15 --json

# Generate HTML file with sortable tables
python team_lineup.py NYM 2024-06-15 --html

# Serve HTML on local network (opens on phone via Wi-Fi)
python team_lineup.py NYM 2024-06-15 --html --serve

# Check a single pitcher's recent workload
python pitch_workload.py 663432 2024-07-01
```

### Run tests

```bash
# Smoke test: verifies pybaseball/Statcast connectivity
python test_savant.py
```

## External Dependencies

- **MLB Stats API** (`statsapi.mlb.com`) — game schedules, rosters, boxscores
- **Statcast / Baseball Savant** (via `pybaseball`) — pitch-level data, xwOBA,
  batted ball classifications
- Requires live network access; no local caching

## Code Style

- Python 3.8+; no type hints enforced
- Snake_case throughout; private helpers prefixed with `_`
- No linting config — follow the existing style in each module
- Keep output width at 80 characters for lineup card formatting
- Return JSON-serializable values from `lineup_data.py` (no datetime objects,
  use `None` instead of `NaN`)

## Development Workflow

- Always update `README.md` to reflect any changes before committing — keep
  usage examples, architecture descriptions, and output formats in sync with
  the code.
- Update `CLAUDE.md` if changes affect architecture, commands, dependencies,
  code style, or other development guidance documented here.

## Key Notes

- Spring training games automatically fall back to previous-season stats
- Valid team abbreviations: AZ, ATL, BAL, BOS, CHC, CWS, CIN, CLE, COL, DET,
  HOU, KC, LAA, LAD, MIA, MIL, MIN, NYM, NYY, OAK, PHI, PIT, SD, SEA, SF,
  STL, TB, TEX, TOR, WSH
- Date format: `YYYY-MM-DD`
- pybaseball prints progress to stdout; `_quiet_stdout()` suppresses this in
  JSON mode
