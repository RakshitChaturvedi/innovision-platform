import cv2
import numpy as np
import collections
import time

class SpeedEstimator:
    def __init__(self, polygon_normalized, distance_meters, frame_width, frame_height, window_size=12):
        """
        Initializes the SpeedEstimator.
        polygon_normalized: List of 4 points in normalized coordinates (top-left, top-right, bottom-right, bottom-left)
        distance_meters: Physical length of the polygon (top to bottom).
        """
        self.distance_meters = float(distance_meters) if distance_meters else 15.0
        self.lane_width_meters = 3.5
        self.frame_width = frame_width
        self.frame_height = frame_height
        
        self.src_points = self._parse_polygon(polygon_normalized)
        self.homography_matrix = None
        if self.src_points is not None and len(self.src_points) == 4 and self.distance_meters > 0:
            self.homography_matrix = self._calculate_homography()
            
        # State tracking: tracker_id -> deque of (timestamp, smoothed_rw_x, smoothed_rw_y)
        self.track_history = {}
        # Track smoothed instantaneous speed: tracker_id -> float
        self.speed_history = {}
        self.window_size = window_size
        self.coord_ema_alpha = 0.6  # Coordinate smoothing factor

    def _parse_polygon(self, poly):
        if not poly or not isinstance(poly, list) or len(poly) != 4:
            return None
        try:
            pts = []
            for pt in poly:
                pts.append([pt['x'] * self.frame_width, pt['y'] * self.frame_height])
            return np.array(pts, dtype=np.float32)
        except Exception as e:
            print(f"Warning: Invalid speed polygon configuration: {e}")
            return None

    def _calculate_homography(self):
        # Top-down projection space (1 meter = 10 pixels)
        scale = 10.0
        projected_height = self.distance_meters * scale
        projected_width = self.lane_width_meters * scale
        
        dst_points = np.array([
            [0, 0],
            [projected_width, 0],
            [projected_width, projected_height],
            [0, projected_height]
        ], dtype=np.float32)
        
        M, _ = cv2.findHomography(self.src_points, dst_points)
        return M

    def update_and_get_speed(self, tracker_id, bottom_center, current_time=None):
        """
        Updates tracking history for a vehicle and returns precision smoothed speed in km/h.
        """
        if self.homography_matrix is None:
            return 0.0
            
        if current_time is None:
            current_time = time.time()
            
        x, y = bottom_center
        # Transform pixel coordinate to ground plane via Homography
        pt = np.array([[[x, y]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(pt, self.homography_matrix)
        raw_rw_x = transformed[0][0][0] / 10.0
        raw_rw_y = transformed[0][0][1] / 10.0
        
        # Initialize or retrieve history
        if tracker_id not in self.track_history:
            self.track_history[tracker_id] = collections.deque(maxlen=self.window_size)
            smooth_x, smooth_y = raw_rw_x, raw_rw_y
        else:
            prev_time, prev_x, prev_y = self.track_history[tracker_id][-1]
            # EMA coordinate smoothing to kill single-frame bounding box jitter
            smooth_x = self.coord_ema_alpha * raw_rw_x + (1.0 - self.coord_ema_alpha) * prev_x
            smooth_y = self.coord_ema_alpha * raw_rw_y + (1.0 - self.coord_ema_alpha) * prev_y
            
        self.track_history[tracker_id].append((current_time, smooth_x, smooth_y))
        
        history = self.track_history[tracker_id]
        if len(history) < 4:
            return self.speed_history.get(tracker_id, 0.0)
            
        # Calculate velocity over the rolling window
        oldest_time, ox, oy = history[0]
        newest_time, nx, ny = history[-1]
        
        dt = newest_time - oldest_time
        if dt < 0.05:
            return self.speed_history.get(tracker_id, 0.0)
            
        # Vector displacement (net distance along ground plane)
        dx = nx - ox
        dy = ny - oy
        displacement = np.sqrt(dx * dx + dy * dy)
        
        raw_speed_mps = displacement / dt
        raw_speed_kmh = raw_speed_mps * 3.6
        
        # Stationary filter: below 1.8 km/h is considered stopped / detector jitter
        if raw_speed_kmh < 1.8:
            raw_speed_kmh = 0.0
            
        # Exponential smoothing on the reported speed
        prev_reported = self.speed_history.get(tracker_id, raw_speed_kmh)
        # Outlier spike suppression (cap unrealistic instantaneous acceleration > 40 km/h jump)
        if abs(raw_speed_kmh - prev_reported) > 35.0 and prev_reported > 0:
            raw_speed_kmh = prev_reported + (35.0 if raw_speed_kmh > prev_reported else -35.0)
            
        smoothed_speed = 0.45 * raw_speed_kmh + 0.55 * prev_reported
        self.speed_history[tracker_id] = round(smoothed_speed, 1)
        return self.speed_history[tracker_id]

    def clean_stale_trackers(self, active_tracker_ids):
        """Removes history for trackers that are no longer active to prevent memory leaks."""
        active_set = set(active_tracker_ids)
        stale = [tid for tid in self.track_history if tid not in active_set]
        for tid in stale:
            del self.track_history[tid]
            if tid in self.speed_history:
                del self.speed_history[tid]
