"""Tests for optimized two-stage VLM pipeline."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from treesleuth.vlm_pipeline import (
    check_contradictions,
    preprocess_image,
    process_genealogy_document,
    transcribe_with_vlm,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a test image (simple grayscale square)."""
    img = Image.new("RGB", (800, 600), color="white")
    img_path = tmp_path / "test.png"
    img.save(img_path)
    return img_path


@pytest.fixture
def large_image(tmp_path: Path) -> Path:
    """Create a test image larger than downscaling threshold."""
    img = Image.new("RGB", (2400, 1800), color="white")
    img_path = tmp_path / "large_test.png"
    img.save(img_path)
    return img_path


@pytest.fixture
def sample_gedcom() -> dict:
    """Sample GEDCOM fields for testing."""
    return {
        "individual_name": "John Smith",
        "birth_date": "1850-03-15",
        "birth_location": "New York",
        "marriage_date": "1875-06-20",
        "spouse_name": "Mary Johnson",
    }


class TestImagePreprocessing:
    """Test Stage 0: Image pre-processing."""

    def test_preprocess_image_basic(self, sample_image: Path) -> None:
        """Test basic image pre-processing."""
        result = preprocess_image(sample_image, max_side=1500)
        
        # Should return base64 string
        assert isinstance(result, str)
        assert len(result) > 0
        # Base64 strings contain only alphanumeric, +, /, and =
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in result)

    def test_preprocess_image_converts_to_grayscale(self, tmp_path: Path) -> None:
        """Test that image is converted to grayscale."""
        # Create colored image
        img = Image.new("RGB", (400, 300), color=(255, 0, 0))  # Red
        img_path = tmp_path / "colored.png"
        img.save(img_path)
        
        result = preprocess_image(img_path, max_side=1500)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_preprocess_image_downscales_large_images(self, large_image: Path) -> None:
        """Test that large images are downscaled."""
        result = preprocess_image(large_image, max_side=1500)
        
        # Verify result is smaller than original
        # Original is 2400x1800, should downscale to fit 1500px max
        assert isinstance(result, str)
        assert len(result) > 0

    def test_preprocess_image_nonexistent_file(self) -> None:
        """Test error handling for missing file."""
        with pytest.raises(FileNotFoundError):
            preprocess_image(Path("/nonexistent/image.png"))

    def test_preprocess_image_invalid_file(self, tmp_path: Path) -> None:
        """Test error handling for corrupted image."""
        bad_path = tmp_path / "not_an_image.png"
        bad_path.write_bytes(b"not image data")
        
        with pytest.raises(ValueError, match="Cannot open image"):
            preprocess_image(bad_path)


class TestVlmTranscription:
    """Test Stage 1: VLM transcription."""

    def test_transcribe_with_vlm_success(self, sample_image: Path) -> None:
        """Test successful VLM transcription."""
        mock_response = {
            "message": {"content": "John Smith born 1850 in New York"}
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            result = transcribe_with_vlm(
                sample_image,
                vlm_model="qwen2.5-vl:7b",
            )
            
            assert result == "John Smith born 1850 in New York"
            
            # Verify ollama.chat was called with correct parameters
            call_args = mock_chat.call_args
            assert call_args is not None
            assert call_args.kwargs["model"] == "qwen2.5-vl:7b"
            assert call_args.kwargs["options"]["num_ctx"] == 4096
            assert "images" in call_args.kwargs["messages"][0]

    def test_transcribe_with_vlm_custom_prompt(self, sample_image: Path) -> None:
        """Test VLM transcription with custom prompt."""
        custom_prompt = "Extract names and dates"
        mock_response = {"message": {"content": "John 1850"}}
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            result = transcribe_with_vlm(
                sample_image,
                custom_prompt=custom_prompt,
            )
            
            assert result == "John 1850"
            call_args = mock_chat.call_args
            assert custom_prompt in call_args.kwargs["messages"][0]["content"]

    def test_transcribe_with_vlm_ctx_window(self, sample_image: Path) -> None:
        """Test that context window is passed to Ollama."""
        mock_response = {"message": {"content": "text"}}
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            transcribe_with_vlm(
                sample_image,
                ctx_window=2048,
            )
            
            # CRITICAL: Verify num_ctx is set correctly
            call_args = mock_chat.call_args
            assert call_args.kwargs["options"]["num_ctx"] == 2048

    def test_transcribe_with_vlm_timeout(self, sample_image: Path) -> None:
        """Test timeout error handling."""
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = TimeoutError("timed out")
            
            with pytest.raises(TimeoutError, match="VLM transcription timed out"):
                transcribe_with_vlm(sample_image)

    def test_transcribe_with_vlm_missing_ollama(self, sample_image: Path) -> None:
        """Test error when ollama library import fails."""
        with patch("builtins.__import__", side_effect=ImportError("No module named 'ollama'")):
            with pytest.raises(ValueError, match="ollama library required"):
                transcribe_with_vlm(sample_image)


class TestContradictionChecking:
    """Test Stage 2: Contradiction checking."""

    def test_check_contradictions_no_issues(self, sample_gedcom: dict) -> None:
        """Test contradiction checking with no issues found."""
        transcription = "John Smith born 1850 in New York, married Mary Johnson 1875"
        
        mock_response = {
            "message": {
                "content": json.dumps({
                    "contradictions_found": False,
                    "issues": [],
                    "summary": "No contradictions detected"
                })
            }
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            result = check_contradictions(
                transcription,
                sample_gedcom,
            )
            
            assert result["contradictions_found"] is False
            assert len(result["issues"]) == 0

    def test_check_contradictions_with_issues(self, sample_gedcom: dict) -> None:
        """Test contradiction checking with issues found."""
        transcription = "John Smith born 1840 in Boston"
        
        mock_response = {
            "message": {
                "content": json.dumps({
                    "contradictions_found": True,
                    "issues": [
                        {
                            "field": "birth_date",
                            "gedcom_value": "1850",
                            "document_value": "1840",
                            "confidence": 0.95,
                            "description": "Birth year discrepancy (10 years)"
                        },
                        {
                            "field": "birth_location",
                            "gedcom_value": "New York",
                            "document_value": "Boston",
                            "confidence": 0.90,
                            "description": "Location mismatch"
                        }
                    ],
                    "summary": "Found 2 contradictions"
                })
            }
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            result = check_contradictions(
                transcription,
                sample_gedcom,
            )
            
            assert result["contradictions_found"] is True
            assert len(result["issues"]) == 2
            assert result["issues"][0]["field"] == "birth_date"

    def test_check_contradictions_malformed_json(self, sample_gedcom: dict) -> None:
        """Test handling of malformed JSON response."""
        transcription = "test text"
        
        mock_response = {
            "message": {"content": "not valid json"}
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            result = check_contradictions(
                transcription,
                sample_gedcom,
            )
            
            # Should return safe fallback
            assert result["contradictions_found"] is False
            assert "Parsing error" in result["summary"]

    def test_check_contradictions_markdown_json(self, sample_gedcom: dict) -> None:
        """Test parsing JSON wrapped in markdown code blocks."""
        transcription = "test text"
        
        json_response = {
            "contradictions_found": True,
            "issues": [],
            "summary": "test"
        }
        
        mock_response = {
            "message": {
                "content": f"```json\n{json.dumps(json_response)}\n```"
            }
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            
            result = check_contradictions(
                transcription,
                sample_gedcom,
            )
            
            assert result["contradictions_found"] is True

    def test_check_contradictions_timeout(self, sample_gedcom: dict) -> None:
        """Test timeout error handling."""
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = TimeoutError("timed out")
            
            with pytest.raises(TimeoutError, match="Contradiction check timed out"):
                check_contradictions("text", sample_gedcom)


class TestEndToEndPipeline:
    """Test full end-to-end pipeline."""

    def test_process_genealogy_document_success(
        self, sample_image: Path, sample_gedcom: dict
    ) -> None:
        """Test successful end-to-end processing."""
        transcription_text = "John Smith born 1850 in New York"
        
        # Mock both stages
        mock_transcription = {"message": {"content": transcription_text}}
        mock_contradictions = {
            "message": {
                "content": json.dumps({
                    "contradictions_found": False,
                    "issues": [],
                    "summary": "No issues"
                })
            }
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = [mock_transcription, mock_contradictions]
            
            result = process_genealogy_document(
                sample_image,
                sample_gedcom,
            )
            
            assert result["success"] is True
            assert result["transcription"] == transcription_text
            assert result["contradictions"]["contradictions_found"] is False
            assert len(result["errors"]) == 0

    def test_process_genealogy_document_stage1_failure(
        self, sample_image: Path, sample_gedcom: dict
    ) -> None:
        """Test pipeline failure in Stage 1."""
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = ValueError("Model not found")
            
            result = process_genealogy_document(
                sample_image,
                sample_gedcom,
            )
            
            assert result["success"] is False
            assert "Stage 1" in result["errors"][0]
            assert result["transcription"] == ""

    def test_process_genealogy_document_stage2_failure(
        self, sample_image: Path, sample_gedcom: dict
    ) -> None:
        """Test pipeline continues if Stage 2 fails."""
        transcription_text = "John Smith born 1850"
        mock_transcription = {"message": {"content": transcription_text}}
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = [
                mock_transcription,
                ValueError("LLM error")
            ]
            
            result = process_genealogy_document(
                sample_image,
                sample_gedcom,
            )
            
            # Should still consider partial success
            assert result["transcription"] == transcription_text
            assert "Stage 2" in result["errors"][0]
            assert result["contradictions"]["contradictions_found"] is None

    def test_process_genealogy_document_empty_transcription(
        self, sample_image: Path, sample_gedcom: dict
    ) -> None:
        """Test pipeline when transcription is empty."""
        mock_transcription = {"message": {"content": ""}}
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_transcription
            
            result = process_genealogy_document(
                sample_image,
                sample_gedcom,
            )
            
            # Should complete without Stage 2
            assert result["success"] is True
            assert result["transcription"] == ""
            assert result["contradictions"] == {}

    def test_process_genealogy_document_custom_models(
        self, sample_image: Path, sample_gedcom: dict
    ) -> None:
        """Test pipeline with custom model names."""
        mock_transcription = {"message": {"content": "text"}}
        mock_contradictions = {
            "message": {"content": json.dumps({
                "contradictions_found": False,
                "issues": [],
                "summary": ""
            })}
        }
        
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = [mock_transcription, mock_contradictions]
            
            result = process_genealogy_document(
                sample_image,
                sample_gedcom,
                text_llm_model="custom-text-model",
                vlm_model="custom-vlm-model",
            )
            
            # Verify custom models were passed
            calls = mock_chat.call_args_list
            assert calls[0].kwargs["model"] == "custom-vlm-model"
            assert calls[1].kwargs["model"] == "custom-text-model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
