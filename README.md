# Baseball Lineup Cards

Generate detailed lineup cards for any MLB game using data from the MLB Stats API and Statcast (Baseball Savant). Each card includes batting orders, bench players, pitching staffs, xwOBA-based performance stats, and a bullpen pitch log showing recent workload.

Works for regular season and spring training games. During spring training, players display their stats from the previous season.

## Requirements

- Python 3.8+
- [pybaseball](https://github.com/jldbc/pybaseball)

```
pip install -r requirements.txt
```

## Usage

### Generate lineup cards

```bash
# Print lineup cards for both teams to the terminal
python team_lineup.py NYM 2024-06-15

# Save to text files (auto-named: SD_2024-06-15_lineup.txt, NYM_2024-06-15_lineup.txt)
python team_lineup.py NYM 2024-06-15 -o

# Save with a custom prefix (creates prefix_SD.txt, prefix_NYM.txt)
python team_lineup.py NYM 2024-06-15 -o my_cards
```

### HTML output (sortable tables)

Use `--html` to generate a self-contained HTML file with sortable columns:

```bash
# Auto-named file (e.g. SD_NYM_2024-06-15_lineup.html)
python team_lineup.py NYM 2024-06-15 --html

# Custom filename
python team_lineup.py NYM 2024-06-15 --html my_cards.html
```

Open the resulting `.html` file in any browser. Click any column header to sort ascending; click again to sort descending. The file is fully self-contained (inline CSS and JavaScript) with no external dependencies.

Can be combined with other flags:

```bash
# Save both .txt files and .html file
python team_lineup.py NYM 2024-06-15 -o --html
```

### Serve HTML on your local network

Add `--serve` to start a local web server after generating the HTML file. This lets you open the lineup card on your phone (or any device on the same Wi-Fi):

```bash
# Serve on default port 8000
python team_lineup.py NYM 2024-06-15 --html --serve

# Serve on a custom port
python team_lineup.py NYM 2024-06-15 --html --serve 9090
```

Open the printed URL in Safari on your iPhone (or any mobile browser). Sorting works fully over HTTP. Press Ctrl+C to stop the server.

### JSON output

Use `--json` to get structured data suitable for other frontends (iOS, web, etc.):

```bash
python team_lineup.py NYM 2024-06-15 --json
```

Returns a JSON object with the full game structure:

```json
{
  "game_pk": 745527,
  "date": "2024-06-15",
  "away": { "abbrev": "SD", "name": "San Diego Padres" },
  "home": { "abbrev": "NYM", "name": "New York Mets" },
  "teams": {
    "NYM": {
      "side": "home",
      "position_players": [
        { "mlbam_id": 624413, "name": "Pete Alonso", "position": "1B",
          "batting_order": 4, "xwoba": 0.352, "xwoba_L": 0.365,
          "xwoba_R": 0.345, "pa": 312, "gb_pct": 38.0, "fb_pct": 30.0 }
      ],
      "starter": {
        "mlbam_id": 592789, "name": "Sean Manaea", "throws": "L",
        "xwoba": 0.310, "xwoba_L": 0.295, "xwoba_R": 0.320, "pa": 450
      },
      "bullpen": [
        { "mlbam_id": 663432, "name": "Edwin Díaz", "throws": "R",
          "xwoba": 0.277, "pa": 92,
          "workload": [
            { "date": "2024-06-14", "pitches": 21 },
            { "date": "2024-06-13", "pitches": 15 },
            { "date": "2024-06-12", "pitches": 0 }
          ] }
      ],
      "opposing_starter": { "mlbam_id": 605483, "name": "Dylan Cease", "throws": "R" }
    }
  }
}
```

### Check a single pitcher's workload

```bash
python pitch_workload.py 663432 2024-07-01
```

## Architecture

The codebase is split into three layers for cross-platform reuse:

| File | Layer | Description |
|---|---|---|
| `lineup_data.py` | **Data** | Pure data layer — fetches roster, Statcast stats, and pitch workloads. Returns JSON-serializable dicts that any frontend can consume. |
| `lineup_formatter.py` | **Presentation** | Text formatter — takes structured data and produces ASCII lineup cards. One of many possible consumers of the data layer. |
| `lineup_html.py` | **Presentation** | HTML formatter — takes structured data and produces a self-contained HTML file with sortable tables. |
| `team_lineup.py` | **CLI** | Thin entry point — wires the data layer to the text formatter or JSON output. |
| `pitch_workload.py` | **Data** | Bullpen pitch log module — pulls per-pitcher pitch counts for the 3 days before a game. |
| `test_savant.py` | **Test** | Smoke test to verify Statcast connectivity. |

To build another frontend (e.g. a SwiftUI iOS app), use `lineup_data.get_game_data(team, date)` or consume the `--json` CLI output. The JSON structure maps directly to Swift `Codable` structs.

## Lineup Card Sections

Each card contains the following sections:

**Opposing Starting Pitcher** — shown at the top for matchup context, with season xwOBA against, L/R splits, and batted ball tendencies.

**Batting Lineup** — starters in batting order, followed by bench players. Each batter shows:
- Jersey number and position
- Season xwOBA, split by pitcher handedness (vL / vR)
- Plate appearances, GB%, FB%

**Starting Pitcher** — the team's own starter with the same stat line.

**Bullpen + Pitch Log** — all bullpen arms with performance stats, plus a 3-day pitch log showing how many pitches each reliever threw in each of the 3 days before the game. Pitch counts appear as a single `d1-d2-d3` column (most recent day first); `0` means the pitcher appeared but threw zero pitches recorded, and the field is `--` when workload data is unavailable. If all 3 values are non-zero, that pitcher has worked 3 days in a row.

### Example output (bullpen section)

```
  Bullpen                Pos  xwOBA     vL     vR     PA   GB%   FB%  Pitches
  ----------------------------------------------------------------------------
      #39 E. Díaz     RHP   .277   .302   .254     92   45%   24%  21-15-0
      #30 J. Diekman  LHP   .308   .279   .333     93   43%   24%  15-0-17
      #38 T. Megill   RHP   .327   .320   .337    111   37%   31%  0-0-0
```

### Output width

Cards are formatted to a maximum of **80 characters per line**, making them suitable for printing on standard paper or displaying in a fixed-width terminal without wrapping. To fit within this limit, bullpen pitcher names are abbreviated to first initial and last name (e.g. `E. Díaz`).

## Data Sources

- **MLB Stats API** (`statsapi.mlb.com`) — game schedules, rosters, boxscores
- **Statcast / Baseball Savant** (via pybaseball) — pitch-level data, xwOBA, batted ball classifications

## Supported Teams

All 30 MLB teams are supported using their standard abbreviations:

`AZ` `ATL` `BAL` `BOS` `CHC` `CWS` `CIN` `CLE` `COL` `DET` `HOU` `KC` `LAA` `LAD` `MIA` `MIL` `MIN` `NYM` `NYY` `OAK` `PHI` `PIT` `SD` `SEA` `SF` `STL` `TB` `TEX` `TOR` `WSH`
