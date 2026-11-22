# AI Intelligence Data Pipeline

An automated Python-based data collection and export system for gathering AI-related information from multiple sources and organizing it into structured datasets.

## Project Overview

The AI Intelligence Data Pipeline collects, processes, stores and exports information about AI startups, applications, research papers, job opportunities and AI industry news.

Collected records are stored in a local SQLite database and can be exported to CSV files and Google Sheets.

## Key Features

- **Startup collection:** Collects AI startup information using the Y Combinator API.
- **AI applications:** Collects Hugging Face Spaces data.
- **Research collection:** Collects AI research papers from arXiv.
- **GitHub verification:** Searches for GitHub repositories related to research papers.
- **Job collection:** Collects AI-related job listings from configured sources.
- **News collection:** Collects AI industry news through RSS feeds.
- **Data storage:** Uses SQLite for structured local storage.
- **Data export:** Exports collected datasets to CSV.
- **Google Sheets integration:** Uploads datasets to a configured Google spreadsheet.
- **HTTP utilities:** Includes reusable HTTP and crawler modules.
- **LLM integration:** Includes LLM integration and fallback modules.

## Technology Stack

- Python
- SQLite
- REST APIs
- RSS feeds
- Hugging Face
- arXiv
- GitHub
- Google Sheets API
- CSV

## Project Structure

```text
AI-Intelligence-Data-Pipeline/
│
├── config.py
├── database.py
├── models.py
├── logger.py
├── http_client.py
├── crawler.py
├── date_utils.py
├── entity_resolver.py
├── source_registry.py
│
├── startup_collector.py
├── product_collector.py
├── research_collector.py
├── github_collector.py
├── job_collector.py
├── job_sources.py
├── news_collector.py
│
├── llm_integration.py
├── llm_fallback.py
├── export_data.py
├── google_sheets_exporter.py
├── pipeline.py
├── main.py
├── verify_jobs.py
│
├── exports/
│   ├── startups.csv
│   ├── products.csv
│   ├── research_papers.csv
│   ├── jobs.csv
│   ├── news.csv
│   └── entity_mapping_log.csv
│
├── requirements.txt
├── .gitignore
└── README.md
```

## Dataset Snapshot

The current exported dataset contains:

| Dataset | Records |
|---|---:|
| AI Startups | 1,894 |
| AI Applications (Hugging Face Spaces) | 1,975 |
| AI Research Papers | 1,000 |
| AI Jobs | 2 |
| AI News | 7 |
| Entity Mapping Log | 0 |
| **Total** | **4,878** |

These figures represent the current collection snapshot and may change when the pipeline runs again.

## Installation

Clone the repository:

```bash
git clone https://github.com/SriDevi1806/AI-Intelligence-Data-Pipeline.git
cd AI-Intelligence-Data-Pipeline
```

Create and activate a virtual environment:

```bash
python -m venv venv
```

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Create a local `.env` file in the project root and configure the API credentials and settings required by the collectors and integrations.

Keep all API keys, service-account credentials and private configuration files out of GitHub.

The Google Sheets exporter requires a configured Google service account and access to the target spreadsheet.

## Run the Pipeline

Run the main application:

```bash
python main.py
```

Optional execution flags:

```bash
python pipeline.py --skip-github
```

```bash
python pipeline.py --skip-sheets
```

```bash
python pipeline.py --skip-github --skip-sheets
```

The pipeline executes its configured collection stages, exports CSV data and optionally uploads the results to Google Sheets.

Running the pipeline again may make external API requests and update the collected data.

## Exported Data

CSV files are generated in the `exports/` directory.

The project uses SQLite for local persistence. Database files and credentials are intentionally excluded from the public Git repository.

## Important Notes

- Data availability depends on the external APIs and feeds.
- API rate limits and access restrictions may affect collection.
- Some integrations require valid credentials and service-account permissions.
- The dataset figures above are a snapshot, not guaranteed future collection totals.
- GitHub repository matches should be reviewed before treating them as verified research implementations.
- LLM functionality requires valid provider credentials when live model requests are used.

## Repository

GitHub: https://github.com/SriDevi1806/AI-Intelligence-Data-Pipeline

## License

See the repository's license information before reusing or distributing this project.
