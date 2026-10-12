"""SQLite cache for price data."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class PriceCache:
    """SQLite-based cache for price data."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize price cache.

        Args:
            db_path: Path to SQLite database (defaults to PRICE_CACHE_DB env var)
        """
        if db_path is None:
            db_path = os.getenv("PRICE_CACHE_DB", "price_cache.db")

        self.db_path = Path(db_path)
        self._initialize_db()

    def _initialize_db(self):
        """Create database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    brand TEXT,
                    model TEXT,
                    variant TEXT,
                    price INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    comparable_count INTEGER DEFAULT 1,
                    timestamp DATETIME NOT NULL,
                    notes TEXT,
                    UNIQUE(product_key, source)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_product_key 
                ON prices(product_key)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_category 
                ON prices(category, brand, model)
                """
            )
            conn.commit()

    def _make_product_key(
        self, category: str, brand: Optional[str], model: Optional[str], variant: Optional[str]
    ) -> str:
        """Create a normalized product key.

        Args:
            category: Product category
            brand: Brand name
            model: Model name
            variant: Variant (storage, color, etc)

        Returns:
            Normalized key string
        """
        parts = [category.lower() if category else "unknown"]
        if brand:
            parts.append(brand.lower())
        if model:
            parts.append(model.lower())
        if variant:
            parts.append(variant.lower())
        return "|".join(parts)

    def get(
        self,
        category: str,
        brand: Optional[str],
        model: Optional[str],
        variant: Optional[str],
        source: str,
        ttl_days: int = 7,
    ) -> Optional[dict]:
        """Get cached price data.

        Args:
            category: Product category
            brand: Brand name
            model: Model name
            variant: Variant
            source: Price source (retail, comparables, depreciation)
            ttl_days: Time-to-live in days (default 7)

        Returns:
            Dict with price data if found and not expired, None otherwise
        """
        product_key = self._make_product_key(category, brand, model, variant)
        cutoff = datetime.now() - timedelta(days=ttl_days)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM prices 
                WHERE product_key = ? AND source = ? AND timestamp > ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (product_key, source, cutoff.isoformat()),
            )
            row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def set(
        self,
        category: str,
        brand: Optional[str],
        model: Optional[str],
        variant: Optional[str],
        price: int,
        source: str,
        comparable_count: int = 1,
        notes: Optional[str] = None,
    ):
        """Store or update price data.

        Args:
            category: Product category
            brand: Brand name
            model: Model name
            variant: Variant
            price: Price in VND
            source: Price source
            comparable_count: Number of comparables (for median calculations)
            notes: Optional notes
        """
        product_key = self._make_product_key(category, brand, model, variant)
        timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO prices 
                (product_key, category, brand, model, variant, price, source, 
                 comparable_count, timestamp, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_key,
                    category,
                    brand,
                    model,
                    variant,
                    price,
                    source,
                    comparable_count,
                    timestamp,
                    notes,
                ),
            )
            conn.commit()

    def find_comparables(
        self, category: str, brand: Optional[str], model: Optional[str], ttl_days: int = 7
    ) -> list[dict]:
        """Find comparable prices for a product.

        Args:
            category: Product category
            brand: Brand name
            model: Model name
            ttl_days: Time-to-live in days

        Returns:
            List of comparable price records
        """
        cutoff = datetime.now() - timedelta(days=ttl_days)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM prices 
                WHERE category = ? AND brand = ? AND model = ? 
                  AND source = 'comparables' AND timestamp > ?
                ORDER BY timestamp DESC
                """,
                (category, brand, model, cutoff.isoformat()),
            )
            rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def cleanup_old_entries(self, days: int = 90):
        """Remove entries older than specified days.

        Args:
            days: Remove entries older than this many days
        """
        cutoff = datetime.now() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM prices WHERE timestamp < ?", (cutoff.isoformat(),)
            )
            deleted = cursor.rowcount
            conn.commit()

        return deleted