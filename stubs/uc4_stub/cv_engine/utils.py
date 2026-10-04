"""
utils.py — Shared utility functions for the Traffic CV pipeline.

Contains:
- Vehicle class mapping
- Indian license plate OCR correction & consensus voting
- Plate image enhancement
- Database flush logic for completed tracker sessions
"""

import re
import cv2
import numpy as np
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Any


# ─── Constants ────────────────────────────────────────────────────────────────

BLACKLISTED_PLATES = {"TS08EX1234", "AP28CH7890", "TS09FF1122"}

YOLO_CLASS_MAP = {1: "Bike", 2: "Car", 3: "Bike", 5: "Bus", 7: "Truck"}

# ─── Plate Correction ────────────────────────────────────────────────────────

VALID_STATE_CODES = {
    "AP", "AR", "AS", "BR", "CG", "GA", "GJ", "HR", "HP", "JH", "KA", "KL", "MP",
    "MH", "MN", "ML", "MZ", "NL", "OD", "PB", "RJ", "SK", "TN", "TS", "TR", "UP",
    "UK", "WB", "AN", "CH", "DN", "DD", "DL", "JK", "LA", "LD", "PY"
}

def clean_plate(text):
    """Clean and return an alphanumeric plate string universally without strict templates."""
    cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
    
    # Strip common non-plate watermarks and country badges (e.g. IND, SUZUKI, HONDA, HYUNDAI)
    watermarks = ["SUZUKI", "HYUNDAI", "HONDA", "TOYOTA", "TATA", "MARUTI", "HERO", "BAJAJ", "MAHINDRA", "INDIA"]
    for wm in watermarks:
        cleaned = cleaned.replace(wm, "")
        
    # Strip standalone or trailing IND badge
    if cleaned.startswith("IND") and len(cleaned) > 7:
        cleaned = cleaned[3:]
    if cleaned.endswith("IND") and len(cleaned) > 7:
        cleaned = cleaned[:-3]
    if "IND" in cleaned and len(cleaned) > 10:
        cleaned = cleaned.replace("IND", "")

    # Filter out absolute garbage (e.g., less than 3 chars or weirdly long)
    if len(cleaned) < 3 or len(cleaned) > 15:
        return None
    return cleaned

def correct_indian_plate(text):
    """Clean and correct an OCR-read Indian license plate string using strict templates."""
    cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
    if not (7 <= len(cleaned) <= 11):
        return None

    letter_to_digit = {
        'O': '0', 'D': '0', 'Q': '0', 'U': '0',
        'I': '1', 'L': '1', 'T': '1', 'J': '1',
        'Z': '2', 'S': '5', 'G': '6', 'B': '8'
    }
    digit_to_letter = {
        '0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'
    }

    def force_letters(s):
        return "".join(digit_to_letter.get(c, c) if c.isdigit() else c for c in s)

    def force_digits(s):
        return "".join(letter_to_digit.get(c, c) if c.isalpha() else c for c in s)

    # Check for Bharat Series (YY BH #### XX)
    if "BH" in cleaned[2:4] or (cleaned[2:4] in ["8H", "OH", "0H", "88"]):
        year = force_digits(cleaned[:2])
        bh = "BH"
        rem = cleaned[4:]
        num = force_digits(rem[:4])
        series = force_letters(rem[4:])
        return year + bh + num + series

    state = force_letters(cleaned[0:2])
    num_part = force_digits(cleaned[-4:])
    if len(cleaned) < 8:
        max_num_len = min(4, len(cleaned) - 3)
        num_part = force_digits(cleaned[-max_num_len:])

    mid_part = cleaned[2:-len(num_part)]

    if len(mid_part) == 0:
        rto = ""
        series = ""
    else:
        if len(mid_part) >= 2:
            c2 = mid_part[1]
            if c2.isdigit() or c2 in letter_to_digit:
                rto = force_digits(mid_part[0:2])
                series = force_letters(mid_part[2:])
            else:
                rto = force_digits(mid_part[0:1])
                series = force_letters(mid_part[1:])
        else:
            rto = force_digits(mid_part[0:1])
            series = ""
            
    return state + rto + series + num_part

def is_indian_plate(text):
    """Regex-based heuristic to check if a plate looks Indian."""
    cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
    if len(cleaned) < 7 or len(cleaned) > 11:
        return False
    state = cleaned[:2]
    # Check if starts with a known state or valid letter sequence
    if state in VALID_STATE_CODES:
        return True
    letters = sum(1 for c in state if c.isalpha() or c in '0852')
    if letters >= 1 and cleaned[-2:].isdigit():
        return True
    return False

def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def get_mode(items, confs=None):
    """Compute consensus plate text using Levenshtein clustering and auto-region detection."""
    if not items:
        return "UNKNOWN"
    if confs is None:
        confs = [1.0] * len(items)

    cleaned_items = []
    for item in items:
        c = clean_plate(item)
        if c: cleaned_items.append(c)
        
    if not cleaned_items:
        return Counter(items).most_common(1)[0][0]

    # Region Detection
    indian_matches = sum(1 for x in cleaned_items if is_indian_plate(x))
    is_india_region = (indian_matches / len(cleaned_items)) > 0.4
    
    processed_items = []
    processed_confs = []
    for item, conf in zip(items, confs):
        if is_india_region:
            c = correct_indian_plate(item)
        else:
            c = clean_plate(item)
        if c:
            processed_items.append(c)
            processed_confs.append(conf)

    if not processed_items:
        return Counter(cleaned_items).most_common(1)[0][0]

    # Levenshtein Clustering
    clusters = []
    for string, conf in zip(processed_items, processed_confs):
        added = False
        for cluster in clusters:
            # If distance is <= 1 (or 2 for long plates), add to cluster
            threshold = 1 if len(string) < 8 else 2
            if levenshtein_distance(string, cluster['center']) <= threshold:
                cluster['strings'].append(string)
                cluster['total_conf'] += conf
                added = True
                break
        if not added:
            clusters.append({'center': string, 'strings': [string], 'total_conf': conf})

    # Pick best cluster
    best_cluster = max(clusters, key=lambda x: x['total_conf'])
    
    # Within best cluster, pick most common string
    final_str = Counter(best_cluster['strings']).most_common(1)[0][0]
    return final_str

# ─── License Plate ROI Extraction ─────────────────────────────────────────────

def extract_plate_candidates(vehicle_crop):
    """
    Fast morphological and edge-gradient license plate localizer on CPU (< 1ms).
    Returns list of high-probability plate crops from the vehicle region.
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return []
        
    vh, vw = vehicle_crop.shape[:2]
    if vh < 30 or vw < 40:
        return [vehicle_crop]

    # Focus on the lower 65% of the vehicle where front/rear plates are mounted
    roi_y1 = int(vh * 0.35)
    roi = vehicle_crop[roi_y1:, :]
    rh, rw = roi.shape[:2]
    if rh < 20 or rw < 30:
        return [vehicle_crop]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # 1. Blackhat morphology to extract dark text/features on high contrast backgrounds
    rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rect_kernel)

    # 2. Sobel horizontal gradient (detecting high density of vertical character edges)
    grad_x = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    grad_x = np.absolute(grad_x)
    min_val, max_val = np.min(grad_x), np.max(grad_x)
    grad_x = (255 * ((grad_x - min_val) / (max_val - min_val + 1e-5))).astype('uint8')

    # 3. Morphological close along horizontal axis to group characters into plate block
    grad_x = cv2.GaussianBlur(grad_x, (5, 5), 0)
    grad_x = cv2.morphologyEx(grad_x, cv2.MORPH_CLOSE, rect_kernel)
    thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    # 4. Contour detection & Aspect Ratio filtering
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        ar = w / float(h)
        # Rectangular plates: 1.8 - 5.8, Square/Two-wheeler: 1.1 - 2.2
        if 1.3 <= ar <= 6.2 and w >= 32 and h >= 9 and (w * h) / (rw * rh) < 0.65:
            # Score candidate by area and texture
            pad_x = max(3, int(w * 0.08))
            pad_y = max(3, int(h * 0.12))
            cand_crop = roi[max(0, y - pad_y):min(rh, y + h + pad_y), max(0, x - pad_x):min(rw, x + w + pad_x)]
            if cand_crop.size > 0:
                # Rank candidates by edge energy & resolution
                score = w * h
                candidates.append((score, cand_crop))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates:
        return [item[1] for item in candidates[:2]]

    # Fallback to bottom-center 40% of the vehicle crop
    return [vehicle_crop[int(vh * 0.60):, int(vw * 0.15):int(vw * 0.85)]]

# ─── Image Enhancement ────────────────────────────────────────────────────────

def enhance_plate(crop):
    """
    High-performance CPU plate enhancement for CCTV/RTSP streams:
    - Upscales small/distant plates to minimum 64px height and 140px width with bicubic interpolation
    - LAB CLAHE adaptive contrast equalization
    - Unsharp mask text edge sharpening
    - 6% white border padding to prevent OCR token boundary clipping
    """
    if crop is None or crop.size == 0:
        return crop
    h, w = crop.shape[:2]
    if h == 0 or w == 0:
        return crop

    # 1. Bicubic Upscaling for distant/small CCTV crops (ensure min 64px height, 140px width)
    scale = 1.0
    if h < 64:
        scale = max(scale, 64.0 / float(h))
    if w < 140:
        scale = max(scale, 140.0 / float(w))
    if scale > 1.0:
        crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        h, w = crop.shape[:2]

    # 2. LAB CLAHE contrast enhancement
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(6, 6))
    l_eq = clahe.apply(l)
    enhanced_bgr = cv2.cvtColor(cv2.merge((l_eq, a, b)), cv2.COLOR_LAB2BGR)

    # 3. Fast Unsharp Mask Sharpening
    gaussian = cv2.GaussianBlur(enhanced_bgr, (0, 0), 1.5)
    sharpened = cv2.addWeighted(enhanced_bgr, 1.4, gaussian, -0.4, 0)

    # 4. White border padding (8px)
    pad_h = max(4, int(h * 0.08))
    pad_w = max(6, int(w * 0.08))
    padded = cv2.copyMakeBorder(sharpened, pad_h, pad_h, pad_w, pad_w, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    return padded

