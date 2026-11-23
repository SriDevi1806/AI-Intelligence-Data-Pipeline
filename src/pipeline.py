import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent


def print_header():
    print("\n" + "=" * 65)
    print("AI INTELLIGENCE DATA PIPELINE")
    print("MASTER PIPELINE EXECUTION")
    print("=" * 65)
    print("Started:", datetime.now(timezone.utc).isoformat())
    print("Project:", BASE_DIR)


def run_stage(name, filename):
    script_path = BASE_DIR / filename

    print("\n" + "=" * 65)
    print("RUNNING:", name)
    print("FILE:", filename)
    print("=" * 65)

    if not script_path.exists():
        print("ERROR: File not found:", script_path)
        return False

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        check=False
    )

    if result.returncode != 0:
        print("\nFAILED:", name)
        print("Exit code:", result.returncode)
        return False

    print("\nCOMPLETED:", name)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="AI Intelligence Data Pipeline"
    )

    parser.add_argument(
        "--skip-github",
        action="store_true",
        help="Skip GitHub repository verification"
    )

    parser.add_argument(
        "--skip-sheets",
        action="store_true",
        help="Skip Google Sheets upload"
    )

    args = parser.parse_args()

    print_header()

    stages = [
        ("Startup Collection", "startup_collector.py"),
        ("Product Collection", "product_collector.py"),
        ("Research Paper Collection", "research_collector.py"),
    ]

    if not args.skip_github:
        stages.append(
            ("GitHub Repository Verification", "github_collector.py")
        )

    stages.extend([
        ("Job Collection", "job_collector.py"),
        ("News Collection", "news_collector.py"),
        ("CSV Data Export", "export_data.py"),
    ])

    if not args.skip_sheets:
        stages.append(
            ("Google Sheets Export", "google_sheets_exporter.py")
        )

    completed = []
    failed = None

    for name, filename in stages:
        if run_stage(name, filename):
            completed.append(name)
        else:
            failed = name
            break

    print("\n" + "=" * 65)
    print("PIPELINE EXECUTION REPORT")
    print("=" * 65)

    print("Completed stages:", len(completed))

    for name in completed:
        print("[SUCCESS]", name)

    if failed:
        print("[FAILED]", failed)
        print("\nPipeline stopped because a stage failed.")
        print("Fix the error and run the pipeline again.")
        return 1

    print("\nALL PIPELINE STAGES COMPLETED SUCCESSFULLY")
    print("Finished:", datetime.now(timezone.utc).isoformat())
    print("=" * 65)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPipeline stopped by user.")
        sys.exit(130)
