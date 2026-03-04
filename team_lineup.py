"""CLI for MLB lineup cards.

Thin entry point that wires the data layer to either the text formatter
or JSON output.  Usage:

    python team_lineup.py NYM 2024-07-01          # print to terminal
    python team_lineup.py NYM 2024-07-01 -o       # save .txt files
    python team_lineup.py NYM 2024-07-01 --json   # print JSON to stdout
    python team_lineup.py NYM 2024-07-01 --html --serve  # serve on LAN
"""

import argparse
import functools
import json
import os
import socket
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from lineup_data import TEAM_IDS, get_game_data
from lineup_formatter import format_game
from lineup_html import format_html


def _get_local_ip():
    """Return this machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _serve_file(html_path, port):
    """Serve *html_path* over HTTP and print the LAN URL."""
    directory = os.path.dirname(os.path.abspath(html_path))
    filename = os.path.basename(html_path)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    server = HTTPServer(("0.0.0.0", port), handler)
    local_ip = _get_local_ip()
    url = f"http://{local_ip}:{port}/{filename}"
    print(f"\nServing at {url}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


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
    parser.add_argument(
        "--html",
        nargs="?", const="auto", default=None,
        help="Save an HTML file with sortable tables. Omit value for auto-named file, or pass a path.",
    )
    parser.add_argument(
        "--serve",
        nargs="?", const=8000, default=None, type=int,
        metavar="PORT",
        help="Start a local HTTP server after generating the HTML file. "
             "Defaults to port 8000. Implies --html.",
    )
    args = parser.parse_args()

    # --serve implies --html
    if args.serve is not None and args.html is None:
        args.html = "auto"

    game_data = get_game_data(args.team, args.date)
    if game_data is None:
        sys.exit(1)

    if args.html is not None:
        html_content = format_html(game_data)
        if args.html == "auto":
            away = game_data["away"]["abbrev"]
            home = game_data["home"]["abbrev"]
            html_filename = f"{away}_{home}_{args.date}_lineup.html"
        else:
            html_filename = args.html if args.html.endswith(".html") else f"{args.html}.html"
        with open(html_filename, "w") as f:
            f.write(html_content)
        print(f"Saved to {html_filename}")

        if args.serve is not None:
            _serve_file(html_filename, args.serve)
            return

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
