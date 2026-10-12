"""Tests for scoring module."""

import pytest

from evaluator.models import (
    CaptionSignals,
    ConditionAssessment,
    ConfidenceLevel,
    PriceReference,
    PriceSource,
    ProductInfo,
)
from evaluator.scoring import Scorer, ScoringConfig


@pytest.fixture
def scorer():
    """Create a scorer instance."""
    return Scorer()


@pytest.fixture
def base_product():
    """Create a base product for testing."""
    return ProductInfo(
        product_name="iPhone 14 Pro 256GB",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        category="smartphone",
        asking_price=18500000,
        currency="VND",
        has_box=True,
        has_invoice=False,
        warranty=None,
        accessories_included=["charger", "cable"],
        extraction_confidence=ConfidenceLevel.HIGH,
    )


@pytest.fixture
def good_condition():
    """Create good condition assessment."""
    return ConditionAssessment(
        condition_score=8.0,
        photo_count=4,
        looks_like_real_photos=True,
        visible_defects=["Minor scratches on frame"],
        positive_observations=["Screen clean", "Back glass good"],
        image_caption_mismatch=False,
        assessment_confidence=ConfidenceLevel.HIGH,
    )


@pytest.fixture
def reference_price_comparables():
    """Create reference price from comparables."""
    return PriceReference(
        source=PriceSource.COMPARABLES,
        value=18000000,
        comparable_count=8,
        confidence=ConfidenceLevel.HIGH,
    )


def test_condition_multiplier_lookup(scorer):
    """Test condition score to multiplier mapping."""
    assert scorer.config.get_condition_multiplier(10.0) == 1.10
    assert scorer.config.get_condition_multiplier(8.0) == 1.00
    assert scorer.config.get_condition_multiplier(5.0) == 0.85
    assert scorer.config.get_condition_multiplier(1.0) == 0.50


def test_fair_price_calculation(scorer, base_product, good_condition, reference_price_comparables):
    """Test fair price range calculation."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )

    # Condition 8.0 = 1.00 multiplier
    # Base: 18,000,000 * 1.00 = 18,000,000
    # Has box bonus: +2% = 18,360,000 mid
    assert fair_price.mid == 18360000
    assert fair_price.low == int(18360000 * 0.9)
    assert fair_price.high == int(18360000 * 1.1)
    assert fair_price.condition_multiplier == 1.00


def test_score_at_fair_price(scorer, base_product, good_condition, reference_price_comparables):
    """Test scoring when asking price equals fair price."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    # Set asking price to fair mid price
    base_product.asking_price = fair_price.mid
    
    signals = CaptionSignals(red_flags=[], positive_signals=["detailed_description"])
    
    score, adjustments, warnings = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals, base_product
    )
    
    # Ratio = 1.0, should score around 7.0
    assert 6.5 <= score <= 7.5
    assert "base_score" in adjustments


def test_score_below_fair_price(scorer, base_product, good_condition, reference_price_comparables):
    """Test scoring when asking price is below fair price (good deal)."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    # Set asking price to 80% of fair price
    base_product.asking_price = int(fair_price.mid * 0.8)
    
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    score, adjustments, warnings = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals, base_product
    )
    
    # Ratio = 0.8, should score high (8-9)
    assert score >= 8.0


def test_score_above_fair_price(scorer, base_product, good_condition, reference_price_comparables):
    """Test scoring when asking price is above fair price (overpriced)."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    # Set asking price to 150% of fair price
    base_product.asking_price = int(fair_price.mid * 1.5)
    
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    score, adjustments, warnings = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals, base_product
    )
    
    # Ratio = 1.5, should score low (1-3)
    assert score <= 3.0


def test_score_too_cheap_warning(scorer, base_product, good_condition, reference_price_comparables):
    """Test that suspiciously cheap prices trigger warnings."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    # Set asking price to 40% of fair price (too good to be true)
    base_product.asking_price = int(fair_price.mid * 0.4)
    
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    score, adjustments, warnings = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals, base_product
    )
    
    # Should have a warning about suspicious pricing
    assert len(warnings) > 0
    assert any("suspicious" in w.lower() or "scam" in w.lower() for w in warnings)


def test_red_flag_penalties(scorer, base_product, good_condition, reference_price_comparables):
    """Test that red flags reduce score."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    base_product.asking_price = fair_price.mid
    
    # No red flags
    signals_clean = CaptionSignals(red_flags=[], positive_signals=[])
    score_clean, _, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals_clean, base_product
    )
    
    # With red flags
    signals_flagged = CaptionSignals(
        red_flags=["ib_gia", "vague_details"], positive_signals=[]
    )
    score_flagged, adjustments, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals_flagged, base_product
    )
    
    # Flagged score should be lower
    assert score_flagged < score_clean
    assert "red_flag_ib_gia" in adjustments


def test_few_photos_penalty(scorer, base_product, reference_price_comparables):
    """Test penalty for insufficient photos."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables,
        ConditionAssessment(
            condition_score=8.0,
            photo_count=4,
            looks_like_real_photos=True,
            visible_defects=[],
            positive_observations=[],
            image_caption_mismatch=False,
            assessment_confidence=ConfidenceLevel.HIGH,
        ),
        base_product,
    )
    
    base_product.asking_price = fair_price.mid
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    # Many photos
    condition_many = ConditionAssessment(
        condition_score=8.0,
        photo_count=5,
        looks_like_real_photos=True,
        visible_defects=[],
        positive_observations=["clear images"],
        image_caption_mismatch=False,
        assessment_confidence=ConfidenceLevel.HIGH,
    )
    score_many, _, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, condition_many, signals, base_product
    )
    
    # Few photos
    condition_few = ConditionAssessment(
        condition_score=8.0,
        photo_count=1,
        looks_like_real_photos=True,
        visible_defects=[],
        positive_observations=[],
        image_caption_mismatch=False,
        assessment_confidence=ConfidenceLevel.LOW,
    )
    score_few, adjustments, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, condition_few, signals, base_product
    )
    
    assert score_few < score_many
    assert "few_photos" in adjustments


def test_stock_photos_penalty(scorer, base_product, good_condition, reference_price_comparables):
    """Test penalty for stock photos only."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    base_product.asking_price = fair_price.mid
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    # Stock photos
    condition_stock = ConditionAssessment(
        condition_score=8.0,
        photo_count=3,
        looks_like_real_photos=False,
        visible_defects=[],
        positive_observations=[],
        image_caption_mismatch=False,
        assessment_confidence=ConfidenceLevel.LOW,
    )
    score, adjustments, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, condition_stock, signals, base_product
    )
    
    assert "no_real_photos" in adjustments
    assert adjustments["no_real_photos"] < 0


def test_insufficient_data_handling(scorer, base_product, good_condition):
    """Test handling when no reference price available."""
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    score, adjustments, warnings = scorer.calculate_score(
        None, None, good_condition, signals, base_product
    )
    
    # Should return neutral score with warning
    assert score == 5.0
    assert len(warnings) > 0
    assert "insufficient" in warnings[0].lower()


def test_missing_price_handling(scorer, good_condition, reference_price_comparables):
    """Test handling when asking price is missing."""
    product = ProductInfo(
        product_name="iPhone 14 Pro",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        category="smartphone",
        asking_price=None,
        currency="VND",
        extraction_confidence=ConfidenceLevel.MEDIUM,
    )
    
    fair_price = scorer.calculate_fair_price(reference_price_comparables, good_condition, product)
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    score, _, warnings = scorer.calculate_score(
        None, fair_price, good_condition, signals, product
    )
    
    assert score == 5.0
    assert len(warnings) > 0


def test_confidence_high(scorer, good_condition, reference_price_comparables):
    """Test high confidence determination."""
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    # High comparables, many photos, no red flags
    ref_price = PriceReference(
        source=PriceSource.COMPARABLES,
        value=18000000,
        comparable_count=12,
        confidence=ConfidenceLevel.HIGH,
    )
    
    confidence = scorer.determine_confidence(ref_price, good_condition, signals)
    assert confidence == ConfidenceLevel.HIGH


def test_confidence_low(scorer):
    """Test low confidence determination."""
    # Few photos, stock images, red flags
    condition = ConditionAssessment(
        condition_score=5.0,
        photo_count=1,
        looks_like_real_photos=False,
        visible_defects=[],
        positive_observations=[],
        image_caption_mismatch=False,
        assessment_confidence=ConfidenceLevel.LOW,
    )
    
    signals = CaptionSignals(red_flags=["ib_gia", "vague_details"], positive_signals=[])
    
    ref_price = PriceReference(
        source=PriceSource.DEPRECIATION,
        value=15000000,
        comparable_count=0,
        confidence=ConfidenceLevel.LOW,
    )
    
    confidence = scorer.determine_confidence(ref_price, condition, signals)
    assert confidence == ConfidenceLevel.LOW


def test_score_clamping(scorer, base_product, good_condition, reference_price_comparables):
    """Test that scores are clamped to 1-10 range."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    # Extreme overpricing
    base_product.asking_price = fair_price.mid * 10
    signals = CaptionSignals(
        red_flags=["ib_gia", "deposit_required", "pressure_tactics"], positive_signals=[]
    )
    
    score, _, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals, base_product
    )
    
    # Should be clamped to minimum 1.0
    assert score >= 1.0
    assert score <= 10.0


def test_explanation_generation(scorer, base_product, good_condition, reference_price_comparables):
    """Test explanation text generation."""
    fair_price = scorer.calculate_fair_price(
        reference_price_comparables, good_condition, base_product
    )
    
    base_product.asking_price = fair_price.mid
    signals = CaptionSignals(red_flags=[], positive_signals=[])
    
    score, adjustments, _ = scorer.calculate_score(
        base_product.asking_price, fair_price, good_condition, signals, base_product
    )
    
    explanation = scorer.generate_explanation(
        score, base_product.asking_price, fair_price, good_condition, adjustments
    )
    
    assert len(explanation) > 0
    assert "fair market value" in explanation.lower()
    assert str(good_condition.condition_score) in explanation