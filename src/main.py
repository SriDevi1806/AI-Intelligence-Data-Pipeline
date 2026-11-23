import sys
from pathlib import Path
from datetime import datetime, timezone

from config import PROJECT_NAME, VERSION
from pipeline import main as run_pipeline


def main():
    print("\n" + "=" * 65)
    print(PROJECT_NAME.upper())
    print("VERSION:", VERSION)
    print("=" * 65)

    print(
        "Execution started:",
        datetime.now(timezone.utc).isoformat()
    )

    print("Project directory:", Path(__file__).resolve().parent)

    exit_code = run_pipeline()

    print("\n" + "=" * 65)
    if exit_code == 0:
        print("APPLICATION EXECUTION COMPLETED")
    else:
        print("APPLICATION EXECUTION FAILED")

    print("=" * 65)

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
        sys.exit(130)
