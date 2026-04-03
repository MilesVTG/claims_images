"""Golden dataset sample definitions.

Each sample defines a test image scenario with expected risk score range,
expected red flags, and must-not flags. Used by the seed script and
regression tests.
"""

# --- Fraud samples (should be flagged, high risk) ---

FRAUD_STOCK_PHOTO = {
    "name": "fraud_stock_tire_damage",
    "storage_key": "golden/FRAUD_CONTRACT_001/CLM_FRAUD_001/stock_tire_damage.jpg",
    "expected_risk_min": 60.0,
    "expected_risk_max": 100.0,
    "expected_flags": [
        "Exact web match",
    ],
    "must_not_flags": [],
    "expected_tire_brand": None,
    "expected_color": None,
    "notes": "Stock photo of tire damage downloaded from shutterstock. Should trigger reverse image match.",
}

FRAUD_TIRE_BRAND_MISMATCH = {
    "name": "fraud_tire_brand_mismatch",
    "storage_key": "golden/FRAUD_CONTRACT_002/CLM_FRAUD_002/michelin_to_goodyear.jpg",
    "expected_risk_min": 30.0,
    "expected_risk_max": 100.0,
    "expected_flags": [
        "Tire brand",
    ],
    "must_not_flags": [],
    "expected_tire_brand": "Goodyear",
    "expected_color": None,
    "notes": "Photo shows Goodyear tire but prior claim on this contract showed Michelin. Should trigger brand mismatch.",
}

FRAUD_EDITED_PHOTO = {
    "name": "fraud_photoshop_edited",
    "storage_key": "golden/FRAUD_CONTRACT_003/CLM_FRAUD_003/edited_damage.jpg",
    "expected_risk_min": 30.0,
    "expected_risk_max": 100.0,
    "expected_flags": [
        "Photo editing software detected",
    ],
    "must_not_flags": [],
    "expected_tire_brand": None,
    "expected_color": None,
    "notes": "Image with Photoshop EXIF metadata. Should trigger editing software detection.",
}

FRAUD_GPS_MISMATCH = {
    "name": "fraud_gps_mismatch",
    "storage_key": "golden/FRAUD_CONTRACT_004/CLM_FRAUD_004/wrong_location.jpg",
    "expected_risk_min": 40.0,
    "expected_risk_max": 100.0,
    "expected_flags": [
        "GPS mismatch",
    ],
    "must_not_flags": [],
    "expected_tire_brand": None,
    "expected_color": None,
    "notes": "Photo GPS coords 200+ miles from service drive location. Should trigger GPS mismatch.",
}

FRAUD_NO_EXIF = {
    "name": "fraud_stripped_exif",
    "storage_key": "golden/FRAUD_CONTRACT_005/CLM_FRAUD_005/no_metadata.jpg",
    "expected_risk_min": 5.0,
    "expected_risk_max": 100.0,
    "expected_flags": [
        "No EXIF metadata found",
    ],
    "must_not_flags": [],
    "expected_tire_brand": None,
    "expected_color": None,
    "notes": "Image with all EXIF stripped. Should trigger missing metadata flag.",
}

FRAUD_TIMESTAMP_MISMATCH = {
    "name": "fraud_timestamp_mismatch",
    "storage_key": "golden/FRAUD_CONTRACT_006/CLM_FRAUD_006/wrong_date.jpg",
    "expected_risk_min": 40.0,
    "expected_risk_max": 100.0,
    "expected_flags": [
        "Timestamp mismatch",
    ],
    "must_not_flags": [],
    "expected_tire_brand": None,
    "expected_color": None,
    "notes": "Photo taken 30 days before reported loss date. Should trigger timestamp mismatch.",
}

# --- Clean/legitimate samples (should NOT be flagged, low risk) ---

CLEAN_LEGITIMATE_DAMAGE = {
    "name": "clean_legitimate_front_damage",
    "storage_key": "golden/CLEAN_CONTRACT_001/CLM_CLEAN_001/front_damage.jpg",
    "expected_risk_min": 0.0,
    "expected_risk_max": 35.0,
    "expected_flags": [],
    "must_not_flags": [
        "Exact web match",
        "Photo editing software detected",
        "GPS mismatch",
    ],
    "expected_tire_brand": None,
    "expected_color": None,
    "notes": "Legitimate photo of front-end damage with valid EXIF, no web matches.",
}

CLEAN_TIRE_CONSISTENT = {
    "name": "clean_consistent_tires",
    "storage_key": "golden/CLEAN_CONTRACT_002/CLM_CLEAN_002/tire_closeup.jpg",
    "expected_risk_min": 0.0,
    "expected_risk_max": 35.0,
    "expected_flags": [],
    "must_not_flags": [
        "Tire brand",
        "Exact web match",
    ],
    "expected_tire_brand": "Michelin",
    "expected_color": None,
    "notes": "Clean tire photo with consistent brand across claims on contract.",
}

CLEAN_WITH_GPS = {
    "name": "clean_gps_matches",
    "storage_key": "golden/CLEAN_CONTRACT_003/CLM_CLEAN_003/side_damage.jpg",
    "expected_risk_min": 0.0,
    "expected_risk_max": 30.0,
    "expected_flags": [],
    "must_not_flags": [
        "GPS mismatch",
        "Photo editing software detected",
    ],
    "expected_tire_brand": None,
    "expected_color": "Blue",
    "notes": "Legitimate photo with GPS matching service drive location.",
}

# --- All samples grouped ---

FRAUD_SAMPLES = [
    FRAUD_STOCK_PHOTO,
    FRAUD_TIRE_BRAND_MISMATCH,
    FRAUD_EDITED_PHOTO,
    FRAUD_GPS_MISMATCH,
    FRAUD_NO_EXIF,
    FRAUD_TIMESTAMP_MISMATCH,
]

CLEAN_SAMPLES = [
    CLEAN_LEGITIMATE_DAMAGE,
    CLEAN_TIRE_CONSISTENT,
    CLEAN_WITH_GPS,
]

ALL_SAMPLES = FRAUD_SAMPLES + CLEAN_SAMPLES
