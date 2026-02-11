"""Pull the batting lineup for a specific team on a specific date using Statcast data."""

import sys
from pybaseball import statcast, playerid_reverse_lookup

TEAM = "NYM"
DATE = "2024-07-01"


def get_team_lineup(team, date):
    print(f"Fetching Statcast data for {date}...")
    data = statcast(start_dt=date, end_dt=date)

    # Find games involving this team
    team_games = data[(data["home_team"] == team) | (data["away_team"] == team)]
    if team_games.empty:
        print(f"No games found for {team} on {date}")
        return None

    game_pk = team_games["game_pk"].iloc[0]
    game = data[data["game_pk"] == game_pk]

    home = game["home_team"].iloc[0]
    away = game["away_team"].iloc[0]
    is_home = home == team
    opponent = away if is_home else home

    print(f"\n{'Home' if is_home else 'Away'} game: {away} @ {home}")

    # Home team bats in bottom half, away in top half
    team_batting = game[game["inning_topbot"] == ("Bot" if is_home else "Top")]

    # Build lineup: unique batters ordered by first plate appearance
    lineup = (
        team_batting.groupby("batter")
        .agg(
            first_ab=("at_bat_number", "min"),
            num_pa=("at_bat_number", "nunique"),
        )
        .sort_values("first_ab")
        .reset_index()
    )

    # Resolve MLBAM IDs to player names
    player_info = playerid_reverse_lookup(lineup["batter"].tolist(), key_type="mlbam")
    id_to_name = {
        row["key_mlbam"]: f"{row['name_first'].title()} {row['name_last'].title()}"
        for _, row in player_info.iterrows()
    }

    lineup["name"] = lineup["batter"].map(id_to_name).fillna("Unknown")

    # First 9 are starters, rest are substitutes
    starters = lineup.head(9)
    subs = lineup.iloc[9:]

    print(f"\n--- {team} Starting Lineup vs {opponent} ({date}) ---\n")
    for i, (_, row) in enumerate(starters.iterrows(), 1):
        print(f"  {i}. {row['name']:<25} ({row['num_pa']} PA)")

    if not subs.empty:
        print(f"\n--- Substitutes ---\n")
        for _, row in subs.iterrows():
            print(f"     {row['name']:<25} ({row['num_pa']} PA)")

    print(f"\nTotal batters used: {len(lineup)}")
    return lineup


if __name__ == "__main__":
    try:
        result = get_team_lineup(TEAM, DATE)
        if result is None:
            sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
