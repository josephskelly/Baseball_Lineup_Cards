"""HTML formatter for MLB lineup cards.

Takes the structured data from lineup_data.get_game_data() and produces
a self-contained HTML file with sortable tables.
"""

import html


def _esc(val):
    """HTML-escape a string value."""
    return html.escape(str(val)) if val is not None else ""


def _fmt_xwoba(val):
    """Format xwOBA as .345 or -- if missing."""
    if val is None:
        return "--"
    return f".{val * 1000:03.0f}"


def _fmt_pct(val):
    """Format percentage as '45%' or '--' if missing."""
    if val is None:
        return "--"
    return f"{val:.0f}%"


def _sort_val(val):
    """Return a numeric sort value for a data-sort attribute."""
    if val is None:
        return -1
    return val


def _pct_sort_val(val):
    """Return numeric sort value for percentage fields."""
    if val is None:
        return -1
    return val


def _workload_str(workload):
    """Format workload as d1-d2-d3 or --."""
    if not workload:
        return "--"
    return "-".join(
        str(d["pitches"]) if d["pitches"] else "0" for d in workload
    )


def _workload_total(workload):
    """Sum of pitches in last 3 days for sorting."""
    if not workload:
        return -1
    return sum(d["pitches"] or 0 for d in workload)


def _build_team_html(team_abbrev, game_data):
    """Build HTML for a single team's lineup card."""
    date = game_data["date"]
    team = game_data["teams"][team_abbrev]
    away_name = _esc(game_data["away"]["name"])
    home_name = _esc(game_data["home"]["name"])

    position_players = team["position_players"]
    own_starter = team.get("starter")
    own_bullpen = team.get("bullpen", [])
    opp_starter = team.get("opposing_starter")

    starters = [p for p in position_players if p.get("batting_order") is not None]
    bench = [p for p in position_players if p.get("batting_order") is None]
    starters.sort(key=lambda x: x["batting_order"])
    bench.sort(key=lambda x: x["name"])

    parts = []
    parts.append(f'<div class="team-card" id="card-{_esc(team_abbrev)}">')
    parts.append(f'<div class="card-header">')
    parts.append(f'<h2>{_esc(team_abbrev)} Batting Lineup &mdash; {_esc(date)}</h2>')
    parts.append(f'<p>{away_name} @ {home_name}</p>')
    parts.append('</div>')

    # Opposing starter
    if opp_starter:
        parts.append('<div class="opp-starter">')
        num = opp_starter.get("number", "")
        num_str = f"#{num}" if num else ""
        if "xwoba" in opp_starter:
            throws = opp_starter["throws"]
            parts.append(
                f'<strong>Opposing SP:</strong> {num_str} {_esc(opp_starter["name"])} '
                f'({throws}HP)'
            )
            xw = _fmt_xwoba(opp_starter["xwoba"])
            xl = _fmt_xwoba(opp_starter.get("xwoba_L"))
            xr = _fmt_xwoba(opp_starter.get("xwoba_R"))
            pa = opp_starter.get("pa", 0)
            gb = _fmt_pct(opp_starter.get("gb_pct"))
            fb = _fmt_pct(opp_starter.get("fb_pct"))
            parts.append(
                f'<br>xwOBA: {xw} &nbsp; vL: {xl} &nbsp; vR: {xr} '
                f'&nbsp; ({pa} PA) &nbsp; GB: {gb} &nbsp; FB: {fb}'
            )
        else:
            parts.append(
                f'<strong>Opposing SP:</strong> {num_str} {_esc(opp_starter["name"])} '
                f'(no Statcast data)'
            )
        parts.append('</div>')

    # Batting lineup table
    parts.append('<h3>Batting Order</h3>')
    parts.append('<table class="lineup sortable">')
    parts.append('<thead><tr>')
    parts.append('<th data-type="num">#</th>')
    parts.append('<th data-type="num">Uni</th>')
    parts.append('<th data-type="str">Player</th>')
    parts.append('<th data-type="str">Pos</th>')
    parts.append('<th data-type="num">xwOBA</th>')
    parts.append('<th data-type="num">vL</th>')
    parts.append('<th data-type="num">vR</th>')
    parts.append('<th data-type="num">PA</th>')
    parts.append('<th data-type="num">GB%</th>')
    parts.append('<th data-type="num">FB%</th>')
    parts.append('</tr></thead>')
    parts.append('<tbody>')

    for p in starters:
        parts.append(_batter_row(p, is_starter=True))
    if bench:
        parts.append(
            '<tr class="bench-divider"><td colspan="10">Bench</td></tr>'
        )
        for p in bench:
            parts.append(_batter_row(p, is_starter=False))

    parts.append('</tbody></table>')

    # Starting pitcher
    if own_starter:
        parts.append('<h3>Starting Pitcher</h3>')
        parts.append('<table class="lineup sortable">')
        parts.append('<thead><tr>')
        parts.append('<th data-type="num">Uni</th>')
        parts.append('<th data-type="str">Pitcher</th>')
        parts.append('<th data-type="str">Pos</th>')
        parts.append('<th data-type="num">xwOBA</th>')
        parts.append('<th data-type="num">vL</th>')
        parts.append('<th data-type="num">vR</th>')
        parts.append('<th data-type="num">PA</th>')
        parts.append('<th data-type="num">GB%</th>')
        parts.append('<th data-type="num">FB%</th>')
        parts.append('</tr></thead>')
        parts.append('<tbody>')
        parts.append(_pitcher_row(own_starter))
        parts.append('</tbody></table>')

    # Bullpen
    if own_bullpen:
        parts.append('<h3>Bullpen</h3>')
        parts.append('<table class="lineup sortable">')
        parts.append('<thead><tr>')
        parts.append('<th data-type="num">Uni</th>')
        parts.append('<th data-type="str">Pitcher</th>')
        parts.append('<th data-type="str">Pos</th>')
        parts.append('<th data-type="num">xwOBA</th>')
        parts.append('<th data-type="num">vL</th>')
        parts.append('<th data-type="num">vR</th>')
        parts.append('<th data-type="num">PA</th>')
        parts.append('<th data-type="num">GB%</th>')
        parts.append('<th data-type="num">FB%</th>')
        parts.append('<th data-type="num">Pitches</th>')
        parts.append('</tr></thead>')
        parts.append('<tbody>')
        for p in own_bullpen:
            parts.append(_bullpen_row(p))
        parts.append('</tbody></table>')

    parts.append('</div>')  # team-card
    return "\n".join(parts)


def _batter_row(p, is_starter):
    """Build a <tr> for a position player."""
    order = p.get("batting_order")
    order_str = f"{order}." if order else ""
    order_sort = order if order else 99

    num = p.get("number", "")
    num_sort = int(num) if num.isdigit() else 999

    xw = _fmt_xwoba(p.get("xwoba"))
    xl = _fmt_xwoba(p.get("xwoba_L"))
    xr = _fmt_xwoba(p.get("xwoba_R"))
    pa = p.get("pa", 0)
    gb = _fmt_pct(p.get("gb_pct"))
    fb = _fmt_pct(p.get("fb_pct"))

    cls = "starter" if is_starter else "bench"
    return (
        f'<tr class="{cls}">'
        f'<td data-sort="{order_sort}">{_esc(order_str)}</td>'
        f'<td data-sort="{num_sort}">{_esc(num)}</td>'
        f'<td>{_esc(p["name"])}</td>'
        f'<td>{_esc(p["position"])}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba"))}">{xw}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba_L"))}">{xl}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba_R"))}">{xr}</td>'
        f'<td data-sort="{pa}">{pa}</td>'
        f'<td data-sort="{_pct_sort_val(p.get("gb_pct"))}">{gb}</td>'
        f'<td data-sort="{_pct_sort_val(p.get("fb_pct"))}">{fb}</td>'
        f'</tr>'
    )


def _pitcher_row(p):
    """Build a <tr> for a pitcher (starter or bullpen without workload)."""
    num = p.get("number", "")
    num_sort = int(num) if num.isdigit() else 999

    if "xwoba" in p:
        pos = p["throws"] + "HP"
        xw = _fmt_xwoba(p["xwoba"])
        xl = _fmt_xwoba(p.get("xwoba_L"))
        xr = _fmt_xwoba(p.get("xwoba_R"))
        pa = p.get("pa", 0)
        gb = _fmt_pct(p.get("gb_pct"))
        fb = _fmt_pct(p.get("fb_pct"))
    else:
        pos = ""
        xw = xl = xr = "--"
        pa = 0
        gb = fb = "--"

    return (
        f'<tr>'
        f'<td data-sort="{num_sort}">{_esc(num)}</td>'
        f'<td>{_esc(p["name"])}</td>'
        f'<td>{_esc(pos)}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba"))}">{xw}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba_L"))}">{xl}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba_R"))}">{xr}</td>'
        f'<td data-sort="{pa}">{pa}</td>'
        f'<td data-sort="{_pct_sort_val(p.get("gb_pct"))}">{gb}</td>'
        f'<td data-sort="{_pct_sort_val(p.get("fb_pct"))}">{fb}</td>'
        f'</tr>'
    )


def _bullpen_row(p):
    """Build a <tr> for a bullpen pitcher (includes workload column)."""
    num = p.get("number", "")
    num_sort = int(num) if num.isdigit() else 999
    wl = p.get("workload")
    pitches = _workload_str(wl)
    pitches_sort = _workload_total(wl)

    if "xwoba" in p:
        pos = p["throws"] + "HP"
        xw = _fmt_xwoba(p["xwoba"])
        xl = _fmt_xwoba(p.get("xwoba_L"))
        xr = _fmt_xwoba(p.get("xwoba_R"))
        pa = p.get("pa", 0)
        gb = _fmt_pct(p.get("gb_pct"))
        fb = _fmt_pct(p.get("fb_pct"))
    else:
        pos = ""
        xw = xl = xr = "--"
        pa = 0
        gb = fb = "--"

    return (
        f'<tr>'
        f'<td data-sort="{num_sort}">{_esc(num)}</td>'
        f'<td>{_esc(p["name"])}</td>'
        f'<td>{_esc(pos)}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba"))}">{xw}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba_L"))}">{xl}</td>'
        f'<td data-sort="{_sort_val(p.get("xwoba_R"))}">{xr}</td>'
        f'<td data-sort="{pa}">{pa}</td>'
        f'<td data-sort="{_pct_sort_val(p.get("gb_pct"))}">{gb}</td>'
        f'<td data-sort="{_pct_sort_val(p.get("fb_pct"))}">{fb}</td>'
        f'<td data-sort="{pitches_sort}">{_esc(pitches)}</td>'
        f'</tr>'
    )


_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 24px;
}
.team-card {
    max-width: 900px;
    margin: 0 auto 40px auto;
    background: #16213e;
    border-radius: 8px;
    padding: 24px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.card-header {
    text-align: center;
    margin-bottom: 16px;
    border-bottom: 2px solid #0f3460;
    padding-bottom: 12px;
}
.card-header h2 { color: #e94560; margin-bottom: 4px; }
.card-header p { color: #a0a0b0; font-size: 14px; }
.opp-starter {
    background: #0f3460;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 16px;
    font-size: 13px;
    line-height: 1.6;
}
h3 {
    color: #e94560;
    font-size: 14px;
    margin: 18px 0 8px 0;
    text-transform: uppercase;
    letter-spacing: 1px;
}
table.lineup {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
table.lineup th {
    background: #0f3460;
    color: #a0c4ff;
    padding: 6px 8px;
    text-align: right;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    position: relative;
}
table.lineup th:hover { background: #1a4a7a; }
table.lineup th::after {
    content: "";
    display: inline-block;
    width: 12px;
    margin-left: 4px;
    font-size: 10px;
}
table.lineup th.sort-asc::after { content: "▲"; }
table.lineup th.sort-desc::after { content: "▼"; }
table.lineup th:nth-child(1),
table.lineup th:nth-child(2) { text-align: center; }
table.lineup th:nth-child(3),
table.lineup th:nth-child(4) { text-align: left; }
table.lineup td {
    padding: 5px 8px;
    text-align: right;
    border-bottom: 1px solid #1a2a4a;
    white-space: nowrap;
}
table.lineup td:nth-child(1),
table.lineup td:nth-child(2) { text-align: center; color: #a0a0b0; }
table.lineup td:nth-child(3) { text-align: left; color: #ffffff; }
table.lineup td:nth-child(4) { text-align: left; color: #a0c4ff; }
table.lineup tbody tr:hover { background: #1a2a50; }
table.lineup tbody tr.bench { color: #888; }
table.lineup tbody tr.bench td:nth-child(3) { color: #bbb; }
tr.bench-divider td {
    text-align: left !important;
    font-weight: bold;
    color: #a0a0b0;
    padding: 10px 8px 4px 8px;
    border-bottom: 1px solid #0f3460;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
"""

_JS = """\
document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll("table.sortable").forEach(function(table) {
        var headers = table.querySelectorAll("th");
        headers.forEach(function(th, colIdx) {
            th.addEventListener("click", function() {
                sortTable(table, colIdx, th);
            });
        });
    });
});

function sortTable(table, colIdx, th) {
    var tbody = table.querySelector("tbody");
    var rows = Array.from(tbody.querySelectorAll("tr:not(.bench-divider)"));
    var dataType = th.getAttribute("data-type") || "str";

    // Determine sort direction
    var asc = true;
    if (th.classList.contains("sort-asc")) {
        asc = false;
    }

    // Clear sort indicators from sibling headers
    th.closest("thead").querySelectorAll("th").forEach(function(h) {
        h.classList.remove("sort-asc", "sort-desc");
    });
    th.classList.add(asc ? "sort-asc" : "sort-desc");

    rows.sort(function(a, b) {
        var aCell = a.children[colIdx];
        var bCell = b.children[colIdx];
        var aVal, bVal;

        if (dataType === "num") {
            aVal = parseFloat(aCell.getAttribute("data-sort"));
            bVal = parseFloat(bCell.getAttribute("data-sort"));
            if (isNaN(aVal)) aVal = -1;
            if (isNaN(bVal)) bVal = -1;
        } else {
            aVal = aCell.textContent.trim().toLowerCase();
            bVal = bCell.textContent.trim().toLowerCase();
        }

        if (aVal < bVal) return asc ? -1 : 1;
        if (aVal > bVal) return asc ? 1 : -1;
        return 0;
    });

    // Re-append rows (removes bench-divider rows)
    rows.forEach(function(row) {
        tbody.appendChild(row);
    });
}
"""


def format_html(game_data):
    """Generate a self-contained HTML page for all teams in a game.

    Args:
        game_data: The full dict returned by lineup_data.get_game_data().

    Returns:
        A complete HTML string.
    """
    team_cards = []
    for abbrev in game_data["teams"]:
        team_cards.append(_build_team_html(abbrev, game_data))

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Lineup Cards &mdash; {_esc(game_data['date'])}</title>\n"
        f"<style>\n{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        + "\n".join(team_cards) +
        "\n"
        f"<script>\n{_JS}</script>\n"
        "</body>\n"
        "</html>\n"
    )
