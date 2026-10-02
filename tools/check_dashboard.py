"""Check that every number and claim on the dashboard and the LinkedIn carousel matches the CSVs in Data/.

Run from the repo root:  python tools/check_dashboard.py
Exits 0 when everything matches, 1 and a list of problems otherwise.

The pages mark what they want checked:
  * chart rows and map tiles:  data-chart="<chart>" data-key="<CSV label>" data-value="<CSV value>"
    (plus data-tip-value, data-code), the shown value in a child with class hbar-val, size-val,
    tile-val or purpose-value, and the bar length as an inline "width:NN%" on a bar element
  * single figures and claims in text:  data-check="<id>" (the expected text is computed below)
"""
from __future__ import annotations

import csv
import html
import math
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data"
PAGE = ROOT / "docs" / "index.html"
CAROUSEL = ROOT / "design" / "linkedin-carousel.html"

DISPLAY_CODE = {"EL": "GR"}  # Eurostat writes Greece as EL; readers expect GR
WIDTH_TOLERANCE = 0.06       # bar widths are written with one decimal


class DataError(ValueError):
    """A CSV does not have the shape the pages assume."""


def read_csv(name: str) -> list[dict[str, str]]:
    with open(DATA / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def half_up(value: float | str | Decimal, places: int = 0) -> Decimal:
    """Round half up on the decimal value, the way published figures are rounded."""
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def fmt(value: float | str | Decimal, places: int = 1) -> str:
    return str(half_up(value, places))


def ratio_text(numerator: float, denominator: float) -> str:
    """A ratio rounded half up to a whole number, computed in decimals (no float surprises)."""
    return fmt(Decimal(str(numerator)) / Decimal(str(denominator)), 0)


def cross_section(name: str, key: str, value: str, where: Callable[[dict[str, str]], bool] | None = None) -> tuple[dict[str, float], str]:
    """key -> value for a one year cross section. Rejects duplicate keys and more than one Year,
    which would otherwise silently keep the last row."""
    rows = [r for r in read_csv(name) if where is None or where(r)]
    keys = [r[key] for r in rows]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise DataError(f"{name}: duplicate {key} values {duplicates}")
    years = sorted({r["Year"] for r in rows if r.get("Year")})
    if len(years) > 1:
        raise DataError(f"{name}: more than one Year {years}")
    return {r[key]: float(r[value]) for r in rows}, (years[0] if years else "")


def load_data() -> dict:
    countries, year = cross_section("AIAdoptionByCountry.csv", "Country", "EnterpriseAdoptionPct")
    sectors, _ = cross_section("AIAdoptionBySector.csv", "Sector", "EnterpriseAdoptionPct")
    sizes, _ = cross_section("AIAdoptionByEnterpriseSize.csv", "EnterpriseSize", "EnterpriseAdoptionPct")
    functions, _ = cross_section(
        "AIAdoptionByBusinessFunction.csv", "BusinessFunction", "PctOfAIUsingEnterprises",
        where=lambda r: r["EnterpriseSize"].startswith("All"),
    )
    overall, _ = cross_section("AIAdoptionOverallEU.csv", "Metric", "Value")
    occupation_rows = {r["OccupationGroup"]: r for r in read_csv("AIAdoptionByOccupation.csv")}
    if len(occupation_rows) != len(read_csv("AIAdoptionByOccupation.csv")):
        raise DataError("AIAdoptionByOccupation.csv: duplicate OccupationGroup values")
    trend_rows = read_csv("AIAdoptionTrendEU.csv")
    trend = {int(r["Year"]): float(r["EnterpriseAdoptionPct"]) for r in trend_rows}
    if len(trend) != len(trend_rows):
        raise DataError("AIAdoptionTrendEU.csv: duplicate Year values")
    genai_rows = [r for r in read_csv("GenAIUseByCountry.csv") if r["Country"].startswith("European Union")]
    if len(genai_rows) != 1:
        raise DataError("GenAIUseByCountry.csv: expected exactly one EU row")
    genai = genai_rows[0]
    codes = {r["Country"]: r["CountryCode"] for r in read_csv("AIAdoptionByCountry.csv")}
    return {
        "year": int(year),
        "countries": countries,
        "codes": codes,
        "functions": functions,
        "sectors": sectors,
        "sizes": sizes,
        "trend": trend,
        "overall": overall,
        "occupations": {name: float(r["HoursSavedPerMonth"]) for name, r in occupation_rows.items()},
        "occupation_rows": occupation_rows,
        "genai": {
            "private": float(genai["PctUsedForPrivatePurposes"]),
            "work": float(genai["PctUsedForProfessionalWorkPurposes"]),
            "education": float(genai["PctUsedForFormalEducation"]),
        },
    }


def claim(holds: bool, text: str) -> str:
    """Expected text for a worded claim; a claim the data no longer supports can never match."""
    return text if holds else f"<data no longer supports: {text}>"


def expected_figures(d: dict) -> dict[str, str]:
    """Text each data-check element must contain exactly (an id may appear several times)."""
    t, c, s, o, g = d["trend"], d["countries"], d["sizes"], d["overall"], d["genai"]
    year = d["year"]
    first, second = sorted(t)[:2]
    earlier = max(y for y in t if y < year)
    large, small = s["Large (250+)"], s["Small (10-49)"]
    ict, construction = d["sectors"]["Information and Communication"], d["sectors"]["Construction"]
    functions, occ, rows = d["functions"], d["occupations"], d["occupation_rows"]
    any_use = o["Uses AI technologies (any use)"]
    students = rows["Students and Unpaid Workers"]
    managers = "Managers and Professionals"
    operators = "Plant and Machine Operators / Elementary Occupations"

    return {
        "lede-any": claim(50 < any_use < 60, "More than half"),
        "lede-work": f"{fmt(o['Uses AI for work'], 0)}%",
        "lede-faster": f"{fmt(o['Reports faster task completion (work AI users)'], 0)}%",
        "kpi-enterprise": fmt(t[year]),
        "kpi-enterprise-delta": f"{fmt(Decimal(str(t[year])) - Decimal(str(t[earlier])))} pp",
        "kpi-any-use": fmt(any_use, 0),
        "kpi-work": fmt(o["Uses AI for work"], 0),
        "kpi-faster": fmt(o["Reports faster task completion (work AI users)"], 0),
        "kpi-hours": fmt(o["Average time saved per month (employed AI users)"]),
        "one-in-n-now": f"1 in {ratio_text(100, t[year])}",
        "one-in-n-2021": f"1 in {ratio_text(100, t[first])}",
        "trend-growth": claim(t[year] / t[first] > 2, "more than doubled"),
        "trend-since-2023": claim(
            (t[year] - t[second]) / (t[year] - t[first]) > 0.9, f"almost all of it since {second}"
        ),
        **{f"trend-{y}": f"{fmt(v)}%" for y, v in t.items()},
        "size-ratio": f"over {math.ceil(large / small) - 1}x",
        "functions-top": claim(max(functions, key=functions.get) == "Marketing or Sales", "Sales and marketing"),
        "functions-bottom": claim(min(functions, key=functions.get) == "Logistics", "logistics"),
        "ict-share": f"{ratio_text(ict, 10)} in 10",
        "construction-share": f"{ratio_text(construction, 10)} in 10",
        "country-top": claim(max(c, key=c.get) == "Denmark", "Denmark"),
        "country-bottom": claim(min(c, key=c.get) == "Romania", "Romania"),
        "dk": f"{fmt(c['Denmark'], 0)}%",
        "ro": f"{fmt(c['Romania'], 0)}%",
        "dk-ro-ratio": f"{ratio_text(c['Denmark'], c['Romania'])}x",
        "eu-average": f"{fmt(t[year])}%",
        "occ-similar": claim(max(occ.values()) - min(occ.values()) < 1, "similar"),
        "occ-managers": fmt(occ[managers]),
        "occ-operators": fmt(occ[operators]),
        "occ-students": fmt(occ["Students and Unpaid Workers"]),
        "occ-managers-concern": f"{rows[managers]['DisplacementConcernLevel']} displacement concern",
        "occ-operators-concern": f"{rows[operators]['DisplacementConcernLevel']} displacement concern",
        "occ-students-concern": f"{students['DisplacementConcernLevel']} displacement concern",
        "occ-students-better": f"{fmt(students['PctReportingQualityImprovement'], 0)}%",
        "occ-students-none": f"{fmt(students['PctReportingNoImprovement'], 0)}%",
        "genai-private": f"{fmt(g['private'], 0)}%",
        "genai-work": f"{fmt(g['work'], 0)}%",
    }


class PageScan(HTMLParser):
    """Collect chart rows and data-check figures, tracking open elements so nested markup is read
    whole and a bar width is only taken from a bar element inside its own row."""

    VALUE_CLASSES = {"hbar-val", "size-val", "tile-val", "purpose-value"}
    BAR_CLASSES = {"hbar-fill", "size-bar", "purpose-fill"}
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    WIDTH = re.compile(r"(?<![\w-])width:\s*([\d.]+)%")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.checks: dict[str, list[str]] = {}
        self._open: list[dict] = []

    def _owner_row(self) -> dict | None:
        return next((el["row"] for el in reversed(self._open) if el["row"] is not None), None)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.VOID_TAGS:
            return
        a = {k: (v or "") for k, v in attrs}
        classes = set(a.get("class", "").split())
        row = None
        if "data-chart" in a:
            row = {"chart": a["data-chart"], "key": a.get("data-key"), "value": a.get("data-value"),
                   "tip_value": a.get("data-tip-value"), "code": a.get("data-code"),
                   "shown": None, "width": None, "tile_code": None}
            self.rows.append(row)
        owner = row or self._owner_row()
        collectors: list[dict] = []
        if owner is not None:
            if classes & self.BAR_CLASSES and owner["width"] is None:
                match = self.WIDTH.search(a.get("style", ""))
                if match:
                    owner["width"] = float(match.group(1))
            if classes & self.VALUE_CLASSES:
                collectors.append({"kind": "shown", "ref": owner, "text": ""})
            if "tile-code" in classes:
                collectors.append({"kind": "tile_code", "ref": owner, "text": ""})
        if "data-check" in a:
            collectors.append({"kind": "check", "ref": a["data-check"], "text": ""})
        self._open.append({"tag": tag, "row": row, "collectors": collectors})

    def handle_data(self, data: str) -> None:
        for el in self._open:
            for collector in el["collectors"]:
                collector["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID_TAGS:
            return
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i]["tag"] == tag:
                for el in self._open[i:]:
                    self._finish(el)
                del self._open[i:]
                return

    def _finish(self, el: dict) -> None:
        for collector in el["collectors"]:
            text = " ".join(collector["text"].split())
            if collector["kind"] == "shown":
                collector["ref"]["shown"] = text
            elif collector["kind"] == "tile_code":
                collector["ref"]["tile_code"] = text
            else:
                self.checks.setdefault(collector["ref"], []).append(text)


def check_chart(
    name: str,
    rows: list[dict],
    truth: dict[str, float],
    problems: list[str],
    *,
    places: int = 1,
    sorted_desc: bool = True,
    bars: bool = True,
    scale_top: float | None = None,
    tips: bool = True,
    codes: dict[str, str] | None = None,
) -> None:
    """Compare one chart's rows with the CSV: labels, values, bar lengths, tooltips, codes, order."""
    got = [r for r in rows if r["chart"] == name]
    keys = [r["key"] for r in got]
    if sorted(keys) != sorted(truth):
        problems.append(f"{name}: labels {sorted(set(keys) ^ set(truth))} differ from the CSV")
        return
    top = scale_top or max(truth.values())
    for r in got:
        true = truth[r["key"]]
        where = f"{name}/{r['key']}"
        if r["value"] is None or abs(float(r["value"]) - true) > 1e-9:
            problems.append(f"{where}: data-value {r['value']} but CSV has {true}")
        if r["shown"] not in (fmt(true, places), f"{fmt(true, places)}%"):
            problems.append(f"{where}: shows {r['shown']!r}, expected {fmt(true, places)}")
        if bars:
            wanted = true / top * 100
            if r["width"] is None or abs(r["width"] - wanted) > WIDTH_TOLERANCE:
                problems.append(f"{where}: bar width {r['width']} should be {wanted:.1f}")
        if tips and r["tip_value"] != f"{fmt(true)}%":
            problems.append(f"{where}: tooltip shows {r['tip_value']!r}, expected {fmt(true)}%")
        if codes is not None:
            code = DISPLAY_CODE.get(codes[r["key"]], codes[r["key"]])
            if r["code"] != code:
                problems.append(f"{where}: code {r['code']!r}, expected {code!r}")
            if r["tile_code"] is not None and r["tile_code"] != code:
                problems.append(f"{where}: tile label {r['tile_code']!r}, expected {code!r}")
    if sorted_desc:
        values = [truth[k] for k in keys]
        if values != sorted(values, reverse=True):
            problems.append(f"{name}: not sorted high to low")


def check_meta(text: str, expected: dict[str, str]) -> list[str]:
    """The share text in the page head quotes figures too; they must still be true."""
    problems = []
    for pattern, label in ((r'<meta name="description" content="([^"]*)"', "description"),
                           (r'<meta property="og:description" content="([^"]*)"', "og:description")):
        match = re.search(pattern, text)
        if not match:
            problems.append(f"meta {label} is missing")
            continue
        content = html.unescape(match.group(1))
        for key in ("dk", "ro", "one-in-n-now"):
            if expected[key] not in content:
                problems.append(f"meta {label} does not contain {expected[key]!r} ({key})")
    return problems


def check_page(path: Path, data: dict, full: bool) -> tuple[list[str], int, int]:
    """Verify one page. The dashboard must carry every chart and figure; a derived page such as the
    carousel only has to get the ones it does show right."""
    text = path.read_text(encoding="utf-8")
    scan = PageScan()
    scan.feed(text)
    scan.close()
    problems: list[str] = []
    expected = expected_figures(data)

    if full:
        check_chart("countries", scan.rows, data["countries"], problems, codes=data["codes"])
        check_chart("functions", scan.rows, data["functions"], problems)
        check_chart("sectors", scan.rows, data["sectors"], problems)
        check_chart("sizes", scan.rows, data["sizes"], problems, sorted_desc=False)
        check_chart("genai", scan.rows, data["genai"], problems, sorted_desc=False, scale_top=100.0, tips=False)
        problems += check_meta(text, expected)
    check_chart("map", scan.rows, data["countries"], problems, places=0, sorted_desc=False, bars=False, codes=data["codes"])

    for key, want in expected.items():
        if key not in scan.checks:
            if full:
                problems.append(f"missing figure data-check={key!r} (expected {want!r})")
            continue
        for shown in scan.checks[key]:
            if shown != want:
                problems.append(f"figure {key}: page shows {shown!r}, data says {want!r}")
    for key in scan.checks.keys() - expected.keys():
        problems.append(f"unknown data-check id {key!r}")

    label = path.relative_to(ROOT).as_posix()
    return [f"{label}: {p}" for p in problems], len(scan.rows), sum(len(v) for v in scan.checks.values())


def main() -> int:
    try:
        data = load_data()
    except DataError as error:
        print(f"FAIL: {error}")
        return 1
    problems: list[str] = []
    marks = figures = 0
    for path, full in ((PAGE, True), (CAROUSEL, False)):
        found, m, f = check_page(path, data, full)
        problems += found
        marks += m
        figures += f

    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        print("\n".join(f"  - {p}" for p in problems))
        return 1
    print(f"OK: {marks} chart marks and {figures} figures on 2 pages match the CSVs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
