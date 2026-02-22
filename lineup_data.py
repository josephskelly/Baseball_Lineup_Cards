"""Pure data layer for MLB lineup cards.

Fetches roster, Statcast stats, and pitch workload data, then returns
JSON-serializable dicts that any frontend (CLI, iOS, web) can consume.
"""

import contextlib
import io
import math
import os
import sys
import requests
from pybaseball import statcast, statcast_batter, statcast_pitcher
from pitch_workload import get_recent_workload


def _log(msg):
    """Print progress to stderr so stdout stays clean for JSON output."""
    print(msg, file=sys.stderr)


@contextlib.contextmanager
def _quiet_stdout():
    """Temporarily redirect stdout to /dev/null to silence pybaseball chatter."""
    devnull = open(os.devnull, "w")
    old = sys.stdout
    sys.stdout = devnull
    try:
        yield
    finally:
        sys.stdout = old
        devnull.close()

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


def _fetch_live_feed(game_pk):
    """Fetch the MLB Stats API live feed for a game."""
    resp = requests.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    resp.raise_for_status()
    return resp.json()


def _fetch_statcast_day(date):
    """Fetch Statcast pitch-level data for a single day. Returns None on failure."""
    try:
        with _quiet_stdout():
            data = statcast(start_dt=date, end_dt=date)
    except Exception:
        return None
    if data is not None and data.empty:
        return None
    return data


def _season_range(date):
    """Return (season_start, season_end) for Statcast queries.

    During the regular season, uses the current year's data up to the given date.
    Before the season starts (e.g. spring training), falls back to the prior
    year's full season so players still have stats on their lineup card.
    """
    year = int(date[:4])
    season_start = f"{year}-03-20"
    if date < season_start:
        return f"{year - 1}-03-20", f"{year - 1}-11-15"
    return season_start, date


def _extract_position_players(live_feed, side):
    """Get all position players from the live feed."""
    players = live_feed["liveData"]["boxscore"]["teams"][side]["players"]
    result = []
    for pid, pdata in players.items():
        pos = pdata["position"]["abbreviation"]
        if pos == "P":
            continue
        result.append({
            "mlbam_id": pdata["person"]["id"],
            "name": pdata["person"]["fullName"],
            "number": pdata.get("jerseyNumber", ""),
            "position": pos,
        })
    return result


def _extract_pitchers(live_feed, side):
    """Get starter and bullpen pitchers from the live feed.

    Returns (starter, bullpen) where starter is a dict or None,
    and bullpen is a list of dicts.
    """
    players = live_feed["liveData"]["boxscore"]["teams"][side]["players"]
    pitchers_list = live_feed["liveData"]["boxscore"]["teams"][side].get("pitchers", [])

    starter_id = pitchers_list[0] if pitchers_list else None

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
        if starter_id is not None and pdata["person"]["id"] == starter_id:
            starter = info
        else:
            bullpen.append(info)

    bullpen.sort(key=lambda x: x["name"])
    return starter, bullpen


def _extract_batting_order(statcast_day, game_pk, side):
    """Get batting order from Statcast data.

    Returns dict mapping mlbam_id -> order position (1-indexed),
    or empty dict when Statcast data is unavailable.
    """
    if statcast_day is None:
        return {}

    game = statcast_day[statcast_day["game_pk"] == game_pk]
    half = "Bot" if side == "home" else "Top"
    team_batting = game[game["inning_topbot"] == half]

    order = (
        team_batting.groupby("batter")
        .agg(first_ab=("at_bat_number", "min"))
        .sort_values("first_ab")
        .reset_index()
    )
    return {row["batter"]: i + 1 for i, (_, row) in enumerate(order.iterrows())}


def _get_batter_stats(batter_id, date):
    """Fetch season xwOBA and L/R splits for a single batter."""
    season_start, season_end = _season_range(date)
    try:
        with _quiet_stdout():
            data = statcast_batter(season_start, season_end, batter_id)
    except Exception:
        return None

    pa_events = data[data["woba_denom"] == 1].copy()
    if pa_events.empty:
        return None

    pa_events["xwoba"] = pa_events["estimated_woba_using_speedangle"].fillna(
        pa_events["woba_value"]
    )

    overall = pa_events["xwoba"].mean()

    vs_l = pa_events[pa_events["p_throws"] == "L"]["xwoba"]
    vs_r = pa_events[pa_events["p_throws"] == "R"]["xwoba"]
    vs_l_mean = vs_l.mean() if not vs_l.empty else None
    vs_r_mean = vs_r.mean() if not vs_r.empty else None

    # NaN -> None for JSON serialization
    if vs_l_mean is not None and math.isnan(vs_l_mean):
        vs_l_mean = None
    if vs_r_mean is not None and math.isnan(vs_r_mean):
        vs_r_mean = None

    batted = pa_events[pa_events["bb_type"].notna()]
    n_batted = len(batted)
    if n_batted > 0:
        gb_pct = round((batted["bb_type"] == "ground_ball").sum() / n_batted * 100, 1)
        fb_pct = round((batted["bb_type"] == "fly_ball").sum() / n_batted * 100, 1)
    else:
        gb_pct = None
        fb_pct = None

    return {
        "xwoba": round(overall, 3),
        "xwoba_L": round(vs_l_mean, 3) if vs_l_mean is not None else None,
        "xwoba_R": round(vs_r_mean, 3) if vs_r_mean is not None else None,
        "pa": len(pa_events),
        "gb_pct": gb_pct,
        "fb_pct": fb_pct,
    }


def _get_pitcher_stats(pitcher_id, date):
    """Fetch season xwOBA against and L/R batter splits for a pitcher."""
    season_start, season_end = _season_range(date)
    try:
        with _quiet_stdout():
            data = statcast_pitcher(season_start, season_end, pitcher_id)
    except Exception:
        return None

    pa_events = data[data["woba_denom"] == 1].copy()
    if pa_events.empty:
        return None

    pa_events["xwoba"] = pa_events["estimated_woba_using_speedangle"].fillna(
        pa_events["woba_value"]
    )

    overall = pa_events["xwoba"].mean()

    vs_l = pa_events[pa_events["stand"] == "L"]["xwoba"]
    vs_r = pa_events[pa_events["stand"] == "R"]["xwoba"]
    vs_l_mean = vs_l.mean() if not vs_l.empty else None
    vs_r_mean = vs_r.mean() if not vs_r.empty else None

    if vs_l_mean is not None and math.isnan(vs_l_mean):
        vs_l_mean = None
    if vs_r_mean is not None and math.isnan(vs_r_mean):
        vs_r_mean = None

    batted = pa_events[pa_events["bb_type"].notna()]
    n_batted = len(batted)
    if n_batted > 0:
        gb_pct = round((batted["bb_type"] == "ground_ball").sum() / n_batted * 100, 1)
        fb_pct = round((batted["bb_type"] == "fly_ball").sum() / n_batted * 100, 1)
    else:
        gb_pct = None
        fb_pct = None

    throws = "R"
    if "p_throws" in data.columns and not data["p_throws"].empty:
        throws = data["p_throws"].iloc[0]

    return {
        "xwoba": round(overall, 3),
        "xwoba_L": round(vs_l_mean, 3) if vs_l_mean is not None else None,
        "xwoba_R": round(vs_r_mean, 3) if vs_r_mean is not None else None,
        "pa": len(pa_events),
        "gb_pct": gb_pct,
        "fb_pct": fb_pct,
        "throws": throws,
    }


def get_game_data(team, date):
    """Fetch all lineup card data for both teams in a game.

    Returns a JSON-serializable dict with the full game structure,
    or None if no game is found.
    """
    _log(f"Finding game for {team} on {date}...")

    game_pk = get_game_pk(team, date)
    if not game_pk:
        _log(f"No game found for {team} on {date}")
        return None

    live_feed = _fetch_live_feed(game_pk)

    _log("Fetching Statcast data for game day...")
    statcast_day = _fetch_statcast_day(date)

    # Identify both teams
    teams_info = live_feed["gameData"]["teams"]
    away_id = teams_info["away"]["id"]
    home_id = teams_info["home"]["id"]
    away_abbrev = TEAM_ABBREVS.get(away_id, "???")
    home_abbrev = TEAM_ABBREVS.get(home_id, "???")

    result = {
        "game_pk": game_pk,
        "date": date,
        "away": {"abbrev": away_abbrev, "name": teams_info["away"]["name"]},
        "home": {"abbrev": home_abbrev, "name": teams_info["home"]["name"]},
        "teams": {},
    }

    for side, abbrev in [("away", away_abbrev), ("home", home_abbrev)]:
        opp_side = "home" if side == "away" else "away"

        # Roster
        position_players = _extract_position_players(live_feed, side)
        batting_order = _extract_batting_order(statcast_day, game_pk, side)
        own_starter, own_bullpen = _extract_pitchers(live_feed, side)
        opp_starter, _ = _extract_pitchers(live_feed, opp_side)

        # Batter stats
        batter_ids = [p["mlbam_id"] for p in position_players]
        _log(f"Fetching xwOBA splits for {len(batter_ids)} {abbrev} batters...")
        for p in position_players:
            order_pos = batting_order.get(p["mlbam_id"])
            p["batting_order"] = order_pos
            stats = _get_batter_stats(p["mlbam_id"], date)
            if stats:
                p.update(stats)

        # Own pitching staff stats
        all_own_pitchers = ([own_starter] if own_starter else []) + own_bullpen
        if all_own_pitchers:
            _log(f"Fetching xwOBA against for {len(all_own_pitchers)} {abbrev} pitchers...")
        for p in all_own_pitchers:
            stats = _get_pitcher_stats(p["mlbam_id"], date)
            if stats:
                p.update(stats)

        # Bullpen workloads
        if own_bullpen:
            _log(f"Fetching pitch log for {len(own_bullpen)} {abbrev} bullpen arms...")
            for p in own_bullpen:
                wl = get_recent_workload(p["mlbam_id"], date)
                p["workload"] = wl["last_3"]

        # Opposing starter stats
        if opp_starter:
            _log(f"Fetching xwOBA against for opposing SP {opp_starter['name']}...")
            stats = _get_pitcher_stats(opp_starter["mlbam_id"], date)
            if stats:
                opp_starter.update(stats)

        result["teams"][abbrev] = {
            "side": side,
            "position_players": position_players,
            "starter": own_starter,
            "bullpen": own_bullpen,
            "opposing_starter": opp_starter,
        }

    return result
