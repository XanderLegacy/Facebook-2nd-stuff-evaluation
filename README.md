# Facebook Second-Hand Post Evaluator

A tool that evaluates second-hand sale posts (originally from Facebook Marketplace) and rates how good the asking price is on a scale of 1-10.

## ⚠️ Legal Notice

**This tool does NOT scrape Facebook or log into any accounts.** It evaluates user-provided data only (pasted caption + uploaded photos). Using automated scraping or bots violates Facebook's Terms of Service and can result in account bans. Always respect platform terms and provide data manually.

## Features

- **Vision-powered extraction**: Uses Claude (Anthropic) to analyze photos and extract product details
- **Vietnamese & English support**: Handles price formats like "14tr5", "14.5 triệu", "14,500,000đ"
- **Intelligent scoring**: Compares asking price to fair market value with condition adjustments
- **Red flag detection**: Identifies suspicious signals (vague details, deposit demands, stock photos only)
- **Confidence levels**: Returns "insufficient data" when reliable pricing is unavailable
- **Configurable rules**: Scoring thresholds in YAML for easy tuning

## Output Example

```
Score: 7.5/10 (Good Deal)

Asking Price: 14,500,000 VND
Fair Price Range: 13,800,000 - 15,200,000 VND (mid: 14,500,000)

Condition: 8/10
  ✓ Screen in good condition
  ✓ Minor scratches on frame
  ⚠ Back has some wear

Caption Signals:
  ✓ Has original box
  ✓ Includes all accessories
  ⚠ No invoice mentioned

Confidence: Medium (5 comparables found)

Explanation: The asking price matches fair market value for this condition.
The phone shows normal wear for its age. Price is reasonable.
```

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Installation

```bash
# Clone the repository
git clone https://github.com/XanderLegacy/Facebook-2nd-stuff-evaluation.git
cd Facebook-2nd-stuff-evaluation

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Usage

#### Command Line Interface

```bash
python -m evaluator.cli \
  --caption "iPhone 14 Pro 256GB, zin all, giá 14tr5" \
  --images photo1.jpg photo2.jpg photo3.jpg

# With manual price override
python -m evaluator.cli \
  --caption "Samsung S23 Ultra" \
  --images phone.jpg \
  --manual-price 18500000
```

#### Web API

```bash
# Start the server
uvicorn evaluator.api:app --reload

# Open browser
http://localhost:8000
```

#### API Endpoints

```bash
# Evaluate a post
curl -X POST http://localhost:8000/evaluate \
  -F "caption=iPhone 14 Pro 256GB, giá 14tr5" \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg"

# Health check
curl http://localhost:8000/health
```

## Project Structure

```
src/evaluator/
  models.py           # Pydantic data models
  extraction.py       # LLM-powered extraction
  scoring.py          # Price scoring logic
  pricing/            # Price provider system
    interface.py      # Abstract base class
    retail.py         # Retail price lookup
    comparable.py     # Used market comparables
    depreciation.py   # Depreciation model
    cache.py          # SQLite price cache
  api.py             # FastAPI application
  cli.py             # Command-line interface

config/
  scoring.yaml       # Scoring rules and thresholds

prompts/
  extraction_system.md  # LLM system prompt

tests/               # Unit tests
docs/                # Architecture & tuning guides
```

## Configuration

Edit `config/scoring.yaml` to tune:
- Price ratio → score mapping
- Condition multipliers
- Red flag penalties
- Bonus adjustments for box, invoice, warranty

See [docs/tuning_guide.md](docs/tuning_guide.md) for detailed tuning instructions.
See [docs/architecture.md](docs/architecture.md) for system design and data flow.

## Limitations

- **External condition only**: Photos show scratches, dents, screen condition. Cannot assess battery health, internal components, or water damage.
- **No authenticity verification**: Cannot verify if items are genuine or counterfeit.
- **Category support**: Currently optimized for smartphones; other categories may have limited reference data.
- **Market coverage**: Price comparables depend on cached data and may be limited initially.
- **Language**: Best results with Vietnamese or English captions.

## Development

```bash
# Run tests
pytest -v

# Lint code
ruff check .

# Format code
ruff format .
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please open an issue first to discuss major changes.

---

**Remember:** This tool provides estimates only. Always inspect items in person and verify condition before purchasing.