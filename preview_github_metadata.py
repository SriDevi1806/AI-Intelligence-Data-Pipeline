import asyncio
import re
import aiohttp

import config
from database import init_db, get_session, ResearchPaper
from github_collector import get_headers

URL_PATTERN = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.I
)

def extract_candidates(raw_data):
    if not isinstance(raw_data, dict):
        return []
    text = str(raw_data)
    found = []
    for match in URL_PATTERN.finditer(text):
        owner, repo = match.groups()
        repo = repo.rstrip(".,;:!?)]}")
        repo = re.sub(r"\.git$", "", repo, flags=re.I)
        if owner.lower() not in {"github", "features"}:
            found.append((owner, repo))
    return list(dict.fromkeys(found))

async def main():
    init_db()
    async with aiohttp.ClientSession(
        headers=get_headers(),
        timeout=aiohttp.ClientTimeout(total=25)
    ) as session:
        with get_session() as db:
            papers = db.query(ResearchPaper).order_by(
                ResearchPaper.id
            ).all()

            candidates = []
            for paper in papers:
                for owner, repo in extract_candidates(paper.raw_data):
                    candidates.append((paper.id, paper.title, owner, repo))

            print(f"Candidate links found: {len(candidates)}")
            print("Checking first 10 only. Database will NOT be changed.\n")

            for paper_id, title, owner, repo in candidates:
                url = f"https://api.github.com/repos/{owner}/{repo}"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            print(
                                f"VALID | Paper ID {paper_id} | "
                                f"{data.get('full_name')} | "
                                f"Stars: {data.get('stargazers_count')} | "
                                f"{title[:65]}"
                            )
                        else:
                            print(
                                f"INVALID ({response.status}) | "
                                f"{owner}/{repo} | Paper ID {paper_id}"
                            )
                except Exception as exc:
                    print(f"ERROR | {owner}/{repo} | {exc}")

if __name__ == "__main__":
    asyncio.run(main())

