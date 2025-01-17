
import requests
from schematics.models import ValidationError
from basemodels.constants import SUPPORTED_CONTENT_TYPES


def validate_content_type(uri: str) -> None:
    """Validate uri content type"""
    response = requests.head(uri)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValidationError(f"Unsupported type {content_type}")
