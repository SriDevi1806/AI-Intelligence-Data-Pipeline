
"""
AI Intelligence Data Pipeline
Public AI company job-board configuration.

These are public employer board identifiers,
not fabricated job records.
"""

# --------------------------------------------------
# GREENHOUSE JOB BOARDS
# --------------------------------------------------

GREENHOUSE_BOARDS = [
    {
        "company_name": "Anthropic",
        "board_token": "anthropic",
    },
    {
        "company_name": "xAI",
        "board_token": "xai",
    },
]


# --------------------------------------------------
# ASHBY JOB BOARDS
# --------------------------------------------------

ASHBY_BOARDS = [
    {
        "company_name": "OpenAI",
        "board_name": "openai",
    },
    {
        "company_name": "Mistral AI",
        "board_name": "mistral.ai",
    },
    {
        "company_name": "Thinking Machines Lab",
        "board_name": "thinkingmachines",
    },
]


# --------------------------------------------------
# LEVER JOB BOARDS
# --------------------------------------------------

LEVER_BOARDS = []


# --------------------------------------------------
# SOURCE SUMMARY
# --------------------------------------------------

def get_job_sources():

    return {
        "Greenhouse": GREENHOUSE_BOARDS,
        "Ashby": ASHBY_BOARDS,
        "Lever": LEVER_BOARDS,
    }


if __name__ == "__main__":

    sources = get_job_sources()

    print("=" * 55)
    print("AI JOB SOURCE CONFIGURATION")
    print("=" * 55)

    total = 0

    for provider, boards in sources.items():

        print(f"\n{provider}: {len(boards)} companies")

        for board in boards:
            print("-", board["company_name"])

        total += len(boards)

    print("\nTotal configured companies:", total)
    print("=" * 55)
