"""FastAPI application for the evaluator."""

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .cli import evaluate_post
from .models import EvaluationResult
from .pricing.comparable import ComparableProvider

app = FastAPI(
    title="Facebook Second-Hand Post Evaluator",
    description="Evaluate second-hand sale posts and rate pricing quality",
    version="0.1.0",
)

# CORS middleware for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if they exist
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """Serve the web UI."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Facebook Second-Hand Post Evaluator API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "evaluator"}


@app.post("/evaluate", response_model=EvaluationResult)
async def evaluate(
    caption: str = Form(..., description="Post caption text"),
    images: list[UploadFile] = File(..., description="1-8 images of the item"),
    manual_price: Optional[int] = Form(None, description="Manual price override in VND"),
):
    """Evaluate a second-hand post.

    Args:
        caption: Post caption text
        images: Uploaded images (1-8)
        manual_price: Optional manual price override

    Returns:
        EvaluationResult with score and analysis
    """
    # Validate image count
    if not images or len(images) > 8:
        raise HTTPException(
            status_code=400, detail="Must provide between 1 and 8 images"
        )

    # Save uploaded images to temp files
    temp_files = []
    temp_paths = []

    try:
        for image in images:
            # Create temp file
            suffix = Path(image.filename or "image.jpg").suffix
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_files.append(temp_file)

            # Write image content
            content = await image.read()
            temp_file.write(content)
            temp_file.close()

            temp_paths.append(temp_file.name)

        # Evaluate
        result = evaluate_post(caption, temp_paths, manual_price)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


@app.post("/cache/seed")
async def seed_cache(
    category: str = Form(...),
    brand: str = Form(...),
    model: str = Form(...),
    variant: Optional[str] = Form(None),
    price: int = Form(...),
    notes: Optional[str] = Form(None),
):
    """Manually add a comparable price to the cache.

    This is an admin endpoint for seeding the price database.

    Args:
        category: Product category
        brand: Brand name
        model: Model name
        variant: Optional variant (storage, color, etc)
        price: Price in VND
        notes: Optional notes

    Returns:
        Success message
    """
    try:
        provider = ComparableProvider()
        provider.add_comparable(
            category=category,
            brand=brand,
            model=model,
            variant=variant,
            price=price,
            notes=notes,
        )

        return {
            "status": "success",
            "message": f"Added comparable for {brand} {model}",
            "price": price,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add comparable: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run(app, host=host, port=port)