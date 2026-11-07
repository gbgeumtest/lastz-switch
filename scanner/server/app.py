"""Live frame receiver and yellow truck candidate detector.

Prototype only: color-based regions are NOT verified S-grade trucks.
No raw image frames are retained. Deploy behind HTTPS and private access controls.
"""
from __future__ import annotations

import os
import re
import secrets
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

import cv2
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="Last Z scanner prototype", docs_url=None, redoc_url=None)
EVENTS = deque(maxlen=200)
GUARD = Lock()
MAX_FRAME_BYTES = 1_500_000
MAX_RESULTS = 15


def authorize(header: str | None) -> None:
    token = os.environ.get("LASTZ_SCANNER_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="token_not_configured")
    supplied = (header or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="unauthorized")


def detect_yellow_candidates(frame: np.ndarray) -> list[dict]:
    """Fast HSV prefilter, not a trained vehicle/object classifier."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (16, 100, 105), (39, 255, 255))
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = frame.shape[:2]
    results = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if 28 <= area <= 0.03 * width * height and w >= 7 and h >= 5:
            results.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    return sorted(results, key=lambda item: item["w"] * item["h"], reverse=True)[:MAX_RESULTS]


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "lastz-scanner-prototype"}


@app.post("/v1/frames")
async def accept_frame(
    request: Request,
    authorization: str | None = Header(default=None),
    x_lastz_state: str = Header(default="unknown"),
) -> dict:
    authorize(authorization)
    if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="jpeg_only")
    if not re.fullmatch(r"[0-9]{1,5}", x_lastz_state):
        raise HTTPException(status_code=400, detail="invalid_state")
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="frame_too_large")
    payload = await request.body()
    if len(payload) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="frame_too_large")
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="invalid_image")
    candidates = detect_yellow_candidates(frame)
    recorded = datetime.now(timezone.utc).isoformat()
    with GUARD:
        for box in candidates:
            EVENTS.appendleft({
                "id": str(uuid4()), "kind": "yellow_truck_candidate",
                "state": x_lastz_state, "detectedAt": recorded, "box": box,
            })
    return {"ok": True, "candidateCount": len(candidates), "verified": False}


@app.get("/v1/events")
def events(authorization: str | None = Header(default=None)) -> dict:
    authorize(authorization)
    with GUARD:
        return {"events": list(EVENTS)}
