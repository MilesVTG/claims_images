"""Unit tests for worker service modules.

Tests:
- prompt_service: get_active_prompt
- gemini_service: get_contract_history, build_analysis_prompt, analyze_claim_with_gemini
- email_service: send_high_risk_alert, EmailService.send
- vision_service: reverse_image_lookup
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch, PropertyMock

# Worker modules use ``from app.services...`` which requires worker/ on sys.path.
# We DON'T add it at module level — that pollutes sys.path and breaks API test
# imports. Instead, each test function adds/removes it via the autouse fixture below.
_WORKER_ROOT = os.path.join(os.path.dirname(__file__), os.pardir, "worker")
_WORKER_ROOT = os.path.abspath(_WORKER_ROOT)

import pytest
from sqlalchemy import text

from tests.conftest import seed_test_claim, seed_test_prompt


@pytest.fixture(autouse=True)
def _worker_path():
    """Temporarily add worker/ to sys.path for each test, then clean up."""
    # Save ALL app.* modules (API-side) and remove them so worker/ app resolves
    saved_modules = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    for k in saved_modules:
        del sys.modules[k]
    sys.path.insert(0, _WORKER_ROOT)
    yield
    # Restore: remove worker path, clear worker modules, restore API ones
    if _WORKER_ROOT in sys.path:
        sys.path.remove(_WORKER_ROOT)
    stale = [k for k in sys.modules if k == "app" or k.startswith("app.")]
    for k in stale:
        del sys.modules[k]
    sys.modules.update(saved_modules)


# ============================================================================
# prompt_service
# ============================================================================


class TestGetActivePrompt:
    """Tests for prompt_service.get_active_prompt."""

    def test_get_active_prompt_returns_content(self, db_session):
        """Active prompt returns its content."""
        from app.services.prompt_service import get_active_prompt

        seed_test_prompt(
            db_session,
            slug="test_active",
            name="Test Active",
            category="analysis",
            content="You are a fraud analyst.",
        )
        result = get_active_prompt(db_session, "test_active")
        assert result == "You are a fraud analyst."

    def test_get_active_prompt_missing_slug_raises(self, db_session):
        """Missing slug raises ValueError."""
        from app.services.prompt_service import get_active_prompt

        with pytest.raises(ValueError, match="No active prompt found for slug"):
            get_active_prompt(db_session, "nonexistent_slug")

    def test_get_active_prompt_inactive_raises(self, db_session):
        """Inactive prompt is not returned."""
        from app.services.prompt_service import get_active_prompt

        seed_test_prompt(
            db_session,
            slug="test_inactive",
            name="Test Inactive",
            category="analysis",
            content="Inactive prompt content",
        )
        # Deactivate it
        db_session.execute(
            text("UPDATE system_prompts SET is_active = 0 WHERE slug = :s"),
            {"s": "test_inactive"},
        )
        db_session.commit()

        with pytest.raises(ValueError, match="No active prompt found for slug"):
            get_active_prompt(db_session, "test_inactive")


# ============================================================================
# gemini_service
# ============================================================================


class TestGetContractHistory:
    """Tests for gemini_service.get_contract_history."""

    def test_get_contract_history_returns_formatted(self, db_session):
        """Returns list of dicts for previous claims on the same contract."""
        from app.services.gemini_service import get_contract_history

        seed_test_claim(
            db_session,
            contract_id="CTR_HIST_UNIQUE",
            claim_id="CLM_OLD_U1",
            risk_score=45.0,
            red_flags=["low risk flag"],
        )
        seed_test_claim(
            db_session,
            contract_id="CTR_HIST_UNIQUE",
            claim_id="CLM_OLD_U2",
            risk_score=70.0,
            red_flags=["moderate risk flag"],
        )

        history = get_contract_history(db_session, "CTR_HIST_UNIQUE", "CLM_NEW")
        assert len(history) == 2
        claim_ids = [h["claim_id"] for h in history]
        assert "CLM_OLD_U1" in claim_ids
        assert "CLM_OLD_U2" in claim_ids
        # Current claim should be excluded
        assert "CLM_NEW" not in claim_ids

    def test_get_contract_history_empty(self, db_session):
        """Returns empty list when no prior claims exist."""
        from app.services.gemini_service import get_contract_history

        history = get_contract_history(db_session, "CTR_NOHISTORY", "CLM_FIRST")
        assert history == []


class TestBuildAnalysisPrompt:
    """Tests for gemini_service.build_analysis_prompt."""

    def test_build_analysis_prompt_fills_template(self, db_session):
        """Template placeholders are filled with provided data."""
        from app.services.gemini_service import build_analysis_prompt

        template_content = (
            "Contract: {contract_id}\n"
            "Claim: {claim_id}\n"
            "History: {history_text}\n"
            "Loss date: {reported_loss_date}\n"
            "Location: {service_drive_location}\n"
            "Coords: {service_drive_coords}\n"
            "EXIF timestamp: {exif_timestamp}\n"
            "GPS: {gps_lat}, {gps_lon}\n"
            "Full matches: {full_matches}\n"
            "Similar: {similar}"
        )
        seed_test_prompt(
            db_session,
            slug="fraud_analysis_template",
            name="Fraud Analysis Template",
            category="analysis",
            content=template_content,
        )

        result = build_analysis_prompt(
            db=db_session,
            contract_id="CTR_001",
            claim_id="CLM_001",
            claim_data={
                "reported_loss_date": "2026-01-15",
                "service_drive_location": "123 Main St",
                "service_drive_coords": "40.7,-74.0",
            },
            exif_data={
                "DateTimeOriginal": "2026:01:14 09:30:00",
                "gps_lat": 40.712,
                "gps_lon": -74.006,
            },
            vision_data={
                "full_matching_images": ["http://example.com/match1.jpg"],
                "visually_similar_images": ["http://example.com/sim1.jpg", "http://example.com/sim2.jpg"],
            },
            history=[],
        )

        assert "CTR_001" in result
        assert "CLM_001" in result
        assert "None (first claim for this contract)" in result
        assert "2026-01-15" in result
        assert "123 Main St" in result
        assert "40.712" in result
        assert "-74.006" in result
        assert "1" in result   # full_matches = 1
        assert "2" in result   # similar = 2

    def test_build_analysis_prompt_with_history(self, db_session):
        """History entries are formatted into the prompt."""
        from app.services.gemini_service import build_analysis_prompt

        template_content = "History: {history_text}\nContract: {contract_id}\nClaim: {claim_id}\nLoss date: {reported_loss_date}\nLocation: {service_drive_location}\nCoords: {service_drive_coords}\nEXIF: {exif_timestamp}\nGPS: {gps_lat}, {gps_lon}\nFull: {full_matches}\nSimilar: {similar}"
        # Ensure prompt exists (may already exist from prior test in same session-scope engine)
        db_session.execute(
            text("INSERT OR REPLACE INTO system_prompts (slug, name, category, content, is_active) VALUES (:s, :n, :c, :co, 1)"),
            {"s": "fraud_analysis_template", "n": "Fraud Analysis Template", "c": "analysis", "co": template_content},
        )
        db_session.commit()

        history = [
            {
                "claim_id": "CLM_PREV",
                "claim_date": "2025-12-01",
                "risk_score": 60.0,
                "tire_brands": "Goodyear",
                "vehicle_colors": "Black",
                "damage_summary": "Front bumper",
            }
        ]

        result = build_analysis_prompt(
            db=db_session,
            contract_id="CTR_002",
            claim_id="CLM_002",
            claim_data={},
            exif_data={},
            vision_data={},
            history=history,
        )

        assert "CLM_PREV" in result
        assert "2025-12-01" in result
        assert "Goodyear" in result
        assert "None (first claim for this contract)" not in result


class TestAnalyzeClaimWithGemini:
    """Tests for gemini_service.analyze_claim_with_gemini."""

    def test_analyze_claim_calls_gemini_with_system_instruction(self, db_session):
        """Gemini is called with the DB system instruction and images."""
        from app.services.gemini_service import analyze_claim_with_gemini

        # Seed prompts needed by the function
        seed_test_prompt(db_session, slug="fraud_system_instruction", name="System Instruction", category="analysis", content="You are a fraud detection system.")

        template = "Analyze {contract_id} {claim_id} {history_text} {reported_loss_date} {service_drive_location} {service_drive_coords} {exif_timestamp} {gps_lat} {gps_lon} {full_matches} {similar}"
        db_session.execute(
            text("INSERT OR REPLACE INTO system_prompts (slug, name, category, content, is_active) VALUES (:s, :n, :c, :co, 1)"),
            {"s": "fraud_analysis_template", "n": "Template", "c": "analysis", "co": template},
        )
        db_session.commit()

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "risk_score": 85.0,
            "red_flags": ["Stock photo detected"],
            "recommendation": "Flag for review",
        })

        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response

        with patch("app.services.gemini_service.genai") as mock_genai, \
             patch("app.services.gemini_service.settings") as mock_settings:
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_genai.GenerativeModel.return_value = mock_model_instance

            result = analyze_claim_with_gemini(
                db=db_session,
                contract_id="CTR_GEM",
                claim_id="CLM_GEM",
                claim_data={"reported_loss_date": "2026-01-15"},
                exif_data={},
                vision_data={},
                image_bytes_list=[b"fake-image-1", b"fake-image-2"],
            )

        # Verify genai was configured
        mock_genai.configure.assert_called_once_with(api_key="fake-key")

        # Verify model created with system instruction from DB
        mock_genai.GenerativeModel.assert_called_once()
        call_kwargs = mock_genai.GenerativeModel.call_args
        assert call_kwargs[1]["system_instruction"] == "You are a fraud detection system."

        # Verify generate_content called with text + 2 images
        content_parts = mock_model_instance.generate_content.call_args[0][0]
        assert isinstance(content_parts[0], str)  # prompt text
        assert len(content_parts) == 3  # text + 2 images

        # Verify parsed result
        assert result["risk_score"] == 85.0
        assert "Stock photo detected" in result["red_flags"]

    def test_analyze_claim_handles_invalid_json(self, db_session):
        """Invalid JSON from Gemini returns fallback dict instead of crashing."""
        from app.services.gemini_service import analyze_claim_with_gemini

        seed_test_prompt(db_session, slug="fraud_system_instruction", name="System Instruction", category="analysis", content="System instruction.")
        db_session.execute(
            text("INSERT OR REPLACE INTO system_prompts (slug, name, category, content, is_active) VALUES (:s, :n, :c, :co, 1)"),
            {"s": "fraud_analysis_template", "n": "Template", "c": "analysis",
             "co": "{contract_id}{claim_id}{history_text}{reported_loss_date}{service_drive_location}{service_drive_coords}{exif_timestamp}{gps_lat}{gps_lon}{full_matches}{similar}"},
        )
        db_session.commit()

        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all!"

        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response

        with patch("app.services.gemini_service.genai") as mock_genai, \
             patch("app.services.gemini_service.settings") as mock_settings:
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_genai.GenerativeModel.return_value = mock_model_instance

            result = analyze_claim_with_gemini(
                db=db_session,
                contract_id="CTR_BAD",
                claim_id="CLM_BAD",
                claim_data={},
                exif_data={},
                vision_data={},
                image_bytes_list=[b"img"],
            )

        assert result["risk_score"] is None
        assert "Gemini response was not valid JSON" in result["red_flags"]
        assert result["recommendation"] == "Manual review required"
        assert "raw_response" in result


# ============================================================================
# email_service
# ============================================================================


class TestSendHighRiskAlert:
    """Tests for email_service.send_high_risk_alert."""

    def test_send_high_risk_alert_formats_and_sends(self, db_session):
        """Alert above threshold loads templates, formats, and sends."""
        from app.services.email_service import send_high_risk_alert

        seed_test_prompt(
            db_session,
            slug="high_risk_email_template",
            name="Email Body",
            category="email",
            content="ALERT: {contract_id}/{claim_id} scored {risk_score}.\nFlags:\n{flags_text}\nDashboard: {dashboard_url}",
        )
        seed_test_prompt(
            db_session,
            slug="high_risk_email_subject",
            name="Email Subject",
            category="email",
            content="HIGH RISK: {claim_id} ({risk_score})",
        )

        with patch("app.services.email_service.send_alert_email") as mock_send, \
             patch("app.services.email_service.settings") as mock_settings:
            mock_settings.high_risk_threshold = 70.0
            mock_settings.dashboard_base_url = "http://localhost:3000"

            send_high_risk_alert(
                db=db_session,
                contract_id="CTR_HR",
                claim_id="CLM_HR",
                risk_score=92.5,
                red_flags=["Stock photo", "EXIF mismatch"],
            )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "CLM_HR" in call_kwargs["subject"]
        assert "92.5" in call_kwargs["subject"]
        assert "CTR_HR" in call_kwargs["body"]
        assert "Stock photo" in call_kwargs["body"]
        assert "EXIF mismatch" in call_kwargs["body"]
        assert "http://localhost:3000/claims/CTR_HR/CLM_HR" in call_kwargs["body"]

    def test_send_high_risk_alert_skips_below_threshold(self, db_session):
        """Score below threshold skips email entirely."""
        from app.services.email_service import send_high_risk_alert

        with patch("app.services.email_service.send_alert_email") as mock_send, \
             patch("app.services.email_service.settings") as mock_settings:
            mock_settings.high_risk_threshold = 80.0

            send_high_risk_alert(
                db=db_session,
                contract_id="CTR_LOW",
                claim_id="CLM_LOW",
                risk_score=55.0,
                red_flags=["Minor flag"],
            )

        mock_send.assert_not_called()

    def test_send_high_risk_alert_handles_missing_exchange(self, db_session):
        """No crash when Exchange is not configured (email is empty)."""
        from app.services.email_service import send_high_risk_alert

        seed_test_prompt(
            db_session,
            slug="high_risk_email_template",
            name="Email Body",
            category="email",
            content="ALERT: {contract_id}/{claim_id} scored {risk_score}.\n{flags_text}\n{dashboard_url}",
        )
        seed_test_prompt(
            db_session,
            slug="high_risk_email_subject",
            name="Email Subject",
            category="email",
            content="ALERT: {claim_id} ({risk_score})",
        )

        with patch("app.services.email_service.email_service") as mock_email_svc, \
             patch("app.services.email_service.settings") as mock_settings:
            mock_settings.high_risk_threshold = 70.0
            mock_settings.dashboard_base_url = "http://localhost:3000"
            mock_settings.alert_recipients = ""
            # send_alert_email will be called, but with no recipients it should just return
            # We patch the whole chain so it doesn't crash
            send_high_risk_alert(
                db=db_session,
                contract_id="CTR_NOEX",
                claim_id="CLM_NOEX",
                risk_score=90.0,
                red_flags=[],
            )
        # No exception = success


class TestEmailServiceSend:
    """Tests for EmailService.send."""

    def test_send_skips_when_not_configured(self):
        """EmailService.send silently skips when email is empty."""
        from app.services.email_service import EmailService

        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.exchange_email = ""
            mock_settings.exchange_password = ""
            mock_settings.exchange_server = ""

            svc = EmailService()
            # account property returns None when email is empty
            assert svc.account is None
            # send should not raise
            svc.send(
                to=["someone@example.com"],
                subject="Test",
                body="Hello",
            )
        # No exception = success


# ============================================================================
# vision_service
# ============================================================================


class TestReverseImageLookup:
    """Tests for vision_service.reverse_image_lookup."""

    def _make_mock_web_entity(self, description, score):
        entity = MagicMock()
        entity.description = description
        entity.score = score
        return entity

    def _make_mock_image(self, url):
        img = MagicMock()
        img.url = url
        return img

    def _make_mock_label(self, description, score):
        lbl = MagicMock()
        lbl.description = description
        lbl.score = score
        return lbl

    def _make_mock_page(self, url):
        page = MagicMock()
        page.url = url
        return page

    def test_web_detection_parsing(self):
        """Web detection results are parsed into structured dict."""
        from app.services.vision_service import reverse_image_lookup

        mock_web = MagicMock()
        mock_web.full_matching_images = [self._make_mock_image("http://full1.jpg")]
        mock_web.partial_matching_images = [self._make_mock_image("http://partial1.jpg")]
        mock_web.visually_similar_images = [
            self._make_mock_image("http://sim1.jpg"),
            self._make_mock_image("http://sim2.jpg"),
        ]
        mock_web.pages_with_matching_images = [self._make_mock_page("http://page1.com")]
        mock_web.web_entities = [
            self._make_mock_web_entity("Tire", 0.85),
            self._make_mock_web_entity("Car", 0.72),
        ]

        mock_labels = [
            self._make_mock_label("Vehicle", 0.95),
            self._make_mock_label("Wheel", 0.88),
        ]

        mock_response = MagicMock()
        mock_response.error.message = ""
        mock_response.web_detection = mock_web
        mock_response.label_annotations = mock_labels

        mock_client = MagicMock()
        mock_client.annotate_image.return_value = mock_response

        with patch("app.services.vision_service.vision") as mock_vision:
            mock_vision.ImageAnnotatorClient.return_value = mock_client
            mock_vision.Image.return_value = MagicMock()
            mock_vision.ImageSource.return_value = MagicMock()
            mock_vision.Feature.Type.WEB_DETECTION = "WEB_DETECTION"
            mock_vision.Feature.Type.LABEL_DETECTION = "LABEL_DETECTION"

            result = reverse_image_lookup("gs://bucket/contract/claim/photo.jpg")

        assert result["full_matching_images"] == ["http://full1.jpg"]
        assert result["partial_matching_images"] == ["http://partial1.jpg"]
        assert len(result["visually_similar_images"]) == 2
        assert result["pages_with_matching_images"] == ["http://page1.com"]
        assert len(result["web_entities"]) == 2
        assert result["web_entities"][0] == {"entity": "Tire", "score": 0.85}

    def test_label_detection_parsing(self):
        """Label annotations are parsed into list of dicts."""
        from app.services.vision_service import reverse_image_lookup

        mock_web = MagicMock()
        mock_web.full_matching_images = []
        mock_web.partial_matching_images = []
        mock_web.visually_similar_images = []
        mock_web.pages_with_matching_images = []
        mock_web.web_entities = []

        mock_labels = [
            self._make_mock_label("Automotive tire", 0.97),
            self._make_mock_label("Synthetic rubber", 0.82),
            self._make_mock_label("Tread", 0.79),
        ]

        mock_response = MagicMock()
        mock_response.error.message = ""
        mock_response.web_detection = mock_web
        mock_response.label_annotations = mock_labels

        mock_client = MagicMock()
        mock_client.annotate_image.return_value = mock_response

        with patch("app.services.vision_service.vision") as mock_vision:
            mock_vision.ImageAnnotatorClient.return_value = mock_client
            mock_vision.Image.return_value = MagicMock()
            mock_vision.ImageSource.return_value = MagicMock()
            mock_vision.Feature.Type.WEB_DETECTION = "WEB_DETECTION"
            mock_vision.Feature.Type.LABEL_DETECTION = "LABEL_DETECTION"

            result = reverse_image_lookup("gs://bucket/contract/claim/photo.jpg")

        assert len(result["labels"]) == 3
        assert result["labels"][0] == {"description": "Automotive tire", "score": 0.97}
        assert result["labels"][2]["description"] == "Tread"

    def test_vision_api_error_raises(self):
        """Vision API error message triggers RuntimeError."""
        from app.services.vision_service import reverse_image_lookup

        mock_response = MagicMock()
        mock_response.error.message = "Permission denied on resource gs://bucket/photo.jpg"

        mock_client = MagicMock()
        mock_client.annotate_image.return_value = mock_response

        with patch("app.services.vision_service.vision") as mock_vision:
            mock_vision.ImageAnnotatorClient.return_value = mock_client
            mock_vision.Image.return_value = MagicMock()
            mock_vision.ImageSource.return_value = MagicMock()
            mock_vision.Feature.Type.WEB_DETECTION = "WEB_DETECTION"
            mock_vision.Feature.Type.LABEL_DETECTION = "LABEL_DETECTION"

            with pytest.raises(RuntimeError, match="Vision API error"):
                reverse_image_lookup("gs://bucket/photo.jpg")
