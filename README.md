# Who's actually using AI at work in Europe? 

An end-to-end BI project: sourcing official EU statistics on AI adoption at work, modeling them in a Power BI semantic model, building a report, and prototyping the same story as a standalone HTML dashboard — paired with a "using AI safely at work" guidance deck.

**Live:** [dashboard](https://sansanabria.github.io/ai-adoption-eu/) · [AI-at-work slide deck](https://sansanabria.github.io/ai-adoption-eu/presentation.html) (GitHub Pages, served from `/docs`).

[![Dashboard preview: headline and key figures](docs/screenshot.png)](https://sansanabria.github.io/ai-adoption-eu/)

## What's in here

| Path | What it is |
|---|---|
| `AI Adoption EU.pbip` + `.SemanticModel` / `.Report` | The Power BI project (PBIP format — open with Power BI Desktop) |
| `Data/` | The source CSVs the semantic model imports, plus the two raw Eurostat exports they were derived from |
| `docs/index.html` | Standalone HTML version of the dashboard (same data, hand-built charts, no Power BI required to view) |
| `docs/presentation.html` | The same guidance deck as a keyboard-navigable web presentation (←/→, `#N` deep links, print to PDF) |
| `AI At Work.pptx` | Guidance deck on using AI chat tools safely (terms, account-tier risks, what not to paste into a prompt, hallucinations, ownership of AI-written work) |

## Data sources

All figures are pulled from official EU statistical releases — no scraped or synthetic data:

- **Eurostat**, *"Use of artificial intelligence in enterprises"* (`isoc_eb_ai`, `isoc_eb_ain2`), 2025 reference year, published 11 Dec 2025 — enterprise adoption by year, country, size, business function, and economic sector.
- **Eurostat**, *"Individuals: use of generative AI tools"* (`isoc_ai_iaiu`), 2025 reference year — generative-AI use by purpose (private / work / education), by country.
- **European Commission, DG ECFIN**, *"The AI-adoption divide: who benefits, who doesn't, and what it means for workers"*, Spring 2026 Economic Forecast — an ad-hoc module of the EC's monthly consumer survey (Feb–Mar 2026, n=21,207, 18 EU member states + 4 candidate countries) covering occupation-level time savings and productivity impact.

Eurostat figures were pulled directly from Eurostat's public API (dataset codes above); the European Commission figures were compiled by hand from the published report, since it has no machine-readable data release.

## Power BI model

- Import-mode semantic model, one table per CSV, no relationships (each table is a self-contained pre-aggregated view — country, sector, business function, enterprise size, occupation, etc.)
- Explicit DAX measures per table (no implicit aggregation), `Decimal` types instead of `Double` for percentage/hour columns, hidden base columns behind their measures
- A small disconnected `# Measures` table for cross-table KPIs (latest adoption %, YoY growth, top country/function)
- Report theme (`EUAdoption-*.json`) built from the same color palette as the HTML version

**Setup after cloning:** every table reads its CSV through a single Power Query parameter, `DataFolder` (default `C:\path\to\ai-adoption-eu\Data`, a placeholder). Open `AI Adoption EU.pbip` in Power BI Desktop, go to *Home → Transform data → Manage parameters*, set `DataFolder` to the full path of this repo's `Data` folder, then *Close & Apply* and refresh. That one value is the only machine-specific setting in the model.

## HTML prototype

`docs/index.html` is a self-contained, dependency-free HTML/CSS page (one Google Fonts link, no JS framework, no chart library — bars and the trend line are hand-drawn SVG/CSS) built to the same design system as the Power BI report: EU blue as the primary color, a single gold accent, Newsreader/Inter type pairing, light/dark mode support.

## Tools used

Built with [Claude Code](https://claude.com/claude-code), using the [`skills-for-fabric`](https://github.com/microsoft/skills-for-fabric) plugin (`powerbi-authoring`) for the semantic model and report authoring, and Anthropic's `dataviz` / `artifact-design` skills for the HTML dashboard's chart and visual design.

## License

Code, HTML and slide deck: [MIT](LICENSE). The underlying data belongs to its publishers (Eurostat, European Commission) and remains subject to their reuse terms — see [Data sources](#data-sources).
