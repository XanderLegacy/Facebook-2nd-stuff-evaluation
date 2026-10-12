"""LLM-powered extraction from caption and images."""

import base64
import json
import os
import re
from pathlib import Path

import anthropic
from pydantic import ValidationError

from .models import (
    CaptionSignals,
    ConditionAssessment,
    ExtractionInput,
    ProductInfo,
)


class ExtractionError(Exception):
    """Raised when extraction fails."""

    pass


class Extractor:
    """Extracts structured data from post caption and images using Claude."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Initialize extractor with Anthropic API.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (defaults to CLAUDE_MODEL env var or claude-3-5-sonnet)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set")

        self.model = model or os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        self.client = anthropic.Anthropic(api_key=self.api_key)

        # Load system prompt
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "extraction_system.md"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def extract(
        self, extraction_input: ExtractionInput
    ) -> tuple[ProductInfo, ConditionAssessment, CaptionSignals]:
        """Extract product info, condition, and signals from post.

        Args:
            extraction_input: Input containing caption, images, and optional manual price

        Returns:
            Tuple of (ProductInfo, ConditionAssessment, CaptionSignals)

        Raises:
            ExtractionError: If extraction or validation fails
        """
        # Prepare message content
        content = []

        # Add caption
        content.append(
            {
                "type": "text",
                "text": f"Caption:\n{extraction_input.caption}",
            }
        )

        # Add images
        for image_path in extraction_input.image_paths:
            try:
                image_data = self._encode_image(image_path)
                # Detect media type
                ext = Path(image_path).suffix.lower()
                media_type_map = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }
                media_type = media_type_map.get(ext, "image/jpeg")

                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    }
                )
            except Exception as e:
                raise ExtractionError(f"Failed to load image {image_path}: {e}")

        # Add instruction
        content.append(
            {
                "type": "text",
                "text": "\nAnalyze the caption and images above. Return ONLY valid JSON matching the schema from the system prompt.",
            }
        )

        # Call Claude API
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self.system_prompt,
                messages=[{"role": "user", "content": content}],
            )

            # Extract text from response
            response_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    response_text += block.text

            # Parse JSON
            data = self._parse_json_response(response_text)

            # Override price if manual price provided
            if extraction_input.manual_price is not None:
                data["product"]["asking_price"] = extraction_input.manual_price

            # Validate and create models
            product = ProductInfo(**data["product"])
            condition = ConditionAssessment(**data["condition"])
            signals = CaptionSignals(**data["caption_signals"])

            return product, condition, signals

        except anthropic.APIError as e:
            raise ExtractionError(f"Anthropic API error: {e}")
        except ValidationError as e:
            raise ExtractionError(f"Invalid extraction format: {e}")
        except Exception as e:
            raise ExtractionError(f"Extraction failed: {e}")

    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded image string
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from LLM response, handling potential markdown wrappers.

        Args:
            response_text: Raw response text from LLM

        Returns:
            Parsed JSON dictionary

        Raises:
            ExtractionError: If JSON parsing fails
        """
        # Remove markdown code blocks if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            # Extract content between ``` markers
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Failed to parse JSON response: {e}\nResponse: {cleaned}")


def extract_from_post(
    caption: str,
    image_paths: list[str],
    manual_price: int | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[ProductInfo, ConditionAssessment, CaptionSignals]:
    """Convenience function to extract data from a post.

    Args:
        caption: Post caption text
        image_paths: List of paths to images
        manual_price: Optional manual price override in VND
        api_key: Optional Anthropic API key
        model: Optional Claude model name

    Returns:
        Tuple of (ProductInfo, ConditionAssessment, CaptionSignals)
    """
    extractor = Extractor(api_key=api_key, model=model)
    extraction_input = ExtractionInput(
        caption=caption, image_paths=image_paths, manual_price=manual_price
    )
    return extractor.extract(extraction_input)
