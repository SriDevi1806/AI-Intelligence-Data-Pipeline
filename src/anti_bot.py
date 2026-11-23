
import random

from logger import logger


PROTECTION_SIGNATURES = {
    "Cloudflare": [
        "cf-chl-",
        "cloudflare ray id",
        "attention required! | cloudflare",
        "checking your browser",
    ],
    "DataDome": [
        "datadome",
        "geo.captcha-delivery.com",
        "captcha-delivery.com",
    ],
    "Generic CAPTCHA": [
        "verify you are human",
        "complete the captcha",
        "captcha challenge",
    ],
}


def detect_protection(html="", status_code=None, headers=None):

    html = (html or "").lower()

    headers = {
        str(key).lower(): str(value).lower()
        for key, value in (headers or {}).items()
    }

    if status_code == 403:
        logger.warning("HTTP 403 access restriction detected.")

    if status_code == 429:
        logger.warning("HTTP 429 rate limit detected.")

    server = headers.get("server", "")

    if "cloudflare" in server:
        return "Cloudflare"

    for provider, signatures in PROTECTION_SIGNATURES.items():

        if any(signature in html for signature in signatures):

            logger.warning(
                "%s protection or challenge page detected.",
                provider
            )

            return provider

    return None


# --------------------------------------------------
# FALLBACK DECISION ENGINE
# --------------------------------------------------

def get_fallback_strategy(
    protection=None,
    status_code=None
):

    if status_code == 429:

        return {
            "action": "RETRY",
            "strategy": "EXPONENTIAL_BACKOFF",
            "delay": random.uniform(2, 5),
            "manual_review": False,
        }

    if status_code == 408 or (
        status_code is not None
        and status_code >= 500
    ):

        return {
            "action": "RETRY",
            "strategy": "EXPONENTIAL_BACKOFF",
            "delay": random.uniform(1, 3),
            "manual_review": False,
        }

    if protection == "Cloudflare":

        return {
            "action": "BROWSER_RENDER",
            "strategy": "AUTHORIZED_JS_RENDERING",
            "delay": None,
            "manual_review": False,
        }

    if protection == "DataDome":

        return {
            "action": "ALTERNATIVE_SOURCE",
            "strategy": "USE_PUBLIC_API_OR_AUTHORIZED_SOURCE",
            "delay": None,
            "manual_review": True,
        }

    if protection == "Generic CAPTCHA":

        return {
            "action": "MANUAL_REVIEW",
            "strategy": "DO_NOT_BYPASS_CAPTCHA",
            "delay": None,
            "manual_review": True,
        }

    if status_code == 403:

        return {
            "action": "ALTERNATIVE_SOURCE",
            "strategy": "CHECK_AUTHORIZATION_OR_PUBLIC_SOURCE",
            "delay": None,
            "manual_review": True,
        }

    return {
        "action": "CONTINUE",
        "strategy": "NORMAL_HTTP",
        "delay": None,
        "manual_review": False,
    }


# --------------------------------------------------
# LOCAL TESTING
# --------------------------------------------------

if __name__ == "__main__":

    tests = [
        ("Cloudflare", 403),
        ("DataDome", 403),
        ("Generic CAPTCHA", 200),
        (None, 429),
        (None, 500),
        (None, 403),
        (None, 200),
    ]

    passed = 0

    for protection, status in tests:

        result = get_fallback_strategy(
            protection,
            status
        )

        valid = isinstance(result, dict) and "action" in result

        print(
            "PASS" if valid else "FAIL",
            "| Protection:", protection,
            "| Status:", status,
            "| Action:", result["action"]
        )

        passed += valid

    print(
        "\nFallback tests:",
        passed,
        "/",
        len(tests)
    )
