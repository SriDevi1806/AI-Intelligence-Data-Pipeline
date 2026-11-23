
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


# --------------------------------------------------
# SOURCE MODEL
# --------------------------------------------------

@dataclass(frozen=True)
class DataSource:

    name: str
    category: str
    url: str
    source_type: str

    enabled: bool = True
    requires_api_key: bool = False
    description: str = ""


# --------------------------------------------------
# SOURCE REGISTRY
# --------------------------------------------------

SOURCES = [

    # ----------------------------------------------
    # STARTUP SOURCES
    # ----------------------------------------------

    DataSource(
        name="Y Combinator",
        category="startups",
        url="https://www.ycombinator.com/companies",
        source_type="web",
        description="Startup directory"
    ),

    DataSource(
        name="Crunchbase",
        category="startups",
        url="https://www.crunchbase.com/",
        source_type="web",
        description="Company discovery; use permitted access"
    ),

    DataSource(
        name="Product Hunt",
        category="startups",
        url="https://www.producthunt.com/",
        source_type="web",
        description="Startup and product discovery"
    ),

    # ----------------------------------------------
    # PRODUCT SOURCES
    # ----------------------------------------------

    DataSource(
        name="Hugging Face Models",
        category="products",
        url="https://huggingface.co/models",
        source_type="web",
        description="AI model and product discovery"
    ),

    DataSource(
        name="Product Hunt",
        category="products",
        url="https://www.producthunt.com/",
        source_type="web",
        description="AI product listings"
    ),

    DataSource(
        name="GitHub",
        category="products",
        url="https://github.com/",
        source_type="api",
        description="Public AI repositories and tools"
    ),

    # ----------------------------------------------
    # RESEARCH PAPER SOURCES
    # ----------------------------------------------

    DataSource(
        name="arXiv",
        category="research_papers",
        url="https://export.arxiv.org/api/query",
        source_type="api",
        description="Scientific research papers"
    ),

    DataSource(
        name="Semantic Scholar",
        category="research_papers",
        url="https://api.semanticscholar.org/graph/v1/paper/search",
        source_type="api",
        description="Research paper metadata"
    ),

    DataSource(
        name="Papers With Code",
        category="research_papers",
        url="https://paperswithcode.com/",
        source_type="web",
        description="Research papers and implementations"
    ),

    # ----------------------------------------------
    # AI NEWS SOURCES
    # ----------------------------------------------

    DataSource(
        name="Google AI Blog",
        category="news",
        url="https://blog.google/technology/ai/rss/",
        source_type="rss",
        description="Google AI announcements"
    ),

    DataSource(
        name="MIT News",
        category="news",
        url="https://news.mit.edu/rss/topic/artificial-intelligence2",
        source_type="rss",
        description="Artificial intelligence research news"
    ),

    DataSource(
        name="TechCrunch AI",
        category="news",
        url="https://techcrunch.com/category/artificial-intelligence/feed/",
        source_type="rss",
        description="AI industry news"
    ),

    DataSource(
        name="VentureBeat AI",
        category="news",
        url="https://venturebeat.com/category/ai/feed/",
        source_type="rss",
        description="AI technology and business news"
    ),

    DataSource(
        name="The Verge AI",
        category="news",
        url="https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        source_type="rss",
        description="AI technology coverage"
    ),

    # ----------------------------------------------
    # AI JOB SOURCES
    # ----------------------------------------------

    DataSource(
        name="Wellfound",
        category="jobs",
        url="https://wellfound.com/jobs",
        source_type="web",
        description="Startup and technology jobs"
    ),

    DataSource(
        name="Greenhouse",
        category="jobs",
        url="https://www.greenhouse.io/",
        source_type="web",
        description="Use individual employers' public job-board feeds"
    ),

    DataSource(
        name="Lever",
        category="jobs",
        url="https://www.lever.co/",
        source_type="web",
        description="Use individual employers' public job-board feeds"
    ),

    DataSource(
        name="Ashby",
        category="jobs",
        url="https://www.ashbyhq.com/",
        source_type="web",
        description="Use public employer job-board endpoints"
    ),

    DataSource(
        name="Work at a Startup",
        category="jobs",
        url="https://www.workatastartup.com/",
        source_type="web",
        description="Startup job discovery"
    ),

    # ----------------------------------------------
    # GITHUB SOURCE
    # ----------------------------------------------

    DataSource(
        name="GitHub REST API",
        category="github",
        url="https://api.github.com/",
        source_type="api",
        description="Repository URLs and star counts"
    )

]


# --------------------------------------------------
# SOURCE VALIDATION
# --------------------------------------------------

def validate_source(source: DataSource):

    parsed = urlparse(source.url)

    if parsed.scheme not in {"http", "https"}:
        return False

    if not parsed.netloc:
        return False

    if not source.name or not source.category:
        return False

    return True


# --------------------------------------------------
# GET SOURCES BY CATEGORY
# --------------------------------------------------

def get_sources(category: str):

    return [
        source
        for source in SOURCES
        if source.category == category and source.enabled
    ]


# --------------------------------------------------
# GET ALL SOURCES
# --------------------------------------------------

def get_all_sources():

    return [
        source
        for source in SOURCES
        if source.enabled
    ]


# --------------------------------------------------
# SOURCE SUMMARY
# --------------------------------------------------

def get_source_summary():

    summary = {}

    for source in get_all_sources():

        summary.setdefault(
            source.category,
            []
        ).append(source.name)

    return summary


# --------------------------------------------------
# TESTING
# --------------------------------------------------

if __name__ == "__main__":

    print("=" * 55)
    print("AI INTELLIGENCE SOURCE REGISTRY")
    print("=" * 55)

    valid_sources = [
        source
        for source in SOURCES
        if validate_source(source)
    ]

    print(
        "\nTotal registered sources:",
        len(SOURCES)
    )

    print(
        "Valid source configurations:",
        len(valid_sources)
    )

    print("\nSources by category:")

    for category, names in get_source_summary().items():

        print(f"\n{category.upper()}")

        for name in names:
            print("-", name)

    print("\nNews source count:", len(get_sources("news")))
    print("Job source count:", len(get_sources("jobs")))

    print("\nSource registry validation completed!")
