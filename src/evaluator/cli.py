"""Command-line interface for the evaluator."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .extraction import extract_from_post
from .models import ConfidenceLevel, EvaluationResult
from .pricing.comparable import ComparableProvider
from .pricing.depreciation import DepreciationProvider
from .pricing.retail import RetailProvider
from .scoring import Scorer


def format_price(price: Optional[int]) -> str:
    """Format price in VND with thousands separators.

    Args:
        price: Price in VND

    Returns:
        Formatted price string
    """
    if price is None:
        return "N/A"
    return f"{price:,} VND".replace(",", ".")


def print_colored(text: str, color: str = "reset"):
    """Print colored text (basic ANSI colors).

    Args:
        text: Text to print
        color: Color name (green, yellow, red, cyan, reset)
    """
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


def print_result(result: EvaluationResult):
    """Print evaluation result in a readable format.

    Args:
        result: Evaluation result to display
    """
    print("\n" + "=" * 70)
    print_colored(f"EVALUATION RESULT", "bold")
    print("=" * 70 + "\n")

    # Score
    score_color = "green" if result.score >= 7 else "yellow" if result.score >= 5 else "red"
    print_colored(f"Score: {result.score}/10", score_color)

    # Rating label
    if result.score >= 8:
        rating = "Excellent Deal"
    elif result.score >= 7:
        rating = "Good Deal"
    elif result.score >= 5:
        rating = "Fair Price"
    elif result.score >= 3:
        rating = "Overpriced"
    else:
        rating = "Poor Deal"
    print(f"Rating: {rating}\n")

    # Insufficient data warning
    if result.insufficient_data:
        print_colored("⚠ INSUFFICIENT DATA - Score may be unreliable\n", "yellow")

    # Price information
    print_colored("PRICE ANALYSIS:", "cyan")
    print(f"  Asking Price: {format_price(result.asking_price)}")

    if result.fair_price_range:
        fp = result.fair_price_range
        print(f"  Fair Price Range:")
        print(f"    Low:  {format_price(fp.low)}")
        print(f"    Mid:  {format_price(fp.mid)}")
        print(f"    High: {format_price(fp.high)}")
        print(f"  Price Source: {fp.reference.source.value}")
        if fp.reference.comparable_count > 0:
            print(f"  Comparables: {fp.reference.comparable_count}")
    print()

    # Condition
    print_colored("CONDITION ASSESSMENT:", "cyan")
    print(f"  Condition Score: {result.condition.condition_score}/10")
    print(f"  Photos: {result.condition.photo_count}")
    print(f"  Real Photos: {'Yes' if result.condition.looks_like_real_photos else 'No'}")

    if result.condition.positive_observations:
        print(f"  Positive:")
        for obs in result.condition.positive_observations:
            print(f"    ✓ {obs}")

    if result.condition.visible_defects:
        print(f"  Defects:")
        for defect in result.condition.visible_defects:
            print(f"    ⚠ {defect}")
    print()

    # Caption signals
    print_colored("CAPTION ANALYSIS:", "cyan")
    if result.caption_signals.positive_signals:
        print("  Positive Signals:")
        for signal in result.caption_signals.positive_signals:
            print(f"    ✓ {signal}")

    if result.caption_signals.red_flags:
        print_colored("  Red Flags:", "red")
        for flag in result.caption_signals.red_flags:
            print_colored(f"    ⚠ {flag}", "red")
    print()

    # Confidence and warnings
    conf_color = "green" if result.confidence == ConfidenceLevel.HIGH else "yellow"
    print(f"Confidence: ", end="")
    print_colored(result.confidence.value.upper(), conf_color)

    if result.warnings:
        print_colored("\nWARNINGS:", "yellow")
        for warning in result.warnings:
            print_colored(f"  ⚠ {warning}", "yellow")

    # Explanation
    print(f"\n{result.explanation}")

    print("\n" + "=" * 70 + "\n")


def evaluate_post(
    caption: str, image_paths: list[str], manual_price: Optional[int] = None
) -> EvaluationResult:
    """Evaluate a post and return the result.

    Args:
        caption: Post caption text
        image_paths: Paths to images
        manual_price: Optional manual price override

    Returns:
        EvaluationResult
    """
    # Extract information
    print("Extracting product information...")
    product, condition, signals = extract_from_post(caption, image_paths, manual_price)

    # Get reference price (try providers in order)
    print("Looking up reference prices...")
    providers = [
        ComparableProvider(),
        RetailProvider(),
        DepreciationProvider(),
    ]

    reference_price = None
    for provider in sorted(providers, key=lambda p: p.priority):
        reference_price = provider.get_reference_price(product)
        if reference_price:
            print(f"Found reference price from: {reference_price.source.value}")
            break

    # Calculate fair price and score
    scorer = Scorer()

    if reference_price and reference_price.value:
        fair_price_range = scorer.calculate_fair_price(reference_price, condition, product)
        score, adjustments, warnings = scorer.calculate_score(
            product.asking_price, fair_price_range, condition, signals, product
        )
        confidence = scorer.determine_confidence(reference_price, condition, signals)
        explanation = scorer.generate_explanation(
            score, product.asking_price, fair_price_range, condition, adjustments
        )
        insufficient_data = False
    else:
        # Insufficient data
        fair_price_range = None
        score = 5.0
        adjustments = {}
        warnings = ["No reference price available - cannot provide accurate scoring"]
        confidence = ConfidenceLevel.LOW
        explanation = (
            "Unable to determine a fair price for this item. "
            "There are no comparable listings and no retail price available. "
            "Please verify the product details and pricing manually."
        )
        insufficient_data = True

    return EvaluationResult(
        score=score,
        asking_price=product.asking_price,
        fair_price_range=fair_price_range,
        product=product,
        condition=condition,
        caption_signals=signals,
        confidence=confidence,
        warnings=warnings,
        explanation=explanation,
        adjustments_applied=adjustments,
        insufficient_data=insufficient_data,
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate second-hand Facebook marketplace posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m evaluator.cli --caption "iPhone 14 Pro 256GB, giá 18tr5" --images photo1.jpg photo2.jpg
  python -m evaluator.cli --caption "Samsung S23 Ultra" --images phone.jpg --manual-price 18500000
        """,
    )

    parser.add_argument("--caption", required=True, help="Post caption text")
    parser.add_argument(
        "--images", nargs="+", required=True, help="Paths to image files (1-8 images)"
    )
    parser.add_argument(
        "--manual-price", type=int, help="Manual price override in VND (integer)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output result as JSON instead of formatted text"
    )

    args = parser.parse_args()

    # Validate images exist
    for img_path in args.images:
        if not Path(img_path).exists():
            print(f"Error: Image file not found: {img_path}", file=sys.stderr)
            sys.exit(1)

    try:
        result = evaluate_post(args.caption, args.images, args.manual_price)

        if args.json:
            # Output as JSON
            print(result.model_dump_json(indent=2))
        else:
            # Output formatted text
            print_result(result)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()