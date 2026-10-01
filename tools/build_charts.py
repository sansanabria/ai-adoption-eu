"""Regenerate the chart markup in docs/index.html (and the carousel) from the CSVs in Data/.

Run from the repo root:  python tools/build_charts.py
Each target file marks the regions it wants filled with
    <!-- gen:NAME --> ... <!-- /gen:NAME -->
and everything between a pair of markers is replaced. Running it twice changes nothing.
Afterwards run tools/check_dashboard.py to confirm the page matches the data.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from check_dashboard import fmt, load_data

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "docs" / "index.html", ROOT / "design" / "linkedin-carousel.html"]

# Sequential blue ramp, steps 100 -> 700 (dataviz reference palette). Step 450 (#2a78d6) is left
# out: neither white nor ink labels reach 4.5:1 on it, and every other step clears it with one.
RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
        "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
MAP_MAX = 45.0            # top of the colour scale, in percent
INK, WHITE = "#0b0b0b", "#ffffff"

# Tile map: (row, column) of each member state on a 7 x 7 grid, roughly where it sits in Europe.
TILES = {
    "Sweden": (1, 5), "Finland": (1, 6),
    "Ireland": (2, 1), "Denmark": (2, 4), "Estonia": (2, 7),
    "Netherlands": (3, 3), "Germany": (3, 4), "Poland": (3, 5), "Lithuania": (3, 6), "Latvia": (3, 7),
    "Belgium": (4, 2), "Luxembourg": (4, 3), "Czechia": (4, 4), "Slovakia": (4, 5),
    "France": (5, 2), "Austria": (5, 4), "Hungary": (5, 5), "Romania": (5, 6),
    "Portugal": (6, 1), "Spain": (6, 2), "Italy": (6, 3), "Slovenia": (6, 4), "Croatia": (6, 5), "Bulgaria": (6, 6),
    "Malta": (7, 3), "Greece": (7, 6), "Cyprus": (7, 7),
}
DISPLAY_CODE = {"EL": "GR"}  # Eurostat writes Greece as EL; readers expect GR

FUNCTION_LABELS = {
    "Marketing or Sales": "Marketing or sales",
    "Business Administration or Management": "Business administration or management",
    "Accounting, Controlling or Finance": "Accounting, controlling or finance",
    "Production Processes": "Production processes",
    "ICT Security": "ICT security",
    "R&D or Innovation": "R&D or innovation",
    "Logistics": "Logistics",
}
SECTOR_LABELS = {
    "Information and Communication": "Information & communication",
    "Professional, Scientific and Technical Activities": "Professional, scientific & technical",
    "Real Estate Activities": "Real estate",
    "Administrative and Support Service": "Administrative & support services",
    "Wholesale and Retail Trade": "Wholesale & retail trade",
    "Manufacturing": "Manufacturing",
    "Accommodation and Food Service": "Accommodation & food service",
    "Construction": "Construction",
}
SIZES = [  # CSV label, label on the page, ordinal colour class
    ("Small (10-49)", "Small, 10–49 staff", "ord-1"),
    ("Medium (50-249)", "Medium, 50–249 staff", "ord-2"),
    ("Large (250+)", "Large, 250+ staff", "ord-3"),
    ("All (10+)", "All companies", "ord-ref"),
]


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def label_colour(fill: str) -> str:
    best = max((WHITE, INK), key=lambda ink: contrast(fill, ink))
    if contrast(fill, best) < 4.5:
        raise ValueError(f"no label colour reaches 4.5:1 on {fill}")
    return best


def bar_row(chart: str, key: str, label: str, value: float, top: float, extra: str = "", dense: bool = False) -> str:
    shown = f"{fmt(value)}%"
    cls = "hbar-row dense" if dense else "hbar-row"
    return (f'<div class="{cls}" data-chart="{chart}" data-key="{esc(key)}" data-value="{value}"{extra} '
            f'data-tip-label="{esc(label)}" data-tip-value="{shown}">'
            f'<span class="hbar-label">{esc(label)}</span>'
            f'<span class="hbar-track"><span class="hbar-fill" style="width:{value / top * 100:.1f}%"></span></span>'
            f'<span class="hbar-val">{shown}</span></div>')


def ranked(values: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(values.items(), key=lambda kv: kv[1], reverse=True)


def country_list(d: dict) -> str:
    countries, eu = d["countries"], d["trend"][2025]
    top = max(countries.values())
    rows = []
    for rank, (name, value) in enumerate(ranked(countries), start=1):
        code = DISPLAY_CODE.get(d["codes"][name], d["codes"][name])
        extra = f' data-code="{code}" data-tip-note="{ordinal(rank)} of {len(countries)}"'
        rows.append(bar_row("countries", name, name, value, top, extra, dense=True))
    head = ('<div class="hbar-row dense ref-head" aria-hidden="true"><span></span><span class="hbar-track">'
            f'<span class="ref-label">EU average <span data-check="eu-average">{fmt(eu)}%</span></span>'
            '</span><span></span></div>')
    return (f'<div class="hbar-chart dense has-ref" id="country-chart" style="--ref:{eu / top * 100:.1f}%">\n'
            + "\n".join([head, *rows]) + "\n</div>")


def map_tiles(d: dict) -> str:
    countries = d["countries"]
    ranks = {name: i for i, (name, _) in enumerate(ranked(countries), start=1)}
    tiles = []
    for name, (row, col) in sorted(TILES.items(), key=lambda kv: kv[1]):
        value = countries[name]
        step = max(0, min(len(RAMP) - 1, round(value / MAP_MAX * (len(RAMP) - 1))))
        light, dark = RAMP[step], RAMP[len(RAMP) - 1 - step]
        code = DISPLAY_CODE.get(d["codes"][name], d["codes"][name])
        tiles.append(
            f'<div class="tile" style="grid-area:{row}/{col};--fl:{light};--tl:{label_colour(light)};'
            f'--fd:{dark};--td:{label_colour(dark)}" data-chart="map" data-key="{esc(name)}" data-value="{value}" '
            f'data-code="{code}" data-tip-label="{esc(name)}" data-tip-value="{fmt(value)}%" '
            f'data-tip-note="{ordinal(ranks[name])} of {len(countries)}">'
            f'<span class="tile-code">{code}</span><span class="tile-val">{fmt(value, 0)}</span></div>')
    if len(tiles) != len(countries):
        raise ValueError("tile layout and country list disagree")
    return "\n".join(tiles)


def simple_bars(chart: str, values: dict[str, float], labels: dict[str, str]) -> str:
    top = max(values.values())
    return "\n".join(bar_row(chart, key, labels[key], value, top) for key, value in ranked(values))


def size_rows(d: dict) -> str:
    sizes = d["sizes"]
    top = max(sizes.values())
    rows = []
    for key, label, cls in SIZES:
        value = sizes[key]
        rows.append(
            f'<div class="size-row{" size-ref" if cls == "ord-ref" else ""}" data-chart="sizes" data-key="{esc(key)}" '
            f'data-value="{value}" data-tip-label="{esc(label)}" data-tip-value="{fmt(value)}%">'
            f'<div class="size-top"><span class="size-name">{esc(label)}</span>'
            f'<span class="size-val">{fmt(value)}%</span></div>'
            f'<div class="size-bar {cls}" style="width:{value / top * 100:.1f}%"></div></div>')
    return "\n".join(rows)


def map_legend(d: dict) -> str:
    eu = d["trend"][2025]
    ticks = "".join(f'<span style="left:{v / MAP_MAX * 100:.1f}%">{v}%</span>' for v in (0, 40))
    return (f'<div class="scale-legend" aria-hidden="true" style="--scale-l:linear-gradient(90deg,{",".join(RAMP)});'
            f'--scale-d:linear-gradient(90deg,{",".join(reversed(RAMP))})">'
            f'<div class="scale-bar"><span class="scale-avg" style="left:{eu / MAP_MAX * 100:.1f}%"></span></div>'
            f'<div class="scale-ticks">{ticks}<span class="scale-avg-label" style="left:{eu / MAP_MAX * 100:.1f}%">'
            'EU average</span></div></div>')


TREND_TOP = 25.0                  # top of the y axis, in percent
TREND_GRID = (0, 10, 20)
TREND_LABELS = {2021: "below start", 2023: "below", 2025: "end"}  # other years: tooltip and table


def trend_chart(d: dict) -> str:
    t = d["trend"]
    years = sorted(t)

    def pos(year: int) -> tuple[float, float]:
        return (year - years[0]) / (years[-1] - years[0]) * 100, t[year] / TREND_TOP * 100

    points = [pos(year) for year in years]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.2f} {100 - y:.2f}" for i, (x, y) in enumerate(points))
    parts = ['<div class="trend-plot">']
    parts += [f'<div class="trend-grid" style="--y:{v / TREND_TOP * 100:g}"><span>{v}%</span></div>' for v in TREND_GRID]
    parts.append('<svg class="trend-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" '
                 f'focusable="false"><path class="trend-area" d="{path} L100 100 L0 100 Z"/>'
                 f'<path class="trend-line" d="{path}"/></svg>')
    for year, (x, y) in zip(years, points):
        shown = f"{fmt(t[year])}%"
        parts.append(f'<button class="trend-pt" type="button" style="--x:{x:.2f};--y:{y:.2f}" '
                     f'aria-label="{year}: {shown}" data-tip-label="{year}" data-tip-value="{shown}"></button>')
        if year in TREND_LABELS:
            parts.append(f'<span class="trend-lbl {TREND_LABELS[year]}" style="--x:{x:.2f};--y:{y:.2f}" '
                         f'aria-hidden="true" data-check="trend-{year}">{shown}</span>')
    parts.append("</div>")
    parts.append('<div class="trend-x" aria-hidden="true">'
                 + "".join(f'<span style="--x:{pos(year)[0]:.2f}">{year}</span>' for year in years) + "</div>")
    rows = "".join(f'<tr><th scope="row">{year}</th><td data-check="trend-{year}">{fmt(t[year])}%</td></tr>'
                   for year in years)
    # Wrapped in a div: a table ignores the 1px width of .sr-only and would widen the page on phones.
    parts.append('<div class="sr-only"><table><caption>Share of EU enterprises using AI, by year</caption>'
                 f'<thead><tr><th scope="col">Year</th><th scope="col">Share</th></tr></thead><tbody>{rows}</tbody>'
                 '</table></div>')
    return "\n".join(parts)


def build_snippets() -> dict[str, str]:
    d = load_data()
    return {
        "trend": trend_chart(d),
        "countries-list": country_list(d),
        "map-tiles": map_tiles(d),
        "map-legend": map_legend(d),
        "functions": simple_bars("functions", d["functions"], FUNCTION_LABELS),
        "sectors": simple_bars("sectors", d["sectors"], SECTOR_LABELS),
        "sizes": size_rows(d),
    }


MARKER = re.compile(r"(<!-- gen:(?P<name>[\w-]+) -->)(?P<body>.*?)(<!-- /gen:(?P=name) -->)", re.S)


def inject(text: str, snippets: dict[str, str]) -> str:
    def fill(m: re.Match) -> str:
        name = m.group("name")
        if name not in snippets:
            raise KeyError(f"no generator for marker gen:{name}")
        return f"{m.group(1)}\n{snippets[name]}\n{m.group(4)}"
    return MARKER.sub(fill, text)


def main() -> int:
    snippets = build_snippets()
    for path in TARGETS:
        if not path.exists():
            print(f"skip {path.relative_to(ROOT)} (not found)")
            continue
        before = path.read_text(encoding="utf-8")
        after = inject(before, snippets)
        found = MARKER.findall(before)
        if after != before:
            path.write_text(after, encoding="utf-8", newline="")
        print(f"{path.relative_to(ROOT)}: {len(found)} region(s), {'updated' if after != before else 'unchanged'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
