
import csv
import json
from pathlib import Path

from database import (
    SessionLocal,
    Startup,
    Product,
    ResearchPaper,
    Job,
    News,
    EntityMappingLog,
)

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

TABLES = {
    "Startups": Startup,
    "Products": Product,
    "Research Papers": ResearchPaper,
    "Jobs": Job,
    "News": News,
    "Entity Mapping Log": EntityMappingLog,
}


def export_table(session, name, model):
    records = session.query(model).all()
    columns = [column.name for column in model.__table__.columns]

    filename = name.lower().replace(" ", "_") + ".csv"
    filepath = EXPORT_DIR / filename

    with filepath.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns
        )
        writer.writeheader()

        for record in records:
            row = {}

            for column in columns:
                value = getattr(record, column)

                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)

                row[column] = value

            writer.writerow(row)

    print(f"{name}: {len(records)} records exported")
    print(f"File: {filepath}")


def main():
    session = SessionLocal()

    try:
        print("=" * 55)
        print("AI INTELLIGENCE DATA PIPELINE")
        print("DATABASE EXPORT")
        print("=" * 55)

        total = 0

        for name, model in TABLES.items():
            export_table(session, name, model)
            total += session.query(model).count()

        print("=" * 55)
        print("TOTAL RECORDS:", total)
        print("EXPORT DIRECTORY:", EXPORT_DIR.resolve())
        print("EXPORT COMPLETED")
        print("=" * 55)

    finally:
        session.close()


if __name__ == "__main__":
    main()
