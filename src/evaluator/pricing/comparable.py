"""Comparable price provider using cached market data."""

import statistics
from typing import Optional

from ..models import ConfidenceLevel, PriceReference, PriceSource, ProductInfo
from .cache import PriceCache
from .interface import PriceProvider


class ComparableProvider(PriceProvider):
    """Provides reference prices from comparable listings."""

    def __init__(self, cache: Optional[PriceCache] = None, min_comparables: int = 3):
        """Initialize comparable provider.

        Args:
            cache: Price cache instance (creates new if None)
            min_comparables: Minimum number of comparables required
        """
        self.cache = cache or PriceCache()
        self.min_comparables = min_comparables

    @property
    def priority(self) -> int:
        """Comparables have highest priority."""
        return 10

    def get_reference_price(self, product: ProductInfo) -> Optional[PriceReference]:
        """Get reference price from comparable listings.

        Args:
            product: Product information

        Returns:
            PriceReference with median comparable price if enough data, None otherwise
        """
        if not product.category or not product.brand or not product.model:
            return None

        # Find comparables
        comparables = self.cache.find_comparables(
            product.category, product.brand, product.model, ttl_days=7
        )

        if len(comparables) < self.min_comparables:
            return None

        # Calculate median price
        prices = [comp["price"] for comp in comparables]
        median_price = int(statistics.median(prices))

        # Determine confidence based on sample size
        if len(comparables) >= 10:
            confidence = ConfidenceLevel.HIGH
        elif len(comparables) >= 5:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        return PriceReference(
            source=PriceSource.COMPARABLES,
            value=median_price,
            comparable_count=len(comparables),
            confidence=confidence,
            notes=f"Median of {len(comparables)} recent listings",
        )

    def add_comparable(
        self,
        category: str,
        brand: str,
        model: str,
        variant: Optional[str],
        price: int,
        notes: Optional[str] = None,
    ):
        """Add a comparable price to the cache.

        Args:
            category: Product category
            brand: Brand name
            model: Model name
            variant: Variant (storage, color, etc)
            price: Price in VND
            notes: Optional notes
        """
        self.cache.set(
            category=category,
            brand=brand,
            model=model,
            variant=variant,
            price=price,
            source="comparables",
            comparable_count=1,
            notes=notes,
        )