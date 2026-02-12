"""Pull all eligible batters for both teams in a game on a specific date.

Uses the MLB Stats API boxscore to get the full roster (including bench players
who never batted), and Statcast data to reconstruct the batting order.
Produces one lineup card per team, each showing that team's batters and the
opposing pitching staff they'll face.
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

# Reverse lookup: team ID -> abbreviation
TEAM_ABBREVS = {v: k for k, v in TEAM_IDS.items()}


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


def fetch_game_data(game_pk, date):
    """Fetch shared game data: live feed and Statcast pitch-level data.

    Returns (live_feed, statcast_day) — both are fetched once and shared
    across both teams' lineup cards.
    """
    resp = requests.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    resp.raise_for_status()
    live_feed = resp.json()

    print("Fetching Statcast data for game day...")
    statcast_day = statcast(start_dt=date, end_dt=date)

    return live_feed, statcast_day


def extract_position_players(live_feed, side):
    """Get all position players from the pre-fetched live feed."""
    players = live_feed["liveData"]["boxscore"]["teams"][side]["players"]
    position_players = []
    for pid, pdata in players.items():
        pos = pdata["position"]["abbreviation"]
        if pos == "P":
            continue
        position_players.append({
            "mlbam_id": pdata["person"]["id"],
            "name": pdata["person"]["fullName"],
            "number": pdata.get("jerseyNumber", ""),
            "position": pos,
            "pa": pdata.get("stats", {}).get("batting", {}).get("plateAppearances", 0),
        })
    return position_players


def extract_pitchers(live_feed, side):
    """Get starter and bullpen pitchers from the pre-fetched live feed.

    Returns (starter, bullpen) where starter is a dict and bullpen is a list.
    All rostered pitchers except the starter are considered bullpen.
    """
    players = live_feed["liveData"]["boxscore"]["teams"][side]["players"]
    pitchers_list = live_feed["liveData"]["boxscore"]["teams"][side].get("pitchers", [])
    if not pitchers_list:
        return None, []

    # The first pitcher in the pitchers list is the starter
    starter_id = pitchers_list[0]

    # Collect all rostered pitchers (position == "P")
    starter = None
    bullpen = []
    for pid, pdata in players.items():
        if pdata["position"]["abbreviation"] != "P":
            continue
        info = {
            "mlbam_id": pdata["person"]["id"],
            "name": pdata["person"]["fullName"],
            "number": pdata.get("jerseyNumber", ""),
        }
        if pdata["person"]["id"] == starter_id:
            starter = info
        else:
            bullpen.append(info)

    bullpen.sort(key=lambda x: x["name"])
    return starter, bullpen


def extract_batting_order(statcast_day, game_pk, side):
    """Get batting order from pre-fetched Statcast data for starters and subs."""
    game = statcast_day[statcast_day["game_pk"] == game_pk]
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
            "xwoba_L": vs_l_mean if not math.isnan(vs_l_mean) else None,
            "xwoba_R": vs_r_mean if not math.isnan(vs_r_mean) else None,
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


def build_lineup_card(team_abbrev, date, side, away_name, home_name,
                      position_players, batting_order, batter_splits,
                      opp_starter, opp_starter_stats,
                      own_starter, own_bullpen, own_pitcher_stats):
    """Format a single team's lineup card as a string.

    This is a pure formatting function — all data has already been fetched
    and computed. Each card shows:
    - The opposing starting pitcher at the top (for matchup context)
    - The team's batting lineup and bench
    - The team's own bullpen
    """
    is_home = side == "home"

    # Split into starters (in batting order) and bench
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
    lines.append(f"  {team_abbrev} Batting Lineup — {date}".center(W))
    matchup = f"{'Home' if is_home else 'Away'}: {away_name} @ {home_name}"
    lines.append(matchup.center(W))
    lines.append("=" * W)

    # Opposing starter at the top
    def fmt_num(p):
        """Format jersey number as '#12' or '   ' if missing."""
        n = p.get("number", "")
        return f"#{n:>2}" if n else "   "

    def pitcher_line(p, stats):
        s = stats.get(p["mlbam_id"])
        num = fmt_num(p)
        if not s:
            return f"   {num} {p['name']:<24}       (no Statcast data)"
        throws = s["throws"]
        name = f"{p['name']} ({throws}HP)"
        xw = format_xwoba(s["xwoba"])
        xl = format_xwoba(s["xwoba_L"]) if s["xwoba_L"] is not None else " -- "
        xr = format_xwoba(s["xwoba_R"]) if s["xwoba_R"] is not None else " -- "
        pa = s["pa"]
        return f"   {num} {name:<24} {xw:>5}  {xl:>5}  {xr:>5}  ({pa:>3} PA)"

    if opp_starter:
        s = opp_starter_stats.get(opp_starter["mlbam_id"])
        num = fmt_num(opp_starter)
        if s:
            throws = s["throws"]
            xw = format_xwoba(s["xwoba"])
            xl = format_xwoba(s["xwoba_L"]) if s["xwoba_L"] is not None else " -- "
            xr = format_xwoba(s["xwoba_R"]) if s["xwoba_R"] is not None else " -- "
            pa = s["pa"]
            lines.append(f"  Opposing SP: {num} {opp_starter['name']} ({throws}HP)")
            lines.append(f"  xwOBA against: {xw}   vL: {xl}   vR: {xr}   ({pa} PA)")
        else:
            lines.append(f"  Opposing SP: {num} {opp_starter['name']} (no Statcast data)")
        lines.append("  " + "-" * (W - 4))

    hdr = f"  {'#':>2}  {'Uni':>3} {'Player':<21} {'Pos':<4} {'xwOBA':>5}  {'vL':>5}  {'vR':>5}"
    lines.append(hdr)
    lines.append("  " + "-" * (W - 4))

    def player_line(prefix, p):
        s = batter_splits.get(p["mlbam_id"], {})
        num = fmt_num(p)
        xw = format_xwoba(s["xwoba"]) if "xwoba" in s else " -- "
        xl = format_xwoba(s["xwoba_L"]) if s.get("xwoba_L") is not None else " -- "
        xr = format_xwoba(s["xwoba_R"]) if s.get("xwoba_R") is not None else " -- "
        return f"  {prefix} {num} {p['name']:<21} {p['position']:<4} {xw:>5}  {xl:>5}  {xr:>5}"

    for i, p in enumerate(starters, 1):
        lines.append(player_line(f"{i:>2}.", p))

    if bench:
        lines.append("")
        lines.append("  Bench")
        lines.append("  " + "-" * (W - 4))
        for p in bench:
            lines.append(player_line("   ", p))

    if own_starter:
        lines.append("")
        lines.append("  Starting Pitcher" + " " * 13 + "xwOBA     vL     vR")
        lines.append("  " + "-" * (W - 4))
        lines.append(pitcher_line(own_starter, own_pitcher_stats))

    if own_bullpen:
        lines.append("")
        lines.append("  Bullpen" + " " * 22 + "xwOBA     vL     vR")
        lines.append("  " + "-" * (W - 4))
        for p in own_bullpen:
            lines.append(pitcher_line(p, own_pitcher_stats))

    lines.append("")
    lines.append(f"  Total eligible batters: {len(position_players)}")
    lines.append("=" * W)

    return "\n".join(lines)


def get_game_lineups(team, date):
    """Fetch game data and produce lineup cards for both teams.

    Returns a dict mapping team abbreviation to its formatted lineup card,
    e.g. {"NYM": "...", "WSH": "..."}.
    """
    print(f"Finding game for {team} on {date}...")

    game_pk = get_game_pk(team, date)
    if not game_pk:
        print(f"No game found for {team} on {date}")
        return None

    live_feed, statcast_day = fetch_game_data(game_pk, date)

    # Identify both teams
    teams = live_feed["gameData"]["teams"]
    away_id = teams["away"]["id"]
    home_id = teams["home"]["id"]
    away_abbrev = TEAM_ABBREVS.get(away_id, "???")
    home_abbrev = TEAM_ABBREVS.get(home_id, "???")
    away_name = teams["away"]["name"]
    home_name = teams["home"]["name"]

    results = {}
    for side, abbrev in [("away", away_abbrev), ("home", home_abbrev)]:
        opp_side = "home" if side == "away" else "away"

        # Extract batters and batting order for this team
        position_players = extract_position_players(live_feed, side)
        batting_order = extract_batting_order(statcast_day, game_pk, side)

        # Extract opposing starter (shown at top for matchup context)
        opp_starter, _ = extract_pitchers(live_feed, opp_side)
        opp_starter_stats = {}
        if opp_starter:
            print(f"Fetching xwOBA against for opposing SP {opp_starter['name']}...")
            stats = get_pitcher_xwoba(opp_starter["mlbam_id"], date)
            if stats:
                opp_starter_stats[opp_starter["mlbam_id"]] = stats

        # Extract this team's own starter and bullpen
        own_starter, own_bullpen = extract_pitchers(live_feed, side)
        own_pitcher_stats = {}
        all_own_pitchers = ([own_starter] if own_starter else []) + own_bullpen
        if all_own_pitchers:
            print(f"Fetching xwOBA against for {len(all_own_pitchers)} {abbrev} pitchers...")
            for p in all_own_pitchers:
                stats = get_pitcher_xwoba(p["mlbam_id"], date)
                if stats:
                    own_pitcher_stats[p["mlbam_id"]] = stats

        # Fetch xwOBA splits for all batters
        batter_ids = [p["mlbam_id"] for p in position_players]
        print(f"Fetching xwOBA splits for {len(batter_ids)} {abbrev} batters...")
        batter_splits = get_xwoba_splits(batter_ids, date)

        card = build_lineup_card(
            abbrev, date, side, away_name, home_name,
            position_players, batting_order, batter_splits,
            opp_starter, opp_starter_stats,
            own_starter, own_bullpen, own_pitcher_stats,
        )
        results[abbrev] = card
        print(card)
        print()

    return results


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
        help="Save to .txt files. Omit value for auto-named files, or pass a path prefix.",
    )

    args = parser.parse_args()

    try:
        results = get_game_lineups(args.team, args.date)
        if results is None:
            sys.exit(1)

        if args.output is not None:
            for abbrev, card in results.items():
                if args.output == "auto":
                    filename = f"{abbrev}_{args.date}_lineup.txt"
                else:
                    filename = f"{args.output}_{abbrev}.txt"
                # "with open(...) as f" is a context manager — it auto-closes the file
                # when the block exits, like Swift's defer { file.close() } but built
                # into the language syntax.
                with open(filename, "w") as f:
                    f.write(card + "\n")
                print(f"Saved to {filename}")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
