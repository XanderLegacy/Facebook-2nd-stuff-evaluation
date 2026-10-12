"""Tests for pricing providers."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from evaluator.models import ProductInfo
from evaluator.pricing.cache import PriceCache
from evaluator.pricing.comparable import ComparableProvider
from evaluator.pricing.depreciation import DepreciationProvider
from evaluator.pricing.retail import RetailProvider


@pytest.fixture
def temp_cache(tmp_path):
    """Create a temporary price cache."""
    db_path = tmp_path / "test_cache.db"
    return PriceCache(str(db_path))


@pytest.fixture
def sample_product():
    """Create a sample product."""
    return ProductInfo(
        product_name="iPhone 14 Pro 256GB",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        category="smartphone",
        asking_price=18500000,
        currency="VND",
    )


def test_price_cache_set_and_get(temp_cache):
    """Test basic cache operations."""
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        price=18500000,
        source="comparables",
    )

    result = temp_cache.get(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        source="comparables",
    )

    assert result is not None
    assert result["price"] == 18500000
    assert result["source"] == "comparables"


def test_price_cache_ttl_expiration(temp_cache):
    """Test that expired entries are not returned."""
    # Insert entry
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        price=18500000,
        source="comparables",
    )

    # Should be found with 7-day TTL
    result = temp_cache.get(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        source="comparables",
        ttl_days=7,
    )
    assert result is not None

    # Should not be found with 0-day TTL
    result = temp_cache.get(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        source="comparables",
        ttl_days=0,
    )
    assert result is None


def test_price_cache_find_comparables(temp_cache):
    """Test finding comparable prices."""
    # Add multiple comparables
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        price=18000000,
        source="comparables",
    )
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB Silver",
        price=18500000,
        source="comparables",
    )
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="512GB",
        price=22000000,
        source="comparables",
    )

    comparables = temp_cache.find_comparables(
        category="smartphone", brand="Apple", model="iPhone 14 Pro"
    )

    assert len(comparables) == 3
    prices = [c["price"] for c in comparables]
    assert 18000000 in prices
    assert 18500000 in prices
    assert 22000000 in prices


def test_retail_provider_exact_match():
    """Test retail provider with exact match."""
    provider = RetailProvider()
    product = ProductInfo(
        product_name="iPhone 15 Pro",
        brand="Apple",
        model="iPhone 15 Pro",
        variant="256GB",
        category="smartphone",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is not None
    assert ref_price.value == 32990000
    assert ref_price.source.value == "retail"


def test_retail_provider_case_insensitive():
    """Test retail provider is case insensitive."""
    provider = RetailProvider()
    product = ProductInfo(
        product_name="iphone 15 pro",
        brand="apple",
        model="iphone 15 pro",
        variant="256gb",
        category="smartphone",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is not None
    assert ref_price.value == 32990000


def test_retail_provider_variant_extraction():
    """Test retail provider extracts storage from variant string."""
    provider = RetailProvider()
    product = ProductInfo(
        product_name="iPhone 15 Pro",
        brand="Apple",
        model="iPhone 15 Pro",
        variant="256GB Deep Purple",  # Storage + color
        category="smartphone",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is not None
    assert ref_price.value == 32990000


def test_retail_provider_no_match():
    """Test retail provider returns None for unknown products."""
    provider = RetailProvider()
    product = ProductInfo(
        product_name="Unknown Phone",
        brand="Unknown",
        model="Unknown Model",
        variant="128GB",
        category="smartphone",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is None


def test_comparable_provider_sufficient_data(temp_cache):
    """Test comparable provider with sufficient comparables."""
    provider = ComparableProvider(cache=temp_cache, min_comparables=3)

    # Add comparables
    for price in [18000000, 18500000, 19000000, 18200000, 18800000]:
        temp_cache.set(
            category="smartphone",
            brand="Apple",
            model="iPhone 14 Pro",
            variant="256GB",
            price=price,
            source="comparables",
        )

    product = ProductInfo(
        product_name="iPhone 14 Pro",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        category="smartphone",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is not None
    assert ref_price.source.value == "comparables"
    assert ref_price.comparable_count == 5
    # Median of [18000000, 18200000, 18500000, 18800000, 19000000] = 18500000
    assert ref_price.value == 18500000


def test_comparable_provider_insufficient_data(temp_cache):
    """Test comparable provider returns None with insufficient data."""
    provider = ComparableProvider(cache=temp_cache, min_comparables=3)

    # Add only 2 comparables
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        price=18000000,
        source="comparables",
    )
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        price=18500000,
        source="comparables",
    )

    product = ProductInfo(
        product_name="iPhone 14 Pro",
        brand="Apple",
        model="iPhone 14 Pro",
        variant="256GB",
        category="smartphone",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is None


def test_depreciation_provider_with_age():
    """Test depreciation provider calculates based on age."""
    provider = DepreciationProvider()

    product = ProductInfo(
        product_name="iPhone 15 Pro",
        brand="Apple",
        model="iPhone 15 Pro",
        variant="256GB",
        category="smartphone",
        age_of_item="6 months",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is not None
    assert ref_price.source.value == "depreciation"
    # Retail: 32990000, 6 months = 75% = 24742500
    expected = int(32990000 * 0.75)
    assert ref_price.value == expected


def test_depreciation_provider_age_parsing():
    """Test depreciation provider parses various age formats."""
    provider = DepreciationProvider()

    # Test month format
    assert provider._extract_age_months("6 months") == 6
    assert provider._extract_age_months("12 tháng") == 12

    # Test year format
    assert provider._extract_age_months("1 year") == 12
    assert provider._extract_age_months("2 năm") == 24

    # Test year number
    assert provider._extract_age_months("2023") == (datetime.now().year - 2023) * 12


def test_depreciation_provider_no_retail_price():
    """Test depreciation provider returns None without retail price."""
    provider = DepreciationProvider()

    product = ProductInfo(
        product_name="Unknown Phone",
        brand="Unknown",
        model="Unknown",
        variant="128GB",
        category="smartphone",
        age_of_item="6 months",
        currency="VND",
    )

    ref_price = provider.get_reference_price(product)

    assert ref_price is None


def test_depreciation_curve():
    """Test depreciation factors at different ages."""
    provider = DepreciationProvider()

    assert provider._get_depreciation_factor(3) == 0.85  # 0-6 months
    assert provider._get_depreciation_factor(10) == 0.75  # 6-12 months
    assert provider._get_depreciation_factor(15) == 0.65  # 12-18 months
    assert provider._get_depreciation_factor(20) == 0.55  # 18-24 months
    assert provider._get_depreciation_factor(30) == 0.45  # 24-36 months
    assert provider._get_depreciation_factor(40) == 0.35  # 36-48 months
    assert provider._get_depreciation_factor(60) == 0.25  # 48+ months


def test_cache_cleanup(temp_cache):
    """Test cleaning up old cache entries."""
    # Add fresh entry
    temp_cache.set(
        category="smartphone",
        brand="Apple",
        model="iPhone 15 Pro",
        variant="256GB",
        price=20000000,
        source="comparables",
    )

    # Add old entry by directly manipulating DB
    old_timestamp = (datetime.now() - timedelta(days=100)).isoformat()
    with sqlite3.connect(temp_cache.db_path) as conn:
        conn.execute(
            """
            INSERT INTO prices 
            (product_key, category, brand, model, variant, price, source, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "smartphone|apple|iphone 14 pro|256gb",
                "smartphone",
                "Apple",
                "iPhone 14 Pro",
                "256GB",
                18000000,
                "comparables",
                old_timestamp,
            ),
        )
        conn.commit()

    # Clean up entries older than 90 days
    deleted = temp_cache.cleanup_old_entries(days=90)

    assert deleted == 1

    # Fresh entry should still be there
    result = temp_cache.get(
        category="smartphone",
        brand="Apple",
        model="iPhone 15 Pro",
        variant="256GB",
        source="comparables",
    )
    assert result is not None