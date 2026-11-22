
import re
from rapidfuzz import fuzz

from database import get_session, EntityMappingLog
from logger import logger


# --------------------------------------------------
# NAME NORMALIZATION
# --------------------------------------------------

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd",
    "limited", "corp", "corporation",
    "co", "company"
}


def normalize_name(name: str) -> str:
    """
    Normalize company names for deterministic comparison.
    """

    if not name or not isinstance(name, str):
        return ""

    name = name.lower().strip()

    # Remove punctuation
    name = re.sub(r"[^\w\s]", " ", name)

    # Remove common legal suffixes
    words = name.split()
    words = [word for word in words if word not in LEGAL_SUFFIXES]

    # Join words to handle variations such as Open AI / OpenAI
    return "".join(words)


# --------------------------------------------------
# SEED DATABASE: 50 AI COMPANIES
# These are matching references, not submitted records.
# --------------------------------------------------

AI_COMPANIES = {
    "OpenAI": ["Open AI", "OpenAI Inc"],
    "Anthropic": ["Anthropic Inc"],
    "Cohere": ["Cohere Inc"],
    "Mistral AI": ["Mistral", "MistralAI"],
    "xAI": ["X AI"],
    "Perplexity AI": ["Perplexity", "PerplexityAI"],
    "Hugging Face": ["HuggingFace"],
    "Stability AI": ["StabilityAI"],
    "Runway": ["Runway ML", "RunwayML"],
    "Scale AI": ["ScaleAI"],
    "Adept AI": ["Adept"],
    "Inflection AI": ["Inflection"],
    "Character.AI": ["Character AI", "CharacterAI"],
    "AI21 Labs": ["AI21", "AI21Labs"],
    "Together AI": ["TogetherAI"],
    "Anyscale": [],
    "Pinecone": ["Pinecone Systems"],
    "Weights & Biases": ["Weights and Biases", "WandB"],
    "Replicate": ["Replicate AI"],
    "Modal": ["Modal Labs"],
    "Groq": ["Groq Inc"],
    "Cerebras Systems": ["Cerebras"],
    "SambaNova Systems": ["SambaNova"],
    "Synthesia": ["Synthesia AI"],
    "ElevenLabs": ["Eleven Labs"],
    "Suno": ["Suno AI"],
    "Midjourney": ["Midjourney Inc"],
    "Pika": ["Pika Labs"],
    "Luma AI": ["Luma"],
    "Glean": ["Glean AI"],
    "Harvey": ["Harvey AI"],
    "Writer": ["Writer AI"],
    "Typeface": ["Typeface AI"],
    "Sierra": ["Sierra AI"],
    "Figure AI": ["Figure"],
    "Physical Intelligence": ["Physical Intelligence AI"],
    "Skild AI": ["Skild"],
    "Wayve": ["Wayve AI"],
    "Shield AI": ["ShieldAI"],
    "Anduril": ["Anduril Industries"],
    "Databricks": ["Databricks Inc"],
    "DataRobot": ["Data Robot"],
    "Snorkel AI": ["Snorkel"],
    "Arize AI": ["Arize"],
    "LangChain": ["Lang Chain"],
    "Vercel": ["Vercel Inc"],
    "Baseten": ["Baseten AI"],
    "DeepL": ["Deep L"],
    "Qdrant": ["Qdrant AI"],
    "Chroma": ["Chroma DB", "ChromaDB"],
}


# --------------------------------------------------
# BUILD NORMALIZED LOOKUP INDEX
# --------------------------------------------------

ALIAS_INDEX = {}

for canonical_name, aliases in AI_COMPANIES.items():

    all_names = [canonical_name] + aliases

    for name in all_names:

        normalized = normalize_name(name)

        if normalized:
            ALIAS_INDEX[normalized] = canonical_name


# --------------------------------------------------
# ENTITY RESOLUTION
# --------------------------------------------------

def resolve_entity(
    original_name: str,
    threshold: int = 92,
    minimum_margin: int = 5
):
    """
    Resolve a company name using:
    1. Exact normalized matching
    2. Controlled fuzzy matching
    3. Unresolved fallback
    """

    if not original_name or not original_name.strip():

        return {
            "original_name": original_name,
            "canonical_name": None,
            "confidence": 0.0,
            "method": "invalid_input",
            "resolved": False
        }

    normalized = normalize_name(original_name)

    if not normalized:

        return {
            "original_name": original_name,
            "canonical_name": None,
            "confidence": 0.0,
            "method": "invalid_input",
            "resolved": False
        }

    # 1. Exact deterministic match
    if normalized in ALIAS_INDEX:

        canonical = ALIAS_INDEX[normalized]

        return {
            "original_name": original_name,
            "canonical_name": canonical,
            "confidence": 1.0,
            "method": "exact_normalization",
            "resolved": True
        }

    # 2. Fuzzy matching fallback
    scores = {}

    for alias, canonical in ALIAS_INDEX.items():

        score = fuzz.ratio(normalized, alias)

        scores[canonical] = max(
            scores.get(canonical, 0),
            score
        )

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    if not ranked:

        return {
            "original_name": original_name,
            "canonical_name": None,
            "confidence": 0.0,
            "method": "unresolved",
            "resolved": False
        }

    best_name, best_score = ranked[0]

    second_score = ranked[1][1] if len(ranked) > 1 else 0

    # Reject weak or ambiguous matches
    if (
        best_score < threshold
        or best_score - second_score < minimum_margin
    ):

        return {
            "original_name": original_name,
            "canonical_name": None,
            "confidence": round(best_score / 100, 4),
            "method": "unresolved",
            "resolved": False
        }

    return {
        "original_name": original_name,
        "canonical_name": best_name,
        "confidence": round(best_score / 100, 4),
        "method": "fuzzy_match",
        "resolved": True
    }


# --------------------------------------------------
# SAVE ENTITY MAPPING TO DATABASE
# --------------------------------------------------

def save_entity_mapping(
    result: dict,
    entity_type: str = "startup",
    source_url: str = None
):
    """
    Save successfully resolved entity mappings.
    Unresolved names are not assigned a false canonical name.
    """

    if not result.get("resolved"):
        logger.warning(
            "Entity unresolved: %s",
            result.get("original_name")
        )
        return False

    try:

        with get_session() as session:

            mapping = EntityMappingLog(
                original_name=result["original_name"],
                canonical_name=result["canonical_name"],
                entity_type=entity_type,
                confidence=result["confidence"],
                method=result["method"],
                source_url=source_url
            )

            session.add(mapping)

        logger.info(
            "Entity mapping saved: %s -> %s",
            result["original_name"],
            result["canonical_name"]
        )

        return True

    except Exception:

        logger.exception("Failed to save entity mapping")
        raise


# --------------------------------------------------
# TESTING
# --------------------------------------------------

if __name__ == "__main__":

    print("=" * 55)
    print("DETERMINISTIC ENTITY RESOLUTION")
    print("=" * 55)

    test_names = [
        "Open AI",
        "OpenAI Inc.",
        "Anthropic, Inc.",
        "MistralAI",
        "HuggingFace",
        "Eleven Labs",
        "Completely Unknown Company"
    ]

    print("\nSeed companies:", len(AI_COMPANIES))

    print("\nEntity resolution results:\n")

    for name in test_names:

        result = resolve_entity(name)

        print("Original:", result["original_name"])
        print("Canonical:", result["canonical_name"])
        print("Confidence:", result["confidence"])
        print("Method:", result["method"])
        print("Resolved:", result["resolved"])
        print("-" * 40)

    print("\nEntity resolution test completed!")
