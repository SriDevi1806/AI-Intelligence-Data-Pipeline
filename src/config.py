
import os
from pathlib import Path
from dotenv import load_dotenv

# --------------------------------------------------
# PROJECT CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

PROJECT_NAME = "AI Intelligence Data Pipeline"
VERSION = "1.0.0"

# --------------------------------------------------
# API KEYS
# --------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./ai_intelligence.db"
)

# --------------------------------------------------
# CRAWLER CONFIGURATION
# --------------------------------------------------

MAX_CONCURRENT_REQUESTS = int(
    os.getenv("MAX_CONCURRENT_REQUESTS", "10")
)

REQUEST_TIMEOUT = int(
    os.getenv("REQUEST_TIMEOUT", "30")
)

MAX_RETRIES = int(
    os.getenv("MAX_RETRIES", "5")
)

BATCH_SIZE = int(
    os.getenv("BATCH_SIZE", "100")
)

# --------------------------------------------------
# DATA COLLECTION TARGETS
# --------------------------------------------------

STARTUP_TARGET = 1000
PRODUCT_TARGET = 1000
RESEARCH_PAPER_TARGET = 1000

# --------------------------------------------------
# FRESHNESS CONFIGURATION
# --------------------------------------------------

NEWS_FRESHNESS_HOURS = 24
JOB_FRESHNESS_HOURS = 24

# --------------------------------------------------
# STORAGE DIRECTORIES
# --------------------------------------------------

DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"

for directory in [
    DATA_DIR,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    EXPORT_DIR,
    LOG_DIR
]:
    directory.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# LOGGING CONFIGURATION
# --------------------------------------------------

LOG_FILE = LOG_DIR / "pipeline.log"

# --------------------------------------------------
# VALIDATION
# --------------------------------------------------

def validate_config():
    if MAX_CONCURRENT_REQUESTS < 1:
        raise ValueError("Concurrency must be at least 1")

    if REQUEST_TIMEOUT < 1:
        raise ValueError("Request timeout must be positive")

    if MAX_RETRIES < 0:
        raise ValueError("Retries cannot be negative")

    if BATCH_SIZE < 1:
        raise ValueError("Batch size must be positive")

    return True


if __name__ == "__main__":
    validate_config()

    print("=" * 50)
    print(PROJECT_NAME)
    print("=" * 50)

    print("Version:", VERSION)
    print("Database:", DATABASE_URL)
    print("Concurrent Requests:", MAX_CONCURRENT_REQUESTS)
    print("Batch Size:", BATCH_SIZE)

    print("Gemini Configured:", bool(GEMINI_API_KEY))
    print("Groq Configured:", bool(GROQ_API_KEY))
    print("DeepSeek Configured:", bool(DEEPSEEK_API_KEY))
    print("GitHub Configured:", bool(GITHUB_TOKEN))

    print("\nConfiguration loaded successfully!")
