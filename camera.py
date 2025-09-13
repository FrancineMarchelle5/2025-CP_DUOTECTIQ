# camera.py
import time
from datetime import datetime
from threading import Thread, Lock

# =========================
# TUNABLE THRESHOLDS (softer, easier to detect)
# =========================
MIN_PRESENT_STREAK      = 1     # consecutive passes required (debounce)
CLASS_STABILITY         = 1     # same class this many times in a row
ARMED_FIRST_MIN_CONF    = 0.40  # min confidence for first detection after arming
MOTION_SCORE_THRESHOLD  = 1.0   # motion score to consider "object moved in"
SCENE_LAP_VAR_MIN       = 10.0  # edge richness gate
SCENE_STD_MIN           = 5.0   # contrast gate
BASELINE_LAP_DELTA_MIN  = 5.0   # change vs baseline (edges)
BASELINE_STD_DELTA_MIN  = 2.0   # change vs baseline (contrast)

# -------------------------
# GLOBALS
# -------------------------
_latest = None                       # last JPEG bytes for MJPEG stream
_lock = Lock()
_running = False

latest_result = {"present": False, "seq": 0}  # shared inference result
_result_lock = Lock()
_last_infer_time = 0.0
_seq = 0

# Debounce & class stability
_present_streak = 0
_class_window = []

# Motion & scene state
_prev_gray = None
_motion_score = 0.0
_motion_after_armed = False
_motion_lock = Lock()

# Baseline scene snapshot taken at Start Sorting
_baseline = {"std": None, "lap": None}
_baseline_lock = Lock()

# Armed window (set by Start Sorting)
_armed = False
_armed_token = 0
_armed_time = 0.0

# Crop selection for inference (fallback only)
_current_crop = "tomato"

# -------------------------
# Model Inference
# -------------------------
from model_inference import predict  # must return keys: present, confidence, crop_type, etc.

# -------------------------
# Camera backend selection
# -------------------------
_USE_PICAM = False
try:
    from picamera2 import Picamera2
    from libcamera import controls
    _USE_PICAM = True
except Exception:
    _USE_PICAM = False

if not _USE_PICAM:
    import cv2


# -------------------------
# Public helpers used by Flask
# -------------------------
def set_current_crop(name: str):
    """Allow UI/API to set currently targeted crop to improve defaults."""
    global _current_crop
    _current_crop = (name or "").lower().strip()


def get_latest_result() -> dict:
    """
    Thread-safe copy of the latest inference payload.
    IMPORTANT: while 'armed', suppress any result whose seq <= _armed_token.
    This prevents UI from showing cached values immediately after Start.
    """
    with _result_lock:
        res = dict(latest_result)
    if _armed:
        # Suppress display until a brand-new detection (seq > token)
        if (not res.get("present")) or int(res.get("seq", 0)) <= int(_armed_token):
            return {
                "present": False,
                "seq": res.get("seq", 0),
                "confidence": float(res.get("confidence", 0.0)),
            }
    return res


def mark_sorting_start() -> int:
    """
    Called by /start_sorting. Clears cached detection, resets gates, arms motion check.
    Returns the current seq token.
    """
    global _present_streak, _armed, _armed_token, _armed_time
    global _motion_after_armed, _class_window, _prev_gray

    with _result_lock:
        token = latest_result.get("seq", 0)
        latest_result.clear()
        latest_result.update({"present": False, "seq": token, "confidence": 0.0})

    _present_streak = 0
    _class_window = []
    _armed = True
    _armed_token = token
    _armed_time = time.time()

    with _motion_lock:
        _motion_after_armed = False  # must see motion AFTER arming

    # force baseline & motion to reinitialize on next frames
    with _baseline_lock:
        _baseline["lap"] = None
        _baseline["std"] = None
    _prev_gray = None
    return token


def detect_crop() -> dict | None:
    """
    Return a UI/DB-ready record ONLY when a crop is actually present
    (all gates passed and debounced). Otherwise return None.
    """
    res = get_latest_result()
    if not res.get("present"):
        return None

    crop_type_raw = (res.get('crop_type') or '').lower()
    color_raw = (res.get('color') or '').lower()

    # Normalize crop type (trust model; fallback to dropdown)
    if 'pepper' in crop_type_raw or 'bellpep' in crop_type_raw or 'bell pepper' in crop_type_raw:
        crop_type = 'Bell Pepper'
    elif 'tomato' in crop_type_raw:
        crop_type = 'Tomato'
    else:
        crop_type = _current_crop.capitalize() if _current_crop else 'Unknown'

    # Normalize color with safe defaults by crop
    if 'red' in color_raw:
        color = 'Red'
    elif 'green' in color_raw:
        color = 'Green'
    else:
        color = 'Red' if crop_type == 'Bell Pepper' else ('Green' if crop_type == 'Tomato' else '')

    return {
        'crop_type':     crop_type,
        'condition':     res.get('condition', ''),
        'color':         color,
        'sorted_to':     res.get('sorted_to', ''),
        'size':          res.get('size', ''),
        'time_detected': res.get('time_detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        'confidence':    float(res.get('confidence', 0.0)),
        'seq':           int(res.get('seq', 0)),
    }


# -------------------------
# Internal helpers
# -------------------------
def _scene_stats(frame):
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()  # edge richness
    std = float(gray.std())                          # overall contrast
    return gray, lap_var, std


def _scene_has_object(frame) -> bool:
    """Reject very flat/blank frames."""
    try:
        _, lap_var, std = _scene_stats(frame)
        return lap_var > SCENE_LAP_VAR_MIN and std > SCENE_STD_MIN
    except Exception:
        # Fail-open so we don't block detection if stats fail for any reason
        return True


def _scene_changed_vs_baseline(frame) -> bool:
    """Require a noticeable change vs. baseline snapshot taken at Start Sorting."""
    try:
        _, lap, std = _scene_stats(frame)
        with _baseline_lock:
            b_lap = _baseline["lap"]
            b_std = _baseline["std"]
        if b_lap is None or b_std is None:
            return True  # no baseline -> don't block
        return (abs(lap - b_lap) > BASELINE_LAP_DELTA_MIN) or (abs(std - b_std) > BASELINE_STD_DELTA_MIN)
    except Exception:
        return True


def _snapshot_scene(frame):
    """Capture baseline scene stats at arming time."""
    try:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        std = float(gray.std())
        with _baseline_lock:
            _baseline["lap"] = float(lap_var)
            _baseline["std"] = std
    except Exception:
        with _baseline_lock:
            _baseline["lap"] = None
            _baseline["std"] = None


def _update_motion_and_baseline(frame):
    """Update motion score and snapshot baseline on the first armed frame."""
    global _prev_gray, _motion_score, _motion_after_armed
    try:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if _prev_gray is None:
            _prev_gray = gray
            # On first frame after Start Sorting, snapshot baseline
            if _armed:
                _snapshot_scene(frame)
            return
        diff = cv2.absdiff(gray, _prev_gray)
        _prev_gray = gray
        score = float(diff.mean())  # simple, robust motion metric
        with _motion_lock:
            _motion_score = score
            if _armed and score > MOTION_SCORE_THRESHOLD:
                _motion_after_armed = True
    except Exception:
        pass


def _classes_equal(a: dict, b: dict) -> bool:
    """Check if two prediction dicts have same canonical class fields."""
    return (
        (a.get("crop_type") == b.get("crop_type")) and
        (a.get("condition") == b.get("condition")) and
        (a.get("color") == b.get("color"))
    )


def _accept_or_reset(pred: dict, frame) -> dict:
    """
    Combine:
      - model confidence gate (handled in model_inference)
      - scene gate (edges/contrast)
      - scene change vs baseline
      - motion gate (must see motion after arming)
      - class stability (N identical classes in a row)
      - debounce (N consecutive frames)
    Returns either a full payload (present=True) or {present: False}.
    """
    global _present_streak, _seq, _armed, _class_window

    conf = float(pred.get("confidence", 0.0))
    model_present = bool(pred.get("present", False))
    scene_ok = _scene_has_object(frame)
    scene_changed = _scene_changed_vs_baseline(frame)
    _update_motion_and_baseline(frame)
    with _motion_lock:
        motion_ok = bool(_motion_after_armed)

    # FIRST detection after Start Sorting must be extra confident
    if _armed and conf < ARMED_FIRST_MIN_CONF:
        model_present = False

    # Basic gates
    if not (model_present and scene_ok and scene_changed and motion_ok):
        _present_streak = 0
        _class_window.clear()
        return {"present": False, "seq": latest_result.get("seq", 0), "confidence": conf}

    # Class stability window
    norm_class = {
        "crop_type": pred.get("crop_type", ""),
        "condition": pred.get("condition", ""),
        "color": pred.get("color", ""),
    }
    _class_window.append(norm_class)
    if len(_class_window) > CLASS_STABILITY:
        _class_window.pop(0)

    stable = (len(_class_window) == CLASS_STABILITY) and all(
        _classes_equal(_class_window[0], c) for c in _class_window
    )
    if not stable:
        return {"present": False, "seq": latest_result.get("seq", 0), "confidence": conf}

    # Passed stability; count toward streak
    _present_streak += 1
    if _present_streak < MIN_PRESENT_STREAK:
        return {"present": False, "seq": latest_result.get("seq", 0), "confidence": conf}

    # Accept new detection (brand-new seq)
    _seq += 1
    payload = {
        "present":       True,
        "seq":           _seq,
        "crop_type":     pred.get("crop_type", _current_crop),
        "condition":     pred.get("condition", ""),
        "color":         pred.get("color", ""),
        "sorted_to":     pred.get("sorted_to", ""),
        "size":          pred.get("size", ""),
        "time_detected": pred.get("time_detected") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "confidence":    conf,
    }
    # consume this detection once
    _present_streak = 0
    _class_window.clear()
    _armed = False  # leave armed-mode on first accepted detection
    return payload


def _update_latest(res: dict):
    """Atomically replace the shared latest_result dict."""
    with _result_lock:
        latest_result.clear()
        latest_result.update(res)


# -------------------------
# Capture loops
# -------------------------
def _picam_loop():
    import cv2
    global _latest, _last_infer_time

    picam2 = Picamera2()
    cfg = picam2.create_preview_configuration(
        main={"size": (640, 480), "format": "RGB888"},
        buffer_count=4
    )
    picam2.configure(cfg)
    picam2.set_controls({
        "AfMode": controls.AfModeEnum.Continuous,
        "AwbEnable": True,
        "AeEnable": True,
        "AwbMode": 1
    })
    picam2.start()
    try:
        while _running:
            frame = picam2.capture_array()  # RGB888

            # Inference every ~0.5s
            now = time.time()
            if now - _last_infer_time > 0.5:
                pred = predict(frame)                  # model-level gate (confidence)
                gated = _accept_or_reset(pred, frame)  # all gates + stability + debounce
                _update_latest(gated)
                _last_infer_time = now

            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                with _lock:
                    _latest = jpg.tobytes()
            time.sleep(0.01)
    finally:
        picam2.stop()


def _opencv_loop(index=0):
    import cv2
    global _latest, _last_infer_time

    cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)

    if not cap.isOpened():
        print(f"[ERROR] Camera at index {index} could not be opened.")
        return

    try:
        while _running:
            ok, frame = cap.read()
            if not ok:
                print("[ERROR] Failed to read frame from camera.")
                time.sleep(0.05)
                continue

            # Snapshot baseline right after arming (first available frame)
            if _armed and (_baseline["std"] is None or _baseline["lap"] is None):
                _snapshot_scene(frame)

            # Inference every ~0.5s
            now = time.time()
            if now - _last_infer_time > 0.5:
                pred = predict(frame)
                gated = _accept_or_reset(pred, frame)
                _update_latest(gated)
                _last_infer_time = now

            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                with _lock:
                    _latest = jpg.tobytes()
            else:
                print("[ERROR] Failed to encode frame to JPEG.")
            time.sleep(0.01)
    finally:
        cap.release()


def start_capture(index=0):
    """Start background capture+inference thread once."""
    global _running
    if _running:
        return
    _running = True
    Thread(
        target=(_picam_loop if _USE_PICAM else _opencv_loop),
        args=(() if _USE_PICAM else (index,)),
        daemon=True
    ).start()


def stop_capture():
    """Stop background capture."""
    global _running
    _running = False


def mjpeg_generator():
    """Yield multipart JPEG stream for <img src='/video_feed'>."""
    boundary = b"--frame"
    while True:
        with _lock:
            frame = _latest
        if frame is None:
            time.sleep(0.05)
            continue
        yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.01)
