
import csv
import os
from pathlib import Path

import gspread
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "exports"

load_dotenv(BASE_DIR / ".env")

SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    str(BASE_DIR / "google_service_account.json")
)

SPREADSHEET_ID = os.getenv(
    "GOOGLE_SHEETS_SPREADSHEET_ID",
    ""
)

SPREADSHEET_TITLE = "AI Intelligence Data Pipeline"

MAKE_PUBLIC = os.getenv(
    "GOOGLE_SHEETS_PUBLIC", "true"
).lower() == "true"

OWNER_EMAIL = os.getenv(
    "GOOGLE_SHEETS_OWNER_EMAIL", ""
)

BATCH_SIZE = 500


# ============================================================
# SIX REQUIRED DATASETS
# ============================================================

DATASETS = {
    "Startups": "startups.csv",
    "Products": "products.csv",
    "Research Papers": "research_papers.csv",
    "Jobs": "jobs.csv",
    "News": "news.csv",
    "Entity Mapping Log": "entity_mapping_log.csv",
}


# ============================================================
# READ CSV
# ============================================================

def read_csv_file(filename):

    filepath = EXPORT_DIR / filename

    if not filepath.exists():
        raise FileNotFoundError(
            f"CSV file not found: {filepath}"
        )

    with filepath.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.reader(file)
        rows = list(reader)

    if not rows:
        raise ValueError(
            f"CSV file is empty: {filename}"
        )

    return rows


# ============================================================
# CONNECT TO GOOGLE SHEETS
# ============================================================

def connect_google_sheets():

    credentials_path = Path(SERVICE_ACCOUNT_FILE)

    if not credentials_path.exists():
        raise FileNotFoundError(
            "Google service account credentials not found.\n"
            f"Expected file: {credentials_path}"
        )

    client = gspread.service_account(
        filename=str(credentials_path)
    )

    if SPREADSHEET_ID:
        spreadsheet = client.open_by_key(
            SPREADSHEET_ID
        )
    else:
        spreadsheet = client.create(
            SPREADSHEET_TITLE
        )

        if OWNER_EMAIL:
            spreadsheet.share(
                OWNER_EMAIL,
                perm_type="user",
                role="writer"
            )

        print("New spreadsheet created.")

    if MAKE_PUBLIC:
        spreadsheet.share(
            None,
            perm_type="anyone",
            role="reader"
        )

    return spreadsheet


# ============================================================
# CREATE OR REUSE WORKSHEET
# ============================================================

def get_or_create_worksheet(spreadsheet, title):

    try:
        worksheet = spreadsheet.worksheet(title)

    except gspread.WorksheetNotFound:

        worksheet = spreadsheet.add_worksheet(
            title=title,
            rows=1000,
            cols=20
        )

    worksheet.clear()

    return worksheet


# ============================================================
# UPLOAD DATA IN BATCHES
# ============================================================

def upload_dataset(spreadsheet, sheet_name, filename):

    print(f"\nUploading: {sheet_name}")

    rows = read_csv_file(filename)

    worksheet = get_or_create_worksheet(
        spreadsheet,
        sheet_name
    )

    total_rows = len(rows)
    total_columns = max(len(row) for row in rows)

    worksheet.resize(
        rows=max(total_rows, 1),
        cols=max(total_columns, 1)
    )

    for start in range(0, total_rows, BATCH_SIZE):

        batch = rows[start:start + BATCH_SIZE]

        start_row = start + 1
        end_row = start + len(batch)

        worksheet.update(
            values=batch,
            range_name=f"A{start_row}",
            value_input_option="RAW"
        )

        print(
            f"Uploaded rows {start_row} - {end_row}"
        )

    print(
        f"Completed: {sheet_name} "
        f"({total_rows - 1} data records)"
    )


# ============================================================
# MAIN EXPORT
# ============================================================

def export_to_google_sheets():

    print("=" * 60)
    print("AI INTELLIGENCE DATA PIPELINE")
    print("GOOGLE SHEETS EXPORT")
    print("=" * 60)

    spreadsheet = connect_google_sheets()

    print("\nSpreadsheet:", spreadsheet.title)

    for sheet_name, filename in DATASETS.items():

        upload_dataset(
            spreadsheet,
            sheet_name,
            filename
        )

    print("\n" + "=" * 60)
    print("GOOGLE SHEETS EXPORT COMPLETED")
    print("=" * 60)

    print("\nSPREADSHEET URL:")
    print(spreadsheet.url)

    return spreadsheet.url


if __name__ == "__main__":

    try:
        export_to_google_sheets()

    except Exception as error:

        print("\nGOOGLE SHEETS EXPORT FAILED")
        print("Reason:", error)
        raise
