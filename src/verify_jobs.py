
from datetime import datetime, timezone, timedelta

from database import Job, get_session


def main():

    print("=" * 55)
    print("JOB DATABASE VERIFICATION")
    print("=" * 55)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    with get_session() as db:

        jobs = db.query(Job).order_by(
            Job.published_at.desc()
        ).all()

        print("\nTotal jobs stored:", len(jobs))

        recent_count = 0

        print("\nSAVED JOB RECORDS")
        print("-" * 55)

        for job in jobs:

            published = job.published_at

            if published and published.tzinfo is None:
                published = published.replace(
                    tzinfo=timezone.utc
                )

            is_recent = (
                published is not None
                and cutoff <= published <= datetime.now(timezone.utc)
            )

            if is_recent:
                recent_count += 1

            print("\nTitle:", job.title)
            print("Company:", job.company_name)
            print("Location:", job.location)
            print("Source:", job.source_name)
            print("Published:", job.published_at)
            print("Verified recent:", job.verified_last_24_hours)
            print("URL:", job.job_url)
            print("Within last 24 hours:", is_recent)

        print("\n" + "-" * 55)
        print("Total stored:", len(jobs))
        print("Actually within last 24 hours:", recent_count)
        print("=" * 55)


if __name__ == "__main__":
    main()
