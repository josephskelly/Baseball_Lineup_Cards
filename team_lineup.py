"""Pull all eligible batters for a specific team on a specific date.

Uses the MLB Stats API boxscore to get the full roster (including bench players
who never batted), and Statcast data to reconstruct the batting order.
"""

import argparse
import sys
import requests
from pybaseball import statcast

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


def get_team_lineup(team, date):
    print(f"Fetching {team} eligible batters for {date}...\n")

    game_pk = get_game_pk(team, date)
    if not game_pk:
        print(f"No game found for {team} on {date}")
        return None

    position_players, side = get_all_position_players(game_pk, team)
    batting_order = get_batting_order(game_pk, side, date)

    # Get game info for display
    resp = requests.get(f"https://statsapi.mlb.com/api/v1/schedule", params={
        "gamePk": game_pk, "sportId": 1,
    })
    game_info = resp.json()["dates"][0]["games"][0]
    away_name = game_info["teams"]["away"]["team"]["name"]
    home_name = game_info["teams"]["home"]["team"]["name"]
    is_home = side == "home"

    print(f"{'Home' if is_home else 'Away'} game: {away_name} @ {home_name}")

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

    print(f"\n--- {team} Batting Lineup ({date}) ---\n")
    for i, p in enumerate(starters, 1):
        print(f"  {i:>2}. {p['name']:<25} {p['position']:<3}  ({p['pa']} PA)")

    if bench:
        print(f"\n--- Bench ---\n")
        for p in bench:
            print(f"      {p['name']:<25} {p['position']:<3}")

    print(f"\nTotal eligible batters: {len(position_players)}")
    return position_players


if __name__ == "__main__":
    # argparse is Python's built-in CLI argument parser (like Swift ArgumentParser).
    # "positional" args are required by default — no flag needed, just order matters.
    parser = argparse.ArgumentParser(description="Pull all eligible batters for a team on a date.")
    parser.add_argument("team", choices=TEAM_IDS.keys(), help="Team abbreviation (e.g. NYM, LAD, NYY)")
    parser.add_argument("date", help="Game date in YYYY-MM-DD format")

    args = parser.parse_args()

    try:
        result = get_team_lineup(args.team, args.date)
        if result is None:
            sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
