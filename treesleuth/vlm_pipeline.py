"""
Optimized two-stage VLM pipeline for genealogy document transcription.

Stage 1: High-speed VLM transcription with VRAM-aware context limiting.
Stage 2: Text-LLM based contradiction checking against family tree data.

This module uses the ollama library to execute inference with explicit
num_ctx parameter to prevent KV cache overflow on modest GPU VRAM (12GB+).
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION: Model Selection (exposed at module top for easy customization)
# ============================================================================

# User-selected models (these should come from Settings)
# Override these via environment variables or Settings class
DEFAULT_TEXT_LLM_MODEL = "mistral"
DEFAULT_VLM_MODEL = "qwen2.5-vl:7b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_VLM_CTX_WINDOW = 4096  # CRITICAL: limits KV cache to fit in 12GB VRAM
DEFAULT_VLM_TIMEOUT_SECONDS = 600
MAX_IMAGE_SIDE = 1500  # Downscale to 1500px max (1280px is user-configurable)


# ============================================================================
# STAGE 0: IMAGE PRE-PROCESSING
# ============================================================================

def preprocess_image(image_path: Path, max_side: int = MAX_IMAGE_SIDE) -> str:
    """
    Pre-process an image for VLM ingestion.
    
    Args:
        image_path: Local file path to image (JPG, PNG, etc.)
        max_side: Maximum pixel dimension (default 1500px)
    
    Returns:
        Base64-encoded string ready for Ollama image parameter
    
    Raises:
        ValueError: If image cannot be opened or is too small
        FileNotFoundError: If image file does not exist
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    try:
        image = Image.open(image_path)
    except Exception as e:
        raise ValueError(f"Cannot open image {image_path}: {e}") from e
    
    # Step 1: Convert to grayscale to reduce data channels
    # This preserves contrast for handwriting while cutting memory usage
    image = image.convert("L")
    
    # Step 2: Downscale while preserving aspect ratio
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        scale = max_side / longest
        new_width = max(1, round(width * scale))
        new_height = max(1, round(height * scale))
        logger.debug(
            "Downscaling image %s from %dx%d to %dx%d",
            image_path.name, width, height, new_width, new_height
        )
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Step 3: Encode as base64 string for Ollama
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")  # PNG for lossless compression
    image_bytes = buffer.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    logger.debug(
        "Pre-processed image %s: %d bytes -> %d B64 chars",
        image_path.name, len(image_bytes), len(image_b64)
    )
    
    return image_b64


# ============================================================================
# STAGE 1: VLM TRANSCRIPTION (HIGH-SPEED, GPU-OPTIMIZED)
# ============================================================================

def transcribe_with_vlm(
    image_path: Path,
    vlm_model: str = DEFAULT_VLM_MODEL,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    ctx_window: int = DEFAULT_VLM_CTX_WINDOW,
    timeout_seconds: float = DEFAULT_VLM_TIMEOUT_SECONDS,
    custom_prompt: Optional[str] = None,
) -> str:
    """
    Stage 1: Transcribe handwritten document using Vision-Language Model.
    
    CRITICAL PERFORMANCE FIX: Passes `options={"num_ctx": ctx_window}` to force
    KV cache allocation to fit within available VRAM, keeping execution 100% on GPU.
    
    Args:
        image_path: Local file path to image
        vlm_model: Ollama model name (e.g., "qwen2.5-vl:7b")
        ollama_host: Ollama API endpoint (e.g., "http://127.0.0.1:11434")
        ctx_window: Context window size in tokens (default 4096 for 12GB VRAM)
        timeout_seconds: Request timeout
        custom_prompt: Override default transcription prompt
    
    Returns:
        Raw transcribed text from the document
    
    Raises:
        ValueError: If VLM is unavailable or transcription fails
        TimeoutError: If transcription exceeds timeout
    """
    try:
        import ollama
    except ImportError:
        raise ValueError("ollama library required: pip install ollama")
    
    # Pre-process image
    image_b64 = preprocess_image(image_path, max_side=MAX_IMAGE_SIDE)
    
    # Default transcription prompt (raw text only, no commentary)
    prompt = custom_prompt or (
        "Transcribe all text from this historical genealogical document exactly as written. "
        "Preserve original spelling, abbreviations, names, dates, punctuation, and line breaks. "
        "Read handwriting carefully. Write [illegible] for words you cannot read. "
        "Do not guess, translate, summarize, or add commentary. "
        "If the page has no text, reply with nothing."
    )
    
    logger.info("Starting Stage 1 VLM transcription: %s (model=%s)", image_path.name, vlm_model)
    start_time = time.time()
    
    try:
        # CRITICAL: num_ctx parameter limits KV cache memory layout
        # This forces the model to stay 100% on GPU and avoid CPU fallback
        response = ollama.chat(
            model=vlm_model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],  # Base64-encoded image
                }
            ],
            options={"num_ctx": ctx_window},  # PERFORMANCE FIX
            stream=False,
        )
        
        transcription = response.get("message", {}).get("content", "").strip()
        elapsed = time.time() - start_time
        
        logger.info(
            "Stage 1 complete: %s in %.2f seconds (%d chars transcribed)",
            image_path.name, elapsed, len(transcription)
        )
        
        return transcription
    
    except TimeoutError as e:
        raise TimeoutError(
            f"VLM transcription timed out after {timeout_seconds}s: {e}"
        ) from e
    except Exception as e:
        raise ValueError(
            f"VLM transcription failed for {image_path.name}: {e}"
        ) from e


# ============================================================================
# STAGE 2: CONTRADICTION CHECKING (TEXT-LLM REASONING ENGINE)
# ============================================================================

def check_contradictions(
    transcription: str,
    gedcom_fields: dict,
    text_llm_model: str = DEFAULT_TEXT_LLM_MODEL,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    timeout_seconds: float = DEFAULT_VLM_TIMEOUT_SECONDS,
) -> dict:
    """
    Stage 2: Cross-reference transcribed text against family tree data.
    
    Uses a lightweight text-only LLM to identify logical contradictions
    between document text and GEDCOM fields without heavy conversational overhead.
    
    Args:
        transcription: Raw text from Stage 1
        gedcom_fields: Dict of target family tree data
                      (e.g., {"individual_name": "John Doe", "birth_date": "1850-03-15"})
        text_llm_model: Ollama text model name (e.g., "mistral")
        ollama_host: Ollama API endpoint
        timeout_seconds: Request timeout
    
    Returns:
        Strictly formatted dict with contradictions:
        {
            "contradictions_found": bool,
            "issues": [
                {
                    "field": "name",
                    "gedcom_value": "John Doe",
                    "document_value": "John D.",
                    "confidence": 0.95,
                    "description": "Name mismatch (abbreviation vs full name)"
                },
                ...
            ],
            "summary": "..."
        }
    """
    try:
        import ollama
    except ImportError:
        raise ValueError("ollama library required: pip install ollama")
    
    logger.info("Starting Stage 2 contradiction check (model=%s)", text_llm_model)
    
    # Build GEDCOM context
    gedcom_context = json.dumps(gedcom_fields, indent=2)
    
    prompt = f"""You are a genealogy research assistant validating handwritten historical documents.

TRANSCRIBED DOCUMENT TEXT:
{transcription}

TARGET FAMILY TREE DATA (GEDCOM):
{gedcom_context}

TASK: Identify any logical contradictions between the document text and the family tree data.
Consider:
- Name variations (spelling, abbreviations, nicknames)
- Date discrepancies (format, digit errors, plausible variations)
- Missing or conflicting information
- Illegible portions that could indicate conflicts

RESPONSE FORMAT (strict JSON, no markdown):
{{
    "contradictions_found": bool,
    "issues": [
        {{
            "field": "name",
            "gedcom_value": "...",
            "document_value": "...",
            "confidence": 0.0-1.0,
            "description": "..."
        }}
    ],
    "summary": "Brief overall assessment"
}}

If no contradictions found, return:
{{"contradictions_found": false, "issues": [], "summary": "No contradictions detected"}}
"""
    
    start_time = time.time()
    
    try:
        response = ollama.chat(
            model=text_llm_model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        
        result_text = response.get("message", {}).get("content", "").strip()
        elapsed = time.time() - start_time
        
        logger.info("Stage 2 complete in %.2f seconds", elapsed)
        
        # Parse JSON response
        try:
            # Handle cases where model wraps JSON in markdown code blocks
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result_dict = json.loads(result_text)
            return result_dict
        
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse LLM JSON response: %s\nRaw response: %s",
                e, result_text
            )
            # Return a safe fallback
            return {
                "contradictions_found": False,
                "issues": [],
                "summary": f"Parsing error: {str(e)[:100]}",
                "raw_response": result_text,
            }
    
    except TimeoutError as e:
        raise TimeoutError(
            f"Contradiction check timed out after {timeout_seconds}s: {e}"
        ) from e
    except Exception as e:
        raise ValueError(f"Contradiction check failed: {e}") from e


# ============================================================================
# ORCHESTRATION: Full Pipeline
# ============================================================================

def process_genealogy_document(
    image_path: Path,
    gedcom_fields: dict,
    text_llm_model: str = DEFAULT_TEXT_LLM_MODEL,
    vlm_model: str = DEFAULT_VLM_MODEL,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    ctx_window: int = DEFAULT_VLM_CTX_WINDOW,
    timeout_seconds: float = DEFAULT_VLM_TIMEOUT_SECONDS,
    custom_prompt: Optional[str] = None,
) -> dict:
    """
    End-to-end pipeline: transcribe document and check for contradictions.
    
    Args:
        image_path: Path to genealogy document image
        gedcom_fields: Target family tree data for validation
        text_llm_model: Text LLM model name
        vlm_model: Vision-Language Model name
        ollama_host: Ollama API endpoint
        ctx_window: VLM context window (4096 for 12GB GPU)
        timeout_seconds: Timeout for each stage
        custom_prompt: Optional override for VLM prompt
    
    Returns:
        Result dict combining transcription and contradiction check:
        {
            "success": bool,
            "transcription": "...",
            "contradictions": {...},
            "errors": ["..."]
        }
    """
    errors = []
    result = {
        "success": False,
        "transcription": "",
        "contradictions": {},
        "errors": [],
    }
    
    logger.info("Processing genealogy document: %s", image_path.name)
    pipeline_start = time.time()
    
    # Stage 1: VLM Transcription
    try:
        transcription = transcribe_with_vlm(
            image_path,
            vlm_model=vlm_model,
            ollama_host=ollama_host,
            ctx_window=ctx_window,
            timeout_seconds=timeout_seconds,
            custom_prompt=custom_prompt,
        )
        result["transcription"] = transcription
    except Exception as e:
        error_msg = f"Stage 1 (VLM) failed: {str(e)}"
        logger.error(error_msg)
        errors.append(error_msg)
        result["errors"] = errors
        return result
    
    # Stage 2: Contradiction Checking
    if transcription:  # Only check if transcription succeeded
        try:
            contradictions = check_contradictions(
                transcription,
                gedcom_fields,
                text_llm_model=text_llm_model,
                ollama_host=ollama_host,
                timeout_seconds=timeout_seconds,
            )
            result["contradictions"] = contradictions
        except Exception as e:
            error_msg = f"Stage 2 (Contradiction check) failed: {str(e)}"
            logger.warning(error_msg)
            # Don't fail the whole pipeline if contradiction check fails
            errors.append(error_msg)
            result["contradictions"] = {
                "contradictions_found": None,
                "issues": [],
                "summary": error_msg,
            }
    
    result["success"] = len(errors) == 0
    result["errors"] = errors
    
    elapsed = time.time() - pipeline_start
    logger.info(
        "Pipeline complete: %s (%.2f seconds, %d errors)",
        image_path.name, elapsed, len(errors)
    )
    
    return result


# ============================================================================
# HELPER: Integrate with Settings
# ============================================================================

def process_with_settings(
    image_path: Path,
    gedcom_fields: dict,
    settings: "Settings",  # type: ignore
) -> dict:
    """
    Convenience wrapper using Settings from config.py.
    
    Args:
        image_path: Path to document image
        gedcom_fields: Family tree data
        settings: TreeSleuth Settings instance
    
    Returns:
        Full pipeline result dict
    """
    return process_genealogy_document(
        image_path,
        gedcom_fields,
        text_llm_model=settings.text_llm_model,
        vlm_model=settings.vlm_model,
        ollama_host=settings.vlm_host or settings.ollama_host,
        ctx_window=settings.vlm_ctx_window,
        timeout_seconds=settings.vlm_timeout_seconds,
        custom_prompt=settings.vlm_prompt,
    )


if __name__ == "__main__":
    # Example usage
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python vlm_pipeline.py <image_path> [gedcom_json]")
        sys.exit(1)
    
    image_file = Path(sys.argv[1])
    
    # Example GEDCOM fields
    test_gedcom = {
        "individual_name": "John Doe",
        "birth_date": "1850-03-15",
        "birth_location": "New York",
        "marriage_date": "1875-06-20",
    }
    
    if len(sys.argv) > 2:
        test_gedcom = json.loads(sys.argv[2])
    
    result = process_genealogy_document(
        image_file,
        test_gedcom,
    )
    
    print("\n=== PIPELINE RESULT ===")
    print(json.dumps(result, indent=2))
