# Architecture Overview

## System Design

The Facebook Second-Hand Post Evaluator is a multi-stage pipeline that analyzes posts and produces a pricing quality score (1-10).

## Data Flow

```
User Input (Caption + Images + Optional Manual Price)
    ↓
Extraction Stage (LLM Vision)
    ↓
├─ ProductInfo (brand, model, variant, asking_price, etc.)
├─ ConditionAssessment (score 0-10, defects, photo quality)
└─ CaptionSignals (red flags, positive signals, accessories)
    ↓
Price Reference Stage (Provider Chain)
    ↓
├─ ComparableProvider (priority 10) → SQLite cache
├─ RetailProvider (priority 50) → hardcoded retail prices
└─ DepreciationProvider (priority 90) → age-based depreciation
    ↓
Scoring Stage
    ↓
├─ Fair Price Calculation (reference × condition multiplier)
├─ Ratio Score (asking / fair → 1-10 via config thresholds)
├─ Adjustments (red flags, missing info, bonuses)
└─ Confidence Determination
    ↓
Output (EvaluationResult JSON + Explanation)
```

## Core Components

### 1. Extraction (`extraction.py`)

Uses Claude (Anthropic API) with vision capabilities to extract structured data from caption text and images.

**Input:**
- Caption text (Vietnamese or English)
- 1-8 images
- Optional manual price override

**Output (Pydantic models):**
- `ProductInfo`: brand, model, variant, category, asking_price, currency, age_of_item, warranty, accessories, etc.
- `ConditionAssessment`: condition_score (0-10), visible_defects, photo_count, looks_like_real_photos, positive_observations
- `CaptionSignals`: red_flags, positive_signals

**Key Features:**
- Parses Vietnamese price formats: "14tr5" → 14,500,000 VND
- Detects red flags: "ib giá" (DM for price), deposit demands, pressure tactics
- Returns `null` for unknown fields instead of guessing
- Describes only visible condition (never claims to know battery health or internals)
- Per-field confidence scores

### 2. Price Providers (`pricing/`)

**Provider Interface:**
```python
class PriceProvider(ABC):
    @abstractmethod
    def get_reference_price(product: ProductInfo) -> Optional[PriceReference]
    
    @property
    @abstractmethod
    def priority(self) -> int  # Lower = higher priority
```

**Provider Chain (by priority):**

1. **ComparableProvider (priority 10)** - Highest priority
   - Queries SQLite cache for recent comparable listings (TTL: 7 days)
   - Requires minimum 3 comparables
   - Returns median price
   - Confidence: HIGH (10+ comparables), MEDIUM (5-9), LOW (3-4)

2. **RetailProvider (priority 50)** - Medium priority
   - Hardcoded retail prices for common smartphones (iPhone 13-15, Samsung S23-S24)
   - Case-insensitive matching on brand/model/variant
   - Extracts storage size from variant strings
   - Returns `None` for unknown products

3. **DepreciationProvider (priority 90)** - Fallback
   - Estimates price from retail × age-based depreciation curve
   - Depreciation curve:
     - 0-6 months: 85%
     - 6-12 months: 75%
     - 12-18 months: 65%
     - 18-24 months: 55%
     - 24-36 months: 45%
     - 36-48 months: 35%
     - 48+ months: 25%
   - Parses age from text: "6 months", "2 năm", "2023"
   - Returns `None` if no retail price available

**SQLite Cache (`cache.py`):**
- Schema: `prices(product_key, category, brand, model, variant, price, source, comparable_count, timestamp, notes)`
- Product key: normalized `category|brand|model|variant`
- TTL enforcement on reads
- `find_comparables()` for median calculation
- `cleanup_old_entries(days)` for maintenance

### 3. Scoring (`scoring.py`)

**Fair Price Calculation:**
```python
fair_price = reference_price × condition_multiplier × bonuses
```

**Condition Multipliers (from `config/scoring.yaml`):**
- Condition 10: 1.10 (mint, premium)
- Condition 8: 1.00 (good used)
- Condition 5: 0.85
- Condition 1: 0.50 (heavily damaged)

**Score Calculation:**
```python
ratio = asking_price / fair_price
base_score = interpolate(ratio, thresholds)  # From config
adjusted_score = base_score + penalties + bonuses
final_score = clamp(adjusted_score, 1.0, 10.0)
```

**Ratio → Score Mapping (configurable):**
- ratio 0.5 → score 9.5 (suspiciously cheap, add warning)
- ratio 0.7 → score 9.0
- ratio 1.0 → score 7.0 (at fair price)
- ratio 1.3 → score 3.0
- ratio 2.0 → score 1.0

**Adjustments:**
- Red flags: -0.5 to -1.5 per flag
- Missing info: -0.3 to -1.5
- Bonuses: +0.2 to +0.5 (box, invoice, warranty, accessories)

**Confidence Determination:**
- HIGH: retail/comparables with 10+ samples, no extraction uncertainties
- MEDIUM: retail/comparables with 5-9 samples, minor uncertainties
- LOW: depreciation fallback, few comparables, uncertain product match
- Returns "insufficient_data" flag when no reference price available

### 4. API & CLI

**CLI (`cli.py`):**
```bash
python -m evaluator.cli \
  --caption "iPhone 14 Pro 256GB, giá 18tr5" \
  --images photo1.jpg photo2.jpg \
  --manual-price 18500000 \
  --json  # Optional: output JSON instead of formatted text
```

**FastAPI (`api.py`):**
- `POST /evaluate` - Multipart form: caption, images (files), manual_price (optional)
- `GET /health` - Health check
- `POST /cache/seed` - Admin: manually add comparable prices
- `GET /` - Serves web UI

**Web UI (`static/index.html`):**
- Single-page app with dark tonal design
- Paste caption, upload images (drag-drop), optional manual price
- Displays score, fair price range, condition, red flags, explanation
- Responsive grid layout

## Configuration

**`config/scoring.yaml`:**
- `ratio_to_score`: thresholds mapping ratio → score
- `condition_multipliers`: condition score → price multiplier
- `adjustments`: penalties and bonuses
- `confidence_rules`: rules for determining confidence level

All scoring logic is config-driven for easy tuning.

## Security & Constraints

1. **No Facebook Scraping:** Tool accepts user-provided input only (pasted caption + uploaded images). Never logs into Facebook or scrapes content.

2. **No Secrets in Git:** All API keys via environment variables (`.env`). `.gitignore` excludes `.env`, `*.db`, `uploads/`, `__pycache__/`.

3. **External Condition Only:** Images show only external appearance. Tool never claims to know battery health, internal faults, or authenticity.

4. **Insufficient Data Handling:** Returns `insufficient_data` flag and LOW confidence when no reference price available, rather than guessing.

## Extensibility

### Adding New Product Categories

1. Add retail prices to `RetailProvider.RETAIL_PRICES`
2. Seed comparable cache via `POST /cache/seed` or directly in SQLite
3. Update extraction prompt if category-specific signals needed

### Adding New Price Sources

Implement `PriceProvider` interface:

```python
class ShopeeAPIProvider(PriceProvider):
    @property
    def priority(self) -> int:
        return 20  # Between comparables and retail
    
    def get_reference_price(self, product: ProductInfo) -> Optional[PriceReference]:
        # Call Shopee API, return median of used listings
        pass
```

Add to provider chain in `cli.py` and `api.py`.

### Tuning Scoring Rules

Edit `config/scoring.yaml`:
- Adjust ratio thresholds to make scoring more/less strict
- Modify condition multipliers to change condition impact
- Add/remove red flag penalties
- Change confidence rules

No code changes required.

## Testing Strategy

- **Unit tests:** Mock LLM responses, test Vietnamese price parsing, red flag detection
- **Scoring tests:** Edge cases (too cheap, too expensive, missing price, insufficient data)
- **Pricing tests:** Cache operations, provider priority, depreciation curve
- Run: `pytest -v`
- Lint: `ruff check . && ruff format --check .`

## Deployment

**Development:**
```bash
uvicorn evaluator.api:app --reload
```

**Production:**
```bash
uvicorn evaluator.api:app --host 0.0.0.0 --port 8000 --workers 4
```

Environment variables:
- `ANTHROPIC_API_KEY` (required)
- `CLAUDE_MODEL` (default: claude-3-5-sonnet-20241022)
- `PRICE_CACHE_DB` (default: price_cache.db)
- `API_HOST`, `API_PORT`