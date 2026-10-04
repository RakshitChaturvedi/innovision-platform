INSERT INTO uc4_camera_calibration (
    camera_id,
    speed_polygon_normalized,
    distance_between_lines_meters
) VALUES (
    '00000000-0000-0000-0000-000000000004',
    '[{"x":0.1,"y":0.2},{"x":0.9,"y":0.2},{"x":0.95,"y":0.95},{"x":0.05,"y":0.95}]'::jsonb,
    15.0
) ON CONFLICT (camera_id) DO NOTHING;
