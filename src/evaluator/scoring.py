"""Scoring engine for evaluating asking price vs fair market value."""

import bisect
from pathlib import Path

import yaml

from .models import (
    CaptionSignals,
    ConditionAssessment,
    ConfidenceLevel,
    FairPriceRange,
    PriceReference,
    ProductInfo,
)


class ScoringConfig:
    """Configuration for scoring rules."""

    def __init__(self, config_path: Path | None = None):
        """Load scoring configuration from YAML.

        Args:
            config_path: Path to scoring.yaml (defaults to config/scoring.yaml)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "scoring.yaml"

        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # Pre-process ratio_to_score for binary search
        self.ratio_thresholds = sorted(
            [(item["ratio"], item["score"], item.get("warning")) for item in self.config["ratio_to_score"]],
            key=lambda x: x[0],
        )

    def get_condition_multiplier(self, condition_score: float) -> float:
        """Get price multiplier based on condition score.

        Args:
            condition_score: Condition score 0-10

        Returns:
            Multiplier for fair price calculation
        """
        # Round to nearest integer for lookup
        rounded = round(condition_score)
        rounded = max(0, min(10, rounded))  # Clamp to 0-10
        return self.config["condition_multipliers"][rounded]

    def get_base_score_from_ratio(self, ratio: float) -> tuple[float, str | None]:
        """Map price ratio to base score using configured thresholds.

        Args:
            ratio: asking_price / fair_price

        Returns:
            Tuple of (score, warning_message)
        """
        # Find the position where ratio would fit
        ratios = [r for r, _, _ in self.ratio_thresholds]
        idx = bisect.bisect_left(ratios, ratio)

        # If ratio is below first threshold, use first score
        if idx == 0:
            return self.ratio_thresholds[0][1], self.ratio_thresholds[0][2]

        # If ratio is beyond last threshold, use last score
        if idx >= len(self.ratio_thresholds):
            return self.ratio_thresholds[-1][1], self.ratio_thresholds[-1][2]

        # Interpolate between two thresholds
        lower_ratio, lower_score, lower_warning = self.ratio_thresholds[idx - 1]
        upper_ratio, upper_score, upper_warning = self.ratio_thresholds[idx]

        # Linear interpolation
        t = (ratio - lower_ratio) / (upper_ratio - lower_ratio)
        score = lower_score + t * (upper_score - lower_score)

        # Use warning from the closer threshold
        warning = lower_warning if t < 0.5 else upper_warning

        return score, warning

    def get_adjustment(self, category: str, key: str) -> float:
        """Get score adjustment value.

        Args:
            category: Adjustment category (red_flags, missing_info, bonuses)
            key: Specific adjustment key

        Returns:
            Adjustment value (positive or negative)
        """
        return self.config["adjustments"].get(category, {}).get(key, 0.0)


class Scorer:
    """Scores posts based on price, condition, and signals."""

    def __init__(self, config: ScoringConfig | None = None):
        """Initialize scorer with configuration.

        Args:
            config: Scoring configuration (defaults to loading from config/scoring.yaml)
        """
        self.config = config or ScoringConfig()

    def calculate_fair_price(
        self,
        reference_price: PriceReference,
        condition: ConditionAssessment,
        product: ProductInfo,
    ) -> FairPriceRange:
        """Calculate fair price range with condition adjustments.

        Args:
            reference_price: Reference price information
            condition: Condition assessment
            product: Product information

        Returns:
            Fair price range with low/mid/high values
        """
        if reference_price.value is None:
            raise ValueError("Reference price cannot be None")

        # Get condition multiplier
        condition_multiplier = self.config.get_condition_multiplier(condition.condition_score)

        # Calculate base fair price
        base_fair_price = reference_price.value * condition_multiplier

        # Apply bonuses
        bonus_multiplier = 1.0
        if product.has_box:
            bonus_multiplier += self.config.get_adjustment("bonuses", "has_box") / 10
        if product.has_invoice:
            bonus_multiplier += self.config.get_adjustment("bonuses", "has_invoice") / 10
        if product.warranty:
            bonus_multiplier += self.config.get_adjustment("bonuses", "warranty_remaining") / 10
        if product.accessories_included and len(product.accessories_included) >= 3:
            bonus_multiplier += self.config.get_adjustment("bonuses", "full_accessories") / 10

        mid_price = int(base_fair_price * bonus_multiplier)

        # Create range: ±10% around mid price
        low_price = int(mid_price * 0.9)
        high_price = int(mid_price * 1.1)

        return FairPriceRange(
            low=low_price,
            mid=mid_price,
            high=high_price,
            condition_multiplier=condition_multiplier,
            reference=reference_price,
        )

    def calculate_score(
        self,
        asking_price: int | None,
        fair_price_range: FairPriceRange | None,
        condition: ConditionAssessment,
        signals: CaptionSignals,
        product: ProductInfo,
    ) -> tuple[float, dict[str, float], list[str]]:
        """Calculate final score with all adjustments.

        Args:
            asking_price: Asking price in VND
            fair_price_range: Fair price range
            condition: Condition assessment
            signals: Caption signals
            product: Product information

        Returns:
            Tuple of (final_score, adjustments_dict, warnings_list)
        """
        adjustments = {}
        warnings = []

        # Handle insufficient data
        if asking_price is None or fair_price_range is None:
            return 5.0, adjustments, ["Insufficient data for accurate scoring"]

        # Calculate base score from ratio
        ratio = asking_price / fair_price_range.mid
        base_score, ratio_warning = self.config.get_base_score_from_ratio(ratio)
        adjustments["base_score"] = base_score

        if ratio_warning:
            warnings.append(ratio_warning)

        # Apply red flag penalties
        for flag in signals.red_flags:
            penalty = self.config.get_adjustment("red_flags", flag)
            if penalty != 0:
                adjustments[f"red_flag_{flag}"] = penalty

        # Apply missing info penalties
        if condition.photo_count < 3:
            penalty = self.config.get_adjustment("missing_info", "few_photos")
            adjustments["few_photos"] = penalty

        if not condition.looks_like_real_photos:
            penalty = self.config.get_adjustment("missing_info", "no_real_photos")
            adjustments["no_real_photos"] = penalty

        if not product.brand or not product.model:
            penalty = self.config.get_adjustment("missing_info", "unclear_product")
            adjustments["unclear_product"] = penalty

        # Apply bonuses (score adjustments, not price adjustments)
        if condition.photo_count >= 5 and len(condition.positive_observations) > 0:
            bonus = self.config.get_adjustment("bonuses", "multiple_angles")
            adjustments["multiple_angles"] = bonus

        if len(product.reason_for_selling or "") > 20:
            bonus = self.config.get_adjustment("bonuses", "detailed_description")
            adjustments["detailed_description"] = bonus

        # Calculate final score
        final_score = base_score + sum(
            v for k, v in adjustments.items() if k != "base_score"
        )

        # Clamp to 1-10 range
        final_score = max(1.0, min(10.0, final_score))

        # Round to 1 decimal place
        final_score = round(final_score, 1)

        return final_score, adjustments, warnings

    def determine_confidence(
        self,
        reference_price: PriceReference | None,
        condition: ConditionAssessment,
        signals: CaptionSignals,
    ) -> ConfidenceLevel:
        """Determine overall confidence level.

        Args:
            reference_price: Price reference information
            condition: Condition assessment
            signals: Caption signals

        Returns:
            Confidence level (low/medium/high)
        """
        if reference_price is None or reference_price.value is None:
            return ConfidenceLevel.LOW

        # Count issues
        issues = len(signals.red_flags)
        if condition.photo_count < 2:
            issues += 1
        if not condition.looks_like_real_photos:
            issues += 2

        # Check comparables
        comparable_count = reference_price.comparable_count

        # Determine confidence
        if comparable_count >= 10 and condition.photo_count >= 4 and issues == 0:
            return ConfidenceLevel.HIGH
        elif comparable_count >= 3 and condition.photo_count >= 2 and issues <= 1:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def generate_explanation(
        self,
        score: float,
        asking_price: int | None,
        fair_price_range: FairPriceRange | None,
        condition: ConditionAssessment,
        adjustments: dict[str, float],
    ) -> str:
        """Generate plain-language explanation of the score.

        Args:
            score: Final score
            asking_price: Asking price
            fair_price_range: Fair price range
            condition: Condition assessment
            adjustments: Applied adjustments

        Returns:
            Human-readable explanation
        """
        if asking_price is None or fair_price_range is None:
            return "Unable to score due to insufficient pricing information."

        ratio = asking_price / fair_price_range.mid

        # Build explanation
        parts = []

        # Price assessment
        if ratio < 0.7:
            parts.append(
                f"The asking price is significantly below fair market value ({ratio:.0%}). "
                "This could be a great deal, but verify the item carefully for hidden issues."
            )
        elif ratio < 0.9:
            parts.append(
                f"The asking price is below fair market value ({ratio:.0%}). "
                "This looks like a good deal."
            )
        elif ratio <= 1.1:
            parts.append(
                f"The asking price matches fair market value ({ratio:.0%}). "
                "This is a fair price for the condition."
            )
        elif ratio <= 1.3:
            parts.append(
                f"The asking price is above fair market value ({ratio:.0%}). "
                "You might be able to negotiate a better price."
            )
        else:
            parts.append(
                f"The asking price is significantly above fair market value ({ratio:.0%}). "
                "This appears overpriced."
            )

        # Condition note
        if condition.condition_score >= 8:
            parts.append(
                f"The item shows {condition.condition_score}/10 condition with minimal wear."
            )
        elif condition.condition_score >= 6:
            parts.append(
                f"The item shows {condition.condition_score}/10 condition with normal used wear."
            )
        else:
            parts.append(
                f"The item shows {condition.condition_score}/10 condition with visible defects."
            )

        # Mention key adjustments
        negative_adjustments = [k for k, v in adjustments.items() if v < 0 and k != "base_score"]
        if negative_adjustments:
            parts.append(
                f"Score reduced due to: {', '.join(negative_adjustments[:3])}."
            )

        return " ".join(parts)
