"""Private Last Z frame detector API.

Only processes images deliberately sent by an authorized broadcast extension or
authorized frame adapter. No gameplay network interception, game controls, or DM.
"""
from __future__ import annotations

import os
import re
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

import cv2
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Last Z scanner", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gbgeumtest.github.io"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-LastZ-State"],
)
EVENTS = deque(maxlen=200)
RECENT = {}
GUARD = Lock()
MAX_FRAME_BYTES = 1_500_000
MAX_RESULTS = 15
EVENT_TTL_SECONDS = 120
DEDUPE_SECONDS = 15
last_frame_at = None
total_frames = 0

def authorize(header: str | None) -> None:
    token = os.environ.get("LASTZ_SCANNER_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="token_not_configured")
    supplied = (header or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="unauthorized")

def detect_yellow_candidates(frame: np.ndarray) -> list[dict]:
    """Fast HSV prefilter. Yellow objects are NOT confirmed S-grade trucks."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (16, 100, 105), (39, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = frame.shape[:2]
    results = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if 28 <= area <= 0.03 * width * height and w >= 7 and h >= 5:
            results.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    return sorted(results, key=lambda item: item["w"] * item["h"], reverse=True)[:MAX_RESULTS]

def purge(now):
    while EVENTS and now - EVENTS[-1]["seenMono"] > EVENT_TTL_SECONDS:
        EVENTS.pop()
    for key, seen in list(RECENT.items()):
        if now - seen > DEDUPE_SECONDS:
            del RECENT[key]

@app.get("/health")
def health():
    return {"ok": True, "service": "lastz-scanner", "frameInput": "authorized_https_jpeg"}

@app.get("/v1/status")
def status(authorization: str | None = Header(default=None)):
    authorize(authorization)
    with GUARD:
        return {
            "ok": True,
            "lastFrameAt": last_frame_at,
            "totalFramesSinceBoot": total_frames,
            "recentCandidateCount": len(EVENTS),
            "bountyDetectionReady": False,
            "truckGradeVerified": False,
        }

@app.post("/v1/frames")
async def accept_frame(
    request: Request,
    authorization: str | None = Header(default=None),
    x_lastz_state: str = Header(default="unknown"),
):
    global last_frame_at, total_frames
    authorize(authorization)
    if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="jpeg_only")
    if not re.fullmatch(r"[0-9]{1,5}", x_lastz_state):
        raise HTTPException(status_code=400, detail="invalid_state")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad_length")
        if length > MAX_FRAME_BYTES:
            raise HTTPException(status_code=413, detail="frame_too_large")
    payload = await request.body()
    if len(payload) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="frame_too_large")
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="invalid_image")
    candidates = detect_yellow_candidates(frame)
    recorded = datetime.now(timezone.utc).isoformat()
    now = time.monotonic()
    added = 0
    with GUARD:
        last_frame_at = recorded
        total_frames += 1
        purge(now)
        for box in candidates:
            # Spatial quantization avoids duplicate results from neighboring frames.
            key = (x_lastz_state, box["x"] // 32, box["y"] // 32)
            if now - RECENT.get(key, -1e9) < DEDUPE_SECONDS:
                continue
            RECENT[key] = now
            EVENTS.appendleft({
                "id": str(uuid4()), "kind": "yellow_truck_candidate",
                "state": x_lastz_state, "detectedAt": recorded,
                "seenMono": now, "box": box, "verified": False,
            })
            added += 1
    return {"ok": True, "candidateCount": len(candidates), "newCandidateCount": added, "verified": False}

@app.get("/v1/events")
def events(authorization: str | None = Header(default=None)):
    authorize(authorization)
    with GUARD:
        purge(time.monotonic())
        return {"events": [{k: v for k, v in item.items() if k != "seenMono"} for item in EVENTS]}
