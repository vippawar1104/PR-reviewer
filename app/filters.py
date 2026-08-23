SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}
MIN_SEVERITY = "medium"
MAX_COMMENTS = 8


def _finding_key(finding: dict) -> tuple:
    return (finding["file"], finding["line"], finding["comment"].strip())


def apply(findings: list[dict], previous_findings: list[dict] | None = None) -> list[dict]:
    """
    Filters raw findings down to what should actually be posted:
    - drop anything below MIN_SEVERITY
    - drop exact repeats of unresolved findings from the last review on this PR
    - cap at MAX_COMMENTS, keeping highest severity first
    """
    previous_keys = {_finding_key(f) for f in (previous_findings or [])}
    min_rank = SEVERITY_RANK[MIN_SEVERITY]

    filtered = [
        f
        for f in findings
        if SEVERITY_RANK.get(f["severity"], -1) >= min_rank and _finding_key(f) not in previous_keys
    ]

    filtered.sort(key=lambda f: SEVERITY_RANK.get(f["severity"], -1), reverse=True)

    return filtered[:MAX_COMMENTS]
