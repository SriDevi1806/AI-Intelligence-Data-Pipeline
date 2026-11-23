import asyncio
import base64
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import aiohttp
from sqlalchemy.orm.attributes import flag_modified

import config
from database import init_db, get_session, ResearchPaper
from logger import logger


# ============================================================
# VERIFIED GITHUB REPOSITORY COLLECTOR
# ============================================================

GITHUB_API = "https://api.github.com"

MAX_PAPERS_PER_RUN = int(
    os.getenv("GITHUB_MAX_PAPERS_PER_RUN", "10")
)

MAX_CANDIDATES = 5

REQUEST_TIMEOUT = getattr(config, "REQUEST_TIMEOUT", 30)
MAX_RETRIES = min(getattr(config, "MAX_RETRIES", 5), 3)

REQUEST_DELAY = 2.2 if getattr(config, "GITHUB_TOKEN", "") else 6.5

ARXIV_PATTERN = re.compile(r"\b\d{4}\.\d{4,5}\b")

# Reject known paper directories, trackers, and research aggregators.

# Reject research aggregators, paper trackers, and daily paper feeds.
AGGREGATOR_PATTERN = re.compile(
    r"(research[-_ ]radar|paper[-_ ]tracker|"
    r"arxiv[-_ ]daily|daily[-_ ]arxiv|"
    r"daily[-_ ]papers|papers[-_ ]daily|"
    r"paper[-_ ]digest|"
    r"awesome[-_ ]papers|paper[-_ ]feed|"
    r"arxiv[-_ ]monitor|paper[-_ ]aggregator|"
    r"arxiv[-_ ]favor|"
    r"paper[-_ ]discovery)",
    re.IGNORECASE
)

AGGREGATOR_REPO_PATTERN = re.compile(
    r"(research[-_ ]radar|paper[-_ ]tracker|"
    r"arxiv[-_ ]daily|daily[-_ ]arxiv|"
    r"daily[-_ ]papers|papers[-_ ]daily|"
    r"paper[-_ ]digest|"
    r"awesome[-_ ]papers|paper[-_ ]feed|"
    r"arxiv[-_ ]monitor|paper[-_ ]aggregator|"
    r"arxiv[-_ ]favor|"
    r"paper[-_ ]discovery)",
    re.IGNORECASE
)


# Source-code file extensions used as implementation evidence.
IMPLEMENTATION_FILE_PATTERN = re.compile(
    r"\.(py|ipynb|js|ts|jsx|tsx|cpp|cc|c|cu|rs|go|java|"
    r"sh|r|jl|swift|kt)$",
    re.IGNORECASE
)

IMPLEMENTATION_CUE_PATTERN = re.compile(
    r"\b("
    r"implementation|installation|quick start|quickstart|"
    r"pip install|inference|training|reproduce|"
    r"run the code|getting started|usage|requirements"
    r")\b",
    re.IGNORECASE
)

STOP_WORDS = {
    "the", "a", "an", "of", "for", "and", "or",
    "in", "on", "with", "to", "from", "by",
    "via", "using", "based", "towards"
}


# ============================================================
# HEADERS
# ============================================================

def get_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-Intelligence-Data-Pipeline"
    }

    token = getattr(config, "GITHUB_TOKEN", "")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def title_match_score(title, readme):
    normalized_title = normalize_text(title)
    normalized_readme = normalize_text(readme)

    if not normalized_title:
        return 0.0

    if normalized_title in normalized_readme:
        return 1.0

    title_words = {
        word for word in normalized_title.split()
        if word not in STOP_WORDS and len(word) > 2
    }

    readme_words = set(normalized_readme.split())

    if len(title_words) < 4:
        return 0.0

    overlap = title_words.intersection(readme_words)
    return len(overlap) / len(title_words)


# ============================================================
# RATE LIMIT HANDLING
# ============================================================

def get_wait_time(response):
    retry_after = response.headers.get("Retry-After")

    if retry_after:
        try:
            return max(1, int(retry_after))
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(retry_after)

                if retry_date.tzinfo is None:
                    retry_date = retry_date.replace(
                        tzinfo=timezone.utc
                    )

                seconds = (
                    retry_date - datetime.now(timezone.utc)
                ).total_seconds()

                return max(1, int(seconds) + 1)

            except (TypeError, ValueError):
                pass

    remaining = response.headers.get("X-RateLimit-Remaining")
    reset = response.headers.get("X-RateLimit-Reset")

    if remaining == "0" and reset:
        try:
            return max(
                1,
                int(reset) - int(
                    datetime.now(timezone.utc).timestamp()
                ) + 2
            )
        except ValueError:
            pass

    return 60


# ============================================================
# API REQUEST
# ============================================================

async def request_json(session, url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(
                    total=REQUEST_TIMEOUT
                )
            ) as response:

                if response.status == 200:
                    return await response.json()

                if response.status in (403, 429):
                    wait_time = min(get_wait_time(response), 300)

                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            "GitHub rate limit. Waiting %s seconds.",
                            wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    logger.error(
                        "GitHub rate limit retries exhausted."
                    )
                    return None

                if response.status in (500, 502, 503, 504):
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue

                error_text = await response.text()
                logger.warning(
                    "GitHub HTTP %s: %s",
                    response.status,
                    error_text[:250]
                )
                return None

        except (
            aiohttp.ClientError,
            asyncio.TimeoutError
        ) as error:
            logger.warning("GitHub request error: %s", error)

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)

    return None


# ============================================================
# READ README CONTENT
# ============================================================

async def fetch_readme(session, full_name):
    if not full_name:
        return None

    encoded_name = quote(full_name, safe="/")
    url = f"{GITHUB_API}/repos/{encoded_name}/readme"

    data = await request_json(session, url)

    if not data or not data.get("content"):
        return None

    try:
        return base64.b64decode(
            data["content"]
        ).decode("utf-8", errors="replace")

    except Exception as error:
        logger.warning(
            "Could not decode README for %s: %s",
            full_name,
            error
        )
        return None


# ============================================================
# INSPECT REPOSITORY FILES
# ============================================================

async def fetch_repository_files(session, repository):
    """Return repository file paths using GitHub's tree API."""

    full_name = repository.get("full_name")

    if not full_name:
        return []

    branch = repository.get("default_branch") or "HEAD"
    encoded_name = quote(full_name, safe="/")
    encoded_branch = quote(branch, safe="/")

    url = (
        f"{GITHUB_API}/repos/{encoded_name}/git/trees/"
        f"{encoded_branch}"
    )

    data = await request_json(
        session,
        url,
        params={"recursive": "1"}
    )

    if not data:
        return []

    if data.get("truncated"):
        logger.warning(
            "Repository tree was truncated: %s",
            full_name
        )

    return [
        item.get("path", "")
        for item in data.get("tree", [])
        if item.get("type") == "blob"
    ]


def has_implementation_evidence(files, readme):
    """Require source files plus implementation-related README guidance."""

    ignored_prefixes = (
        "docs/",
        "examples/",
        "assets/",
        "vendor/",
        "node_modules/",
        "tests/",
        "test/"
    )

    source_files = [
        path for path in files
        if IMPLEMENTATION_FILE_PATTERN.search(path)
        and not path.lower().startswith(ignored_prefixes)
    ]

    if not source_files:
        return False

    if not IMPLEMENTATION_CUE_PATTERN.search(readme or ""):
        return False

    return True


# ============================================================
# VERIFY REPOSITORY EVIDENCE
# ============================================================

def verify_repository(paper, repository, readme, files=None):
    if not readme:
        return None

    full_name = repository.get("full_name", "")
    description = repository.get("description") or ""

    searchable_text = "\n".join([
        full_name,
        description,
        readme
    ])

    if (
        AGGREGATOR_PATTERN.search(searchable_text)
        or AGGREGATOR_REPO_PATTERN.search(full_name)
    ):
        logger.info(
            "Rejected %s: research aggregator or paper tracker.",
            full_name
        )
        return None

    if not has_implementation_evidence(files or [], readme):
        logger.info(
            "Rejected %s: insufficient implementation evidence.",
            full_name
        )
        return None

    arxiv_id = paper.arxiv_id

    id_match = bool(
        arxiv_id and re.search(
            rf"(?<![0-9]){re.escape(arxiv_id)}(?![0-9])",
            readme,
            flags=re.IGNORECASE
        )
    )

    referenced_ids = set(ARXIV_PATTERN.findall(readme))

    if len(referenced_ids) > 8:
        logger.info(
            "Rejected %s: README contains %s different arXiv IDs.",
            full_name,
            len(referenced_ids)
        )
        return None

    normalized_title = normalize_text(paper.title)
    normalized_readme = normalize_text(readme)

    exact_title_match = (
        bool(normalized_title)
        and normalized_title in normalized_readme
    )

    score = title_match_score(paper.title, readme)

    # ID-based evidence requires strong title overlap.
    if id_match and score < 0.75:
        return None

    # Title-only evidence requires the complete normalized title.
    if not id_match and not exact_title_match:
        return None

    if not id_match and score < 0.90:
        return None

    html_url = repository.get("html_url")
    stars = repository.get("stargazers_count")

    if not html_url or stars is None:
        return None

    evidence_method = (
        "Exact arXiv ID and title + source-code evidence"
        if id_match
        else "Exact paper title + source-code evidence"
    )

    return {
        "name": full_name,
        "url": html_url,
        "stars": stars,
        "description": description,
        "language": repository.get("language"),
        "updated_at": repository.get("updated_at"),
        "matched_arxiv_id": arxiv_id if id_match else None,
        "title_match_score": round(score, 3),
        "source_file_count": len(files or []),
        "match_method": evidence_method,
        "verification_note": (
            "README paper match and repository source-file checks passed. "
            "This is strong implementation evidence, not independent "
            "proof of author ownership or code correctness."
        ),
        "verified_at": datetime.now(timezone.utc).isoformat()
    }


# ============================================================
# BUILD SEARCH QUERIES
# ============================================================

def build_search_queries(paper):
    queries = []

    if paper.arxiv_id:
        queries.append(f"{paper.arxiv_id} in:readme")

    if paper.title:
        escaped_title = paper.title.replace('"', " ")
        queries.append(f'"{escaped_title}" in:readme')
        queries.append(
            f'"{escaped_title}" in:name,description,readme'
        )

    return list(dict.fromkeys(queries))


# ============================================================
# SEARCH AND VERIFY REPOSITORY
# ============================================================

async def search_github_repository(session, paper):
    if not paper.arxiv_id or not paper.title:
        return None

    search_url = f"{GITHUB_API}/search/repositories"
    candidates = {}
    queries = build_search_queries(paper)

    for query_index, query in enumerate(queries):
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": 10
        }

        search_data = await request_json(
            session,
            search_url,
            params=params
        )

        if search_data:
            for repository in search_data.get("items", []):
                full_name = repository.get("full_name")
                if full_name:
                    candidates[full_name] = repository

        if query_index < len(queries) - 1:
            await asyncio.sleep(REQUEST_DELAY)

    if not candidates:
        return None

    print(
        "Unique repository candidates discovered:",
        len(candidates)
    )

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda item: item.get("stargazers_count", 0),
        reverse=True
    )

    checked = 0

    for repository in ordered_candidates:
        if checked >= MAX_CANDIDATES:
            break

        full_name = repository.get("full_name")
        if not full_name:
            continue

        checked += 1

        readme = await fetch_readme(session, full_name)

        if not readme:
            await asyncio.sleep(REQUEST_DELAY)
            continue

        files = await fetch_repository_files(
            session,
            repository
        )

        verified = verify_repository(
            paper,
            repository,
            readme,
            files
        )

        if verified:
            return verified

        await asyncio.sleep(REQUEST_DELAY)

    return None


# ============================================================
# CLEAR OLD PROVISIONAL MATCHES
# ============================================================

def clear_provisional_matches(db_session):
    cleared = 0

    papers = db_session.query(
        ResearchPaper
    ).filter(
        ResearchPaper.github_url.isnot(None)
    ).all()

    for paper in papers:
        raw_data = paper.raw_data or {}

        if not isinstance(raw_data, dict):
            continue

        github_data = raw_data.get("github_repository", {})

        if not isinstance(github_data, dict):
            continue

        if github_data.get("match_method") == "GitHub README search":
            paper.github_url = None
            paper.github_stars = None
            raw_data.pop("github_repository", None)
            paper.raw_data = raw_data
            flag_modified(paper, "raw_data")
            cleared += 1

    if cleared:
        db_session.commit()

    return cleared


# ============================================================
# SAVE VERIFIED REPOSITORY
# ============================================================

def save_verified_repository(db_session, paper, repository):
    paper.github_url = repository["url"]
    paper.github_stars = repository["stars"]

    raw_data = paper.raw_data or {}

    if not isinstance(raw_data, dict):
        raw_data = {}

    raw_data["github_repository"] = repository
    paper.raw_data = raw_data
    flag_modified(paper, "raw_data")

    db_session.flush()


# ============================================================
# MAIN COLLECTION
# ============================================================

async def collect_github_repositories():
    print("\n" + "=" * 60)
    print("VERIFIED GITHUB REPOSITORY COLLECTION")
    print("=" * 60)

    init_db()

    searched = 0
    matched = 0
    not_found = 0
    failed = 0

    token_configured = bool(
        getattr(config, "GITHUB_TOKEN", "")
    )

    print("GitHub token configured:", token_configured)
    print("Maximum papers this run:", MAX_PAPERS_PER_RUN)

    connector = aiohttp.TCPConnector(
        limit=2,
        enable_cleanup_closed=True
    )

    async with aiohttp.ClientSession(
        headers=get_headers(),
        connector=connector
    ) as http_session:

        with get_session() as db_session:
            cleared = clear_provisional_matches(db_session)

            print(
                "Previous provisional links cleared:",
                cleared
            )

            all_unlinked = db_session.query(
                ResearchPaper
            ).filter(
                ResearchPaper.arxiv_id.isnot(None),
                ResearchPaper.arxiv_id != "",
                ResearchPaper.github_url.is_(None)
            ).order_by(
                ResearchPaper.id.asc()
            ).all()

            papers = []

            for candidate in all_unlinked:
                raw = candidate.raw_data or {}

                if not isinstance(raw, dict):
                    raw = {}

                history = raw.get("github_search_history", {})

                if history.get("status") == "completed":
                    continue

                papers.append(candidate)

                if len(papers) >= MAX_PAPERS_PER_RUN:
                    break

            total = len(papers)

            print("\nResearch papers to verify:", total)

            for index, paper in enumerate(papers, start=1):
                print(f"\n[{index}/{total}] {paper.title[:75]}")
                print("arXiv ID:", paper.arxiv_id)

                try:
                    repository = await search_github_repository(
                        http_session,
                        paper
                    )

                    searched += 1

                    raw = paper.raw_data or {}
                    if not isinstance(raw, dict):
                        raw = {}

                    raw["github_search_history"] = {
                        "status": "completed",
                        "searched_at": datetime.now(timezone.utc).isoformat()
                    }
                    paper.raw_data = raw
                    flag_modified(paper, "raw_data")

                    if repository:
                        save_verified_repository(
                            db_session,
                            paper,
                            repository
                        )

                        matched += 1

                        print(
                            "MATCHED REPOSITORY:",
                            repository["name"]
                        )
                        print("URL:", repository["url"])
                        print("Stars:", repository["stars"])
                        print("Evidence:", repository["match_method"])
                        print(
                            "Title score:",
                            repository["title_match_score"]
                        )

                    else:
                        not_found += 1
                        print(
                            "No sufficiently verified repository found."
                        )

                except Exception as error:
                    db_session.rollback()
                    failed += 1

                    logger.exception(
                        "Paper processing failed: %s",
                        error
                    )

                if index < total:
                    await asyncio.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print("VERIFIED GITHUB COLLECTION SUMMARY")
    print("=" * 60)
    print("Papers searched:", searched)
    print("Verified repositories:", matched)
    print("No verified repository:", not_found)
    print("Failed:", failed)
    print(
        "Completed at:",
        datetime.now(timezone.utc).isoformat()
    )
    print("=" * 60)


# ============================================================
# EXECUTION
# ============================================================

if __name__ == "__main__":
    asyncio.run(collect_github_repositories())
