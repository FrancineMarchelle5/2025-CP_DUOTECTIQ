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
      crop_type, condition, color, sorted_to, size,
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

        # parse class -> fields

        # ex: "tomato_not_damaged_red" / "bellpepper_damaged_green"
        parts = pred_class.split("_")
        base  = parts[0] if parts else ""

        # Crop type
        if "pepper" in base or "bellpep" in base:
            crop = "Bell Pepper"
        elif "tomato" in base:
            crop = "Tomato"
        else:
            crop = ""

        # Condition
        if "damaged" in pred_class:
            condition = "Damaged"
        elif "not" in pred_class and "damaged" in pred_class:
            condition = "Not Damaged"
        else:
            condition = "Unknown"

        # Color
        if "red" in pred_class:
            color = "Red"
        elif "green" in pred_class:
            color = "Green"
        else:
            color = "Unknown"

        # Sorting bin logic
        if condition == "Damaged":
            sorted_to = "Center Bin"
        elif color == "Green":
            sorted_to = "Left Bin" if crop == "Tomato" else "Right Bin"
        elif color == "Red":
            sorted_to = "Right Bin" if crop == "Tomato" else "Left Bin"
        else:
            sorted_to = "Unknown"

        # Size logic (example: you can use more advanced logic here)
        if crop == "Tomato":
            size = "Large" if color == "Red" else "Medium"
        elif crop == "Bell Pepper":
            size = "Small" if color == "Green" else "Medium"
        else:
            size = "Unknown"

        # confidence threshold for presence
        present = conf >= 0.20  # further lowered threshold for easier detection

        # Debug logging for detection output
        print(f"[DEBUG] Detection result: crop={crop}, color={color}, condition={condition}, conf={conf}, present={present}")

        return {
            "present": present,
            "confidence": conf,
            "crop_type": crop,
            "condition": condition,
            "color": color,
            "sorted_to": sorted_to,
            "size": "Medium",
            "time_detected": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        return {
            "present": False,
            "confidence": 0.0,
            "crop_type": "",
            "condition": "",
            "color": "",
            "sorted_to": "",
            "size": "",
            "time_detected": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
