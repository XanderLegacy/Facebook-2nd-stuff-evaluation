# Scoring Configuration Tuning Guide

This guide explains how to adjust the scoring rules without modifying code.

## Configuration File

All scoring rules are in `config/scoring.yaml`. Edit this file to tune the evaluation behavior.

## Ratio-to-Score Mapping

Controls how the asking price vs fair price ratio translates to a score.

```yaml
ratio_to_score:
  - ratio: 0.5   # Asking price is 50% of fair price
    score: 9.5
    warning: "Suspiciously cheap - possible scam or hidden defects"
  - ratio: 1.0   # Asking price equals fair price
    score: 7.0
  - ratio: 1.5   # Asking price is 150% of fair price
    score: 2.0
```

**How to tune:**
- Add more thresholds for finer control
- Lower the score at ratio 1.0 to make "fair price" less attractive
- Adjust warnings for very low ratios
- The system interpolates between thresholds

**Example adjustment (more strict):**
```yaml
  - ratio: 1.0
    score: 6.5  # Was 7.0, now fair price = slightly lower score
```

## Condition Multipliers

Controls how condition affects the fair price calculation.

```yaml
condition_multipliers:
  10: 1.10  # Mint condition = 110% of reference price
  8: 1.00   # Good condition = 100% (baseline)
  5: 0.85   # Moderate damage = 85%
  1: 0.50   # Heavy damage = 50%
```

**How to tune:**
- Increase multipliers if you think condition should have more impact
- Decrease if condition seems to dominate scoring too much
- Ensure multipliers decrease as condition worsens

**Example adjustment (more condition-sensitive):**
```yaml
condition_multipliers:
  10: 1.20  # Was 1.10, mint now worth even more
  8: 1.00
  5: 0.75   # Was 0.85, moderate damage now more penalized
  1: 0.40   # Was 0.50, heavy damage more penalized
```

## Adjustments (Penalties and Bonuses)

Fine-tune score adjustments for specific signals.

### Red Flag Penalties

```yaml
adjustments:
  red_flags:
    ib_gia: -0.5            # "DM for price"
    deposit_required: -1.0   # Demands deposit
    stock_photos_only: -1.5  # No real photos
```

**How to tune:**
- Make penalties more severe (more negative) if red flags are too lightly treated
- Reduce penalties if they're dominating scores too much
- Add new red flags detected by the extraction stage

### Missing Info Penalties

```yaml
  missing_info:
    few_photos: -0.3        # Less than 3 photos
    no_real_photos: -1.5    # Stock images only
    unclear_product: -0.8   # Can't identify model
```

### Bonuses

```yaml
  bonuses:
    has_box: 0.2
    has_invoice: 0.3
    warranty_remaining: 0.5
    full_accessories: 0.2
```

**How to tune:**
- Increase bonuses if having documentation should be more valuable
- Decrease if bonuses seem excessive

## Confidence Rules

Controls when the system reports HIGH/MEDIUM/LOW confidence.

```yaml
confidence_rules:
  high:
    min_comparables: 10
    min_photo_count: 4
    requires_real_photos: true
    max_red_flags: 0
  
  medium:
    min_comparables: 3
    min_photo_count: 2
    requires_real_photos: true
    max_red_flags: 1
```

**How to tune:**
- Increase `min_comparables` if you want stricter confidence levels
- Adjust `min_photo_count` based on your quality standards
- Modify `max_red_flags` tolerance

## Depreciation Curve

Controls the fallback age-based pricing when no comparables exist.

```yaml
depreciation_curve:
  0_to_6_months: 0.85    # 85% of retail
  6_to_12_months: 0.75   # 75% of retail
  12_to_18_months: 0.65
  18_to_24_months: 0.55
  24_to_36_months: 0.45
  36_to_48_months: 0.35
  over_48_months: 0.25
```

**How to tune:**
- Adjust values based on your market (tech depreciates faster in some regions)
- Make depreciation more aggressive (lower values) or less (higher values)
- Add more granular age brackets if needed

## Seeding the Price Cache

To improve accuracy, seed the comparable price cache with real market data.

### Method 1: API Endpoint

```bash
curl -X POST http://localhost:8000/cache/seed \
  -F "category=smartphone" \
  -F "brand=Apple" \
  -F "model=iPhone 14 Pro" \
  -F "variant=256GB" \
  -F "price=18500000" \
  -F "notes=Facebook Marketplace listing, good condition"
```

### Method 2: Direct SQLite

```python
from evaluator.pricing.comparable import ComparableProvider

provider = ComparableProvider()

# Add multiple comparables
comparables = [
    ("smartphone", "Apple", "iPhone 14 Pro", "256GB", 18000000),
    ("smartphone", "Apple", "iPhone 14 Pro", "256GB", 18500000),
    ("smartphone", "Apple", "iPhone 14 Pro", "256GB", 19000000),
]

for category, brand, model, variant, price in comparables:
    provider.add_comparable(category, brand, model, variant, price)
```

### Method 3: Bulk Import Script

Create `scripts/seed_prices.py`:

```python
import csv
from evaluator.pricing.comparable import ComparableProvider

provider = ComparableProvider()

with open("prices.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        provider.add_comparable(
            category=row["category"],
            brand=row["brand"],
            model=row["model"],
            variant=row.get("variant"),
            price=int(row["price"]),
            notes=row.get("notes")
        )
```

CSV format:
```csv
category,brand,model,variant,price,notes
smartphone,Apple,iPhone 14 Pro,256GB,18500000,Good condition
smartphone,Samsung,Galaxy S23 Ultra,256GB,19000000,Excellent
```

## Testing Configuration Changes

After modifying `scoring.yaml`:

1. **Validate YAML syntax:**
```bash
python -c "import yaml; yaml.safe_load(open('config/scoring.yaml'))"
```

2. **Run unit tests:**
```bash
pytest tests/test_scoring.py -v
```

3. **Test with sample data:**
```bash
python -m evaluator.cli \
  --caption "iPhone 14 Pro 256GB, giá 18tr5" \
  --images sample.jpg
```

4. **Compare before/after scores** with the same input to verify changes.

## Common Tuning Scenarios

### "Scores are too generous"

- Lower the score at ratio 1.0 (e.g., 7.0 → 6.5)
- Increase red flag penalties
- Increase missing info penalties
- Require more comparables for HIGH confidence

### "Scores are too harsh"

- Raise the score at ratio 1.0 (e.g., 7.0 → 7.5)
- Decrease red flag penalties
- Increase bonuses for documentation

### "Condition doesn't matter enough"

- Increase the spread in condition_multipliers
- Example: condition 10 = 1.20 (was 1.10), condition 1 = 0.40 (was 0.50)

### "Too many 'insufficient data' results"

- Lower `min_comparables` in ComparableProvider (default 3)
- Add more retail prices to RetailProvider
- Seed the comparable cache with market data
- Adjust depreciation curve to be more lenient

### "Red flags don't impact score enough"

- Increase penalties: `ib_gia: -1.0` (was -0.5)
- Add cumulative effect (already happens automatically)

## Best Practices

1. **Document changes:** Add comments in YAML explaining why you changed values
2. **Test incrementally:** Change one section at a time
3. **Keep backups:** Copy `scoring.yaml` before major changes
4. **Validate with real data:** Test with actual marketplace posts
5. **Monitor edge cases:** Very cheap, very expensive, missing data scenarios
6. **Gather feedback:** Adjust based on user reports of over/under-scoring

## Rollback

If changes cause problems:

```bash
git checkout config/scoring.yaml
```

Or restore from backup:
```bash
cp config/scoring.yaml.backup config/scoring.yaml
```