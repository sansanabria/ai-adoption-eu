"""Regenerate the chart markup in docs/index.html, the LinkedIn carousel and the share card from the CSVs in Data/.

Run from the repo root:  python tools/build_charts.py
Each target file marks the regions it wants filled with
    <!-- gen:NAME --> ... <!-- /gen:NAME -->
and everything between a pair of markers is replaced. Running it twice changes nothing.
Afterwards run tools/check_dashboard.py to confirm the pages match the data.
"""
from __future__ import annotations

import html
import math
import re
import sys
from pathlib import Path

from check_dashboard import DISPLAY_CODE, axis_top, fmt, load_data, round_up  # noqa: F401  (round_up is re-exported)

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "docs" / "index.html",
    ROOT / "design" / "linkedin-carousel.html",
    ROOT / "design" / "og-image.html",
]

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
GENAI_LABELS = {"private": "Private purposes", "work": "Professional or work purposes", "education": "Formal education"}

AXIS_TICKS = (0, 10, 20, 30, 40)   # percent
UNITS_ACROSS = 29.0                # plot width in dot diameters; the stylesheet keeps a dot at or below 1/29 of it
DOT_GAP = 0.15                     # clear space between two dots, in dot diameters


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def ranked(values: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(values.items(), key=lambda kv: kv[1], reverse=True)


def bar_row(chart: str, key: str, label: str, value: float, top: float) -> str:
    shown = f"{fmt(value)}%"
    return (f'<div class="hbar-row" data-chart="{chart}" data-key="{esc(key)}" data-value="{value}" '
            f'data-tip-label="{esc(label)}" data-tip-value="{shown}">'
            f'<span class="hbar-label">{esc(label)}</span>'
            f'<span class="hbar-track"><span class="hbar-fill" style="width:{value / top * 100:.1f}%"></span></span>'
            f'<span class="hbar-val">{shown}</span></div>')


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


def swarm(positions: list[float], gap: float = DOT_GAP) -> list[float]:
    """Vertical offsets, in dot diameters, that stop equal sized dots from overlapping.

    `positions` are the dots' horizontal centres in dot diameters, in the order they are placed.
    Each dot takes the free spot nearest the centre line, which gives a compact, even swarm."""
    need = 1.0 + gap
    placed: list[tuple[float, float]] = []
    for x in positions:
        candidates = {0.0}
        for px, py in placed:
            dx = abs(x - px)
            if dx < need:
                reach = math.sqrt(need * need - dx * dx)
                candidates.update((py + reach, py - reach))
        free = [y for y in candidates if all((x - px) ** 2 + (y - py) ** 2 >= need * need - 1e-9 for px, py in placed)]
        fallback = max((py for _, py in placed), default=0.0) + need
        placed.append((x, min(free, key=lambda y: (abs(y), y)) if free else fallback))
    return [y for _, y in placed]


def dot_plot(d: dict) -> str:
    """One dot per country on a single axis, the EU average as a line, the two extremes labelled."""
    countries, codes = d["countries"], d["codes"]
    eu = d["trend"][d["year"]]                               # same year as the countries being compared
    top = axis_top(countries)
    ordered = sorted(countries.items(), key=lambda kv: kv[1])    # low to high: the order the dots are placed in
    order_high_to_low = ranked(countries)
    ranks = {name: i for i, (name, _) in enumerate(order_high_to_low, start=1)}
    (high, high_value), (low, low_value) = order_high_to_low[0], order_high_to_low[-1]

    offsets = swarm([value / top * UNITS_ACROSS for _, value in ordered])
    middle = (max(offsets) + min(offsets)) / 2
    y_of = {name: y - middle for (name, _), y in zip(ordered, offsets)}
    span = max(y_of.values()) - min(y_of.values()) + 1.0          # height of the field in dot diameters
    highest_edge = min(y_of.values())

    def position(value: float) -> str:
        return f"{value / top * 100:.2f}"

    dots = []
    for name, value in ordered:
        code = DISPLAY_CODE.get(codes[name], codes[name])
        role = " hi" if name == high else " lo" if name == low else ""
        dots.append(
            f'<span class="dp-dot{role}" data-chart="countries" data-key="{esc(name)}" data-value="{value}" '
            f'data-code="{code}" data-tip-label="{esc(name)}" data-tip-value="{fmt(value)}%" '
            f'data-tip-note="{ordinal(ranks[name])} of {len(countries)}" '
            f'style="--v:{position(value)};--y:{y_of[name]:.3f}"><span class="dp-code">{code}</span></span>')

    def callout(kind: str, name: str, value: float, checks: tuple[str, str]) -> str:
        lead = y_of[name] - highest_edge                           # gap from the field's top edge down to this dot
        return (f'<span class="dp-call dp-call-{kind}" style="--v:{position(value)};--lead:{lead:.3f}">'
                f'<span data-check="{checks[0]}">{esc(name)}</span> '
                f'<b data-check="{checks[1]}">{fmt(value, 0)}%</b></span>')

    grid = "".join(f'<span class="dp-grid" style="--v:{position(t)}"></span>' for t in AXIS_TICKS if t <= top)
    axis = "".join(f'<span style="--v:{position(t)}">{t}%</span>' for t in AXIS_TICKS if t <= top)
    label = (f"Each dot is an EU country, placed by the share of its companies using AI. {high} is highest at "
             f"{fmt(high_value, 0)}% and {low} lowest at {fmt(low_value, 0)}%. The ranked list below has every value.")
    return (
        f'<div class="dp" style="--span:{span:.3f}"><div class="dp-inner">\n'
        f'<div class="dp-avg-row"><span class="dp-avg-label" style="--v:{position(eu)}">EU average '
        f'<b data-check="eu-average">{fmt(eu)}%</b></span></div>\n'
        f'<div class="dp-call-row">{callout("lo", low, low_value, ("country-bottom", "ro"))}'
        f'{callout("hi", high, high_value, ("country-top", "dk"))}</div>\n'
        f'<div class="dp-field" role="img" aria-label="{esc(label)}">{grid}'
        f'<span class="dp-avg" data-chart="eu-average" data-key="EU" data-value="{eu}" style="--v:{position(eu)}"></span>\n'
        + "\n".join(dots) +
        f'\n</div>\n<div class="dp-axis" aria-hidden="true">{axis}</div>\n</div></div>'
    )


def country_table(d: dict) -> str:
    """Every country, ranked: the full list behind the dot plot, and its accessible twin."""
    countries, codes = d["countries"], d["codes"]
    rows = []
    for rank, (name, value) in enumerate(ranked(countries), start=1):
        code = DISPLAY_CODE.get(codes[name], codes[name])
        rows.append(
            f'<li data-chart="countries-table" data-key="{esc(name)}" data-value="{value}" data-code="{code}" '
            f'data-tip-label="{esc(name)}" data-tip-value="{fmt(value)}%" '
            f'data-tip-note="{ordinal(rank)} of {len(countries)}">'
            f'<span class="rk">{rank}</span><span class="nm">{esc(name)}</span>'
            f'<span class="tbl-val">{fmt(value)}%</span></li>')
    return ('<ol class="rank-list" aria-label="All countries, ranked by share of companies using AI">\n'
            + "\n".join(rows) + "\n</ol>")


def trend_chart(d: dict) -> str:
    t = d["trend"]
    years = sorted(t)
    top = round_up(max(t.values()) * 1.2)            # headroom for the end label
    # Labelled points: first, second (the flat stretch) and last. The others live in tooltips and the table.
    labels = {years[0]: "below start", years[1]: "below", years[-1]: "end"}

    def pos(year: int) -> tuple[float, float]:
        return (year - years[0]) / (years[-1] - years[0]) * 100, t[year] / top * 100

    points = [pos(year) for year in years]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.2f} {100 - y:.2f}" for i, (x, y) in enumerate(points))
    parts = ['<div class="trend-plot">']
    parts += [f'<div class="trend-grid" style="--y:{v / top * 100:g}"><span>{v}%</span></div>' for v in range(0, int(top), 10)]
    parts.append('<svg class="trend-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" '
                 f'focusable="false"><path class="trend-area" d="{path} L100 100 L0 100 Z"/>'
                 f'<path class="trend-line" d="{path}"/></svg>')
    for year, (x, y) in zip(years, points):
        shown = f"{fmt(t[year])}%"
        parts.append(f'<button class="trend-pt" type="button" style="--x:{x:.2f};--y:{y:.2f}" '
                     f'aria-label="{year}: {shown}" data-tip-label="{year}" data-tip-value="{shown}"></button>')
        if year in labels:
            parts.append(f'<span class="trend-lbl {labels[year]}" style="--x:{x:.2f};--y:{y:.2f}" '
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


def genai_meters(d: dict) -> str:
    return "\n".join(
        f'<div data-chart="genai" data-key="{key}" data-value="{value}">'
        f'<p class="purpose-name">{esc(GENAI_LABELS[key])}</p>'
        f'<p class="purpose-value">{fmt(value)}%</p>'
        f'<div class="purpose-track"><div class="purpose-fill" style="width:{fmt(value)}%"></div></div></div>'
        for key, value in d["genai"].items()
    )


def build_snippets() -> dict[str, str]:
    d = load_data()
    return {
        "trend": trend_chart(d),
        "dotplot": dot_plot(d),
        "country-table": country_table(d),
        "functions": simple_bars("functions", d["functions"], FUNCTION_LABELS),
        "sectors": simple_bars("sectors", d["sectors"], SECTOR_LABELS),
        "sizes": size_rows(d),
        "genai": genai_meters(d),
    }


# Regions each target must contain, so a deleted or misspelt marker fails loudly instead of leaving stale charts.
REQUIRED_REGIONS = {
    "docs/index.html": {"trend", "sizes", "functions", "sectors", "dotplot", "country-table", "genai"},
    "design/linkedin-carousel.html": {"dotplot"},
    "design/og-image.html": {"dotplot"},
}
OPEN_MARKER = re.compile(r"<!--\s*gen:([\w-]+)\s*-->")
CLOSE_MARKER = re.compile(r"<!--\s*/gen:([\w-]+)\s*-->")
ANY_MARKER = re.compile(r"<!--\s*/?gen:")
MARKER = re.compile(r"(<!--\s*gen:(?P<name>[\w-]+)\s*-->)(?P<body>.*?)(<!--\s*/gen:(?P=name)\s*-->)", re.S)


def check_markers(text: str, required: set[str], label: str) -> None:
    opens, closes = OPEN_MARKER.findall(text), CLOSE_MARKER.findall(text)
    if len(ANY_MARKER.findall(text)) != len(opens) + len(closes) or sorted(opens) != sorted(closes):
        raise ValueError(f"{label}: unbalanced or malformed gen markers (open {sorted(opens)}, close {sorted(closes)})")
    missing = required - set(opens)
    if missing:
        raise ValueError(f"{label}: missing region(s) {sorted(missing)}")


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
        label = path.relative_to(ROOT).as_posix()
        check_markers(before, REQUIRED_REGIONS.get(label, set()), label)
        after = inject(before, snippets)
        found = MARKER.findall(before)
        if after != before:
            path.write_text(after, encoding="utf-8", newline="")
        print(f"{path.relative_to(ROOT)}: {len(found)} region(s), {'updated' if after != before else 'unchanged'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
