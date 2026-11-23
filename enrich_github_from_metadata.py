import asyncio
import re
import aiohttp

import config
from database import init_db, get_session, ResearchPaper

URL_PATTERN = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.I
)

def extract_candidates(raw_data):
    if not isinstance(raw_data, dict):
        return []
    found = []
    for owner, repo in URL_PATTERN.findall(str(raw_data)):
        repo = repo.rstrip(".,;:!?)]}")
        repo = re.sub(r"\.git$", "", repo, flags=re.I)
        if owner.lower() not in {"github", "features"}:
            found.append((owner, repo))
    return list(dict.fromkeys(found))

async def main():
    init_db()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-Intelligence-Data-Pipeline"
    }

    token = getattr(config, "GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    verified = []
    invalid = []

    async with aiohttp.ClientSession(
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30)
    ) as http:
        with get_session() as db:
            papers = db.query(ResearchPaper).order_by(
                ResearchPaper.id
            ).all()

            for paper in papers:
                candidates = extract_candidates(paper.raw_data)

                for owner, repo in candidates:
                    url = f"https://api.github.com/repos/{owner}/{repo}"
                    try:
                        async with http.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                verified.append({
                                    "paper_id": paper.id,
                                    "title": paper.title,
                                    "url": data["html_url"],
                                    "stars": data["stargazers_count"],
                                    "full_name": data["full_name"]
                                })
                                break
                            elif response.status == 404:
                                invalid.append((paper.id, owner, repo))
                            else:
                                print(
                                    f"STOP: GitHub returned HTTP {response.status} "
                                    f"for {owner}/{repo}. No database changes made."
                                )
                                return
                    except Exception as exc:
                        print(f"STOP: Request failed: {exc}")
                        print("No database changes made.")
                        return

    print(f"\nValidated repositories: {len(verified)}")
    print(f"Invalid URLs: {len(invalid)}")

    if not verified:
        print("Nothing to save.")
        return

    with get_session() as db:
        saved = 0
        for item in verified:
            paper = db.query(ResearchPaper).filter_by(
                id=item["paper_id"]
            ).first()

            if not paper:
                continue

            paper.github_url = item["url"]
            paper.github_stars = item["stars"]

            raw_data = paper.raw_data or {}
            if not isinstance(raw_data, dict):
                raw_data = {}

            raw_data["github_repository"] = {
                "full_name": item["full_name"],
                "url": item["url"],
                "stars": item["stars"],
                "match_method": "Source metadata URL + GitHub API validation",
                "verified_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
            }
            paper.raw_data = raw_data
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(paper, "raw_data")
            saved += 1

    print(f"\nSUCCESS: Saved {saved} verified GitHub repositories.")
    print(f"Invalid links left untouched: {len(invalid)}")
    for paper_id, owner, repo in invalid:
        print(f"404 | Paper {paper_id} | {owner}/{repo}")

if __name__ == "__main__":
    asyncio.run(main())
