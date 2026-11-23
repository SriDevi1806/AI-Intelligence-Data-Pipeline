
from datetime import datetime, timezone
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    Boolean,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL
from logger import logger


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

engine_options = {
    "pool_pre_ping": True,
}

if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    **engine_options
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


# --------------------------------------------------
# 1. STARTUPS TABLE
# --------------------------------------------------

class Startup(Base):

    __tablename__ = "startups"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(300), nullable=False, index=True)
    normalized_name = Column(String(300), index=True)

    website = Column(String(1000))
    description = Column(Text)
    industry = Column(String(300))
    headquarters = Column(String(300))

    source_url = Column(String(1500), unique=True, index=True)

    raw_data = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=utc_now)


# --------------------------------------------------
# 2. PRODUCTS TABLE
# --------------------------------------------------

class Product(Base):

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(500), nullable=False, index=True)
    company_name = Column(String(300))

    description = Column(Text)
    category = Column(String(300))
    website = Column(String(1000))

    source_url = Column(String(1500), unique=True, index=True)

    raw_data = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=utc_now)


# --------------------------------------------------
# 3. RESEARCH PAPERS TABLE
# --------------------------------------------------

class ResearchPaper(Base):

    __tablename__ = "research_papers"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(1000), nullable=False, index=True)
    authors = Column(JSON)

    abstract = Column(Text)
    published_date = Column(DateTime(timezone=True))

    arxiv_id = Column(String(100), unique=True, index=True)

    github_url = Column(String(1000))
    github_stars = Column(Integer)

    paper_url = Column(String(1500), unique=True, index=True)
    source_url = Column(String(1500))

    raw_data = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=utc_now)


# --------------------------------------------------
# 4. JOBS TABLE
# --------------------------------------------------

class Job(Base):

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(500), nullable=False, index=True)
    company_name = Column(String(300), index=True)

    location = Column(String(300))
    job_type = Column(String(100))

    description = Column(Text)

    published_at = Column(DateTime(timezone=True), index=True)
    verified_last_24_hours = Column(Boolean, default=False)

    job_url = Column(String(1500), unique=True, index=True)
    source_name = Column(String(300))

    raw_data = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=utc_now)


# --------------------------------------------------
# 5. NEWS TABLE
# --------------------------------------------------

class News(Base):

    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(1000), nullable=False, index=True)
    source_name = Column(String(300))

    description = Column(Text)
    full_text = Column(Text)

    published_at = Column(DateTime(timezone=True), index=True)
    verified_last_24_hours = Column(Boolean, default=False)

    article_url = Column(String(1500), unique=True, index=True)

    raw_data = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=utc_now)


# --------------------------------------------------
# 6. ENTITY MAPPING LOG TABLE
# --------------------------------------------------

class EntityMappingLog(Base):

    __tablename__ = "entity_mapping_log"

    id = Column(Integer, primary_key=True, index=True)

    original_name = Column(String(500), nullable=False, index=True)
    canonical_name = Column(String(500), nullable=False, index=True)

    entity_type = Column(String(100))

    confidence = Column(Float)
    method = Column(String(100))

    source_url = Column(String(1500))

    created_at = Column(DateTime(timezone=True), default=utc_now)


# --------------------------------------------------
# DATABASE INDEXES
# --------------------------------------------------

Index(
    "idx_jobs_published_at",
    Job.published_at
)

Index(
    "idx_news_published_at",
    News.published_at
)

Index(
    "idx_startups_normalized_name",
    Startup.normalized_name
)


# --------------------------------------------------
# INITIALIZE DATABASE
# --------------------------------------------------

def init_db():

    try:
        Base.metadata.create_all(bind=engine)

        logger.info("Database tables created successfully.")

        return True

    except Exception as error:

        logger.exception("Database initialization failed: %s", error)

        raise


# --------------------------------------------------
# DATABASE SESSION
# --------------------------------------------------

@contextmanager
def get_session():

    session = SessionLocal()

    try:
        yield session
        session.commit()

    except Exception:

        session.rollback()
        raise

    finally:
        session.close()


# --------------------------------------------------
# DATABASE TEST
# --------------------------------------------------

if __name__ == "__main__":

    print("=" * 50)
    print("AI INTELLIGENCE DATABASE")
    print("=" * 50)

    init_db()

    print("\nDatabase initialized successfully!")

    print("\nAvailable tables:")

    for table_name in Base.metadata.tables:
        print("-", table_name)

    print("\nDatabase connection is working!")
