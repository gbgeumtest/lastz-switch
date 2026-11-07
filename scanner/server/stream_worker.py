"""Read a private RTSP stream from MediaMTX and submit sampled frames to the detector API.

No Last Z APIs are accessed. The user must explicitly start an iOS screen broadcast.
Use one worker per independent broadcast source. Avoid printing URLs containing secrets.
"""
import os
import time
import urllib.request
import urllib.error

import cv2

STREAM_URL = os.getenv("STREAM_URL", "rtsp://mediamtx:8554/lastz")
API_URL = os.getenv("SCANNER_API_URL", "http://detector:8765/v1/frames")
TOKEN = os.getenv("LASTZ_SCANNER_TOKEN", "")
STATE = os.getenv("LASTZ_STATE", "406")
SAMPLE_INTERVAL = max(0.2, float(os.getenv("SAMPLE_INTERVAL", "1.0")))

def main():
    if not TOKEN:
        raise SystemExit("LASTZ_SCANNER_TOKEN must be configured")
    while True:
        cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print("Waiting for authorized live broadcast...", flush=True)
            time.sleep(3)
            continue
        last_sent = 0.0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                now = time.monotonic()
                if now - last_sent < SAMPLE_INTERVAL:
                    continue
                last_sent = now
                h, w = frame.shape[:2]
                if max(h, w) > 960:
                    scale = 960.0 / max(h, w)
                    frame = cv2.resize(frame, None, fx=scale, fy=scale)
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                if not ok:
                    continue
                request = urllib.request.Request(API_URL, data=encoded.tobytes(), method="POST", headers={
                    "Content-Type": "image/jpeg",
                    "Authorization": f"Bearer {TOKEN}",
                    "X-LastZ-State": STATE,
                })
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        response.read()
                except (urllib.error.URLError, TimeoutError) as exc:
                    print("Detector temporarily unavailable:", type(exc).__name__, flush=True)
        finally:
            cap.release()
        time.sleep(2)

if __name__ == "__main__":
    main()
