
from datetime import datetime, timedelta, timezone
from typing import Optional

import dateparser

from logger import logger


# --------------------------------------------------
# CURRENT UTC TIME
# --------------------------------------------------

def get_current_utc():
    return datetime.now(timezone.utc)


# --------------------------------------------------
# PARSE DATE
# --------------------------------------------------

def parse_date(date_value) -> Optional[datetime]:
    """
    Convert supported date formats into timezone-aware UTC.
    """

    if date_value is None:
        return None

    if isinstance(date_value, datetime):

        parsed = date_value

    elif isinstance(date_value, str):

        date_value = date_value.strip()

        if not date_value:
            return None

        parsed = dateparser.parse(
            date_value,
            settings={
                "RETURN_AS_TIMEZONE_AWARE": True,
                "TIMEZONE": "UTC",
                "TO_TIMEZONE": "UTC",
                "PREFER_DATES_FROM": "past",
                "RELATIVE_BASE": get_current_utc()
            }
        )

    else:
        return None

    if parsed is None:
        logger.warning("Unable to parse date: %s", date_value)
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


# --------------------------------------------------
# VERIFY LAST 24 HOURS
# --------------------------------------------------

def is_within_last_24_hours(
    published_at: Optional[datetime],
    reference_time: Optional[datetime] = None
) -> bool:
    """
    Check whether a publication date is within the previous
    24 hours. Future dates are rejected.
    """

    if published_at is None:
        return False

    if reference_time is None:
        reference_time = get_current_utc()

    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    published_at = published_at.astimezone(timezone.utc)
    reference_time = reference_time.astimezone(timezone.utc)

    age = reference_time - published_at

    return timedelta(0) <= age <= timedelta(hours=24)


# --------------------------------------------------
# FRESHNESS DETAILS
# --------------------------------------------------

def get_freshness_details(date_value):
    """
    Return normalized date and freshness information.
    """

    published_at = parse_date(date_value)

    if published_at is None:

        return {
            "published_at": None,
            "verified_last_24_hours": False,
            "status": "unverified",
            "age_hours": None
        }

    now = get_current_utc()

    age = now - published_at

    verified = is_within_last_24_hours(
        published_at,
        now
    )

    return {
        "published_at": published_at,
        "verified_last_24_hours": verified,
        "status": "fresh" if verified else (
            "future_date" if age < timedelta(0) else "older_than_24_hours"
        ),
        "age_hours": round(age.total_seconds() / 3600, 2)
    }


# --------------------------------------------------
# FILTER FRESH RECORDS
# --------------------------------------------------

def filter_fresh_records(records, date_field="published_at"):
    """
    Keep only records with verified publication dates
    within the previous 24 hours.
    """

    fresh_records = []

    for record in records:

        if isinstance(record, dict):
            date_value = record.get(date_field)
        else:
            date_value = getattr(record, date_field, None)

        details = get_freshness_details(date_value)

        if details["verified_last_24_hours"]:
            fresh_records.append(record)

    return fresh_records


# --------------------------------------------------
# TESTING
# --------------------------------------------------

if __name__ == "__main__":

    print("=" * 55)
    print("DATE NORMALIZATION AND FRESHNESS VALIDATION")
    print("=" * 55)

    now = get_current_utc()

    test_dates = [
        "2 hours ago",
        "yesterday",
        "2026-11-22T10:00:00Z",
        "invalid date"
    ]

    for value in test_dates:

        result = get_freshness_details(value)

        print("\nInput:", value)
        print("Normalized:", result["published_at"])
        print("Fresh:", result["verified_last_24_hours"])
        print("Status:", result["status"])
        print("Age (hours):", result["age_hours"])

    print("\nDate validation completed!")
