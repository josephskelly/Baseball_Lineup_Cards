"""Calculate recent pitch workload for pitchers.

Looks back over the last N days (default 4) using Statcast pitch-level
data and returns the total number of pitches thrown per day, plus the
overall total.
"""

from datetime import datetime, timedelta
from pybaseball import statcast_pitcher


def get_recent_workload(pitcher_id, date, days_back=4):
    """Get pitch counts per day for a pitcher over the last `days_back` days.

    Args:
        pitcher_id: MLB AM ID for the pitcher.
        date: Reference date as 'YYYY-MM-DD'. Pitches on this date are
              NOT included — only the preceding `days_back` days.
        days_back: Number of days to look back (default 4).

    Returns:
        dict with:
            "daily": list of {"date": str, "pitches": int} for days pitched,
            "total": int total pitches across the window.
    """
    ref = datetime.strptime(date, "%Y-%m-%d")
    start = ref - timedelta(days=days_back)
    end = ref - timedelta(days=1)

    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    try:
        data = statcast_pitcher(start_str, end_str, pitcher_id)
    except Exception:
        return {"daily": [], "total": 0}

    if data.empty:
        return {"daily": [], "total": 0}

    # Each row is one pitch; group by game date and count
    daily = (
        data.groupby("game_date")
        .size()
        .reset_index(name="pitches")
        .sort_values("game_date")
    )

    daily_list = [
        {"date": str(row["game_date"]).split(" ")[0], "pitches": int(row["pitches"])}
        for _, row in daily.iterrows()
    ]

    total = sum(d["pitches"] for d in daily_list)
    return {"daily": daily_list, "total": total}


def get_team_workloads(pitcher_ids, date, days_back=4):
    """Get recent pitch workload for a list of pitchers.

    Args:
        pitcher_ids: list of (mlbam_id, name) tuples.
        date: Reference date as 'YYYY-MM-DD'.
        days_back: Number of days to look back (default 4).

    Returns:
        dict mapping mlbam_id -> workload result from get_recent_workload.
    """
    results = {}
    for pid, name in pitcher_ids:
        print(f"  Fetching workload for {name}...")
        results[pid] = get_recent_workload(pid, date, days_back)
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Show recent pitch workload for pitchers in a game."
    )
    parser.add_argument("pitcher_id", type=int, help="MLB AM pitcher ID")
    parser.add_argument("date", help="Reference date (YYYY-MM-DD)")
    parser.add_argument(
        "--days", type=int, default=4, help="Days to look back (default 4)"
    )
    args = parser.parse_args()

    print(f"Pitch workload for pitcher {args.pitcher_id}, "
          f"{args.days} days before {args.date}:\n")

    result = get_recent_workload(args.pitcher_id, args.date, args.days)

    if not result["daily"]:
        print("  No pitches found in this window.")
    else:
        for day in result["daily"]:
            print(f"  {day['date']}:  {day['pitches']} pitches")
        print(f"\n  Total: {result['total']} pitches")
