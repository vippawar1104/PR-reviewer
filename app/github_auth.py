import time

import httpx
import jwt

from app.config import settings

GITHUB_API = "https://api.github.com"

# installation_id -> (token, expires_at_epoch)
_token_cache: dict[int, tuple[str, float]] = {}


def generate_app_jwt() -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,  # allow for clock drift
        "exp": now + (9 * 60),  # GitHub caps this at 10 minutes
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, settings.github_private_key_pem, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    cached = _token_cache.get(installation_id)
    if cached and cached[1] > time.time() + 30:
        return cached[0]

    app_jwt = generate_app_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    # expires_at is an ISO8601 string; store a rough epoch estimate instead of parsing tz
    expires_at = time.time() + 55 * 60  # GitHub tokens are valid ~1hr, refresh a bit early
    _token_cache[installation_id] = (token, expires_at)
    return token
