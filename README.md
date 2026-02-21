# Baseball Lineup Cards

Generate detailed lineup cards for any MLB game using data from the MLB Stats API and Statcast (Baseball Savant). Each card includes batting orders, bench players, pitching staffs, xwOBA-based performance stats, and a bullpen pitch log showing recent workload.

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

### Check a single pitcher's workload

```bash
python pitch_workload.py 663432 2024-07-01
```

## Lineup Card Sections

Each card contains the following sections:

**Opposing Starting Pitcher** — shown at the top for matchup context, with season xwOBA against, L/R splits, and batted ball tendencies.

**Batting Lineup** — starters in batting order, followed by bench players. Each batter shows:
- Jersey number and position
- Season xwOBA, split by pitcher handedness (vL / vR)
- Plate appearances, GB%, FB%

**Starting Pitcher** — the team's own starter with the same stat line.

**Bullpen + Pitch Log** — all bullpen arms with performance stats, plus a 3-day pitch log showing how many pitches each reliever threw in each of the 3 days before the game. A dash means the pitcher did not appear that day. If all 3 columns show pitch counts, that pitcher has worked 3 days in a row.

### Example output (bullpen section)

```
  Bullpen                       Pos  xwOBA     vL     vR     PA   GB%   FB%  |      Pitch Log
  -----------------------------------------------------------------------------------+--------------------
      #39 Edwin Díaz            RHP   .277   .302   .254     92   45%   24%  |    21     15      -
      #30 Jake Diekman          LHP   .308   .279   .333     93   43%   24%  |    15      -     17
      #38 Tylor Megill          RHP   .327   .320   .337    111   37%   31%  |     -      -      -
                                                                             | 06-14  06-13  06-12
```

## Files

| File | Description |
|---|---|
| `team_lineup.py` | Main script — fetches game data and generates lineup cards |
| `pitch_workload.py` | Bullpen pitch log module — pulls per-pitcher pitch counts for the 3 days before a game |
| `test_savant.py` | Smoke test to verify Statcast connectivity |
| `requirements.txt` | Python dependencies |

## Data Sources

- **MLB Stats API** (`statsapi.mlb.com`) — game schedules, rosters, boxscores
- **Statcast / Baseball Savant** (via pybaseball) — pitch-level data, xwOBA, batted ball classifications

## Supported Teams

All 30 MLB teams are supported using their standard abbreviations:

`AZ` `ATL` `BAL` `BOS` `CHC` `CWS` `CIN` `CLE` `COL` `DET` `HOU` `KC` `LAA` `LAD` `MIA` `MIL` `MIN` `NYM` `NYY` `OAK` `PHI` `PIT` `SD` `SEA` `SF` `STL` `TB` `TEX` `TOR` `WSH`
