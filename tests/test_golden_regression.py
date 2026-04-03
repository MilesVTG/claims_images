"""Golden dataset regression test suite (CI-031).

Validates that the risk scoring engine produces expected results for
known fraud and clean samples. Tests the risk_service.compute_risk_score()
function directly with controlled inputs.
"""

import importlib.util
import pytest
import sys
import os

# Load worker's risk_service directly (avoid conflict with api/app module cache)
_worker_risk_path = os.path.join(
    os.path.dirname(__file__), "..", "worker", "app", "services", "risk_service.py"
)
_spec = importlib.util.spec_from_file_location("worker_risk_service", _worker_risk_path)
_risk_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_risk_mod)
compute_risk_score = _risk_mod.compute_risk_score

from tests.golden_dataset.samples import (
    ALL_SAMPLES,
    FRAUD_SAMPLES,
    CLEAN_SAMPLES,
    FRAUD_STOCK_PHOTO,
    FRAUD_TIRE_BRAND_MISMATCH,
    FRAUD_EDITED_PHOTO,
    FRAUD_GPS_MISMATCH,
    FRAUD_NO_EXIF,
    FRAUD_TIMESTAMP_MISMATCH,
    CLEAN_LEGITIMATE_DAMAGE,
    CLEAN_TIRE_CONSISTENT,
    CLEAN_WITH_GPS,
)


# ---------------------------------------------------------------------------
# Simulated analysis inputs per golden sample
# These replicate what the worker pipeline would produce for each sample.
# ---------------------------------------------------------------------------

SIMULATED_INPUTS = {
    "fraud_stock_tire_damage": {
        "exif_data": {
            "DateTimeOriginal": "2026:01:10 14:30:00",
            "Make": "Canon",
            "Model": "EOS R5",
        },
        "vision_data": {
            "full_matching_images": [
                "https://stock.example.com/tire-damage-001.jpg",
                "https://stock.example.com/tire-damage-002.jpg",
            ],
            "partial_matching_images": [],
            "pages_with_matching_images": ["https://shutterstock.com/photo/12345"],
            "web_entities": [{"entity": "tire damage", "score": 0.9}],
            "labels": [{"description": "tire", "score": 0.95}],
        },
        "gemini_data": {
            "risk_score": 80,
            "red_flags": ["Stock photo detected", "Image found on shutterstock"],
            "reverse_image_flag": True,
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
    "fraud_tire_brand_mismatch": {
        "exif_data": {
            "DateTimeOriginal": "2026:03:15 09:00:00",
            "Make": "iPhone",
            "Model": "15 Pro",
            "gps_lat": 41.8781,
            "gps_lon": -87.6298,
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 70,
            "red_flags": [
                "Tire brand changed from Michelin to Goodyear between claims",
            ],
            "tire_brands_detected": {"current": "Goodyear", "previous": ["Michelin"]},
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
    "fraud_photoshop_edited": {
        "exif_data": {
            "DateTimeOriginal": "2026:02:20 11:00:00",
            "Software": "Adobe Photoshop CC 2024",
            "Make": "Canon",
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 60,
            "red_flags": ["Image appears to have been digitally altered"],
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
    "fraud_gps_mismatch": {
        "exif_data": {
            "DateTimeOriginal": "2026:02:25 16:45:00",
            "gps_lat": 34.0522,
            "gps_lon": -118.2437,
            "gps_location": "34.0522,-118.2437",
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 75,
            "red_flags": ["Photo GPS location 1745 miles from service drive"],
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MISMATCH (1745 miles from service drive)",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
    "fraud_stripped_exif": {
        "exif_data": {},
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 40,
            "red_flags": ["Image metadata completely stripped"],
            "geo_timestamp_check": {},
        },
    },
    "fraud_timestamp_mismatch": {
        "exif_data": {
            "DateTimeOriginal": "2025:12:01 08:00:00",
            "Make": "Samsung",
            "Model": "Galaxy S24",
            "gps_lat": 41.8781,
            "gps_lon": -87.6298,
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 65,
            "red_flags": ["Photo taken 35 days before reported loss date"],
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MISMATCH (photo 35 days before loss)",
            },
        },
    },
    "clean_legitimate_front_damage": {
        "exif_data": {
            "DateTimeOriginal": "2026:03:20 10:15:00",
            "Make": "iPhone",
            "Model": "15 Pro",
            "gps_lat": 41.8819,
            "gps_lon": -87.6278,
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 10,
            "red_flags": [],
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
    "clean_consistent_tires": {
        "exif_data": {
            "DateTimeOriginal": "2026:03:22 14:30:00",
            "Make": "iPhone",
            "Model": "14 Pro",
            "gps_lat": 41.8800,
            "gps_lon": -87.6290,
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 5,
            "red_flags": [],
            "tire_brands_detected": {"current": "Michelin", "previous": ["Michelin"]},
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
    "clean_gps_matches": {
        "exif_data": {
            "DateTimeOriginal": "2026:03:25 11:00:00",
            "Make": "Samsung",
            "Model": "Galaxy S24",
            "gps_lat": 41.8785,
            "gps_lon": -87.6300,
        },
        "vision_data": {
            "full_matching_images": [],
            "partial_matching_images": [],
        },
        "gemini_data": {
            "risk_score": 8,
            "red_flags": [],
            "geo_timestamp_check": {
                "gps_vs_service_drive": "MATCH",
                "timestamp_vs_loss_date": "MATCH",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

class TestFraudSamplesFlagged:
    """Known fraud samples must produce risk scores in expected range."""

    @pytest.mark.parametrize("sample", FRAUD_SAMPLES, ids=lambda s: s["name"])
    def test_fraud_sample_risk_in_range(self, sample):
        inputs = SIMULATED_INPUTS[sample["name"]]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        score = result["risk_score"]
        assert sample["expected_risk_min"] <= score <= sample["expected_risk_max"], (
            f"{sample['name']}: score {score} not in "
            f"[{sample['expected_risk_min']}, {sample['expected_risk_max']}]"
        )

    @pytest.mark.parametrize("sample", FRAUD_SAMPLES, ids=lambda s: s["name"])
    def test_fraud_sample_has_expected_flags(self, sample):
        inputs = SIMULATED_INPUTS[sample["name"]]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        flags_text = " ".join(result["red_flags"])
        for expected in sample["expected_flags"]:
            assert expected.lower() in flags_text.lower(), (
                f"{sample['name']}: expected flag containing '{expected}' "
                f"not found in: {result['red_flags']}"
            )

    @pytest.mark.parametrize("sample", FRAUD_SAMPLES, ids=lambda s: s["name"])
    def test_fraud_sample_has_flags(self, sample):
        inputs = SIMULATED_INPUTS[sample["name"]]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        assert len(result["red_flags"]) > 0, (
            f"{sample['name']}: fraud sample should have at least one red flag"
        )


class TestCleanSamplesNotFlagged:
    """Clean/legitimate samples must produce low risk scores."""

    @pytest.mark.parametrize("sample", CLEAN_SAMPLES, ids=lambda s: s["name"])
    def test_clean_sample_risk_in_range(self, sample):
        inputs = SIMULATED_INPUTS[sample["name"]]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        score = result["risk_score"]
        assert sample["expected_risk_min"] <= score <= sample["expected_risk_max"], (
            f"{sample['name']}: score {score} not in "
            f"[{sample['expected_risk_min']}, {sample['expected_risk_max']}]"
        )

    @pytest.mark.parametrize("sample", CLEAN_SAMPLES, ids=lambda s: s["name"])
    def test_clean_sample_no_forbidden_flags(self, sample):
        inputs = SIMULATED_INPUTS[sample["name"]]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        flags_text = " ".join(result["red_flags"])
        for forbidden in sample["must_not_flags"]:
            assert forbidden.lower() not in flags_text.lower(), (
                f"{sample['name']}: forbidden flag '{forbidden}' "
                f"found in: {result['red_flags']}"
            )


class TestRiskScoreBreakdown:
    """Verify score breakdown components are present and reasonable."""

    @pytest.mark.parametrize(
        "sample_name",
        [s["name"] for s in ALL_SAMPLES],
    )
    def test_breakdown_present(self, sample_name):
        inputs = SIMULATED_INPUTS[sample_name]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        assert "score_breakdown" in result
        breakdown = result["score_breakdown"]
        assert "exif_anomalies" in breakdown
        assert "vision_web_matches" in breakdown
        assert "gemini_analysis" in breakdown

    @pytest.mark.parametrize(
        "sample_name",
        [s["name"] for s in ALL_SAMPLES],
    )
    def test_score_clamped_0_100(self, sample_name):
        inputs = SIMULATED_INPUTS[sample_name]
        result = compute_risk_score(
            inputs["exif_data"],
            inputs["vision_data"],
            inputs["gemini_data"],
        )
        assert 0 <= result["risk_score"] <= 100


class TestRiskServiceEdgeCases:
    """Edge cases for the risk scoring engine."""

    def test_all_empty_inputs(self):
        result = compute_risk_score({}, {}, {})
        assert result["risk_score"] >= 0
        assert isinstance(result["red_flags"], list)

    def test_null_gemini_score(self):
        result = compute_risk_score(
            {"DateTimeOriginal": "2026:01:01 00:00:00"},
            {},
            {"risk_score": None, "red_flags": []},
        )
        assert result["risk_score"] >= 0

    def test_extreme_web_matches(self):
        """Many web matches should cap contribution, not exceed 100."""
        result = compute_risk_score(
            {},
            {
                "full_matching_images": [f"url{i}" for i in range(50)],
                "partial_matching_images": [f"url{i}" for i in range(50)],
            },
            {"risk_score": 100, "red_flags": ["Everything suspicious"]},
        )
        assert result["risk_score"] <= 100

    def test_editing_software_detection(self):
        """Each known editor should trigger the flag."""
        for editor in ["Photoshop", "GIMP 2.10", "Adobe Lightroom", "Snapseed"]:
            result = compute_risk_score(
                {"Software": editor, "DateTimeOriginal": "2026:01:01"},
                {},
                {"risk_score": 0, "red_flags": []},
            )
            flags_text = " ".join(result["red_flags"])
            assert "editing software" in flags_text.lower(), f"Editor '{editor}' not detected"

    def test_missing_datetime_original(self):
        """Missing DateTimeOriginal should add a small penalty."""
        result = compute_risk_score(
            {"Make": "Canon"},  # Has EXIF but no DateTimeOriginal
            {},
            {"risk_score": 0, "red_flags": []},
        )
        assert result["score_breakdown"]["exif_anomalies"] > 0
        flags_text = " ".join(result["red_flags"])
        assert "DateTimeOriginal" in flags_text

    def test_flags_deduplicated(self):
        """Duplicate flags should be removed."""
        result = compute_risk_score(
            {},
            {},
            {
                "risk_score": 50,
                "red_flags": ["Duplicate flag", "Duplicate flag", "Unique flag"],
            },
        )
        assert result["red_flags"].count("Duplicate flag") == 1
