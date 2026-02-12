"""Pull all eligible batters for a specific team on a specific date.

Uses the MLB Stats API boxscore to get the full roster (including bench players
who never batted), and Statcast data to reconstruct the batting order.
"""

import argparse
import math
import sys
import requests
from pybaseball import statcast, statcast_batter, statcast_pitcher

# Statcast abbreviation -> MLB Stats API team ID
TEAM_IDS = {
    "AZ": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112,
    "CWS": 145, "CIN": 113, "CLE": 114, "COL": 115, "DET": 116,
    "HOU": 117, "KC": 118, "LAA": 108, "LAD": 119, "MIA": 146,
    "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "OAK": 133,
    "PHI": 143, "PIT": 134, "SD": 135, "SEA": 136, "SF": 137,
    "STL": 138, "TB": 139, "TEX": 140, "TOR": 141, "WSH": 120,
}


def get_game_pk(team, date):
    """Find the game_pk for a team on a given date via MLB Stats API."""
    team_id = TEAM_IDS.get(team)
    if not team_id:
        raise ValueError(f"Unknown team abbreviation: {team}")

    resp = requests.get("https://statsapi.mlb.com/api/v1/schedule", params={
        "date": date, "sportId": 1, "teamId": team_id,
    })
    resp.raise_for_status()
    dates = resp.json().get("dates", [])
    if not dates or not dates[0].get("games"):
        return None
    return dates[0]["games"][0]["gamePk"]


def get_all_position_players(game_pk, team):
    """Get all position players from the boxscore for the given team."""
    resp = requests.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    resp.raise_for_status()
    game_data = resp.json()

    teams = game_data["gameData"]["teams"]
    team_id = TEAM_IDS[team]
    side = "away" if teams["away"]["id"] == team_id else "home"

    players = game_data["liveData"]["boxscore"]["teams"][side]["players"]
    position_players = []
    for pid, pdata in players.items():
        pos = pdata["position"]["abbreviation"]
        if pos == "P":
            continue
        mlbam_id = pdata["person"]["id"]
        name = pdata["person"]["fullName"]
        batting = pdata.get("stats", {}).get("batting", {})
        pa = batting.get("plateAppearances", 0)
        position_players.append({
            "mlbam_id": mlbam_id, "name": name, "position": pos, "pa": pa,
        })
    return position_players, side


def get_opposing_pitcher(game_pk, side):
    """Get the opposing team's starting pitcher from the boxscore."""
    opp_side = "home" if side == "away" else "away"

    resp = requests.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    resp.raise_for_status()
    game_data = resp.json()

    players = game_data["liveData"]["boxscore"]["teams"][opp_side]["players"]
    pitchers_list = game_data["liveData"]["boxscore"]["teams"][opp_side].get("pitchers", [])
    if not pitchers_list:
        return None

    # The first pitcher in the pitchers list is the starter
    starter_id = pitchers_list[0]
    pdata = players.get(f"ID{starter_id}")
    if not pdata:
        return None

    return {
        "mlbam_id": starter_id,
        "name": pdata["person"]["fullName"],
        "throws": pdata.get("position", {}).get("abbreviation", "P"),
    }


def get_batting_order(game_pk, side, date):
    """Get batting order from Statcast data for starters and in-game subs."""
    data = statcast(start_dt=date, end_dt=date)
    game = data[data["game_pk"] == game_pk]
    half = "Bot" if side == "home" else "Top"
    team_batting = game[game["inning_topbot"] == half]

    order = (
        team_batting.groupby("batter")
        .agg(first_ab=("at_bat_number", "min"))
        .sort_values("first_ab")
        .reset_index()
    )
    # Return dict: mlbam_id -> order position (1-indexed)
    return {row["batter"]: i + 1 for i, (_, row) in enumerate(order.iterrows())}


def get_xwoba_splits(batter_ids, date):
    """Calculate season xwOBA and L/R splits for each batter up to the given date.

    For each plate appearance, we use the Statcast "expected" wOBA based on exit
    velocity and launch angle when available, falling back to the actual wOBA
    value for non-batted-ball outcomes (walks, strikeouts, HBP).
    """
    year = date[:4]
    season_start = f"{year}-03-20"

    splits = {}
    for batter_id in batter_ids:
        try:
            data = statcast_batter(season_start, date, batter_id)
        except Exception:
            continue

        # woba_denom == 1 marks plate-appearance-ending events (filters out
        # mid-AB pitches). Similar to filtering with a predicate in Swift.
        pa_events = data[data["woba_denom"] == 1].copy()
        if pa_events.empty:
            continue

        # .fillna() replaces NaN values with a fallback — like Swift's ?? operator.
        pa_events["xwoba"] = pa_events["estimated_woba_using_speedangle"].fillna(
            pa_events["woba_value"]
        )

        overall = pa_events["xwoba"].mean()

        vs_l = pa_events[pa_events["p_throws"] == "L"]["xwoba"]
        vs_r = pa_events[pa_events["p_throws"] == "R"]["xwoba"]

        vs_l_mean = vs_l.mean() if not vs_l.empty else float("nan")
        vs_r_mean = vs_r.mean() if not vs_r.empty else float("nan")

        splits[batter_id] = {
            "xwoba": overall,
            "diff_L": vs_l_mean - overall if not math.isnan(vs_l_mean) else None,
            "diff_R": vs_r_mean - overall if not math.isnan(vs_r_mean) else None,
        }

    return splits


def get_pitcher_xwoba(pitcher_id, date):
    """Calculate season xwOBA against and L/R batter splits for a pitcher.

    Same computation as get_xwoba_splits but from the pitcher's perspective:
    - xwOBA against = expected wOBA allowed to all batters
    - vL/vR = absolute xwOBA against left-handed / right-handed batters (by stand)
    """
    year = date[:4]
    season_start = f"{year}-03-20"

    try:
        data = statcast_pitcher(season_start, date, pitcher_id)
    except Exception:
        return None

    pa_events = data[data["woba_denom"] == 1].copy()
    if pa_events.empty:
        return None

    pa_events["xwoba"] = pa_events["estimated_woba_using_speedangle"].fillna(
        pa_events["woba_value"]
    )

    overall = pa_events["xwoba"].mean()
    pa_count = len(pa_events)

    # "stand" is the batter's handedness (L/R), used for pitcher splits
    vs_l = pa_events[pa_events["stand"] == "L"]["xwoba"]
    vs_r = pa_events[pa_events["stand"] == "R"]["xwoba"]

    vs_l_mean = vs_l.mean() if not vs_l.empty else float("nan")
    vs_r_mean = vs_r.mean() if not vs_r.empty else float("nan")

    # Determine pitcher's throwing hand from the data
    throws = "R"
    if "p_throws" in data.columns and not data["p_throws"].empty:
        throws = data["p_throws"].iloc[0]

    return {
        "xwoba": overall,
        "xwoba_L": vs_l_mean if not math.isnan(vs_l_mean) else None,
        "xwoba_R": vs_r_mean if not math.isnan(vs_r_mean) else None,
        "pa": pa_count,
        "throws": throws,
    }


def format_xwoba(val):
    """Format xwOBA in baseball convention (no leading zero): .345"""
    return f".{val * 1000:03.0f}"


def format_diff(val):
    """Format a split diff as a signed value: +0.032 or -0.015"""
    if val is None:
        return "  --  "
    return f"{val:+.3f}"


def get_team_lineup(team, date):
    """Fetch lineup data, compute xwOBA splits, and return formatted output string."""
    print(f"Fetching {team} eligible batters for {date}...")

    game_pk = get_game_pk(team, date)
    if not game_pk:
        print(f"No game found for {team} on {date}")
        return None

    position_players, side = get_all_position_players(game_pk, team)
    batting_order = get_batting_order(game_pk, side, date)

    # Get game info for display
    resp = requests.get("https://statsapi.mlb.com/api/v1/schedule", params={
        "gamePk": game_pk, "sportId": 1,
    })
    game_info = resp.json()["dates"][0]["games"][0]
    away_name = game_info["teams"]["away"]["team"]["name"]
    home_name = game_info["teams"]["home"]["team"]["name"]
    is_home = side == "home"

    # Fetch opposing starter pitcher info and xwOBA against
    opp_pitcher = get_opposing_pitcher(game_pk, side)
    pitcher_stats = None
    if opp_pitcher:
        print(f"Fetching xwOBA against for {opp_pitcher['name']}...")
        pitcher_stats = get_pitcher_xwoba(opp_pitcher["mlbam_id"], date)

    # Fetch season xwOBA splits for all position players
    batter_ids = [p["mlbam_id"] for p in position_players]
    print(f"Fetching xwOBA splits for {len(batter_ids)} batters...")
    splits = get_xwoba_splits(batter_ids, date)

    # Split into starters (had PAs, in batting order) and bench
    starters = []
    bench = []
    for p in position_players:
        order_pos = batting_order.get(p["mlbam_id"])
        if order_pos is not None:
            p["order"] = order_pos
            starters.append(p)
        else:
            bench.append(p)

    starters.sort(key=lambda x: x["order"])
    bench.sort(key=lambda x: x["name"])

    # Build formatted output as a list of strings, then join at the end.
    # In Python, building a list and joining is idiomatic — more like
    # Array<String> in Swift than repeated string concatenation.
    W = 66
    lines = []
    lines.append("=" * W)
    lines.append(f"  {team} Batting Lineup — {date}".center(W))
    matchup = f"{'Home' if is_home else 'Away'}: {away_name} @ {home_name}"
    lines.append(matchup.center(W))
    lines.append("=" * W)

    # Opposing pitcher section
    if opp_pitcher and pitcher_stats:
        throws = pitcher_stats["throws"]
        xw = format_xwoba(pitcher_stats["xwoba"])
        xl = format_xwoba(pitcher_stats["xwoba_L"]) if pitcher_stats["xwoba_L"] is not None else " -- "
        xr = format_xwoba(pitcher_stats["xwoba_R"]) if pitcher_stats["xwoba_R"] is not None else " -- "
        pa = pitcher_stats["pa"]
        lines.append(f"  Opposing SP: {opp_pitcher['name']} ({throws}HP)")
        lines.append(f"  xwOBA against: {xw}   vL: {xl}   vR: {xr}   ({pa} PA)")
        lines.append("  " + "-" * (W - 4))
    elif opp_pitcher:
        lines.append(f"  Opposing SP: {opp_pitcher['name']} (no Statcast data)")
        lines.append("  " + "-" * (W - 4))

    hdr = f"  {'#':>2}   {'Player':<24} {'Pos':<4} {'xwOBA':>5}  {'vL':>6}  {'vR':>6}"
    lines.append(hdr)
    lines.append("  " + "-" * (W - 4))

    def player_line(prefix, p):
        s = splits.get(p["mlbam_id"], {})
        xw = format_xwoba(s["xwoba"]) if "xwoba" in s else " --  "
        dl = format_diff(s.get("diff_L"))
        dr = format_diff(s.get("diff_R"))
        return f"  {prefix} {p['name']:<24} {p['position']:<4} {xw:>5}  {dl:>6}  {dr:>6}"

    for i, p in enumerate(starters, 1):
        lines.append(player_line(f"{i:>2}.", p))

    if bench:
        lines.append("")
        lines.append("  Bench")
        lines.append("  " + "-" * (W - 4))
        for p in bench:
            lines.append(player_line("   ", p))

    lines.append("")
    lines.append(f"  Total eligible batters: {len(position_players)}")
    lines.append("=" * W)

    output = "\n".join(lines)
    print(output)
    return output


if __name__ == "__main__":
    # argparse is Python's built-in CLI argument parser (like Swift ArgumentParser).
    # "positional" args are required by default — no flag needed, just order matters.
    parser = argparse.ArgumentParser(description="Pull all eligible batters for a team on a date.")
    parser.add_argument("team", choices=TEAM_IDS.keys(), help="Team abbreviation (e.g. NYM, LAD, NYY)")
    parser.add_argument("date", help="Game date in YYYY-MM-DD format")

    # nargs="?" makes a flag accept 0 or 1 values:
    #   -o          → uses `const` ("auto")    — auto-generates filename
    #   -o FILE     → uses the value ("FILE")  — explicit filename
    #   (omitted)   → uses `default` (None)    — no file output
    # In Swift terms, this is like an Optional<String> with a default value.
    parser.add_argument(
        "-o", "--output",
        nargs="?", const="auto", default=None,
        help="Save to .txt file. Omit value for auto-named file, or pass a path.",
    )

    args = parser.parse_args()

    try:
        result = get_team_lineup(args.team, args.date)
        if result is None:
            sys.exit(1)

        if args.output is not None:
            filename = (f"{args.team}_{args.date}_lineup.txt"
                        if args.output == "auto" else args.output)
            # "with open(...) as f" is a context manager — it auto-closes the file
            # when the block exits, like Swift's defer { file.close() } but built
            # into the language syntax.
            with open(filename, "w") as f:
                f.write(result + "\n")
            print(f"\nSaved to {filename}")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
