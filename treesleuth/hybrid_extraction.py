"""
Hybrid OCR/HTR + VLM pipeline for historical document transcription.

Three-stage architecture:
1. Row Segmentation: Detect individual rows in page images using contours
2. Line-Level HTR: Extract raw text from each row using Hugging Face transformers
3. VLM Refinement: Clean and structure HTR output with semantic understanding
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class RowSegment:
    """A single row crop from a page image."""
    image: Image.Image
    row_index: int
    y_top: int
    y_bottom: int
    raw_htr_text: Optional[str] = None
    structured_data: Optional[dict] = None


@dataclass
class HybridExtractionResult:
    """Result from hybrid extraction pipeline."""
    page_image_path: Path
    rows: list[RowSegment]
    raw_full_page_text: str
    structured_rows: list[dict]
    metadata: dict


def detect_rows_by_horizontal_lines(
    image: Image.Image,
    threshold: int = 200,
    min_row_height: int = 20,
    vertical_padding_percent: float = 0.12,
) -> list[tuple[int, int]]:
    """
    Detect horizontal text lines/rows using edge detection and contour analysis.

    Args:
        image: PIL Image (RGB or grayscale)
        threshold: Binary threshold for edge detection (0-255)
        min_row_height: Minimum height in pixels to consider a row
        vertical_padding_percent: Padding as % of detected row height (e.g., 0.12 = 12%)

    Returns:
        List of (y_top, y_bottom) tuples with padding applied
    """
    import cv2

    # Convert PIL to OpenCV format
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    # Invert for contour detection (text is dark on light background)
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    # Detect horizontal lines using morphological operations
    kernel_horizontal = cv2.getStructuringElement(cv2.MORPH_RECT, (image.width // 4, 1))
    horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_horizontal, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Extract bounding boxes for each row
    rows = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h >= min_row_height:
            rows.append((y, h))

    # Sort by y position (top to bottom)
    rows.sort(key=lambda r: r[0])

    # Apply vertical padding to prevent clipping ascenders/descenders
    padded_rows = []
    for y_top, height in rows:
        padding = max(1, int(height * vertical_padding_percent))
        y_top_padded = max(0, y_top - padding)
        y_bottom_padded = min(image.height, y_top + height + padding)
        padded_rows.append((y_top_padded, y_bottom_padded))

    logger.debug(f"Detected {len(padded_rows)} rows in image")
    return padded_rows


def segment_rows(
    image: Image.Image,
    row_bounds: list[tuple[int, int]],
) -> list[RowSegment]:
    """
    Crop image into individual row segments.

    Args:
        image: PIL Image
        row_bounds: List of (y_top, y_bottom) tuples from detect_rows_by_horizontal_lines

    Returns:
        List of RowSegment objects with cropped images
    """
    segments = []
    for idx, (y_top, y_bottom) in enumerate(row_bounds):
        row_image = image.crop((0, y_top, image.width, y_bottom))
        segment = RowSegment(
            image=row_image,
            row_index=idx,
            y_top=y_top,
            y_bottom=y_bottom,
        )
        segments.append(segment)
    return segments


def extract_htr_text(
    row_segment: RowSegment,
    model_name: str = "microsoft/trocr-large-handwritten",
    device: str = "cuda",
) -> str:
    """
    Extract raw text from a single row using Hugging Face HTR model.

    Args:
        row_segment: RowSegment with image crop
        model_name: HF model ID (trocr-large-handwritten, surya-ocr, etc.)
        device: "cuda" or "cpu"

    Returns:
        Raw HTR text output
    """
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    try:
        processor = TrOCRProcessor.from_pretrained(model_name)
        model = VisionEncoderDecoderModel.from_pretrained(model_name).to(device)

        # Prepare image
        pixel_values = processor(images=row_segment.image, return_tensors="pt").pixel_values.to(device)

        # Generate text
        generated_ids = model.generate(pixel_values, max_length=500)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        logger.debug(f"Row {row_segment.row_index} HTR: {text[:100]}...")
        return text.strip()

    except Exception as exc:
        logger.exception(f"HTR failed for row {row_segment.row_index}: {exc}")
        return "[HTR FAILED]"


def batch_extract_htr(
    row_segments: list[RowSegment],
    model_name: str = "microsoft/trocr-large-handwritten",
    device: str = "cuda",
) -> list[RowSegment]:
    """
    Extract HTR text for all row segments.

    Args:
        row_segments: List of RowSegment objects
        model_name: HF model ID
        device: "cuda" or "cpu"

    Returns:
        Updated RowSegment list with raw_htr_text populated
    """
    for segment in row_segments:
        segment.raw_htr_text = extract_htr_text(segment, model_name=model_name, device=device)
    return row_segments


def refine_htr_with_vlm(
    row_segment: RowSegment,
    target_schema: Optional[dict] = None,
    vlm_client: Optional[Any] = None,
    vlm_model: str = "qwen2.5vl",
    context_rows: Optional[list[RowSegment]] = None,
) -> dict:
    """
    Refine HTR output using VLM for semantic understanding and structuring.

    Args:
        row_segment: RowSegment with image and raw_htr_text
        target_schema: Dict of field names (e.g., {"Name": str, "Age": int, "Occupation": str})
        vlm_client: Ollama/OpenRouter client (should have .chat() method)
        vlm_model: Model name to use
        context_rows: Previous rows for ditto mark expansion context

    Returns:
        Dict with keys:
            - raw_htr_input: Original HTR text
            - structured_fields: Cleaned/expanded fields matching target_schema
            - flags: Dict with metadata (ditto_expanded, confidence, etc.)
    """
    import base64
    from io import BytesIO

    if not row_segment.raw_htr_text:
        return {
            "raw_htr_input": "[NO HTR TEXT]",
            "structured_fields": {},
            "flags": {"error": "missing_htr_text"},
        }

    # Convert PIL image to base64 for VLM
    buffer = BytesIO()
    row_segment.image.save(buffer, format="JPEG", quality=85)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # Build schema description
    schema_desc = ""
    if target_schema:
        schema_desc = "Expected fields: " + ", ".join(target_schema.keys())
    else:
        schema_desc = "Extract key-value pairs from the row text and image."

    # Build context for ditto mark expansion
    ditto_context = ""
    if context_rows:
        recent_rows = context_rows[-3:]  # Look back 3 rows for ditto context
        ditto_context = "\n\nContext for ditto mark expansion (last few rows):\n"
        for prev_row in recent_rows:
            if prev_row.structured_data:
                ditto_context += json.dumps(prev_row.structured_data.get("structured_fields", {})) + "\n"

    prompt = f"""You are transcribing a row from a historical census, register, or similar document.

Raw HTR (Handwritten Text Recognition) output:
"{row_segment.raw_htr_text}"

Visual content: Row {row_segment.row_index} from the document image shown above.

{schema_desc}

INSTRUCTIONS:
1. Clean obvious OCR character glitches (e.g., "l" vs "1", "O" vs "0") by comparing HTR output with the image.
2. PRESERVE rare or archaic surnames/spellings as HTR transcribed them unless the image clearly shows an error.
3. Detect and expand ditto marks (" or "do" or similar) by checking context from previous rows.{ditto_context}
4. Return ONLY valid JSON (no markdown, no explanation) with these keys:
   - "raw_htr_input": The original HTR text
   - "structured_fields": Object with cleaned/extracted fields from schema
   - "flags": Object with metadata:
     * "ditto_expanded": bool - whether any ditto marks were expanded
     * "confidence": float (0.0-1.0) - confidence in transcription
     * "issues": list of noted problems (e.g., ["illegible_section", "unusual_character"])

Example output:
{{"raw_htr_input": "Arthur Astle 40 Married", "structured_fields": {{"Name": "Arthur Astle", "Age": 40, "Status": "Married"}}, "flags": {{"ditto_expanded": false, "confidence": 0.92, "issues": []}}}}
"""

    try:
        if vlm_client is None:
            from ollama import Client
            vlm_client = Client()

        response = vlm_client.chat(
            model=vlm_model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            options={"temperature": 0, "num_ctx": 2048},
        )

        response_text = response["message"]["content"].strip()

        # Parse JSON response
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(f"VLM returned non-JSON for row {row_segment.row_index}: {response_text}")
            result = {
                "raw_htr_input": row_segment.raw_htr_text,
                "structured_fields": {},
                "flags": {"error": "vlm_response_not_json"},
            }

        row_segment.structured_data = result
        return result

    except Exception as exc:
        logger.exception(f"VLM refinement failed for row {row_segment.row_index}: {exc}")
        return {
            "raw_htr_input": row_segment.raw_htr_text,
            "structured_fields": {},
            "flags": {"error": str(exc)},
        }


def batch_refine_htr_with_vlm(
    row_segments: list[RowSegment],
    target_schema: Optional[dict] = None,
    vlm_client: Optional[Any] = None,
    vlm_model: str = "qwen2.5vl",
) -> list[RowSegment]:
    """
    Refine all row segments with context-aware ditto mark expansion.

    Args:
        row_segments: List of RowSegment with raw_htr_text populated
        target_schema: Column schema dict
        vlm_client: Ollama/OpenRouter client
        vlm_model: Model name

    Returns:
        Updated RowSegment list with structured_data populated
    """
    for idx, segment in enumerate(row_segments):
        # Pass previous rows as context for ditto mark expansion
        context_rows = row_segments[max(0, idx - 3) : idx]
        refine_htr_with_vlm(
            segment,
            target_schema=target_schema,
            vlm_client=vlm_client,
            vlm_model=vlm_model,
            context_rows=context_rows,
        )
    return row_segments


def run_hybrid_extraction_pipeline(
    image_path: Path,
    target_schema: Optional[dict] = None,
    vlm_client: Optional[Any] = None,
    vlm_model: str = "qwen2.5vl",
    htr_model: str = "microsoft/trocr-large-handwritten",
    device: str = "cuda",
    row_detection_threshold: int = 200,
    min_row_height: int = 20,
) -> HybridExtractionResult:
    """
    Execute full hybrid pipeline: row segmentation → HTR → VLM refinement.

    Args:
        image_path: Path to document image
        target_schema: Column schema (e.g., {"Name": str, "Age": int, ...})
        vlm_client: Ollama/OpenRouter client
        vlm_model: VLM model name
        htr_model: HTR model name
        device: "cuda" or "cpu"
        row_detection_threshold: For contour detection
        min_row_height: Minimum row height in pixels

    Returns:
        HybridExtractionResult with all rows and metadata
    """
    logger.info(f"Starting hybrid extraction pipeline for {image_path.name}")

    # Load image
    image = Image.open(image_path).convert("RGB")

    # Stage 1: Row Segmentation
    logger.info("Stage 1: Detecting row boundaries...")
    row_bounds = detect_rows_by_horizontal_lines(
        image,
        threshold=row_detection_threshold,
        min_row_height=min_row_height,
    )
    row_segments = segment_rows(image, row_bounds)
    logger.info(f"Segmented into {len(row_segments)} rows")

    # Stage 2: HTR
    logger.info("Stage 2: Extracting text with HTR...")
    row_segments = batch_extract_htr(row_segments, model_name=htr_model, device=device)

    # Stage 3: VLM Refinement
    logger.info("Stage 3: Refining with VLM...")
    row_segments = batch_refine_htr_with_vlm(
        row_segments,
        target_schema=target_schema,
        vlm_client=vlm_client,
        vlm_model=vlm_model,
    )

    # Compile results
    raw_full_page_text = "\n".join(seg.raw_htr_text or "[FAILED]" for seg in row_segments)
    structured_rows = [seg.structured_data or {} for seg in row_segments]

    result = HybridExtractionResult(
        page_image_path=image_path,
        rows=row_segments,
        raw_full_page_text=raw_full_page_text,
        structured_rows=structured_rows,
        metadata={
            "total_rows": len(row_segments),
            "htr_model": htr_model,
            "vlm_model": vlm_model,
            "target_schema": target_schema,
        },
    )

    logger.info(f"Hybrid extraction complete: {len(row_segments)} rows processed")
    return result
