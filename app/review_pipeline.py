import logging

from app import activity, filters, github_client, persistence, reviewer
from app.db import get_session

logger = logging.getLogger("ai_pr_reviewer")


async def run(payload: dict) -> dict:
    installation_id = payload["installation"]["id"]
    owner = payload["repository"]["owner"]["login"]
    repo = payload["repository"]["name"]
    repo_full_name = f"{owner}/{repo}"
    pr = payload["pull_request"]
    pr_number = pr["number"]
    head_sha = pr["head"]["sha"]

    logger.info("Starting review: %s#%s", repo_full_name, pr_number)
    await activity.broadcast({"type": "started", "repo": repo_full_name, "pr_number": pr_number})

    with get_session() as session:
        if persistence.already_reviewed(session, repo_full_name, pr_number, head_sha):
            logger.info("Commit %s already reviewed for %s#%s, skipping", head_sha[:10], repo_full_name, pr_number)
            await activity.broadcast(
                {"type": "duplicate", "repo": repo_full_name, "pr_number": pr_number}
            )
            return {"status": "skipped", "reason": "already_reviewed"}

    files = await github_client.get_pr_review_context(
        installation_id, owner, repo, pr_number, head_sha
    )
    if not files:
        logger.info("No reviewable files for %s#%s, skipping", repo_full_name, pr_number)
        await activity.broadcast(
            {"type": "skipped", "repo": repo_full_name, "pr_number": pr_number, "reason": "no_reviewable_files"}
        )
        return {"status": "skipped", "reason": "no_reviewable_files"}

    raw_result = reviewer.review(pr["title"], pr.get("body", ""), files)
    all_findings = raw_result["findings"]
    await activity.broadcast(
        {"type": "reviewed", "repo": repo_full_name, "pr_number": pr_number, "findings_count": len(all_findings)}
    )

    with get_session() as session:
        previous_findings = persistence.get_previous_findings(session, repo_full_name, pr_number)
        accepted = filters.apply(all_findings, previous_findings=previous_findings)

        if accepted:
            comments = [
                {
                    "path": f["file"],
                    "line": f["line"],
                    "body": f"**[{f['severity']}] {f['category']}**: {f['comment']}",
                }
                for f in accepted
            ]
            await github_client.post_review(
                installation_id, owner, repo, pr_number, head_sha, raw_result["summary"], comments
            )
            await activity.broadcast(
                {
                    "type": "posted",
                    "repo": repo_full_name,
                    "pr_number": pr_number,
                    "findings_count": len(accepted),
                }
            )
        else:
            logger.info("No findings above threshold for %s#%s", repo_full_name, pr_number)

        persistence.save_review(
            session,
            installation_id=installation_id,
            account_login=owner,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            commit_sha=head_sha,
            summary=raw_result["summary"],
            all_findings=all_findings,
            posted_findings=accepted,
        )

    logger.info("Posted %d findings on %s#%s", len(accepted), repo_full_name, pr_number)
    return {"status": "completed", "findings_posted": len(accepted)}
