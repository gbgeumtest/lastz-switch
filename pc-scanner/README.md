# Last Z PC Scanner (Windows)

An **actual local Windows application** for live screen capture, candidate detection and CSV reports. No streaming account, phone, Render, or login token needed.

## What works
- Select a running Last Z / LDPlayer / BlueStacks / MuMu game window.
- Click **▶ 실시간 스캔 시작** and the app captures the visible part of that window about 3 times/second.
- Highlight yellow regions as **possible moving S trucks**.
- Highlight orange + nearby blue shapes as **possible blue-box bounty locations**.
- Keep a local CSV log with timestamps and selected State number.
- Never click in-game controls, read memory, access private game data, or send game DM.

## Important limitations
These are COLOR/SHAPE *candidate prefilters*, not trained object recognition. They may highlight unrelated objects. A yellow region is **not proof** of an S truck. A blue+orange region is **not proof** of `물자 받기` Lv.5+; the level/title OCR and validation model are NOT implemented. No false claim of fully automatic detection.
- Window must stay visible; minimized/covered portions cannot be read by a screenshot capture.
- No automatic map scrolling. Move the map by hand; the scanner scans what is visible only.
- Results have screen coordinates inside the captured window, not game map X/Y.
- Use the game’s native share function manually to DM a second account.
- Game terms and permissions still apply.

## Run from Python (Windows)
Install Python 3.11 or newer. Open PowerShell in `pc-scanner`:
```powershell
py -m pip install -r requirements.txt
py lastz_scanner.py
```
Or download a Windows EXE artifact from the GitHub Actions **PC Scanner Windows EXE** run (if the build succeeds). Unzip `LastZ-PC-Scanner-Windows.zip` and run `LastZ-PC-Scanner.exe`.

## Operating guide
1. Run Last Z on PC (native Windows game client or emulator).
2. Start the scanner. Select that game window in the combo box; click **창 새로고침** if necessary.
3. Type the current State number for logging only (no automatic State switching).
4. Enable truck and/or bounty candidates; press **▶ 실시간 스캔 시작**.
5. Move the game map by hand; keep the game visible.
6. Inspect the outlined objects and click the appropriate share option in Last Z if desired.
7. CSV logs are stored at `%LOCALAPPDATA%\LastZScanner\detections.csv`.

## Privacy
Screenshots are processed locally in RAM and not uploaded. This module neither uses the Render service nor touches existing Quick Switch/OTP credentials.

## Future accuracy work
Train a real detector with labeled map screenshots, add validated OCR for bounty levels, and distinguish confirmed hits from candidates only after testing against real examples.
