# iPhone-only interaction / live stream receiver

The Quick Switch website **cannot read any other iOS app's screen**. This is an iOS security limit.

## Prototype stream bridge
- A separately operated, **private** server runs MediaMTX, frame worker and detector.
- A broadcasting app on iPhone starts an explicit **system screen broadcast** and sends the Last Z gameplay screen to the server.
- The worker samples live video frames (initially 1 FPS) and sends JPEG frames to the detector on an internal network.
- The scanner dashboard can query the detector's events endpoint through an authenticated HTTPS reverse proxy.
- This module does **not** automatically operate the game, send DM, or extract undisclosed game-server data.
- **No cloud server has been deployed** by committing this repository.

## Private server trial
Requires Docker and Docker Compose on a server machine:
```sh
cd scanner
export LASTZ_SCANNER_TOKEN="random-secret-at-least-32-characters"
export LASTZ_STATE=406
docker compose up --build
```
The compose example binds local ports only and is NOT reachable publicly from an iPhone.
For Internet access, provision an authenticated ingest endpoint and a properly authenticated TLS proxy.
This step is *required* before an iPhone can connect. Do not expose anonymous RTMP streams.

## Current detector limitations
- The detector searches bright yellow regions only and may report gold UI, buildings, etc. as false positives.
- It cannot certify 'S' grade from color alone.
- Quest type, blue crate and level OCR are not implemented.
- Game map movement is manual.
- A moving truck may be missed between frames; 100% coverage is not possible.

## Data privacy
A broadcast can include chats and notifications. Use a private receiver, strip personal overlays where possible, avoid retaining raw frames, and use a strong unique scanner token distinct from the OTP key.
