# AI Intelligence Data Pipeline

An automated Python pipeline for collecting, processing, enriching, storing, and exporting AI ecosystem data from public APIs, RSS feeds, and configured job boards.

## 1. Project Overview

The pipeline gathers information about:

- AI startups
- AI applications and Hugging Face Spaces
- AI research papers from arXiv
- Related GitHub repositories and repository metadata
- AI job opportunities
- AI industry news
- Entity resolution and canonical company mappings

Records are stored in SQLite and exported to CSV and Google Sheets.

## 2. Final Dataset Summary

Latest successful collection and export:

| Dataset | Records |
|---|---:|
| AI Startups | 1,894 |
| AI Applications / Spaces | 1,975 |
| Research Papers | 1,000 |
| Jobs | 8 |
| News | 8 |
| Entity Mapping Log | 3 |
| **Total** | **4,888** |

**Research paper GitHub enrichment:** 79 of the 1,000 papers have validated GitHub repository associations and star counts. The remaining papers do not currently have validated repository links.

Note: The applications dataset includes Hugging Face Spaces, which may contain demos and experimental applications rather than commercial products.

## 3. Key Features

- Asynchronous HTTP requests and reusable crawler utilities.
- Startup, application, research, job, and news collectors.
- Date parsing and rolling 24-hour freshness filtering.
- Duplicate detection and SQLite persistence.
- Entity normalization and fuzzy matching against a seed list.
- GitHub repository search and implementation-evidence heuristics.
- LLM provider fallback design: Gemini Flash → Groq → DeepSeek.
- HTTP 413 chunking and HTTP 429 retry/backoff handling.
- Cloudflare/DataDome detection and responsible fallback strategies.
- CSV and Google Sheets export.

## 4. Technology Stack

Python, SQLite, aiohttp, BeautifulSoup, lxml, Playwright, REST APIs, RSS, arXiv, Hugging Face, GitHub API, and Google Sheets API.

## 5. Project Structure

```text
AI-Intelligence-Data-Pipeline/
├── src/
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── logger.py
│   ├── http_client.py
│   ├── crawler.py
│   ├── anti_bot.py
│   ├── browser_renderer.py
│   ├── date_utils.py
│   ├── entity_resolver.py
│   ├── source_registry.py
│   ├── startup_collector.py
│   ├── product_collector.py
│   ├── research_collector.py
│   ├── github_collector.py
│   ├── job_collector.py
│   ├── job_sources.py
│   ├── news_collector.py
│   ├── llm_fallback.py
│   ├── llm_integration.py
│   ├── export_data.py
│   ├── google_sheets_exporter.py
│   ├── pipeline.py
│   └── main.py
├── exports/
├── data/
├── architecture.pdf
├── README.md
├── requirements.txt
└── .gitignore
```

Root-level Python modules are retained for the current execution workflow. The `src/` directory contains the organized source-code package copy.

## 6. Installation

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure API credentials in a local `.env` file. Never commit API keys or service-account credentials.

## 7. Running the Pipeline

Run the main pipeline:

```powershell
python main.py
```

Export collected datasets:

```powershell
python export_data.py
```

Run entity mapping:

```powershell
python populate_entity_mapping.py
```

## 8. Data Outputs

CSV exports include:

- startups.csv
- products.csv
- research_papers.csv
- jobs.csv
- news.csv
- entity_mapping_log.csv

Google Sheets export supports six corresponding datasets.

**Google Sheets:**  
https://docs.google.com/spreadsheets/d/1-ZkLTK_lRYSMIxOPI44dz7YgZWKM9UL-w3emkrQeJDs

## 9. Reliability and Data Quality

The implementation includes retry handling, exponential backoff with jitter, Retry-After support, duplicate checks, date validation, and LLM provider fallback logic.

HTTP 413 handling uses recursive prompt chunking. Merged extraction output still requires structured validation.

Crawler protection handling detects common Cloudflare, DataDome, and CAPTCHA signals. Browser rendering is intended only for authorized access. CAPTCHA and persistent access restrictions require manual review or an alternative permitted source.

GitHub matching uses repository metadata and implementation-evidence heuristics. Repository associations should not be treated as independently verified semantic matches without review.

## 10. Scalability Architecture

The accompanying `architecture.pdf` describes a proposed production design for 500,000+ records using distributed workers, a durable queue, PostgreSQL, object storage, search/vector indexing, and centralized monitoring.

The current project is a local Python/SQLite implementation. Distributed deployment and 500,000-record load testing have not yet been established.

## 11. Verification and Limitations

- Python source compilation completed successfully.
- CSV and Google Sheets exports completed successfully.
- Selected local tests and mocked HTTP retry/fallback tests have been performed.
- Live LLM provider requests have not been fully validated.
- Full browser-rendering behavior against protected websites requires further validation.
- Complete source coverage and distributed performance benchmarks remain unverified.
- Dynamic GitHub star refresh across the entire research-paper dataset remains future work.

Dataset counts and freshness should be taken from the latest successful collection run.

## 12. Security

- Keep `.env` out of Git.
- Never commit service-account JSON files.
- Exclude databases, backups, virtual environments, and logs.
- Rotate credentials that may have been exposed.
- Use authorized public APIs and respect source access policies.

## 13. Repository

GitHub:  
https://github.com/SriDevi1806/AI-Intelligence-Data-Pipeline