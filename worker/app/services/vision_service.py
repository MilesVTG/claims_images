"""Cloud Vision reverse image lookup service (Section 5).

Runs Web Detection + Label Detection on a GCS-hosted photo using the
google-cloud-vision client library.  Returns structured dicts of matches,
similar images, web entities, and labels.
"""

import logging
from typing import Any

from google.cloud import vision

logger = logging.getLogger(__name__)


def reverse_image_lookup(gs_uri: str) -> dict[str, Any]:
    """Run Cloud Vision Web Detection on a GCS image.

    Args:
        gs_uri: Full GCS URI, e.g. ``gs://bucket/contract/claim/photo.jpg``

    Returns:
        Dict with keys: full_matching_images, partial_matching_images,
        visually_similar_images, pages_with_matching_images, web_entities.
    """
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(image_uri=gs_uri))

    response = client.annotate_image(
        {
            "image": image,
            "features": [
                {"type_": vision.Feature.Type.WEB_DETECTION},
                {"type_": vision.Feature.Type.LABEL_DETECTION, "max_results": 20},
            ],
        }
    )

    if response.error.message:
        logger.error("Vision API error for %s: %s", gs_uri, response.error.message)
        raise RuntimeError(f"Vision API error: {response.error.message}")

    web = response.web_detection
    labels = response.label_annotations

    return {
        "full_matching_images": [img.url for img in web.full_matching_images],
        "partial_matching_images": [img.url for img in web.partial_matching_images],
        "visually_similar_images": [img.url for img in web.visually_similar_images],
        "pages_with_matching_images": [
            page.url for page in web.pages_with_matching_images
        ],
        "web_entities": [
            {"entity": e.description, "score": e.score} for e in web.web_entities
        ],
        "labels": [
            {"description": lbl.description, "score": lbl.score} for lbl in labels
        ],
    }
