"""Retail price provider with hardcoded smartphone prices."""

from typing import Optional

from ..models import ConfidenceLevel, PriceReference, PriceSource, ProductInfo
from .interface import PriceProvider


class RetailProvider(PriceProvider):
    """Provides retail prices for common smartphones."""

    # Hardcoded retail prices for common models (VND)
    # Format: (brand, model, variant) -> price
    RETAIL_PRICES = {
        # iPhone 15 Series
        ("apple", "iphone 15", "128gb"): 22990000,
        ("apple", "iphone 15", "256gb"): 25990000,
        ("apple", "iphone 15", "512gb"): 31990000,
        ("apple", "iphone 15 plus", "128gb"): 25990000,
        ("apple", "iphone 15 plus", "256gb"): 28990000,
        ("apple", "iphone 15 plus", "512gb"): 34990000,
        ("apple", "iphone 15 pro", "128gb"): 28990000,
        ("apple", "iphone 15 pro", "256gb"): 32990000,
        ("apple", "iphone 15 pro", "512gb"): 38990000,
        ("apple", "iphone 15 pro", "1tb"): 44990000,
        ("apple", "iphone 15 pro max", "256gb"): 34990000,
        ("apple", "iphone 15 pro max", "512gb"): 40990000,
        ("apple", "iphone 15 pro max", "1tb"): 46990000,
        # iPhone 14 Series
        ("apple", "iphone 14", "128gb"): 19990000,
        ("apple", "iphone 14", "256gb"): 22990000,
        ("apple", "iphone 14", "512gb"): 28990000,
        ("apple", "iphone 14 plus", "128gb"): 22990000,
        ("apple", "iphone 14 plus", "256gb"): 25990000,
        ("apple", "iphone 14 plus", "512gb"): 31990000,
        ("apple", "iphone 14 pro", "128gb"): 27990000,
        ("apple", "iphone 14 pro", "256gb"): 30990000,
        ("apple", "iphone 14 pro", "512gb"): 36990000,
        ("apple", "iphone 14 pro", "1tb"): 42990000,
        ("apple", "iphone 14 pro max", "128gb"): 30990000,
        ("apple", "iphone 14 pro max", "256gb"): 33990000,
        ("apple", "iphone 14 pro max", "512gb"): 39990000,
        ("apple", "iphone 14 pro max", "1tb"): 45990000,
        # iPhone 13 Series
        ("apple", "iphone 13", "128gb"): 17990000,
        ("apple", "iphone 13", "256gb"): 20990000,
        ("apple", "iphone 13", "512gb"): 26990000,
        ("apple", "iphone 13 pro", "128gb"): 25990000,
        ("apple", "iphone 13 pro", "256gb"): 28990000,
        ("apple", "iphone 13 pro", "512gb"): 34990000,
        ("apple", "iphone 13 pro", "1tb"): 40990000,
        ("apple", "iphone 13 pro max", "128gb"): 28990000,
        ("apple", "iphone 13 pro max", "256gb"): 31990000,
        ("apple", "iphone 13 pro max", "512gb"): 37990000,
        ("apple", "iphone 13 pro max", "1tb"): 43990000,
        # Samsung Galaxy S24 Series
        ("samsung", "galaxy s24", "128gb"): 18990000,
        ("samsung", "galaxy s24", "256gb"): 21990000,
        ("samsung", "galaxy s24 plus", "256gb"): 24990000,
        ("samsung", "galaxy s24 plus", "512gb"): 29990000,
        ("samsung", "galaxy s24 ultra", "256gb"): 30990000,
        ("samsung", "galaxy s24 ultra", "512gb"): 35990000,
        ("samsung", "galaxy s24 ultra", "1tb"): 42990000,
        # Samsung Galaxy S23 Series
        ("samsung", "galaxy s23", "128gb"): 16990000,
        ("samsung", "galaxy s23", "256gb"): 19990000,
        ("samsung", "galaxy s23 plus", "256gb"): 22990000,
        ("samsung", "galaxy s23 plus", "512gb"): 27990000,
        ("samsung", "galaxy s23 ultra", "256gb"): 28990000,
        ("samsung", "galaxy s23 ultra", "512gb"): 33990000,
        ("samsung", "galaxy s23 ultra", "1tb"): 40990000,
        # Samsung Galaxy S23 FE
        ("samsung", "galaxy s23 fe", "128gb"): 13990000,
        ("samsung", "galaxy s23 fe", "256gb"): 15990000,
    }

    @property
    def priority(self) -> int:
        """Retail has medium priority (after comparables)."""
        return 50

    def get_reference_price(self, product: ProductInfo) -> Optional[PriceReference]:
        """Get retail price for a product.

        Args:
            product: Product information

        Returns:
            PriceReference with retail price if found, None otherwise
        """
        if not product.brand or not product.model:
            return None

        # Normalize keys
        brand = product.brand.lower()
        model = product.model.lower()
        variant = self._extract_storage_variant(product.variant)

        # Try exact match
        key = (brand, model, variant)
        if key in self.RETAIL_PRICES:
            return PriceReference(
                source=PriceSource.RETAIL,
                value=self.RETAIL_PRICES[key],
                comparable_count=0,
                confidence=ConfidenceLevel.HIGH,
                notes=f"Retail price for {product.brand} {product.model} {variant}",
            )

        # Try without variant
        if variant:
            for stored_key, price in self.RETAIL_PRICES.items():
                if stored_key[0] == brand and stored_key[1] == model:
                    return PriceReference(
                        source=PriceSource.RETAIL,
                        value=price,
                        comparable_count=0,
                        confidence=ConfidenceLevel.MEDIUM,
                        notes=f"Retail price for {product.brand} {product.model} (variant match may be inexact)",
                    )

        return None

    def _extract_storage_variant(self, variant: Optional[str]) -> str:
        """Extract storage size from variant string.

        Args:
            variant: Variant string (e.g., "256GB Deep Purple", "512GB")

        Returns:
            Normalized storage size (e.g., "256gb")
        """
        if not variant:
            return ""

        variant_lower = variant.lower()

        # Extract storage patterns
        for size in ["1tb", "512gb", "256gb", "128gb", "64gb", "32gb", "16gb"]:
            if size in variant_lower:
                return size

        return ""