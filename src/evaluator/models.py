"""Pydantic models for the evaluator."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ConfidenceLevel(StrEnum):
    """Confidence level for assessments."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriceSource(StrEnum):
    """Source of reference price."""

    RETAIL = "retail"
    COMPARABLES = "comparables"
    DEPRECIATION = "depreciation"
    INSUFFICIENT_DATA = "insufficient_data"


class ExtractionInput(BaseModel):
    """Input for extraction."""

    caption: str = Field(..., description="Post caption text")
    image_paths: list[str] = Field(..., description="Paths to uploaded images")
    manual_price: int | None = Field(None, description="Manual price override in VND")


class ProductInfo(BaseModel):
    """Extracted product information."""

    product_name: str | None = Field(None, description="Full product name")
    brand: str | None = Field(None, description="Brand name")
    model: str | None = Field(None, description="Model name")
    variant: str | None = Field(None, description="Storage/size/color variant")
    category: str | None = Field(None, description="Product category (smartphone, laptop, etc)")
    asking_price: int | None = Field(None, description="Asking price in VND")
    currency: str = Field("VND", description="Currency code")
    age_of_item: str | None = Field(None, description="Age or purchase date")
    reason_for_selling: str | None = Field(None, description="Stated reason for selling")
    warranty: str | None = Field(None, description="Warranty information")
    accessories_included: list[str] | None = Field(None, description="List of accessories")
    has_box: bool | None = Field(None, description="Original box included")
    has_invoice: bool | None = Field(None, description="Invoice/receipt included")
    extraction_confidence: ConfidenceLevel = Field(
        ConfidenceLevel.MEDIUM, description="Overall extraction confidence"
    )


class ConditionAssessment(BaseModel):
    """Physical condition assessment from photos."""

    condition_score: float = Field(..., ge=0, le=10, description="Condition score 0-10")
    photo_count: int = Field(..., description="Number of photos analyzed")
    looks_like_real_photos: bool = Field(..., description="Real photos vs stock/screenshots")
    visible_defects: list[str] = Field(
        default_factory=list,
        description="List of visible defects (scratches, dents, cracks, etc)",
    )
    positive_observations: list[str] = Field(
        default_factory=list, description="Positive condition observations"
    )
    image_caption_mismatch: bool = Field(
        False, description="Photos don't match caption description"
    )
    mismatch_explanation: str | None = Field(
        None, description="Explanation of mismatch if detected"
    )
    assessment_confidence: ConfidenceLevel = Field(
        ConfidenceLevel.MEDIUM, description="Confidence in condition assessment"
    )


class CaptionSignals(BaseModel):
    """Signals extracted from caption text."""

    red_flags: list[str] = Field(
        default_factory=list,
        description="Red flags detected (ib giá, deposit demands, pressure tactics, etc)",
    )
    positive_signals: list[str] = Field(
        default_factory=list, description="Positive signals (detailed info, transparency, etc)"
    )


class PriceReference(BaseModel):
    """Reference price information."""

    source: PriceSource = Field(..., description="Source of reference price")
    value: int | None = Field(None, description="Reference price in VND")
    comparable_count: int = Field(0, description="Number of comparables used")
    confidence: ConfidenceLevel = Field(
        ConfidenceLevel.MEDIUM, description="Confidence in reference price"
    )
    notes: str | None = Field(None, description="Additional notes about pricing")


class FairPriceRange(BaseModel):
    """Fair price range with adjustments."""

    low: int = Field(..., description="Low end of fair range")
    mid: int = Field(..., description="Mid-point fair price")
    high: int = Field(..., description="High end of fair range")
    condition_multiplier: float = Field(..., description="Multiplier applied for condition")
    reference: PriceReference = Field(..., description="Reference price information")


class EvaluationResult(BaseModel):
    """Final evaluation result."""

    score: float = Field(..., ge=1, le=10, description="Overall score 1-10")
    asking_price: int | None = Field(None, description="Asking price in VND")
    fair_price_range: FairPriceRange | None = Field(None, description="Fair price range")
    product: ProductInfo = Field(..., description="Extracted product information")
    condition: ConditionAssessment = Field(..., description="Condition assessment")
    caption_signals: CaptionSignals = Field(..., description="Caption analysis")
    confidence: ConfidenceLevel = Field(..., description="Overall confidence level")
    warnings: list[str] = Field(default_factory=list, description="Warnings and alerts")
    explanation: str = Field(..., description="Plain-language explanation of the score")
    adjustments_applied: dict[str, float] = Field(
        default_factory=dict, description="Score adjustments applied"
    )
    insufficient_data: bool = Field(
        False, description="True if reliable pricing is unavailable"
    )
