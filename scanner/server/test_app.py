import os
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app import app, detect_yellow_candidates


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_yellow_prefilter(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(frame, (80, 90), (125, 110), (0, 210, 255), -1)
        self.assertGreaterEqual(len(detect_yellow_candidates(frame)), 1)

    def test_no_false_event_without_yellow(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertEqual(detect_yellow_candidates(frame), [])

    def test_auth_required(self):
        with patch.dict(os.environ, {"LASTZ_SCANNER_TOKEN": "secret"}, clear=False):
            r = self.client.get("/v1/events")
        self.assertEqual(r.status_code, 401)

    def test_frame_rejects_bad_state(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        success, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(success)
        with patch.dict(os.environ, {"LASTZ_SCANNER_TOKEN": "secret"}, clear=False):
            r = self.client.post("/v1/frames", content=encoded.tobytes(), headers={
                "Authorization": "Bearer secret",
                "X-LastZ-State": "not-a-number",
                "Content-Type": "image/jpeg",
            })
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
