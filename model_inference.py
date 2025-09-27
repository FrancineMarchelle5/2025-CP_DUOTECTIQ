# model_inference.py
import onnxruntime as ort
import numpy as np
import cv2
import json
from pathlib import Path
from datetime import datetime

# ---------------------------
# CONFIG
# ---------------------------
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH    = ARTIFACTS_DIR / "resnet18_duotectiq.onnx"
CLASSES_PATH  = ARTIFACTS_DIR / "class_names.json"
PREPROC_PATH  = ARTIFACTS_DIR / "preprocess.json"

# ---------------------------
# LOAD ARTIFACTS
# ---------------------------
with open(CLASSES_PATH, "r") as f:
    CLASS_NAMES = json.load(f)

with open(PREPROC_PATH, "r") as f:
    PREPROC = json.load(f)

IMG_SIZE = PREPROC.get("img_size", 224)
MEAN = np.array(PREPROC.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
STD  = np.array(PREPROC.get("std",  [0.229, 0.224, 0.225]), dtype=np.float32)

# ---------------------------
# LOAD MODEL
# ---------------------------
session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])

# ---------------------------
# IMAGE PREPROCESSING
# ---------------------------
def preprocess(img_bgr):
    img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
    img = img.astype(np.float32) / 255.0
    img = (img - MEAN) / STD
    img = np.transpose(img, (2, 0, 1))    # HWC -> CHW
    img = np.expand_dims(img, axis=0)
    return img

def _softmax(logits):
    logits = logits.astype(np.float64)
    m = logits.max(axis=1, keepdims=True)
    e = np.exp(logits - m)
    p = e / e.sum(axis=1, keepdims=True)
    return p

# ---------------------------
# RUN INFERENCE
# ---------------------------
def predict(img_bgr):
    """
    Return a dict the camera loop understands:
      crop_type, condition, color, size,
      time_detected, confidence, present
    """
    try:
        # preprocess
        input_tensor = preprocess(img_bgr)

        # inference
        inputs = {session.get_inputs()[0].name: input_tensor}
        logits = session.run(None, inputs)[0]            # shape [1, C]
        probs  = _softmax(logits)                        # [1, C]
        pred_i = int(np.argmax(probs, axis=1)[0])
        conf   = float(probs[0, pred_i])
        pred_class = CLASS_NAMES[pred_i].lower()

        # Parse crop, color, condition
        crop, color, condition = "", "", ""
        if "tomato" in pred_class:
            crop = "Tomato"
        elif "pepper" in pred_class or "bellpep" in pred_class:
            crop = "Bell Pepper"

        if "red" in pred_class:
            color = "Red"
        elif "green" in pred_class:
            color = "Green"

        if "not" in pred_class and "damaged" in pred_class:
            condition = "Not Damaged"
        elif "damaged" in pred_class:
            condition = "Damaged"

        # Presence threshold: keep this modest, camera gates still apply
        present = conf >= 0.40

        # (Optional) size heuristic
        size = ""
        # keep size blank unless your model provides a better hint

        # Debug
        print(f"[DEBUG] raw='{CLASS_NAMES[pred_i]}', crop={crop}, cond={condition}, color={color}, conf={conf:.3f}, present={present}")

        return {
            "present": present,
            "confidence": conf,
            "crop_type": crop,
            "condition": condition,
            "color": color,
            "size": size,
            "time_detected": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        print(f"[ERROR] inference: {e}")
        return {
            "present": False,
            "confidence": 0.0,
            "crop_type": "",
            "condition": "",
            "color": "",
            "size": "",
            "time_detected": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
