"""Add claims_dashboard_view and daily_fraud_summary_view (Section 8).

Revision ID: 002_sql_views
Revises: 001_initial
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_sql_views"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- claims_dashboard_view ---
    op.execute("""
        CREATE OR REPLACE VIEW claims_dashboard_view AS
        SELECT
            c.id,
            c.contract_id,
            c.claim_id,
            c.claim_date,
            c.reported_loss_date,
            c.service_drive_location,
            c.service_drive_coords,

            -- Risk & Flags
            c.risk_score,
            array_to_string(c.red_flags, ' | ') AS red_flags_list,

            -- Gemini Analysis (flattened)
            c.gemini_analysis->>'explanation' AS gemini_explanation,
            c.gemini_analysis->>'recommendation' AS recommendation,
            c.gemini_analysis->>'damage_assessment' AS damage_assessment,
            c.gemini_analysis->'tire_brands_detected'->>'current' AS current_tire_brand,
            c.gemini_analysis->'vehicle_colors_detected'->>'current' AS current_vehicle_color,

            -- Change Detection (derived booleans)
            (c.gemini_analysis->'tire_brands_detected'->>'current') IS DISTINCT FROM
                (c.gemini_analysis->'tire_brands_detected'->'previous'->>0)
                AS tire_brand_changed,
            (c.gemini_analysis->'vehicle_colors_detected'->>'current') IS DISTINCT FROM
                (c.gemini_analysis->'vehicle_colors_detected'->'previous'->>0)
                AS vehicle_color_changed,

            -- Geo/Timestamp Checks
            c.gemini_analysis->'geo_timestamp_check'->>'gps_vs_service_drive'
                AS gps_match_status,
            c.gemini_analysis->'geo_timestamp_check'->>'timestamp_vs_loss_date'
                AS timestamp_match_status,

            -- Reverse Image Results (flattened)
            jsonb_array_length(
                COALESCE(c.reverse_image_results->'full_matching_images', '[]'::jsonb)
            ) AS exact_web_matches,
            jsonb_array_length(
                COALESCE(c.reverse_image_results->'visually_similar_images', '[]'::jsonb)
            ) AS similar_web_images,
            c.reverse_image_results->'pages_with_matching_images'->>0
                AS first_matching_page,
            jsonb_array_length(
                COALESCE(c.reverse_image_results->'full_matching_images', '[]'::jsonb)
            ) > 0 AS has_exact_web_match,

            -- Photo Metadata
            c.extracted_metadata->>'DateTimeOriginal' AS photo_timestamp,
            c.extracted_metadata->>'gps_location' AS photo_gps,
            c.extracted_metadata->>'Make' AS camera_make,
            c.extracted_metadata->>'Model' AS camera_model,
            c.photo_uris[1] AS latest_photo_uri,
            c.processed_at

        FROM claims c
        ORDER BY c.risk_score DESC NULLS LAST, c.claim_date DESC
    """)

    # --- daily_fraud_summary_view ---
    op.execute("""
        CREATE OR REPLACE VIEW daily_fraud_summary_view AS
        SELECT
            DATE(processed_at) AS process_date,
            COUNT(*) AS total_claims_processed,
            COUNT(*) FILTER (WHERE risk_score >= 70) AS high_risk_count,
            COUNT(*) FILTER (WHERE risk_score BETWEEN 40 AND 69) AS medium_risk_count,
            COUNT(*) FILTER (WHERE risk_score < 40) AS low_risk_count,
            ROUND(AVG(risk_score)::numeric, 1) AS avg_risk_score,
            COUNT(*) FILTER (WHERE
                jsonb_array_length(
                    COALESCE(reverse_image_results->'full_matching_images', '[]'::jsonb)
                ) > 0
            ) AS claims_with_web_matches
        FROM claims
        GROUP BY DATE(processed_at)
        ORDER BY process_date DESC
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS daily_fraud_summary_view")
    op.execute("DROP VIEW IF EXISTS claims_dashboard_view")
