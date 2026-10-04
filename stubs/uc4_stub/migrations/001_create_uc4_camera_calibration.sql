-- UC4-Owned Camera Calibration Table
-- This table is owned by UC4 and NOT part of the platform schema.
-- No foreign key to the platform's cameras table — camera_id is a plain UUID
-- matching what Camera Registry returns.
--
-- To apply:
--   psql -U innovision -d innovision_platform -f 001_create_uc4_camera_calibration.sql

CREATE TABLE IF NOT EXISTS uc4_camera_calibration (
    camera_id              UUID PRIMARY KEY,
    speed_polygon_normalized JSONB NOT NULL,
    distance_between_lines_meters FLOAT NOT NULL,
    entry_line             JSONB,
    exit_line              JSONB,
    updated_at             TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE uc4_camera_calibration IS
    'UC4-owned calibration data for speed estimation zones. '
    'camera_id is a plain UUID matching Camera Registry — no FK to platform cameras table.';
