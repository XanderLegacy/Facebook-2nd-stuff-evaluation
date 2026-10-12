"""Depreciation-based price provider (fallback)."""

import re

from ..models import ConfidenceLevel, PriceReference, PriceSource, ProductInfo
from .interface import PriceProvider
from .retail import RetailProvider


class DepreciationProvider(PriceProvider):
    """Provides depreciation-based price estimates (fallback)."""

    # Depreciation curve based on age
    DEPRECIATION_CURVE = {
        (0, 6): 0.85,  # 0-6 months: 85% of retail
        (6, 12): 0.75,  # 6-12 months: 75%
        (12, 18): 0.65,  # 12-18 months: 65%
        (18, 24): 0.55,  # 18-24 months: 55%
        (24, 36): 0.45,  # 24-36 months: 45%
        (36, 48): 0.35,  # 36-48 months: 35%
        (48, 999): 0.25,  # 48+ months: 25%
    }

    def __init__(self, retail_provider: RetailProvider | None = None):
        """Initialize depreciation provider.

        Args:
            retail_provider: Retail provider instance (creates new if None)
        """
        self.retail_provider = retail_provider or RetailProvider()

    @property
    def priority(self) -> int:
        """Depreciation has lowest priority (fallback)."""
        return 90

    def get_reference_price(self, product: ProductInfo) -> PriceReference | None:
        """Get depreciation-based price estimate.

        Args:
            product: Product information

        Returns:
            PriceReference with depreciated price if retail price available, None otherwise
        """
        # Get retail price first
        retail_ref = self.retail_provider.get_reference_price(product)
        if not retail_ref or not retail_ref.value:
            return None

        # Extract age in months
        age_months = self._extract_age_months(product.age_of_item)
        if age_months is None:
            # Default to 12 months if age unknown
            age_months = 12

        # Get depreciation factor
        depreciation_factor = self._get_depreciation_factor(age_months)

        # Calculate depreciated price
        depreciated_price = int(retail_ref.value * depreciation_factor)

        return PriceReference(
            source=PriceSource.DEPRECIATION,
            value=depreciated_price,
            comparable_count=0,
            confidence=ConfidenceLevel.LOW,
            notes=f"Estimated from retail price with {age_months}-month depreciation ({depreciation_factor:.0%})",
        )

    def _extract_age_months(self, age_of_item: str | None) -> int | None:
        """Extract age in months from text.

        Args:
            age_of_item: Age description (e.g., "6 months", "1 year", "2 năm")

        Returns:
            Age in months if parseable, None otherwise
        """
        if not age_of_item:
            return None

        text = age_of_item.lower()

        # Look for month patterns
        month_match = re.search(r"(\d+)\s*(?:month|tháng)", text)
        if month_match:
            return int(month_match.group(1))

        # Look for year patterns
        year_match = re.search(r"(\d+)\s*(?:year|năm)", text)
        if year_match:
            return int(year_match.group(1)) * 12

        # Look for just numbers
        number_match = re.search(r"(\d+)", text)
        if number_match:
            num = int(number_match.group(1))
            # Assume months if < 20, years if >= 20
            if num < 20:
                return num
            elif num >= 2020:
                # Looks like a year
                from datetime import datetime

                current_year = datetime.now().year
                return (current_year - num) * 12

        return None

    def _get_depreciation_factor(self, age_months: int) -> float:
        """Get depreciation factor for given age.

        Args:
            age_months: Age in months

        Returns:
            Depreciation factor (0.0-1.0)
        """
        for (min_age, max_age), factor in self.DEPRECIATION_CURVE.items():
            if min_age <= age_months < max_age:
                return factor

        # Default to oldest depreciation
        return 0.25
