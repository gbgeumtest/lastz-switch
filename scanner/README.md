# Last Z Live Scanner — iOS experimental module

**Status: source-code prototype, not installed/tested on an iPhone.** This module is completely separate from the existing Quick Switch website and OTP mail bridge.

## Goal
- User manually switches Last Z State/server and moves the map.
- User explicitly starts iOS ReplayKit screen broadcast.
- Broadcast Upload Extension periodically sends compressed frames to a separate HTTPS detector service.
- Detector reports **yellow moving truck candidates**. They are *not* verified S-grade without further visual validation.
- Bounty identification (blue attached chest + `물자 받기` + level >= 5) is **not implemented** yet.
- **No screenshot picker or upload form** in the intended UI; all inputs originate from ReplayKit.
- No game button automation, no DM automation, no private game API calls.

## Architecture
`Last Z -> iOS ReplayKit Broadcast Upload Extension -> HTTPS POST /v1/frames -> OpenCV heuristic -> GET /v1/events -> SwiftUI status screen`

### Important limits
- Safari / GitHub Pages cannot capture the Last Z app screen live.
- The ReplayKit broadcast runs only after the user explicitly starts screen broadcasting. This is not an iPhone-installable artifact yet.
- Broadcast Extension and host app need the same App Group entitlement; use your own group ID.
- HTTPS endpoint must be reachable from iPhone; do not expose the local detector directly to the Internet without authentication/TLS.
- The first detector deliberately returns candidates, not confirmed prizes. False positives are expected. No OCR/YOLO models are included.
- Sending gameplay screen frames off-device requires care with personal data shown in chat and notification overlays; the user should disable sensitive overlays and use a private server.
- Review Last Z policies before automated operation.

## Xcode integration (Mac required)
1. Create an iOS SwiftUI app target `LastZScanner`, iOS 16+.
2. Add a **Broadcast Upload Extension** target `LastZBroadcast`.
3. Add `ios/ScannerView.swift` to the app target and `ios/SampleHandler.swift` to the broadcast extension target.
4. Enable App Groups for **both** targets. Replace `group.example.lastzscanner` with your own ID in both files.
5. In `ScannerView.swift`, specify `com.example.LastZBroadcast` as the extension bundle identifier and configure an HTTPS server and private token. Do not commit credentials.
6. In the broadcast extension, make sure networking is permitted, and choose the ReplayKit broadcast from the system control.
7. Build and test with a physical iPhone; simulator-only testing is insufficient.

## Detector service
```bash
cd scanner/server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export LASTZ_SCANNER_TOKEN='choose-long-random-token'
uvicorn app:app --host 127.0.0.1 --port 8765
```
Provide a private HTTPS reverse proxy / secure tunnel for your iPhone. Set that URL and token in the iOS app UI; never use the public OTP bridge server for video.

## Acceptance tests still needed
1. Permission-based broadcast starts while Last Z is foreground.
2. At least one authentic iPhone frame reaches the detector.
3. Frame send rate, bandwidth and overheating measured.
4. False positives reviewed against authentic yellow truck clips.
5. Map zoom and moving-object tracking tested.
6. Blue chest + level >= 5 + quest title recognition trained and validated.
7. In-game second-account DM is still **manual**.
