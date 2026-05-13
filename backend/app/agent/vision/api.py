from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agent.vision.schemas import PortfolioImageExtractResponse
from app.agent.vision.adapter import VisionPortfolioExtractor

router = APIRouter(prefix="/api/agent/vision", tags=["agent-vision"])

# Allowed image MIME types
ALLOWED_IMAGE_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
})

_MAX_IMAGE_MB = 20
_MAX_IMAGE_BYTES = _MAX_IMAGE_MB * 1024 * 1024


@router.post("/extract-portfolio", response_model=PortfolioImageExtractResponse)
async def extract_portfolio(
    image: UploadFile = File(...),
    broker_hint: str | None = Form(None),
) -> PortfolioImageExtractResponse:
    """Extract portfolio positions from a broker screenshot.

    Requires a Vision-capable LLM (e.g. gpt-4o) to be configured via
    ``OPENAI_API_KEY``.  The image is validated and immediately passed to
    the extractor; **no image data is persisted or logged**.
    """
    # --- Validate content type ------------------------------------------------
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type '{image.content_type}'. "
            f"Accepted: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}.",
        )

    # --- Read bytes (stream to memory only) -----------------------------------
    image_bytes = await image.read()

    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large ({len(image_bytes) / 1024 / 1024:.1f} MiB). "
            f"Maximum: {_MAX_IMAGE_MB} MiB.",
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    # --- Delegate to extraction adapter ---------------------------------------
    # NOTE: image_bytes is intentionally NOT logged or persisted anywhere.
    extractor = VisionPortfolioExtractor()
    return extractor.extract(image_bytes, broker_hint=broker_hint)
