"""Tests for tools/check_dashboard.py and tools/build_charts.py.

Run from the repo root:  python -m pytest tests --cov=tools --cov-report=term-missing
"""
from __future__ import annotations

import copy
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_charts as bc  # noqa: E402
import check_dashboard as cd  # noqa: E402


@pytest.fixture(scope="module")
def data() -> dict:
    return cd.load_data()


@pytest.fixture()
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway copy of the three generated pages, with both tools pointed at it."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "design").mkdir()
    shutil.copy(cd.PAGE, tmp_path / "docs" / "index.html")
    shutil.copy(cd.CAROUSEL, tmp_path / "design" / "linkedin-carousel.html")
    shutil.copy(cd.OG_CARD, tmp_path / "design" / "og-image.html")
    pages = (tmp_path / "docs" / "index.html", tmp_path / "design" / "linkedin-carousel.html",
             tmp_path / "design" / "og-image.html")
    for module in (cd, bc):
        monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(cd, "PAGE", pages[0])
    monkeypatch.setattr(cd, "CAROUSEL", pages[1])
    monkeypatch.setattr(cd, "OG_CARD", pages[2])
    monkeypatch.setattr(bc, "TARGETS", list(pages))
    return tmp_path


def row(chart: str = "c", key: str = "k", value: str = "10", shown: str | None = "10.0%", extent: float | None = 100.0,
        tip: str | None = "10.0%", code: str | None = None, label_code: str | None = None) -> dict:
    return {"chart": chart, "key": key, "value": value, "shown": shown, "extent": extent,
            "tip_value": tip, "code": code, "label_code": label_code}


# ---------------------------------------------------------------- rounding and claims

def test_fmt_rounds_half_up_not_to_even() -> None:
    assert cd.fmt(2.5, 0) == "3"
    assert cd.fmt(0.125, 2) == "0.13"
    assert cd.fmt(Decimal("20.0") - Decimal("13.55")) == "6.5"   # float subtraction would give 6.4


def test_ratio_text_is_computed_in_decimals() -> None:
    assert cd.ratio_text(100, 8.0) == "13"       # 12.5 rounds half up, not to even
    assert cd.ratio_text(42.03, 5.21) == "8"


def test_axis_top_rounds_the_data_up_to_a_clean_number(data: dict) -> None:
    assert cd.round_up(42.03) == 45 and cd.round_up(45) == 45 and cd.round_up(19.95 * 1.2) == 25
    assert cd.axis_top(data["countries"]) == 45


def test_claim_cannot_match_once_the_data_stops_supporting_it() -> None:
    assert cd.claim(True, "more than doubled") == "more than doubled"
    assert cd.claim(False, "more than doubled") != "more than doubled"


def test_expected_figures_match_the_published_numbers(data: dict) -> None:
    expected = cd.expected_figures(data)
    assert expected["one-in-n-now"] == "1 in 5"
    assert expected["dk-ro-ratio"] == "8x"
    assert expected["size-ratio"] == "over 3x"
    assert expected["kpi-enterprise-delta"] == "6.5 pp"
    assert expected["occ-managers-concern"] == "Lower displacement concern"


def test_claims_flip_when_the_data_changes(data: dict) -> None:
    changed = copy.deepcopy(data)
    changed["trend"][changed["year"]] = changed["trend"][min(changed["trend"])] * 1.5
    assert "no longer supports" in cd.expected_figures(changed)["trend-growth"]


# ---------------------------------------------------------------- loading and validating the CSVs

def write_csv(folder: Path, name: str, header: str, *lines: str) -> None:
    (folder / name).write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")


def test_cross_section_reads_one_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_csv(tmp_path, "x.csv", "Key,Value,Year", "a,1.5,2025", "b,2.5,2025")
    monkeypatch.setattr(cd, "DATA", tmp_path)
    values, year = cd.cross_section("x.csv", "Key", "Value")
    assert values == {"a": 1.5, "b": 2.5} and year == "2025"


def test_cross_section_rejects_duplicate_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_csv(tmp_path, "x.csv", "Key,Value,Year", "a,1,2025", "a,2,2025")
    monkeypatch.setattr(cd, "DATA", tmp_path)
    with pytest.raises(cd.DataError, match="duplicate"):
        cd.cross_section("x.csv", "Key", "Value")


def test_cross_section_rejects_two_years(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_csv(tmp_path, "x.csv", "Key,Value,Year", "a,1,2024", "b,2,2025")
    monkeypatch.setattr(cd, "DATA", tmp_path)
    with pytest.raises(cd.DataError, match="more than one Year"):
        cd.cross_section("x.csv", "Key", "Value")


def test_load_data_reads_the_real_files(data: dict) -> None:
    assert data["year"] == 2025
    assert len(data["countries"]) == 27 and set(data["codes"]) == set(data["countries"])
    assert set(data["genai"]) == {"private", "work", "education"}


@pytest.fixture()
def data_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "Data"
    shutil.copytree(cd.DATA, folder, ignore=shutil.ignore_patterns("*.pdf", "*.xlsx"))
    monkeypatch.setattr(cd, "DATA", folder)
    return folder


def append_line(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(line + "\n")


def test_load_data_rejects_a_duplicate_occupation(data_copy: Path) -> None:
    first = (data_copy / "AIAdoptionByOccupation.csv").read_text(encoding="utf-8").splitlines()[1]
    append_line(data_copy / "AIAdoptionByOccupation.csv", first)
    with pytest.raises(cd.DataError, match="OccupationGroup"):
        cd.load_data()


def test_load_data_rejects_a_duplicate_trend_year(data_copy: Path) -> None:
    append_line(data_copy / "AIAdoptionTrendEU.csv", "2025,21.0,source")
    with pytest.raises(cd.DataError, match="Year"):
        cd.load_data()


def test_load_data_needs_exactly_one_eu_row(data_copy: Path) -> None:
    path = data_copy / "GenAIUseByCountry.csv"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("European Union")]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(cd.DataError, match="EU row"):
        cd.load_data()


def test_main_reports_a_data_error(data_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    append_line(data_copy / "AIAdoptionTrendEU.csv", "2025,21.0,source")
    assert cd.main() == 1
    assert "FAIL" in capsys.readouterr().out


# ---------------------------------------------------------------- the page parser

def scan(markup: str) -> cd.PageScan:
    scanner = cd.PageScan()
    scanner.feed(markup)
    scanner.close()
    return scanner


def test_scan_reads_nested_markup_whole() -> None:
    assert scan('<span data-check="x"><span>1</span> in 5</span>').checks["x"] == ["1 in 5"]


def test_scan_ignores_void_tags() -> None:
    assert scan('<img src="a.png"><meta charset="utf-8"><span data-check="y">2</span>').checks["y"] == ["2"]


def test_scan_takes_a_bar_length_only_from_a_bar_inside_the_row() -> None:
    page = ('<div data-chart="c" data-key="a" data-value="1"><span class="hbar-val">1.0%</span></div>'
            '<div class="purpose-fill" style="width:78.0%"></div>')
    assert scan(page).rows[0]["extent"] is None


def test_scan_does_not_mistake_max_width_for_width() -> None:
    page = ('<div data-chart="c" data-key="a" data-value="1">'
            '<span class="hbar-fill" style="max-width:50%;width:20%"></span><span class="hbar-val">1.0%</span></div>')
    result = scan(page).rows[0]
    assert result["extent"] == 20.0 and result["shown"] == "1.0%"


def test_scan_reads_a_dot_position_label_and_attributes() -> None:
    page = ('<span class="dp-dot" data-chart="countries" data-key="Greece" data-value="8.9" data-code="GR" '
            'data-tip-value="8.9%" style="--v:19.84;--y:1.4"><span class="dp-code">GR</span></span>')
    result = scan(page).rows[0]
    assert (result["label_code"], result["extent"], result["code"], result["tip_value"]) == ("GR", 19.84, "GR", "8.9%")


def test_scan_reads_the_average_marker_position() -> None:
    assert scan('<span class="dp-avg" data-chart="eu-average" data-key="EU" data-value="19.95" style="--v:44.33"></span>'
                ).rows[0]["extent"] == 44.33


def test_scan_closes_elements_left_open_inside_a_closed_one() -> None:
    assert scan('<div data-check="z"><b>text</div><p data-check="z">again</p>').checks["z"] == ["text", "again"]


# ---------------------------------------------------------------- chart checks

TRUTH = {"a": 10.0, "b": 5.0}


def chart_rows() -> list[dict]:
    return [row(key="a", value="10.0", shown="10.0%", extent=100.0, tip="10.0%"),
            row(key="b", value="5.0", shown="5.0%", extent=50.0, tip="5.0%")]


def problems_for(rows: list[dict], **options) -> list[str]:
    found: list[str] = []
    cd.check_chart("c", rows, TRUTH, found, **options)
    return found


def test_check_chart_accepts_a_correct_chart() -> None:
    assert problems_for(chart_rows()) == []


@pytest.mark.parametrize("change, expected", [
    ({"value": "11.0"}, "data-value"),
    ({"shown": "9.0%"}, "shows"),
    ({"extent": 90.0}, "length or position"),
    ({"tip_value": "9.0%"}, "tooltip"),
])
def test_check_chart_catches_a_wrong_mark(change: dict, expected: str) -> None:
    rows = chart_rows()
    rows[0] = {**rows[0], **change}
    assert any(expected in p for p in problems_for(rows))


def test_check_chart_catches_wrong_order_and_missing_labels() -> None:
    assert any("not sorted" in p for p in problems_for(list(reversed(chart_rows()))))
    assert any("labels" in p for p in problems_for(chart_rows()[:1]))


def test_check_chart_missing_extent_is_a_problem() -> None:
    rows = chart_rows()
    rows[1] = {**rows[1], "extent": None}
    assert any("length or position" in p for p in problems_for(rows))


def test_check_chart_checks_codes_including_the_greece_display_code() -> None:
    rows = [row(chart="d", key="Greece", value="8.9", shown=None, extent=19.8, tip="8.9%", code="GR", label_code="GR")]
    found: list[str] = []
    options = {"sorted_desc": False, "scale_top": 45.0, "shown": False, "codes": {"Greece": "EL"}}
    cd.check_chart("d", rows, {"Greece": 8.9}, found, **options)
    assert found == []
    rows[0] = {**rows[0], "label_code": "EL"}
    cd.check_chart("d", rows, {"Greece": 8.9}, found, **options)
    assert any("label 'EL'" in p for p in found)


def test_check_chart_can_use_a_fixed_scale_and_skip_the_shown_value() -> None:
    rows = [row(key="a", value="10.0", shown=None, extent=10.0, tip=None)]
    found: list[str] = []
    cd.check_chart("c", rows, {"a": 10.0}, found, scale_top=100.0, tips=False, shown=False)
    assert found == []


def test_check_meta() -> None:
    expected = {"dk": "42%", "ro": "5%", "one-in-n-now": "1 in 5"}
    good = ('<meta name="description" content="1 in 5 firms, 42% in X, 5% in Y.">'
            '<meta property="og:description" content="1 in 5 &amp; 42% and 5%">')
    assert cd.check_meta(good, expected) == []
    stale = good.replace("42%", "41%")
    assert len(cd.check_meta(stale, expected)) == 2
    assert any("missing" in p for p in cd.check_meta("<html></html>", expected))


# ---------------------------------------------------------------- whole pages

def test_the_real_pages_pass(site: Path, data: dict) -> None:
    for path, full in ((cd.PAGE, True), (cd.CAROUSEL, False), (cd.OG_CARD, False)):
        assert cd.check_page(path, data, full)[0] == []


def mutated(path: Path, old: str, new: str) -> Path:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


@pytest.mark.parametrize("old, new, fragment", [
    (">55.0%<", ">56.0%<", "Large"),
    ('data-check="dk-ro-ratio">8x', 'data-check="dk-ro-ratio">9x', "dk-ro-ratio"),
    ('data-check="occ-students-better">41%', 'data-check="occ-students-better">45%', "occ-students-better"),
    ('class="purpose-fill" style="width:78.0%"', 'class="purpose-fill" style="width:70.0%"', "genai/private"),
    ('data-tip-value="42.0%"', 'data-tip-value="24.0%"', "tooltip"),
    ('data-key="Denmark" data-value="42.03" data-code="DK" data-tip-label="Denmark" data-tip-value="42.0%" '
     'data-tip-note="1st of 27" style="--v:93.40', 'data-key="Denmark" data-value="42.03" data-code="DK" '
     'data-tip-label="Denmark" data-tip-value="42.0%" data-tip-note="1st of 27" style="--v:60.00', "countries/Denmark"),
    ('<span class="dp-avg" data-chart="eu-average" data-key="EU" data-value="19.95" style="--v:44.33"',
     '<span class="dp-avg" data-chart="eu-average" data-key="EU" data-value="19.95" style="--v:30.00"', "eu-average"),
    ('<span class="dp-code">DK</span>', '<span class="dp-code">DX</span>', "label"),
])
def test_page_mutations_are_caught(site: Path, data: dict, old: str, new: str, fragment: str) -> None:
    mutated(cd.PAGE, old, new)
    assert any(fragment in p for p in cd.check_page(cd.PAGE, data, True)[0])


def test_swapping_two_ranked_rows_is_caught(site: Path, data: dict) -> None:
    lines = cd.PAGE.read_text(encoding="utf-8").split("\n")
    i = next(n for n, l in enumerate(lines) if 'data-chart="countries-table"' in l and 'data-key="Denmark"' in l)
    lines[i], lines[i + 1] = lines[i + 1], lines[i]
    cd.PAGE.write_text("\n".join(lines), encoding="utf-8")
    assert any("not sorted" in p for p in cd.check_page(cd.PAGE, data, True)[0])


def test_the_ranked_list_must_show_the_right_value(site: Path, data: dict) -> None:
    mutated(cd.PAGE, '<span class="tbl-val">42.0%</span>', '<span class="tbl-val">24.0%</span>')
    assert any("countries-table/Denmark" in p and "shows" in p for p in cd.check_page(cd.PAGE, data, True)[0])


def test_carousel_and_card_numbers_are_checked_too(site: Path, data: dict) -> None:
    mutated(cd.CAROUSEL, 'data-check="lede-work">27%', 'data-check="lede-work">29%')
    assert any("lede-work" in p for p in cd.check_page(cd.CAROUSEL, data, False)[0])
    mutated(cd.OG_CARD, '<b data-check="dk">42%</b> in Denmark', '<b data-check="dk">41%</b> in Denmark')
    assert any("figure dk" in p for p in cd.check_page(cd.OG_CARD, data, False)[0])


def test_unknown_and_missing_ids_are_reported(site: Path, data: dict) -> None:
    mutated(cd.PAGE, 'data-check="kpi-hours"', 'data-check="kpi-hourz"')
    found = cd.check_page(cd.PAGE, data, True)[0]
    assert any("unknown data-check id 'kpi-hourz'" in p for p in found)
    assert any("missing figure data-check='kpi-hours'" in p for p in found)


def test_main_passes_on_the_real_repo(capsys: pytest.CaptureFixture[str]) -> None:
    assert cd.main() == 0
    assert capsys.readouterr().out.startswith("OK")


def test_main_fails_and_lists_problems(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mutated(cd.PAGE, ">55.0%<", ">56.0%<")
    assert cd.main() == 1
    assert "Large" in capsys.readouterr().out


def test_main_works_without_the_share_card(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cd.OG_CARD.unlink()
    assert cd.main() == 0
    assert "2 pages" in capsys.readouterr().out


# ---------------------------------------------------------------- the swarm layout

def distances(xs: list[float], ys: list[float]) -> list[float]:
    return [((xs[i] - xs[j]) ** 2 + (ys[i] - ys[j]) ** 2) ** 0.5 for i in range(len(xs)) for j in range(i)]


def test_swarm_of_nothing_and_of_one_dot() -> None:
    assert bc.swarm([]) == []
    assert bc.swarm([3.0]) == [0.0]


def test_swarm_keeps_dots_that_are_far_apart_on_the_centre_line() -> None:
    assert bc.swarm([0.0, 5.0, 10.0]) == [0.0, 0.0, 0.0]


def test_swarm_separates_stacked_dots() -> None:
    ys = bc.swarm([5.0, 5.0, 5.0, 5.0])
    assert min(distances([5.0] * 4, ys)) >= 1.0 + bc.DOT_GAP - 1e-9


def test_swarm_never_overlaps_on_the_real_data(data: dict) -> None:
    top = cd.axis_top(data["countries"])
    xs = [v / top * bc.UNITS_ACROSS for _, v in sorted(data["countries"].items(), key=lambda kv: kv[1])]
    ys = bc.swarm(xs)
    assert min(distances(xs, ys)) >= 1.0 + bc.DOT_GAP - 1e-9
    assert max(ys) - min(ys) < 6          # a compact swarm, not a tall pile


def test_swarm_is_deterministic(data: dict) -> None:
    xs = [v / 45 * bc.UNITS_ACROSS for v in data["countries"].values()]
    assert bc.swarm(xs) == bc.swarm(xs)


# ---------------------------------------------------------------- the generator

@pytest.mark.parametrize("n, expected", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"),
                                         (12, "12th"), (13, "13th"), (21, "21st"), (22, "22nd"), (27, "27th")])
def test_ordinal(n: int, expected: str) -> None:
    assert bc.ordinal(n) == expected


def test_snippets_cover_every_region(data: dict) -> None:
    snippets = bc.build_snippets()
    assert set(snippets) == set(bc.REQUIRED_REGIONS["docs/index.html"])
    assert snippets["dotplot"].count('class="dp-dot') == 27
    assert snippets["country-table"].count("<li ") == 27
    assert snippets["genai"].count('data-chart="genai"') == 3


def test_dot_plot_marks_the_extremes_and_the_average(data: dict) -> None:
    plot = bc.dot_plot(data)
    assert plot.count('dp-dot hi"') == 1 and plot.count('dp-dot lo"') == 1
    assert 'data-key="Denmark"' in plot.split('dp-dot hi"')[1].split("</span></span>")[0]
    assert 'data-key="Romania"' in plot.split('dp-dot lo"')[1].split("</span></span>")[0]
    assert plot.count('class="dp-grid"') == 5 and plot.count("dp-call dp-call-") == 2
    assert 'data-check="eu-average">20.0%' in plot and "--v:44.33" in plot


def test_dot_plot_callout_leaders_reach_their_dots(data: dict) -> None:
    for lead in [float(chunk.split(";--lead:")[1].split('"')[0]) for chunk in bc.dot_plot(data).split("dp-call dp-call-")[1:]]:
        assert lead >= 0


def test_the_eu_average_uses_the_country_data_year(data: dict) -> None:
    changed = copy.deepcopy(data)
    changed["trend"][2026] = 99.0                     # a newer trend year must not move the 2025 average
    plot = bc.dot_plot(changed)
    assert 'data-check="eu-average">20.0%' in plot and "--v:44.33" in plot


def test_country_table_lists_every_country_in_rank_order(data: dict) -> None:
    table = bc.country_table(data)
    names = [line.split('data-key="')[1].split('"')[0] for line in table.splitlines() if "<li " in line]
    assert names == [n for n, _ in bc.ranked(data["countries"])]
    assert 'data-code="GR"' in table and 'data-code="EL"' not in table      # Greece reads GR, not Eurostat's EL


GOOD = "<!-- gen:a -->old<!-- /gen:a -->\n<!-- gen:b -->old<!-- /gen:b -->"


def test_check_markers_accepts_balanced_markers() -> None:
    bc.check_markers(GOOD, {"a", "b"}, "page")


@pytest.mark.parametrize("text, message", [
    (GOOD.replace("<!-- /gen:b -->", "<!--/gen:bb-->"), "unbalanced"),
    (GOOD.replace("<!-- /gen:b -->", "<!-- /gen:b -- >"), "unbalanced"),
    (GOOD.replace("<!-- gen:b -->", ""), "unbalanced"),
])
def test_check_markers_rejects_a_broken_marker(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        bc.check_markers(text, set(), "page")


def test_check_markers_rejects_a_missing_region() -> None:
    with pytest.raises(ValueError, match="missing region"):
        bc.check_markers("<!-- gen:a -->x<!-- /gen:a -->", {"a", "b"}, "page")


def test_inject_fills_regions_and_is_idempotent() -> None:
    once = bc.inject(GOOD, {"a": "A", "b": "B"})
    assert once == "<!-- gen:a -->\nA\n<!-- /gen:a -->\n<!-- gen:b -->\nB\n<!-- /gen:b -->"
    assert bc.inject(once, {"a": "A", "b": "B"}) == once


def test_inject_needs_a_generator_for_every_marker() -> None:
    with pytest.raises(KeyError):
        bc.inject(GOOD, {"a": "A"})


def test_main_is_idempotent_and_the_result_passes_the_checker(site: Path, data: dict,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    mutated(cd.PAGE, ">55.0%<", ">56.0%<")                       # make the generated page stale
    assert bc.main() == 0
    assert "updated" in capsys.readouterr().out
    assert cd.check_page(cd.PAGE, data, True)[0] == []            # regenerated, so correct again
    assert bc.main() == 0
    assert "updated" not in capsys.readouterr().out               # second run changes nothing


def test_main_refuses_a_page_with_a_deleted_marker(site: Path) -> None:
    text = cd.PAGE.read_text(encoding="utf-8").replace("<!-- /gen:dotplot -->", "")
    cd.PAGE.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="unbalanced"):
        bc.main()


def test_main_skips_a_target_that_does_not_exist(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cd.CAROUSEL.unlink()
    assert bc.main() == 0
    assert "skip" in capsys.readouterr().out
