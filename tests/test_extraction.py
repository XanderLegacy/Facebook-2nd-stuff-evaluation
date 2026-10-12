"""Tests for extraction module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from evaluator.extraction import Extractor, ExtractionError
from evaluator.models import ExtractionInput


# Mock API responses
MOCK_GOOD_LISTING_RESPONSE = {
    "product": {
        "product_name": "iPhone 14 Pro 256GB",
        "brand": "Apple",
        "model": "iPhone 14 Pro",
        "variant": "256GB Deep Purple",
        "category": "smartphone",
        "asking_price": 18500000,
        "currency": "VND",
        "age_of_item": None,
        "reason_for_selling": None,
        "warranty": "6 months remaining",
        "accessories_included": ["box", "charger", "cable"],
        "has_box": True,
        "has_invoice": None,
        "extraction_confidence": "high",
    },
    "condition": {
        "condition_score": 8.5,
        "photo_count": 4,
        "looks_like_real_photos": True,
        "visible_defects": ["Minor scratches on frame"],
        "positive_observations": ["Screen in excellent condition", "Back glass clean"],
        "image_caption_mismatch": False,
        "mismatch_explanation": None,
        "assessment_confidence": "high",
    },
    "caption_signals": {
        "red_flags": [],
        "positive_signals": ["detailed_description", "multiple_angles", "has_documentation"],
    },
}

MOCK_SUSPICIOUS_LISTING_RESPONSE = {
    "product": {
        "product_name": "iPhone 15 Pro Max",
        "brand": "Apple",
        "model": "iPhone 15 Pro Max",
        "variant": None,
        "category": "smartphone",
        "asking_price": None,
        "currency": "VND",
        "age_of_item": None,
        "reason_for_selling": None,
        "warranty": None,
        "accessories_included": None,
        "has_box": None,
        "has_invoice": None,
        "extraction_confidence": "low",
    },
    "condition": {
        "condition_score": 5.0,
        "photo_count": 1,
        "looks_like_real_photos": False,
        "visible_defects": [],
        "positive_observations": [],
        "image_caption_mismatch": False,
        "mismatch_explanation": None,
        "assessment_confidence": "low",
    },
    "caption_signals": {
        "red_flags": ["ib_gia", "vague_details", "stock_photos_only"],
        "positive_signals": [],
    },
}

MOCK_PRICE_FORMATS_RESPONSE = {
    "product": {
        "product_name": "Samsung Galaxy S23 Ultra",
        "brand": "Samsung",
        "model": "Galaxy S23 Ultra",
        "variant": "256GB",
        "category": "smartphone",
        "asking_price": 14500000,
        "currency": "VND",
        "age_of_item": "6 months",
        "reason_for_selling": None,
        "warranty": None,
        "accessories_included": None,
        "has_box": True,
        "has_invoice": False,
        "extraction_confidence": "medium",
    },
    "condition": {
        "condition_score": 7.5,
        "photo_count": 3,
        "looks_like_real_photos": True,
        "visible_defects": ["Minor wear on corners"],
        "positive_observations": ["Screen perfect"],
        "image_caption_mismatch": False,
        "mismatch_explanation": None,
        "assessment_confidence": "medium",
    },
    "caption_signals": {"red_flags": [], "positive_signals": ["detailed_description"]},
}


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client."""
    with patch("evaluator.extraction.anthropic.Anthropic") as mock:
        yield mock


@pytest.fixture
def mock_image_encoder():
    """Mock image encoding."""
    with patch("evaluator.extraction.Extractor._encode_image") as mock:
        mock.return_value = "fake_base64_data"
        yield mock


def create_mock_response(data: dict) -> MagicMock:
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(data)
    mock_response.content = [mock_content]
    return mock_response


def test_extractor_initialization_with_api_key():
    """Test extractor initializes with provided API key."""
    extractor = Extractor(api_key="test_key")
    assert extractor.api_key == "test_key"


def test_extractor_initialization_without_api_key():
    """Test extractor raises error without API key."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY must be set"):
            Extractor()


def test_extract_good_listing(mock_anthropic_client, mock_image_encoder):
    """Test extraction of a good listing with clear details."""
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_client.messages.create.return_value = create_mock_response(MOCK_GOOD_LISTING_RESPONSE)

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Extract
    extraction_input = ExtractionInput(
        caption="iPhone 14 Pro 256GB Deep Purple, zin all, fullbox, bảo hành 6 tháng, giá 18tr5",
        image_paths=["photo1.jpg", "photo2.jpg"],
    )
    product, condition, signals = extractor.extract(extraction_input)

    # Assertions
    assert product.brand == "Apple"
    assert product.model == "iPhone 14 Pro"
    assert product.asking_price == 18500000
    assert product.has_box is True
    assert condition.condition_score == 8.5
    assert condition.looks_like_real_photos is True
    assert len(signals.red_flags) == 0
    assert "detailed_description" in signals.positive_signals


def test_extract_suspicious_listing(mock_anthropic_client, mock_image_encoder):
    """Test extraction of a suspicious listing with red flags."""
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_client.messages.create.return_value = create_mock_response(
        MOCK_SUSPICIOUS_LISTING_RESPONSE
    )

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Extract
    extraction_input = ExtractionInput(
        caption="iPhone 15 Pro Max, máy đẹp, ib giá", image_paths=["stock.jpg"]
    )
    product, condition, signals = extractor.extract(extraction_input)

    # Assertions
    assert product.asking_price is None
    assert product.extraction_confidence == "low"
    assert condition.looks_like_real_photos is False
    assert "ib_gia" in signals.red_flags
    assert "vague_details" in signals.red_flags
    assert "stock_photos_only" in signals.red_flags


def test_vietnamese_price_parsing(mock_anthropic_client, mock_image_encoder):
    """Test various Vietnamese price format parsing."""
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_client.messages.create.return_value = create_mock_response(MOCK_PRICE_FORMATS_RESPONSE)

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Test "14tr5" format
    extraction_input = ExtractionInput(
        caption="Samsung S23 Ultra 256GB, giá 14tr5", image_paths=["photo.jpg"]
    )
    product, _, _ = extractor.extract(extraction_input)
    assert product.asking_price == 14500000


def test_manual_price_override(mock_anthropic_client, mock_image_encoder):
    """Test manual price override."""
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_response_data = MOCK_GOOD_LISTING_RESPONSE.copy()
    mock_response_data["product"]["asking_price"] = 20000000  # Original price from LLM
    mock_client.messages.create.return_value = create_mock_response(mock_response_data)

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Extract with manual price
    extraction_input = ExtractionInput(
        caption="iPhone 14 Pro 256GB", image_paths=["photo.jpg"], manual_price=18500000
    )
    product, _, _ = extractor.extract(extraction_input)

    # Manual price should override
    assert product.asking_price == 18500000


def test_parse_json_with_markdown_wrapper(mock_anthropic_client, mock_image_encoder):
    """Test JSON parsing when response includes markdown code blocks."""
    # Setup mock with markdown wrapper
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_response = MagicMock()
    mock_content = MagicMock()
    # Wrap JSON in markdown
    mock_content.text = f"```json\n{json.dumps(MOCK_GOOD_LISTING_RESPONSE)}\n```"
    mock_response.content = [mock_content]
    mock_client.messages.create.return_value = mock_response

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Extract
    extraction_input = ExtractionInput(caption="Test", image_paths=["photo.jpg"])
    product, _, _ = extractor.extract(extraction_input)

    # Should parse successfully
    assert product.brand == "Apple"


def test_extraction_error_on_api_failure(mock_anthropic_client, mock_image_encoder):
    """Test that API errors are caught and wrapped."""
    # Setup mock to raise API error
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("API Error")

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Extract should raise ExtractionError
    extraction_input = ExtractionInput(caption="Test", image_paths=["photo.jpg"])
    with pytest.raises(ExtractionError, match="Extraction failed"):
        extractor.extract(extraction_input)


def test_extraction_error_on_invalid_json(mock_anthropic_client, mock_image_encoder):
    """Test that invalid JSON responses are caught."""
    # Setup mock to return invalid JSON
    mock_client = MagicMock()
    mock_anthropic_client.return_value = mock_client
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "Not valid JSON at all"
    mock_response.content = [mock_content]
    mock_client.messages.create.return_value = mock_response

    # Create extractor
    extractor = Extractor(api_key="test_key")

    # Extract should raise ExtractionError
    extraction_input = ExtractionInput(caption="Test", image_paths=["photo.jpg"])
    with pytest.raises(ExtractionError, match="Failed to parse JSON"):
        extractor.extract(extraction_input)


def test_missing_image_file():
    """Test that missing image files raise appropriate error."""
    extractor = Extractor(api_key="test_key")
    extraction_input = ExtractionInput(
        caption="Test", image_paths=["nonexistent_file.jpg"]
    )

    with pytest.raises(ExtractionError, match="Failed to load image"):
        extractor.extract(extraction_input)