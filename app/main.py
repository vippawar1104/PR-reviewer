import hashlib
import hmac
import logging

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.config import settings
from app import activity, control, github_client, review_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_pr_reviewer")

app = FastAPI()

HANDLED_ACTIONS = {"opened", "synchronize"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "testclient"}


def require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client else None
    if client_host not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="Control endpoints are local-only")


class TriggerRequest(BaseModel):
    owner: str
    repo: str
    pr_number: int


def verify_signature(payload_body: bytes, signature_header: str | None) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing or malformed signature")

    expected = hmac.new(
        settings.github_webhook_secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")

    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="Invalid signature")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/activity")
async def ws_activity(websocket: WebSocket):
    await websocket.accept()
    activity.register(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep the connection open; we don't expect client messages
    except WebSocketDisconnect:
        pass
    finally:
        activity.unregister(websocket)


@app.get("/control/status")
async def control_status(_: None = Depends(require_loopback)):
    return {"paused": control.paused}


@app.post("/control/pause")
async def control_pause(_: None = Depends(require_loopback)):
    control.paused = True
    await activity.broadcast({"type": "paused"})
    return {"paused": True}


@app.post("/control/resume")
async def control_resume(_: None = Depends(require_loopback)):
    control.paused = False
    await activity.broadcast({"type": "resumed"})
    return {"paused": False}


@app.post("/control/trigger")
async def control_trigger(
    req: TriggerRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_loopback),
):
    installation_id = await github_client.get_installation_id_for_repo(req.owner, req.repo)
    pr = await github_client.get_pull_request(installation_id, req.owner, req.repo, req.pr_number)
    payload = {
        "installation": {"id": installation_id},
        "repository": {"name": req.repo, "owner": {"login": req.owner}, "full_name": f"{req.owner}/{req.repo}"},
        "pull_request": pr,
    }
    background_tasks.add_task(_run_review_safely, payload)
    return {"status": "triggered"}


async def _run_review_safely(payload: dict) -> None:
    repo = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]
    try:
        result = await review_pipeline.run(payload)
        logger.info("Review pipeline finished for %s#%s: %s", repo, pr_number, result)
    except Exception:
        logger.exception("Review pipeline failed for %s#%s", repo, pr_number)
        await activity.broadcast({"type": "error", "repo": repo, "pr_number": pr_number})


@app.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    raw_body = await request.body()
    verify_signature(raw_body, x_hub_signature_256)

    payload = await request.json()

    if x_github_event != "pull_request":
        logger.info("Ignoring event type=%s", x_github_event)
        return {"status": "ignored"}

    action = payload.get("action")
    if action not in HANDLED_ACTIONS:
        logger.info("Ignoring pull_request action=%s", action)
        return {"status": "ignored"}

    pr = payload["pull_request"]
    repo = payload["repository"]["full_name"]
    logger.info(
        "Received PR event: repo=%s pr_number=%s action=%s sha=%s",
        repo,
        pr["number"],
        action,
        pr["head"]["sha"],
    )

    if control.paused:
        logger.info("Bot paused, ignoring PR event for %s#%s", repo, pr["number"])
        return {"status": "paused"}

    background_tasks.add_task(_run_review_safely, payload)
    return {"status": "accepted"}
