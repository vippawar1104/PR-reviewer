import fnmatch

import httpx

from app.github_auth import generate_app_jwt, get_installation_token

GITHUB_API = "https://api.github.com"

SKIP_PATTERNS = [
    "*.lock",
    "*-lock.json",
    "*.min.js",
    "*.min.css",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.woff*",
    "*.ico",
    "*.pdf",
    "dist/*",
    "build/*",
    "node_modules/*",
]
MAX_FILE_LINES = 800


def _should_skip(filename: str) -> bool:
    return any(fnmatch.fnmatch(filename, pattern) for pattern in SKIP_PATTERNS)


async def _headers(installation_id: int) -> dict:
    token = await get_installation_token(installation_id)
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


async def get_pr_files(installation_id: int, owner: str, repo: str, pr_number: int) -> list[dict]:
    """Returns the list of changed files (filename, status, patch, additions, deletions)."""
    headers = await _headers(installation_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=headers,
            params={"per_page": 100},
        )
        resp.raise_for_status()
        return resp.json()


async def get_file_content(
    installation_id: int, owner: str, repo: str, path: str, ref: str
) -> str | None:
    """Fetches full file content at a given ref. Returns None if not found or not a text file."""
    headers = await _headers(installation_id)
    headers["Accept"] = "application/vnd.github.raw+json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
            params={"ref": ref},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text


async def get_pr_review_context(
    installation_id: int, owner: str, repo: str, pr_number: int, head_sha: str
) -> list[dict]:
    """
    Returns a list of {filename, patch, content} for reviewable changed files,
    skipping binaries/generated files and files over MAX_FILE_LINES.
    """
    files = await get_pr_files(installation_id, owner, repo, pr_number)
    context = []

    for f in files:
        filename = f["filename"]
        if _should_skip(filename) or f.get("status") == "removed":
            continue

        content = await get_file_content(installation_id, owner, repo, filename, head_sha)
        if content is not None and content.count("\n") > MAX_FILE_LINES:
            content = None  # too large, review diff-only for this file

        context.append(
            {
                "filename": filename,
                "patch": f.get("patch", ""),
                "content": content,
            }
        )

    return context


async def post_review(
    installation_id: int,
    owner: str,
    repo: str,
    pr_number: int,
    commit_sha: str,
    summary: str,
    comments: list[dict],
) -> dict:
    """
    comments: list of {path, line, body}
    Posts a single PR review with inline comments + summary body.
    """
    headers = await _headers(installation_id)
    body = {
        "commit_id": commit_sha,
        "body": summary,
        "event": "COMMENT",
        "comments": [
            {"path": c["path"], "line": c["line"], "body": c["body"]} for c in comments
        ],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def get_installation_id_for_repo(owner: str, repo: str) -> int:
    app_jwt = generate_app_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/installation",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def get_pull_request(installation_id: int, owner: str, repo: str, pr_number: int) -> dict:
    headers = await _headers(installation_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}", headers=headers)
        resp.raise_for_status()
        return resp.json()
