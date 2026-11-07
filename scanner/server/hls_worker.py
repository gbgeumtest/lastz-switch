"""Pull operator-configured HLS playback and submit frames to the local scanner API.

Requires an HLS provider (e.g. Livepeer Studio). Render HTTPS cannot receive
RTMP directly. Reads no content until HLS_PLAYBACK_URL is configured.
"""
import os
import time
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlparse

import cv2

def run():
    url = os.getenv("HLS_PLAYBACK_URL", "").strip()
    token = os.getenv("LASTZ_SCANNER_TOKEN", "")
    state = os.getenv("LASTZ_STATE", "406")
    port = int(os.getenv("PORT", "8765"))
    interval = max(0.4, float(os.getenv("HLS_SAMPLE_SECONDS", "1.0")))
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not url.endswith(".m3u8"):
        print("HLS bridge disabled: configure HTTPS HLS_PLAYBACK_URL ending .m3u8", flush=True)
        return
    if not token:
        print("HLS bridge disabled: missing detector authentication", flush=True)
        return
    endpoint = f"http://127.0.0.1:{port}/v1/frames"
    while True:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print("HLS stream unavailable; retrying", flush=True)
            cap.release()
            time.sleep(5)
            continue
        previous = 0.0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                now = time.monotonic()
                if now - previous < interval:
                    continue
                previous = now
                h, w = frame.shape[:2]
                if max(h, w) > 960:
                    scale = 960.0 / max(h, w)
                    frame = cv2.resize(frame, None, fx=scale, fy=scale)
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                if not ok:
                    continue
                req = Request(endpoint, data=jpg.tobytes(), method="POST", headers={
                    "Content-Type": "image/jpeg",
                    "Authorization": "Bearer " + token,
                    "X-LastZ-State": state,
                })
                try:
                    with urlopen(req, timeout=8) as response:
                        response.read()
                except (URLError, TimeoutError):
                    print("Detector temporarily unavailable", flush=True)
        finally:
            cap.release()
        time.sleep(3)

if __name__ == "__main__":
    run()
