"""Text formatter for MLB lineup cards.

Takes the structured data from lineup_data.get_game_data() and produces
the ASCII lineup card strings.
"""

from datetime import datetime, timedelta


def format_xwoba(val):
    """Format xwOBA in baseball convention (no leading zero): .345"""
    return f".{val * 1000:03.0f}"


def _fmt_num(p):
    """Format jersey number as '#12' or '   ' if missing."""
    n = p.get("number", "")
    return f"#{n:>2}" if n else "   "


def _fmt_pct(val):
    """Format a percentage value like '45%' or ' --' if missing."""
    return f"{val:.0f}%" if val is not None else " --"


def _pitcher_line(p):
    """Format a single pitcher row."""
    num = _fmt_num(p)
    if "xwoba" not in p:
        return (
            f"      {num} {p['name']:<21} {'':4} {'--':>5}  {'--':>5}"
            f"  {'--':>5}  {'--':>5}  {'--':>4}  {'--':>4}"
        )
    pos = p["throws"] + "HP"
    xw = format_xwoba(p["xwoba"])
    xl = format_xwoba(p["xwoba_L"]) if p.get("xwoba_L") is not None else " -- "
    xr = format_xwoba(p["xwoba_R"]) if p.get("xwoba_R") is not None else " -- "
    pa = p["pa"]
    gb = _fmt_pct(p.get("gb_pct"))
    fb = _fmt_pct(p.get("fb_pct"))
    return (
        f"      {num} {p['name']:<21} {pos:<4} {xw:>5}  {xl:>5}"
        f"  {xr:>5}  {pa:>5}  {gb:>4}  {fb:>4}"
    )


def _player_line(prefix, p):
    """Format a single position-player row."""
    num = _fmt_num(p)
    xw = format_xwoba(p["xwoba"]) if "xwoba" in p else " -- "
    xl = format_xwoba(p["xwoba_L"]) if p.get("xwoba_L") is not None else " -- "
    xr = format_xwoba(p["xwoba_R"]) if p.get("xwoba_R") is not None else " -- "
    pa = p.get("pa", 0)
    gb = _fmt_pct(p.get("gb_pct"))
    fb = _fmt_pct(p.get("fb_pct"))
    return (
        f"  {prefix} {num} {p['name']:<21} {p['position']:<4} {xw:>5}"
        f"  {xl:>5}  {xr:>5}  {pa:>5}  {gb:>4}  {fb:>4}"
    )


def build_lineup_card(team_abbrev, game_data):
    """Format a single team's lineup card from structured game data.

    Args:
        team_abbrev: Team abbreviation key into game_data["teams"].
        game_data: The full dict returned by lineup_data.get_game_data().

    Returns:
        Formatted lineup card string.
    """
    date = game_data["date"]
    team = game_data["teams"][team_abbrev]
    is_home = team["side"] == "home"
    away_name = game_data["away"]["name"]
    home_name = game_data["home"]["name"]

    position_players = team["position_players"]
    own_starter = team.get("starter")
    own_bullpen = team.get("bullpen", [])
    opp_starter = team.get("opposing_starter")

    # Split into starters (in batting order) and bench
    starters = [p for p in position_players if p.get("batting_order") is not None]
    bench = [p for p in position_players if p.get("batting_order") is None]
    starters.sort(key=lambda x: x["batting_order"])
    bench.sort(key=lambda x: x["name"])

    W = 85
    lines = []
    lines.append("=" * W)
    lines.append(f"  {team_abbrev} Batting Lineup — {date}".center(W))
    matchup = f"{'Home' if is_home else 'Away'}: {away_name} @ {home_name}"
    lines.append(matchup.center(W))
    lines.append("=" * W)

    # Opposing starter at the top
    if opp_starter:
        num = _fmt_num(opp_starter)
        if "xwoba" in opp_starter:
            throws = opp_starter["throws"]
            xw = format_xwoba(opp_starter["xwoba"])
            xl = format_xwoba(opp_starter["xwoba_L"]) if opp_starter.get("xwoba_L") is not None else " -- "
            xr = format_xwoba(opp_starter["xwoba_R"]) if opp_starter.get("xwoba_R") is not None else " -- "
            pa = opp_starter["pa"]
            gb = _fmt_pct(opp_starter.get("gb_pct"))
            fb = _fmt_pct(opp_starter.get("fb_pct"))
            lines.append(f"  Opposing SP: {num} {opp_starter['name']} ({throws}HP)")
            lines.append(f"  xwOBA against: {xw}   vL: {xl}   vR: {xr}   ({pa} PA)   GB: {gb}  FB: {fb}")
        else:
            lines.append(f"  Opposing SP: {num} {opp_starter['name']} (no Statcast data)")
        lines.append("  " + "-" * (W - 4))

    hdr = (
        f"  {'#':>2}  {'Uni':>3} {'Player':<21} {'Pos':<4} {'xwOBA':>5}"
        f"  {'vL':>5}  {'vR':>5}  {'PA':>5}  {'GB%':>4}  {'FB%':>4}"
    )
    lines.append(hdr)
    lines.append("  " + "-" * (W - 4))

    if starters:
        for i, p in enumerate(starters, 1):
            lines.append(_player_line(f"{i:>2}.", p))
        if bench:
            lines.append("")
            lines.append("  Bench")
            lines.append("  " + "-" * (W - 4))
            for p in bench:
                lines.append(_player_line("   ", p))
    else:
        all_players = sorted(position_players, key=lambda x: x["name"])
        for p in all_players:
            lines.append(_player_line("   ", p))

    if own_starter:
        lines.append("")
        lines.append(
            f"  {'Starting Pitcher':<29} {'Pos':<4} {'xwOBA':>5}  {'vL':>5}"
            f"  {'vR':>5}  {'PA':>5}  {'GB%':>4}  {'FB%':>4}"
        )
        lines.append("  " + "-" * (W - 4))
        lines.append(_pitcher_line(own_starter))

    if own_bullpen:
        # Build date labels from workload data or derive from game date
        sample_wl = None
        for p in own_bullpen:
            if "workload" in p and p["workload"]:
                sample_wl = p["workload"]
                break

        if sample_wl:
            day_labels = [d["date"][5:] for d in sample_wl]
        else:
            ref = datetime.strptime(date, "%Y-%m-%d")
            day_labels = [(ref - timedelta(days=i)).strftime("%m-%d") for i in range(1, 4)]

        lines.append("")
        pitch_log_hdr = "  ".join(f"{dl:>5}" for dl in day_labels)
        lines.append(
            f"  {'Bullpen':<29} {'Pos':<4} {'xwOBA':>5}  {'vL':>5}  {'vR':>5}"
            f"  {'PA':>5}  {'GB%':>4}  {'FB%':>4}  | {'Pitch Log':^19}"
        )
        lines.append("  " + "-" * (W - 4) + "--+-" + "-" * 19)
        for p in own_bullpen:
            base = _pitcher_line(p)
            wl = p.get("workload")
            if wl:
                counts = "  ".join(
                    f"{d['pitches']:>5}" if d["pitches"] else "    -" for d in wl
                )
            else:
                counts = "  ".join(f"{'--':>5}" for _ in range(3))
            lines.append(f"{base}  | {counts}")
        lines.append(
            f"  {'':29} {'':4} {'':5}  {'':5}  {'':5}"
            f"  {'':5}  {'':4}  {'':4}  | {pitch_log_hdr}"
        )

    lines.append("=" * W)
    return "\n".join(lines)


def format_game(game_data):
    """Format lineup cards for all teams in a game.

    Args:
        game_data: The full dict returned by lineup_data.get_game_data().

    Returns:
        Dict mapping team abbreviation to its formatted lineup card string.
    """
    return {
        abbrev: build_lineup_card(abbrev, game_data)
        for abbrev in game_data["teams"]
    }
