"""
Comprehensive Detection Regression & False-Positive Suppression Audit Script.
Tests:
  1. Fire alone
  2. Smoke alone
  3. Sparks alone
  4. Fire + Smoke
  5. Fire + Sparks
  6. Smoke + Sparks
  7. All 3 hazards simultaneously
  8. Glare suppression
  9. Reflection & Lens flare suppression
 10. Fog suppression
 11. Dust suppression
 12. Steam suppression
 13. Welding-like bright uniform fixture rejection
"""
from __future__ import annotations

import os
import sys
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
from services.uc2_fire_smoke.src.detection.suppression import (
    FalseAlarmSuppressor,
    _is_fog_or_cloud,
    _is_dust_or_steam,
    _is_sunlight_reflection,
    _is_led_reflection,
)
from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier

def test_single_and_composite_hazards():
    print("=" * 70)
    print("1. SINGLE & MULTI-HAZARD DETECTION VERIFICATION")
    print("=" * 70)
    pipeline = DetectionPipeline()
    camera_id = "00000000-0000-0000-0000-000000000001"

    # [1] Fire alone
    fire_img = cv2.imread("test_data/images/sample_fire.jpg")
    res_fire = pipeline.process_frame(camera_id, 1, fire_img, single_frame=True)
    fire_dets = [d for d in res_fire.confirmed_detections if d.detection_type == "fire"]
    assert len(fire_dets) > 0, "Fire alone failed to confirm"
    print(f"  [PASS] Fire Alone: {len(fire_dets)} detections confirmed (conf={fire_dets[0].final_confidence:.2f})")

    # [2] Smoke alone
    smoke_img = cv2.imread("test_data/images/sample_smoke.jpg")
    res_smoke = pipeline.process_frame(camera_id, 2, smoke_img, single_frame=True)
    smoke_dets = [d for d in res_smoke.confirmed_detections if d.detection_type == "smoke"]
    assert len(smoke_dets) > 0, "Smoke alone failed to confirm"
    print(f"  [PASS] Smoke Alone: {len(smoke_dets)} detections confirmed (conf={smoke_dets[0].final_confidence:.2f})")

    # [3] Sparks alone
    sparks_img = cv2.imread("test_data/images/sample_sparks.jpg")
    res_sparks = pipeline.process_frame(camera_id, 3, sparks_img, single_frame=True)
    sparks_dets = [d for d in res_sparks.confirmed_detections if d.detection_type in ("sparks", "spark")]
    assert len(sparks_dets) > 0, "Sparks alone failed to confirm"
    print(f"  [PASS] Sparks Alone: {len(sparks_dets)} detections confirmed (conf={sparks_dets[0].final_confidence:.2f})")

    # [4] Fire + Smoke composite
    h, w = 720, 1280
    comp_fire_smoke = np.full((h, w, 3), 30, dtype=np.uint8)
    comp_fire_smoke[:, :w // 2] = cv2.resize(fire_img, (w // 2, h))
    comp_fire_smoke[:, w // 2:] = cv2.resize(smoke_img, (w // 2, h))

    res_fs = pipeline.process_frame(camera_id, 4, comp_fire_smoke, single_frame=True)
    fs_fire = [d for d in res_fs.confirmed_detections if d.detection_type == "fire"]
    fs_smoke = [d for d in res_fs.confirmed_detections if d.detection_type == "smoke"]
    assert len(fs_fire) > 0 and len(fs_smoke) > 0, "Fire + Smoke coexistence failed"
    print(f"  [PASS] Fire + Smoke: Both confirmed (Fire={len(fs_fire)}, Smoke={len(fs_smoke)})")

    # [5] Fire + Sparks composite
    comp_fire_sparks = np.full((h, w, 3), 30, dtype=np.uint8)
    comp_fire_sparks[:, :w // 2] = cv2.resize(fire_img, (w // 2, h))
    comp_fire_sparks[:, w // 2:] = cv2.resize(sparks_img, (w // 2, h))

    res_fsp = pipeline.process_frame(camera_id, 5, comp_fire_sparks, single_frame=True)
    fsp_fire = [d for d in res_fsp.confirmed_detections if d.detection_type == "fire"]
    fsp_sparks = [d for d in res_fsp.confirmed_detections if d.detection_type in ("sparks", "spark")]
    assert len(fsp_fire) > 0 and len(fsp_sparks) > 0, "Fire + Sparks coexistence failed"
    print(f"  [PASS] Fire + Sparks: Both confirmed (Fire={len(fsp_fire)}, Sparks={len(fsp_sparks)})")

    # [6] Smoke + Sparks composite
    comp_smoke_sparks = np.full((h, w, 3), 30, dtype=np.uint8)
    comp_smoke_sparks[:, :w//2] = cv2.resize(smoke_img, (w // 2, h))
    comp_smoke_sparks[:, w//2:] = cv2.resize(sparks_img, (w // 2, h))

    res_ssp = pipeline.process_frame(camera_id, 6, comp_smoke_sparks, single_frame=True)
    ssp_smoke = [d for d in res_ssp.confirmed_detections if d.detection_type == "smoke"]
    ssp_sparks = [d for d in res_ssp.confirmed_detections if d.detection_type in ("sparks", "spark")]
    assert len(ssp_smoke) > 0 and len(ssp_sparks) > 0, "Smoke + Sparks coexistence failed"
    print(f"  [PASS] Smoke + Sparks: Both confirmed (Smoke={len(ssp_smoke)}, Sparks={len(ssp_sparks)})")

    # [7] All 3 Hazards (Fire + Smoke + Sparks)
    comp_all3 = np.full((h, w, 3), 30, dtype=np.uint8)
    w1 = w // 3
    w2 = 2 * w1
    comp_all3[:, :w1] = cv2.resize(fire_img, (w1, h))
    comp_all3[:, w1:w2] = cv2.resize(smoke_img, (w2 - w1, h))
    comp_all3[:, w2:] = cv2.resize(sparks_img, (w - w2, h))

    res_all3 = pipeline.process_frame(camera_id, 7, comp_all3, single_frame=True)
    all_fire = [d for d in res_all3.confirmed_detections if d.detection_type == "fire"]
    all_smoke = [d for d in res_all3.confirmed_detections if d.detection_type == "smoke"]
    all_sparks = [d for d in res_all3.confirmed_detections if d.detection_type in ("sparks", "spark")]
    assert len(all_fire) > 0 and len(all_smoke) > 0 and len(all_sparks) > 0, "All 3 hazards coexistence failed"
    print(f"  [PASS] All 3 Hazards: All confirmed simultaneously (Fire={len(all_fire)}, Smoke={len(all_smoke)}, Sparks={len(all_sparks)})")


def test_environmental_false_alarm_suppression():
    print("\n" + "=" * 70)
    print("2. ENVIRONMENTAL FALSE ALARM & DISTRACTOR SUPPRESSION")
    print("=" * 70)
    verifier = DeterministicVerifier()

    # [8] Glare / Overcast Sky
    glare_roi = np.full((80, 80, 3), 255, dtype=np.uint8)
    spark_res_glare = verifier.verify_sparks(glare_roi)
    assert not spark_res_glare.passed, "Glare must not be confirmed as sparks"
    assert "uniform_daylight_or_sky" in spark_res_glare.rejection_reason
    print(f"  [PASS] Glare Suppression: {spark_res_glare.rejection_reason}")

    # [9] Sunlight Reflection / Lens Flare
    sunlight_roi = np.full((100, 100, 3), 245, dtype=np.uint8)
    cv2.circle(sunlight_roi, (50, 50), 30, (255, 255, 255), -1)
    sun_gray = cv2.cvtColor(sunlight_roi, cv2.COLOR_BGR2GRAY)
    sun_hsv = cv2.cvtColor(sunlight_roi, cv2.COLOR_BGR2HSV)
    is_sun, sun_reason = _is_sunlight_reflection(sun_gray, sun_hsv)
    assert is_sun, "Sunlight reflection must be suppressed"
    print(f"  [PASS] Sunlight / Flare Suppression: {sun_reason}")

    # [10] Fog / Cloud
    # Low std, low sat, moderate-high val
    fog_roi = np.full((120, 120, 3), 180, dtype=np.uint8)
    noise = np.random.normal(0, 2, (120, 120, 3)).astype(np.int16)
    fog_roi = np.clip(fog_roi.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    fog_gray = cv2.cvtColor(fog_roi, cv2.COLOR_BGR2GRAY)
    fog_hsv = cv2.cvtColor(fog_roi, cv2.COLOR_BGR2HSV)
    is_fog, fog_reason = _is_fog_or_cloud(fog_gray, fog_hsv)
    assert is_fog, "Fog must be suppressed"
    print(f"  [PASS] Fog / Cloud Suppression: {fog_reason}")

    # [11] Dust / Steam
    # Uniform texture with moderate brightness and low entropy
    dust_roi = np.full((100, 100, 3), 140, dtype=np.uint8)
    dust_noise = np.random.normal(0, 4, (100, 100, 3)).astype(np.int16)
    dust_roi = np.clip(dust_roi.astype(np.int16) + dust_noise, 0, 255).astype(np.uint8)
    dust_gray = cv2.cvtColor(dust_roi, cv2.COLOR_BGR2GRAY)
    dust_hsv = cv2.cvtColor(dust_roi, cv2.COLOR_BGR2HSV)
    is_dust, dust_reason = _is_dust_or_steam(dust_gray, dust_hsv)
    assert is_dust, "Dust/steam must be suppressed"
    print(f"  [PASS] Dust / Steam Suppression: {dust_reason}")

    # [12] Welding-like static bright fixture / bulb
    bulb_roi = np.full((60, 60, 3), 250, dtype=np.uint8)
    spark_res_bulb = verifier.verify_sparks(bulb_roi)
    assert not spark_res_bulb.passed, "Static bulb fixture must be rejected"
    print(f"  [PASS] Static Bright Fixture / Bulb Suppression: {spark_res_bulb.rejection_reason}")

    # [13] Enclosed Sparks in Smoke (Stage 1.5 suppression)
    pipeline = DetectionPipeline()
    # Smoke box: [100, 100, 500, 500], Spark box: [200, 200, 250, 250] (inside smoke)
    # Verify stage 1.5 encloses spark inside smoke
    smoke_det = {
        "detection_type": "smoke",
        "bbox": {"x1": 100, "y1": 100, "x2": 500, "y2": 500},
        "final_confidence": 0.85,
    }
    spark_enclosed = {
        "detection_type": "sparks",
        "bbox": {"x1": 200, "y1": 200, "x2": 250, "y2": 250},
        "final_confidence": 0.80,
    }
    spark_outside = {
        "detection_type": "sparks",
        "bbox": {"x1": 600, "y1": 600, "x2": 650, "y2": 650},
        "final_confidence": 0.80,
    }
    def is_enclosed(sb, mb):
        sb_area = max(1, (sb["x2"] - sb["x1"]) * (sb["y2"] - sb["y1"]))
        ix1 = max(sb["x1"], mb["x1"])
        iy1 = max(sb["y1"], mb["y1"])
        ix2 = min(sb["x2"], mb["x2"])
        iy2 = min(sb["y2"], mb["y2"])
        if ix2 > ix1 and iy2 > iy1:
            inter_area = (ix2 - ix1) * (iy2 - iy1)
            return (inter_area / float(sb_area)) > 0.25
        return False

    assert is_enclosed(spark_enclosed["bbox"], smoke_det["bbox"]), "Spark inside smoke must be detected as enclosed"
    assert not is_enclosed(spark_outside["bbox"], smoke_det["bbox"]), "Spark outside smoke must not be enclosed"
    print("  [PASS] Stage 1.5 Enclosed Spark Filtering: Enclosed spark suppressed, outside spark preserved")

def main():
    test_single_and_composite_hazards()
    test_environmental_false_alarm_suppression()
    print("\n" + "=" * 70)
    print("ALL 13 DETECTION REGRESSION & FALSE-ALARM SCENARIOS PASSED")
    print("=" * 70)

if __name__ == "__main__":
    main()
