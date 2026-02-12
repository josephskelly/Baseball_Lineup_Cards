"""Calculate recent pitch workload for pitchers.

Looks back over the last 3 days using Statcast pitch-level data and
returns per-day pitch counts so a lineup card can show at a glance how
heavily a reliever has been used.
"""

from datetime import datetime, timedelta
from pybaseball import statcast_pitcher


def get_recent_workload(pitcher_id, date):
    """Get pitch counts for each of the 3 days before a game.

    Args:
        pitcher_id: MLB AM ID for the pitcher.
        date: Game date as 'YYYY-MM-DD'. Pitches on this date are
              NOT included — only the preceding 3 days.

    Returns:
        dict with:
            "last_3": list of {"date": str, "pitches": int} for each of the
                      3 days before the game (most recent first), with 0
                      pitches for days the pitcher did not appear.
    """
    ref = datetime.strptime(date, "%Y-%m-%d")
    start = ref - timedelta(days=3)
    end = ref - timedelta(days=1)

    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # Build the 3-day scaffold (most recent day first)
    last_3_dates = [
        (ref - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 4)
    ]

    try:
        data = statcast_pitcher(start_str, end_str, pitcher_id)
    except Exception:
        return {"last_3": [{"date": d, "pitches": 0} for d in last_3_dates]}

    if data.empty:
        return {"last_3": [{"date": d, "pitches": 0} for d in last_3_dates]}

    # Each row is one pitch; group by game date and count
    daily = (
        data.groupby("game_date")
        .size()
        .reset_index(name="pitches")
    )
    pitch_map = {
        str(row["game_date"]).split(" ")[0]: int(row["pitches"])
        for _, row in daily.iterrows()
    }

    last_3 = [
        {"date": d, "pitches": pitch_map.get(d, 0)} for d in last_3_dates
    ]
    return {"last_3": last_3}


def get_team_workloads(pitcher_ids, date):
    """Get recent pitch workload for a list of pitchers.

    Args:
        pitcher_ids: list of (mlbam_id, name) tuples.
        date: Game date as 'YYYY-MM-DD'.

    Returns:
        dict mapping mlbam_id -> workload result from get_recent_workload.
    """
    results = {}
    for pid, name in pitcher_ids:
        print(f"  Fetching workload for {name}...")
        results[pid] = get_recent_workload(pid, date)
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Show recent pitch workload for pitchers in a game."
    )
    parser.add_argument("pitcher_id", type=int, help="MLB AM pitcher ID")
    parser.add_argument("date", help="Game date (YYYY-MM-DD)")
    args = parser.parse_args()

    print(f"Pitch workload for pitcher {args.pitcher_id}, "
          f"3 days before {args.date}:\n")

    result = get_recent_workload(args.pitcher_id, args.date)

    for day in result["last_3"]:
        label = f"{day['pitches']} pitches" if day["pitches"] else "-"
        print(f"  {day['date']}:  {label}")

    pitched_all_3 = all(d["pitches"] > 0 for d in result["last_3"])
    if pitched_all_3:
        print("\n  *** 3 days in a row — unavailable ***")
