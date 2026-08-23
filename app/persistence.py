from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Finding, Installation, Review


def already_reviewed(session: Session, repo_full_name: str, pr_number: int, commit_sha: str) -> bool:
    """True if this exact commit on this PR has already been reviewed (guards against webhook redelivery)."""
    stmt = select(Review.id).where(
        Review.repo_full_name == repo_full_name,
        Review.pr_number == pr_number,
        Review.commit_sha == commit_sha,
    )
    return session.execute(stmt).first() is not None


def get_previous_findings(session: Session, repo_full_name: str, pr_number: int) -> list[dict]:
    """Findings from the most recent review of this PR, as plain dicts (for filters.apply dedupe)."""
    stmt = (
        select(Review)
        .where(Review.repo_full_name == repo_full_name, Review.pr_number == pr_number)
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    last_review = session.execute(stmt).scalar_one_or_none()
    if not last_review:
        return []
    return [
        {
            "file": f.file,
            "line": f.line,
            "severity": f.severity,
            "category": f.category,
            "comment": f.comment,
        }
        for f in last_review.findings
    ]


def save_review(
    session: Session,
    installation_id: int,
    account_login: str,
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    summary: str,
    all_findings: list[dict],
    posted_findings: list[dict],
) -> Review:
    """Upserts the Installation, then records the review with every finding (posted flag marks what was actually sent to GitHub)."""
    installation = session.get(Installation, installation_id)
    if installation is None:
        installation = Installation(id=installation_id, account_login=account_login)
        session.add(installation)

    posted_keys = {(f["file"], f["line"], f["comment"].strip()) for f in posted_findings}

    review = Review(
        installation_id=installation_id,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        commit_sha=commit_sha,
        summary=summary,
    )
    for f in all_findings:
        key = (f["file"], f["line"], f["comment"].strip())
        review.findings.append(
            Finding(
                file=f["file"],
                line=f["line"],
                severity=f["severity"],
                category=f["category"],
                comment=f["comment"],
                posted=key in posted_keys,
            )
        )

    session.add(review)
    session.flush()
    return review
