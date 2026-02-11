"""Simple test to verify pybaseball can pull Statcast data from Baseball Savant."""

from pybaseball import statcast

# Pull a small sample: one day of Statcast data
print("Fetching Statcast data for 2024-07-01...")
try:
    data = statcast(start_dt="2024-07-01", end_dt="2024-07-01")
except Exception as e:
    print(f"\nError fetching data: {e}")
    raise SystemExit(1)

print(f"\nRows returned: {len(data)}")
print(f"Columns: {len(data.columns)}")
print(f"\nSample columns: {list(data.columns[:10])}")
print(f"\nFirst 10 rows (key fields):")
print(data[["game_date", "player_name", "pitch_type", "release_speed", "events"]].head(10).to_string())
