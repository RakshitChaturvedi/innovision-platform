"""
Zone Engine — Polygon ROI, Priority, Labels, and Spatial Filtering for Fire & Smoke Detections.

Enables zone-aware detection where cameras can define multiple ROI polygons with
associated priorities (CRITICAL, HIGH, MEDIUM, LOW), occupancy limits, and zone tags.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("innovision.uc2.zone_engine")


@dataclass
class ZoneDefinition:
    zone_id: str
    zone_name: str
    priority: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    polygon: List[Tuple[float, float]]  # Normalized [0.0 - 1.0] or pixel coords (x, y)
    alert_on_fire: bool = True
    alert_on_smoke: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ZoneMatch:
    zone_id: str
    zone_name: str
    zone_priority: str
    overlap_ratio: float
    is_inside: bool


class ZoneEngine:
    """
    Manages zone ROI polygons per camera and tests bounding boxes against zone geometries.
    """

    def __init__(self) -> None:
        # camera_id -> list of ZoneDefinition
        self._camera_zones: Dict[str, List[ZoneDefinition]] = {}

    def set_camera_zones(self, camera_id: str, zones: List[ZoneDefinition]) -> None:
        """Register or update zone definitions for a camera."""
        self._camera_zones[camera_id] = zones
        logger.info(f"Registered {len(zones)} zones for camera {camera_id}")

    def get_camera_zones(self, camera_id: str) -> List[ZoneDefinition]:
        """Return configured zones for a camera."""
        return self._camera_zones.get(camera_id, [])

    def filter_and_assign_zones(
        self,
        camera_id: str,
        bbox: Tuple[int, int, int, int],  # (x1, y1, x2, y2)
        frame_shape: Tuple[int, int],     # (height, width)
        detection_class: str,              # "fire" or "smoke"
    ) -> Optional[ZoneMatch]:
        """
        Evaluate which zone a detection bbox belongs to.
        Returns the highest priority matching zone, or None if no zone matches or no zones are defined.
        If no zones are defined for the camera, returns a default full-frame zone.
        """
        zones = self._camera_zones.get(camera_id)
        if not zones:
            # Default fallback zone if no specific polygons configured
            return ZoneMatch(
                zone_id="zone-default",
                zone_name="Full View",
                zone_priority="MEDIUM",
                overlap_ratio=1.0,
                is_inside=True,
            )

        h, w = frame_shape
        x1, y1, x2, y2 = bbox
        bbox_cx = (x1 + x2) / 2.0
        bbox_cy = (y1 + y2) / 2.0
        bbox_bottom_cx = (x1 + x2) / 2.0
        bbox_bottom_cy = float(y2)

        # Compute bbox area
        bbox_area = max(1.0, float((x2 - x1) * (y2 - y1)))

        best_match: Optional[ZoneMatch] = None
        priority_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

        for zone in zones:
            if detection_class == "fire" and not zone.alert_on_fire:
                continue
            if detection_class == "smoke" and not zone.alert_on_smoke:
                continue

            # Convert polygon coords to pixel coordinates if normalized
            poly_pts = []
            for px, py in zone.polygon:
                if 0.0 <= px <= 1.0 and 0.0 <= py <= 1.0:
                    poly_pts.append([int(px * w), int(py * h)])
                else:
                    poly_pts.append([int(px), int(py)])
            
            pts_array = np.array(poly_pts, dtype=np.int32)
            if len(pts_array) < 3:
                continue

            # Test point polygon containment for center and bottom center
            dist_center = cv2.pointPolygonTest(pts_array, (float(bbox_cx), float(bbox_cy)), False)
            dist_bottom = cv2.pointPolygonTest(pts_array, (float(bbox_bottom_cx), float(bbox_bottom_cy)), False)

            # Check overlap via mask intersection
            mask_poly = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask_poly, [pts_array], 255)
            
            # Crop bbox region in mask
            x1_c, y1_c = max(0, min(w - 1, x1)), max(0, min(h - 1, y1))
            x2_c, y2_c = max(0, min(w, x2)), max(0, min(h, y2))
            
            if x2_c > x1_c and y2_c > y1_c:
                roi_mask = mask_poly[y1_c:y2_c, x1_c:x2_c]
                intersection_area = float(np.count_nonzero(roi_mask))
                overlap_ratio = min(1.0, intersection_area / bbox_area)
            else:
                overlap_ratio = 0.0

            is_inside = (dist_center >= 0) or (dist_bottom >= 0) or (overlap_ratio > 0.3)

            if is_inside or overlap_ratio > 0.15:
                current_match = ZoneMatch(
                    zone_id=zone.zone_id,
                    zone_name=zone.zone_name,
                    zone_priority=zone.priority,
                    overlap_ratio=overlap_ratio,
                    is_inside=is_inside,
                )

                if best_match is None:
                    best_match = current_match
                else:
                    # Choose by priority rank first, then overlap
                    curr_rank = priority_rank.get(zone.priority.upper(), 0)
                    best_rank = priority_rank.get(best_match.zone_priority.upper(), 0)
                    if curr_rank > best_rank:
                        best_match = current_match
                    elif curr_rank == best_rank and overlap_ratio > best_match.overlap_ratio:
                        best_match = current_match

        return best_match
