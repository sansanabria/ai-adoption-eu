"""Check that every number shown on docs/index.html matches the CSVs in Data/.

Run from the repo root:  python tools/check_dashboard.py
Exits 0 when everything matches, 1 and a list of problems otherwise.

The page marks what it wants checked:
  * chart rows / map tiles:  data-chart="<chart>" data-key="<CSV label>" data-value="<CSV value>"
    with the shown value in a child element carrying class "hbar-val", "size-val" or "tile-val"
    and the bar length in an inline style "width:NN%"
  * single figures in text:  data-check="<id>"  (expected text computed below)
"""
from __future__ import annotations

import csv
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data"
PAGE = ROOT / "docs" / "index.html"
CAROUSEL = ROOT / "design" / "linkedin-carousel.html"


def read_csv(name: str) -> list[dict[str, str]]:
    with open(DATA / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fmt(value: float, places: int = 1) -> str:
    """Round half-up on the decimal value, the way the figures are published."""
    quantum = Decimal(1).scaleb(-places)
    return str(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def load_data() -> dict:
    size_col = "EnterpriseAdoptionPct"
    sizes = {r["EnterpriseSize"]: float(r[size_col]) for r in read_csv("AIAdoptionByEnterpriseSize.csv")}
    eu = next(r for r in read_csv("GenAIUseByCountry.csv") if r["Country"].startswith("European Union"))
    return {
        "countries": {r["Country"]: float(r["EnterpriseAdoptionPct"]) for r in read_csv("AIAdoptionByCountry.csv")},
        "codes": {r["Country"]: r["CountryCode"] for r in read_csv("AIAdoptionByCountry.csv")},
        "functions": {
            r["BusinessFunction"]: float(r["PctOfAIUsingEnterprises"])
            for r in read_csv("AIAdoptionByBusinessFunction.csv")
            if r["EnterpriseSize"].startswith("All")
        },
        "sectors": {r["Sector"]: float(r["EnterpriseAdoptionPct"]) for r in read_csv("AIAdoptionBySector.csv")},
        "sizes": sizes,
        "trend": {int(r["Year"]): float(r["EnterpriseAdoptionPct"]) for r in read_csv("AIAdoptionTrendEU.csv")},
        "overall": {r["Metric"]: float(r["Value"]) for r in read_csv("AIAdoptionOverallEU.csv")},
        "occupations": {r["OccupationGroup"]: float(r["HoursSavedPerMonth"]) for r in read_csv("AIAdoptionByOccupation.csv")},
        "genai": {
            "private": float(eu["PctUsedForPrivatePurposes"]),
            "work": float(eu["PctUsedForProfessionalWorkPurposes"]),
            "education": float(eu["PctUsedForFormalEducation"]),
        },
    }


def claim(holds: bool, text: str) -> str:
    """Expected text for a worded claim; a claim the data no longer supports can never match."""
    return text if holds else f"<data no longer supports: {text}>"


def expected_figures(d: dict) -> dict[str, str]:
    """Text each data-check element must contain exactly (an id may appear several times)."""
    t, c, s, o, g = d["trend"], d["countries"], d["sizes"], d["overall"], d["genai"]
    large, small = s["Large (250+)"], s["Small (10-49)"]
    ict, construction = d["sectors"]["Information and Communication"], d["sectors"]["Construction"]
    functions, occ = d["functions"], d["occupations"]
    any_use = o["Uses AI technologies (any use)"]
    return {
        "lede-any": claim(50 < any_use < 60, "More than half"),
        "lede-work": f"{fmt(o['Uses AI for work'], 0)}%",
        "lede-faster": f"{fmt(o['Reports faster task completion (work AI users)'], 0)}%",
        "kpi-enterprise": fmt(t[2025]),
        "kpi-enterprise-delta": f"{fmt(t[2025] - t[2024])} pp",
        "kpi-any-use": fmt(any_use, 0),
        "kpi-work": fmt(o["Uses AI for work"], 0),
        "kpi-faster": fmt(o["Reports faster task completion (work AI users)"], 0),
        "kpi-hours": fmt(o["Average time saved per month (employed AI users)"]),
        "one-in-n-now": f"1 in {round(100 / t[2025])}",
        "one-in-n-2021": f"1 in {round(100 / t[2021])}",
        "trend-growth": claim(t[2025] / t[2021] > 2, "more than doubled"),
        "trend-since-2023": claim((t[2025] - t[2023]) / (t[2025] - t[2021]) > 0.9, "almost all of it since 2023"),
        **{f"trend-{year}": f"{fmt(value)}%" for year, value in t.items()},
        "size-ratio": f"over {int(large / small)}x",
        "functions-top": claim(max(functions, key=functions.get) == "Marketing or Sales", "Sales and marketing"),
        "functions-bottom": claim(min(functions, key=functions.get) == "Logistics", "logistics"),
        "ict-share": f"{int(ict / 10)} in 10",
        "construction-share": f"{int(construction / 10)} in 10",
        "country-top": claim(max(c, key=c.get) == "Denmark", "Denmark"),
        "country-bottom": claim(min(c, key=c.get) == "Romania", "Romania"),
        "dk": f"{fmt(c['Denmark'], 0)}%",
        "ro": f"{fmt(c['Romania'], 0)}%",
        "dk-ro-ratio": f"{int(c['Denmark'] / c['Romania'])}x",
        "eu-average": f"{fmt(t[2025])}%",
        "occ-similar": claim(max(occ.values()) - min(occ.values()) < 1, "similar"),
        "occ-managers": fmt(occ["Managers and Professionals"]),
        "occ-operators": fmt(occ["Plant and Machine Operators / Elementary Occupations"]),
        "occ-students": fmt(occ["Students and Unpaid Workers"]),
        "genai-private": f"{fmt(g['private'], 0)}%",
        "genai-work": f"{fmt(g['work'], 0)}%",
        "genai-private-exact": f"{fmt(g['private'])}%",
        "genai-work-exact": f"{fmt(g['work'])}%",
        "genai-education": f"{fmt(g['education'])}%",
    }


class PageScan(HTMLParser):
    """Collect chart rows (with their shown value and bar width) and data-check figures."""

    VALUE_CLASSES = {"hbar-val", "size-val", "tile-val"}

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self.checks: dict[str, list[str]] = {}
        self._stack: list[dict] = []  # open elements that collect text

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if "data-chart" in a:
            self.rows.append({"chart": a["data-chart"], "key": a.get("data-key"),
                              "value": a.get("data-value"), "shown": None, "width": None})
        if self.rows and "width:" in (a.get("style") or "") and self.rows[-1]["width"] is None:
            m = re.search(r"width:\s*([\d.]+)%", a["style"])
            if m:
                self.rows[-1]["width"] = float(m.group(1))
        if classes & self.VALUE_CLASSES and self.rows:
            self._stack.append({"kind": "shown", "row": self.rows[-1], "text": "", "tag": tag})
        if "data-check" in a:
            self._stack.append({"kind": "check", "id": a["data-check"], "text": "", "tag": tag})

    def handle_data(self, data):
        for item in self._stack:
            item["text"] += data

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1]["tag"] == tag:
            item = self._stack.pop()
            text = " ".join(item["text"].split())
            if item["kind"] == "shown":
                item["row"]["shown"] = text
            else:
                self.checks.setdefault(item["id"], []).append(text)


def check_chart(name: str, rows: list[dict], truth: dict[str, float], problems: list[str],
                places: int = 1, sorted_desc: bool = True, bars: bool = True) -> None:
    got = [r for r in rows if r["chart"] == name]
    keys = [r["key"] for r in got]
    if sorted(keys) != sorted(truth):
        problems.append(f"{name}: labels {sorted(set(keys) ^ set(truth))} differ from the CSV")
        return
    top = max(truth.values())
    for r in got:
        true = truth[r["key"]]
        if r["value"] is None or abs(float(r["value"]) - true) > 1e-9:
            problems.append(f"{name}/{r['key']}: data-value {r['value']} but CSV has {true}")
        shown_ok = r["shown"] in (fmt(true, places), f"{fmt(true, places)}%")
        if not shown_ok:
            problems.append(f"{name}/{r['key']}: shows {r['shown']!r}, expected {fmt(true, places)}")
        if bars and (r["width"] is None or abs(r["width"] - true / top * 100) > 0.2):
            problems.append(f"{name}/{r['key']}: bar width {r['width']} should be {true / top * 100:.1f}")
    if sorted_desc:
        values = [truth[k] for k in keys]
        if values != sorted(values, reverse=True):
            problems.append(f"{name}: not sorted high to low")


def check_page(path: Path, data: dict, full: bool) -> tuple[list[str], int, int]:
    """Verify one page. The dashboard must carry every chart and figure; a derived page such as the
    carousel only has to get the ones it does show right."""
    scan = PageScan()
    scan.feed(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    if full:
        check_chart("countries", scan.rows, data["countries"], problems)
        check_chart("functions", scan.rows, data["functions"], problems)
        check_chart("sectors", scan.rows, data["sectors"], problems)
        check_chart("sizes", scan.rows, data["sizes"], problems, sorted_desc=False)
    check_chart("map", scan.rows, data["countries"], problems, places=0, sorted_desc=False, bars=False)

    expected = expected_figures(data)
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
    data = load_data()
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
    print(f"OK: {marks} chart marks and {figures} figures on {2} pages match the CSVs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
