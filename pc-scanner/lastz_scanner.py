"""Last Z PC Scanner: visible-window capture with candidate detection.

Requires Windows + Python 3.10+, mss, opencv-python, numpy, Pillow.
No game memory reading, game input automation, passwords, or network uploads.
"""
from __future__ import annotations

import csv
import ctypes
import os
import queue
import re
import threading
import time
import tkinter as tk
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import ttk

import cv2
import mss
import numpy as np
from PIL import Image, ImageTk

try:
    import pytesseract
except ImportError:
    pytesseract = None

APP_TITLE = "Last Z · PC Scanner"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LastZScanner"
CSV_PATH = DATA_DIR / "detections.csv"
EVENT_COOLDOWN = 18.0
KNOWN_NAMES = ("last z", "lastz", "ldplayer", "bluestacks", "mumu", "gameloop")
user32 = ctypes.windll.user32 if os.name == "nt" else None


def list_windows():
    """Return visible top-level windows as (HWND, title) tuples."""
    if user32 is None:
        return []
    items = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        size = user32.GetWindowTextLengthW(hwnd)
        if size < 3:
            return True
        buf = ctypes.create_unicode_buffer(size + 1)
        user32.GetWindowTextW(hwnd, buf, size + 1)
        title = buf.value.strip()
        if title:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.right - rect.left >= 260 and rect.bottom - rect.top >= 220:
                items.append((int(hwnd), title))
        return True

    cb = callback_type(collect)
    user32.EnumWindows(cb, 0)
    return sorted(items, key=lambda item: (not any(n in item[1].lower() for n in KNOWN_NAMES), item[1].lower()))


def window_bounds(hwnd):
    if user32 is None or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    # Screen coordinates, including high-DPI monitor layouts.
    left, top = rect.left, rect.top
    width, height = rect.right - left, rect.bottom - top
    if width < 260 or height < 220:
        return None
    return {"left": left, "top": top, "width": width, "height": height}


def find_trucks(frame):
    """Return yellow-object candidates; NOT verified S-grade truck identities."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (16, 105, 105), (39, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if x < w * .04 or y < h * .10 or x + bw > w * .96 or y + bh > h * .92:
            continue
        if not (30 <= area <= 0.007 * w * h and 9 <= bw <= 0.13 * w and 5 <= bh <= 0.10 * h):
            continue
        ratio = bw / max(bh, 1)
        if not (0.7 <= ratio <= 5.0):
            continue
        result.append({"kind": "truck_candidate", "box": (x, y, bw, bh),
                       "label": "노란 트럭 후보 (S급 미확정)", "confidence": "candidate"})
    return result[:30]


def find_bounties(frame):
    """Coarse spatial detector: small blue icon adjacent to orange building.

    Requires OCR confirmation of '물자 받기' and Lv >= 5 before claiming verified.
    We NEVER treat this prefilter alone as a valid high-grade bounty.
    """
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    orange = cv2.inRange(hsv, (5, 100, 90), (23, 255, 255))
    blue = cv2.inRange(hsv, (90, 75, 75), (132, 255, 255))
    orange = cv2.morphologyEx(orange, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    blue = cv2.morphologyEx(blue, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    orange_contours, _ = cv2.findContours(orange, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blue_contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blue_boxes = [cv2.boundingRect(c) for c in blue_contours if 12 <= cv2.contourArea(c) <= 0.006 * w * h]
    result = []
    for contour in orange_contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if not (70 < area < 0.018 * w * h and bw >= 12 and bh >= 12):
            continue
        if x < w * .04 or y < h * .12 or x + bw > w * .96 or y + bh > h * .91:
            continue
        # Attached blue crate typically sits on / near the right upper side.
        nearby = any((x + bw * .35 <= bx <= x + bw * 1.65) and
                     (y - bh * .6 <= by <= y + bh * .65) and
                     (6 <= bb_w <= max(75, bw * 1.2)) for bx, by, bb_w, bb_h in blue_boxes)
        if not nearby:
            continue
        result.append({"kind": "bounty_candidate", "box": (x, y, bw, bh),
                       "label": "파란상자 현상금 후보 (Lv.5+ 확인 필요)",
                       "confidence": "candidate"})
    return result[:20]


def analyze_frame(frame, use_trucks=True, use_bounties=True):
    """Pure computer-vision component suitable for offline unit tests."""
    found = []
    if use_trucks:
        found.extend(find_trucks(frame))
    if use_bounties:
        found.extend(find_bounties(frame))
    return found


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("840x740")
        self.root.minsize(660, 560)
        self.root.configure(bg="#111827")
        self.window_map = {}
        self.running = False
        self.latest = None
        self.detections = []
        self.previous_keys = {}
        self.jobs = queue.Queue(maxsize=3)
        self.stop_event = threading.Event()
        self.photo = None
        self.server = tk.StringVar(value="406")
        self.selected_window = tk.StringVar()
        self.trucks_enabled = tk.BooleanVar(value=True)
        self.bounties_enabled = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="대기 · 게임 창을 선택하세요")
        self.total = tk.StringVar(value="트럭 후보 0 · 현상금 후보 0")
        self._build_ui()
        self.refresh_windows()
        self.root.after(80, self.process_results)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#e5e7eb")
        style.configure("TCheckbutton", background="#111827", foreground="#e5e7eb")
        style.configure("TButton", padding=6)
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="LAST Z · PC SCANNER", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(frame, text="게임 화면 직접 캡처 · 화면에 보이는 대상만 분석 · 자동 게임 조작 없음").pack(anchor="w", pady=(0, 10))
        options = ttk.Frame(frame)
        options.pack(fill="x")
        ttk.Label(options, text="게임 창").grid(row=0, column=0, sticky="w", pady=4)
        self.windows = ttk.Combobox(options, textvariable=self.selected_window, state="readonly", width=51)
        self.windows.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(options, text="창 새로고침", command=self.refresh_windows).grid(row=0, column=2)
        ttk.Label(options, text="서버").grid(row=1, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.server, width=9).grid(row=1, column=1, sticky="w", padx=6)
        toggles = ttk.Frame(options)
        toggles.grid(row=2, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Checkbutton(toggles, text="노란 S급 트럭 후보", variable=self.trucks_enabled).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(toggles, text="파란 상자 현상금 후보", variable=self.bounties_enabled).pack(side="left")
        options.columnconfigure(1, weight=1)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=5)
        self.start_button = ttk.Button(actions, text="▶ 실시간 스캔 시작", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="■ 중지", command=self.stop).pack(side="left")
        ttk.Button(actions, text="기록 폴더 열기", command=self.open_records).pack(side="right")
        ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=4)
        ttk.Label(frame, textvariable=self.total).pack(anchor="w", pady=(0, 6))
        self.preview = tk.Label(frame, bg="#070d16", fg="#9ca3af", text="Last Z 게임을 실행하고 스캔 시작을 누르세요", anchor="center")
        self.preview.pack(fill="both", expand=True)
        ttk.Label(frame, text="최근 발견 후보 (중복 방지 · 자동 CSV 기록)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 4))
        self.listing = tk.Listbox(frame, height=6, bg="#172033", fg="#eef2ff",
                                  selectbackground="#374a71", relief="flat", borderwidth=0)
        self.listing.pack(fill="x")
        ttk.Label(frame, text="노란색·파란색 형상은 1차 후보만 감지합니다. S등급 및 Lv.5 이상 확정은 아직 검증되지 않았습니다.",
                  wraplength=750).pack(anchor="w", pady=(6, 0))

    def refresh_windows(self):
        windows = list_windows()
        self.window_map = {f"{title}  [HWND {handle}]": handle for handle, title in windows}
        self.windows["values"] = list(self.window_map)
        matches = [item for item in self.window_map if any(n in item.lower() for n in KNOWN_NAMES)]
        if matches:
            self.selected_window.set(matches[0])
        elif self.window_map and not self.selected_window.get():
            self.selected_window.set(next(iter(self.window_map)))

    def start(self):
        if self.running:
            return
        if not re.fullmatch(r"\d{1,5}", self.server.get().strip()):
            self.status.set("서버 번호는 1~5자리 숫자여야 합니다")
            return
        hwnd = self.window_map.get(self.selected_window.get())
        if hwnd is None:
            self.status.set("Last Z 또는 에뮬레이터 창을 선택하세요")
            return
        self.stop_event.clear()
        self.running = True
        self.start_button.state(["disabled"])
        self.status.set("화면 분석 시작 · 게임 창을 앞에 표시해 주세요")
        worker = threading.Thread(target=self.worker, args=(hwnd,), daemon=True)
        worker.start()

    def stop(self):
        self.stop_event.set()
        self.running = False
        self.start_button.state(["!disabled"])
        self.status.set("스캔 중지")

    def worker(self, hwnd):
        try:
            if user32:
                user32.SetProcessDPIAware()
            with mss.mss() as screen:
                while not self.stop_event.is_set():
                    bounds = window_bounds(hwnd)
                    if bounds is None:
                        self._post(("error", "게임 창이 닫혔거나 최소화되었습니다"))
                        break
                    raw = np.asarray(screen.grab(bounds))
                    frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
                    # Limit 1280px processing width to maintain low CPU usage.
                    if frame.shape[1] > 1280:
                        factor = 1280 / frame.shape[1]
                        frame = cv2.resize(frame, None, fx=factor, fy=factor)
                    found = analyze_frame(frame, self.trucks_enabled.get(), self.bounties_enabled.get())
                    annotated = frame.copy()
                    for hit in found:
                        x, y, w, h = hit["box"]
                        color = (0, 220, 255) if hit["kind"] == "truck_candidate" else (255, 180, 30)
                        cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 2)
                        cv2.putText(annotated, "S?" if hit["kind"] == "truck_candidate" else "Lv?", (x, max(12, y-6)), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
                    self._post(("frame", annotated, found, time.time()))
                    time.sleep(.28)
        except Exception as exc:
            self._post(("error", str(exc)))
        finally:
            self._post(("stopped",))

    def _post(self, event):
        try:
            if self.jobs.full():
                self.jobs.get_nowait()
            self.jobs.put_nowait(event)
        except queue.Empty:
            pass

    def process_results(self):
        try:
            while not self.jobs.empty():
                event = self.jobs.get_nowait()
                if event[0] == "frame":
                    _, frame, found, now = event
                    self.present(frame)
                    count_truck = sum(x["kind"] == "truck_candidate" for x in found)
                    count_bounty = len(found) - count_truck
                    self.total.set(f"화면 후보 · 트럭 {count_truck} / 현상금 {count_bounty}")
                    self.status.set("스캔 중 · 게임 창을 가리지 마세요")
                    for hit in found:
                        self.save_candidate(hit, now)
                elif event[0] == "error":
                    self.status.set("캡처 오류: " + event[1])
                elif event[0] == "stopped":
                    self.running = False
                    self.start_button.state(["!disabled"])
        except Exception as exc:
            self.status.set("표시 오류: " + str(exc))
        self.root.after(80, self.process_results)

    def present(self, frame):
        height = max(self.preview.winfo_height(), 300)
        width = max(self.preview.winfo_width(), 500)
        scale = min(width / frame.shape[1], height / frame.shape[0], 1.0)
        shown = cv2.resize(frame, None, fx=scale, fy=scale)
        image = Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB))
        self.photo = ImageTk.PhotoImage(image=image)
        self.preview.configure(image=self.photo, text="")

    def save_candidate(self, hit, now):
        x, y, w, h = hit["box"]
        key = (self.server.get(), hit["kind"], round(x / 48), round(y / 48))
        if now - self.previous_keys.get(key, -1e9) < EVENT_COOLDOWN:
            return
        self.previous_keys[key] = now
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        time_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        create_header = not CSV_PATH.exists()
        with CSV_PATH.open("a", newline="", encoding="utf-8-sig") as out:
            writer = csv.writer(out)
            if create_header:
                writer.writerow(["time", "server", "kind", "verified", "x", "y", "w", "h"])
            writer.writerow([time_str, self.server.get(), hit["kind"], "NO", x, y, w, h])
        self.listing.insert(0, f"{time_str} | #{self.server.get()} | {hit['label']} | 화면({x}, {y})")
        if self.listing.size() > 120:
            self.listing.delete(120, tk.END)
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def open_records(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(DATA_DIR)

    def close(self):
        self.stop_event.set()
        self.root.destroy()


def main():
    if os.name != "nt":
        raise SystemExit("This scanner requires Windows.")
    # High DPI awareness should be configured prior to creating Tk windows.
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    root = tk.Tk()
    ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
