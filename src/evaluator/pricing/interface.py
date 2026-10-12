"""Abstract interface for price providers."""

from abc import ABC, abstractmethod
from typing import Optional

from ..models import PriceReference, ProductInfo


class PriceProvider(ABC):
    """Abstract base class for price providers."""

    @abstractmethod
    def get_reference_price(self, product: ProductInfo) -> Optional[PriceReference]:
        """Get reference price for a product.

        Args:
            product: Product information

        Returns:
            PriceReference if found, None otherwise
        """
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Priority of this provider (lower = higher priority).

        Returns:
            Priority value (1-100)
        """
        pass