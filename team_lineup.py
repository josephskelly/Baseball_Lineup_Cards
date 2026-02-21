"""CLI for MLB lineup cards.

Thin entry point that wires the data layer to either the text formatter
or JSON output.  Usage:

    python team_lineup.py NYM 2024-07-01          # print to terminal
    python team_lineup.py NYM 2024-07-01 -o       # save .txt files
    python team_lineup.py NYM 2024-07-01 --json   # print JSON to stdout
"""

import argparse
import json
import sys
from lineup_data import TEAM_IDS, get_game_data
from lineup_formatter import format_game


def main():
    parser = argparse.ArgumentParser(description="MLB lineup cards with Statcast data.")
    parser.add_argument("team", choices=sorted(TEAM_IDS.keys()), help="Team abbreviation (e.g. NYM, LAD, NYY)")
    parser.add_argument("date", help="Game date in YYYY-MM-DD format")
    parser.add_argument(
        "-o", "--output",
        nargs="?", const="auto", default=None,
        help="Save to .txt files. Omit value for auto-named files, or pass a path prefix.",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Print structured JSON to stdout instead of formatted text.",
    )
    args = parser.parse_args()

    game_data = get_game_data(args.team, args.date)
    if game_data is None:
        sys.exit(1)

    if args.json_output:
        print(json.dumps(game_data, indent=2))
        return

    cards = format_game(game_data)
    for abbrev, card in cards.items():
        print(card)
        print()

    if args.output is not None:
        for abbrev, card in cards.items():
            if args.output == "auto":
                filename = f"{abbrev}_{args.date}_lineup.txt"
            else:
                filename = f"{args.output}_{abbrev}.txt"
            with open(filename, "w") as f:
                f.write(card + "\n")
            print(f"Saved to {filename}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
