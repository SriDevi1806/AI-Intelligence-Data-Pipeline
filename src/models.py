
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------
# BASE MODEL
# --------------------------------------------------

class BaseRecord(BaseModel):

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore"
    )

    @field_validator("*", mode="before")
    @classmethod
    def validate_urls(cls, value, info):

        url_fields = {
            "website",
            "source_url",
            "paper_url",
            "github_url",
            "job_url",
            "article_url",
        }

        if info.field_name in url_fields and value:
            value = str(value).strip()

            if not value.startswith(("http://", "https://")):
                raise ValueError(
                    f"{info.field_name} must be a valid HTTP or HTTPS URL"
                )

        return value


def normalize_datetime(value):

    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


# --------------------------------------------------
# 1. STARTUP MODEL
# --------------------------------------------------

class StartupModel(BaseRecord):

    name: str = Field(min_length=1, max_length=300)

    normalized_name: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    source_url: Optional[str] = None

    raw_data: Optional[dict] = None


# --------------------------------------------------
# 2. PRODUCT MODEL
# --------------------------------------------------

class ProductModel(BaseRecord):

    name: str = Field(min_length=1, max_length=500)

    company_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    website: Optional[str] = None
    source_url: Optional[str] = None

    raw_data: Optional[dict] = None


# --------------------------------------------------
# 3. RESEARCH PAPER MODEL
# --------------------------------------------------

class ResearchPaperModel(BaseRecord):

    title: str = Field(min_length=1, max_length=1000)

    authors: list[str] = Field(default_factory=list)

    abstract: Optional[str] = None
    published_date: Optional[datetime] = None

    arxiv_id: Optional[str] = None

    github_url: Optional[str] = None
    github_stars: Optional[int] = Field(default=None, ge=0)

    paper_url: Optional[str] = None
    source_url: Optional[str] = None

    raw_data: Optional[dict] = None

    @field_validator("published_date")
    @classmethod
    def validate_published_date(cls, value):
        return normalize_datetime(value)


# --------------------------------------------------
# 4. JOB MODEL
# --------------------------------------------------

class JobModel(BaseRecord):

    title: str = Field(min_length=1, max_length=500)

    company_name: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None

    description: Optional[str] = None

    published_at: Optional[datetime] = None
    verified_last_24_hours: bool = False

    job_url: Optional[str] = None
    source_name: Optional[str] = None

    raw_data: Optional[dict] = None

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value):
        return normalize_datetime(value)


# --------------------------------------------------
# 5. NEWS MODEL
# --------------------------------------------------

class NewsModel(BaseRecord):

    title: str = Field(min_length=1, max_length=1000)

    source_name: Optional[str] = None

    description: Optional[str] = None
    full_text: Optional[str] = None

    published_at: Optional[datetime] = None
    verified_last_24_hours: bool = False

    article_url: Optional[str] = None

    raw_data: Optional[dict] = None

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value):
        return normalize_datetime(value)


# --------------------------------------------------
# 6. ENTITY MAPPING MODEL
# --------------------------------------------------

class EntityMappingModel(BaseRecord):

    original_name: str = Field(min_length=1, max_length=500)

    canonical_name: str = Field(min_length=1, max_length=500)

    entity_type: Optional[str] = None

    confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=1
    )

    method: Optional[str] = None
    source_url: Optional[str] = None


# --------------------------------------------------
# TEST MODELS
# --------------------------------------------------

if __name__ == "__main__":

    print("=" * 50)
    print("PYDANTIC DATA MODEL VALIDATION")
    print("=" * 50)

    startup = StartupModel(
        name="OpenAI",
        normalized_name="openai",
        website="https://openai.com",
        industry="Artificial Intelligence",
        source_url="https://openai.com"
    )

    product = ProductModel(
        name="ChatGPT",
        company_name="OpenAI",
        website="https://chatgpt.com",
        source_url="https://openai.com"
    )

    paper = ResearchPaperModel(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        paper_url="https://arxiv.org/abs/1706.03762",
        github_stars=100
    )

    job = JobModel(
        title="AI Engineer",
        company_name="Example Company",
        job_url="https://example.com/jobs/ai-engineer"
    )

    news = NewsModel(
        title="Example AI News",
        source_name="Example Source",
        article_url="https://example.com/news/ai"
    )

    mapping = EntityMappingModel(
        original_name="Open AI",
        canonical_name="OpenAI",
        entity_type="startup",
        confidence=0.95,
        method="exact_normalization"
    )

    print("\nAll six data models validated successfully!")

    print("\nValidated examples:")

    print("Startup:", startup.name)
    print("Product:", product.name)
    print("Research Paper:", paper.title)
    print("Job:", job.title)
    print("News:", news.title)
    print("Entity Mapping:", mapping.original_name, "->", mapping.canonical_name)

    print("\nPydantic validation is working!")
