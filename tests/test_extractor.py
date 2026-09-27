"""
tests/test_extractor.py

Unit tests for src.extractor.LLMExtractor.
All Gemini API calls are mocked — no real API key required.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.extractor import LLMExtractor, _SCHEMA_KEYS
from src.exceptions import RateLimitError, SchemaValidationError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_valid_raw(overrides: dict = None) -> dict:
    """Return a minimal valid raw dict (all nulls except overrides)."""
    base = {k: None for k in _SCHEMA_KEYS}
    if overrides:
        base.update(overrides)
    return base


def _mock_response(data: dict) -> MagicMock:
    """Produce a mock Gemini response object whose .text is a JSON string."""
    mock = MagicMock()
    mock.text = json.dumps(data)
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def extractor(mocker):
    """Return an LLMExtractor with the Gemini client fully mocked out."""
    # Prevent actual network calls during __init__
    mocker.patch("src.extractor.genai.Client", return_value=MagicMock())
    mock_client = MagicMock()
    mock_client.models.list.return_value = []
    with patch("src.extractor.genai.Client", return_value=mock_client):
        ext = LLMExtractor()
    ext._client = mock_client
    ext._active_model = "gemini-flash-latest"
    return ext


# ── Single-chunk extraction ───────────────────────────────────────────────────

def test_extract_single_call_small_doc(extractor):
    """Short document (<= MAX_CHUNK_CHARS) makes exactly ONE API call."""
    raw = _make_valid_raw({"bid_number": "RFP-001", "company_name": "Testville"})
    extractor._client.models.generate_content.return_value = _mock_response(raw)

    result = extractor.extract("Short document text.", "test.pdf")

    extractor._client.models.generate_content.assert_called_once()
    assert result["bid_number"] == "RFP-001"
    assert result["company_name"] == "Testville"


def test_extract_returns_20_keys(extractor):
    """Result dict must have exactly the 20 schema keys."""
    raw = _make_valid_raw()
    extractor._client.models.generate_content.return_value = _mock_response(raw)
    result = extractor.extract("short text", "test.pdf")
    assert set(result.keys()) == set(_SCHEMA_KEYS)


# ── Multi-chunk extraction ────────────────────────────────────────────────────

def test_chunking_triggered_large_doc(extractor):
    """A document exceeding max_chunk_chars must trigger multiple API calls."""
    extractor._max_chunk_chars = 100  # tiny limit to force chunking
    extractor._max_chunks = 8

    # Build text big enough to produce ≥2 chunks
    big_text = ("Alpha beta gamma. " * 30 + "\n\n") * 4  # ~2 160 chars
    raw = _make_valid_raw({"bid_number": "RFP-999"})
    extractor._client.models.generate_content.return_value = _mock_response(raw)

    result = extractor.extract(big_text, "big.pdf")

    call_count = extractor._client.models.generate_content.call_count
    assert call_count > 1, f"Expected multiple calls for large doc, got {call_count}"
    assert result["bid_number"] == "RFP-999"


def test_max_chunks_limit_respected(extractor):
    """API calls must never exceed max_chunks even for very large documents."""
    MAX = 3
    extractor._max_chunk_chars = 50
    extractor._max_chunks = MAX

    long_text = ("Sentence here. " * 20 + "\n\n") * 10  # would normally produce many chunks
    raw = _make_valid_raw()
    extractor._client.models.generate_content.return_value = _mock_response(raw)

    extractor.extract(long_text, "huge.pdf")
    call_count = extractor._client.models.generate_content.call_count
    assert call_count <= MAX, f"Expected <= {MAX} calls, got {call_count}"


# ── Chunk merging ─────────────────────────────────────────────────────────────

def test_merge_first_nonnull_wins():
    """For scalar fields, first non-null value wins across chunks."""
    chunks_data = [
        _make_valid_raw({"bid_number": "FIRST", "due_date": None}),
        _make_valid_raw({"bid_number": "SECOND", "due_date": "2025-10-01"}),
    ]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    assert merged["bid_number"] == "FIRST"  # first non-null wins
    assert merged["due_date"] == "2025-10-01"   # only non-null


def test_merge_null_does_not_overwrite():
    """A null in a later chunk must NOT overwrite an earlier valid value."""
    chunks_data = [
        _make_valid_raw({"company_name": "City of Springfield"}),
        _make_valid_raw({"company_name": None}),
    ]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    assert merged["company_name"] == "City of Springfield"


def test_merge_list_union():
    """additional_documentation_required from multiple chunks is unioned."""
    chunks_data = [
        _make_valid_raw({"additional_documentation_required": ["W-9", "Insurance"]}),
        _make_valid_raw({"additional_documentation_required": ["Insurance", "References"]}),
    ]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    docs = merged["additional_documentation_required"]
    assert "W-9" in docs
    assert "Insurance" in docs
    assert "References" in docs
    assert docs.count("Insurance") == 1  # deduped


def test_merge_all_nulls_stays_null():
    """If every chunk returns null for a field, merged result is null."""
    chunks_data = [_make_valid_raw() for _ in range(3)]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    for key in _SCHEMA_KEYS:
        assert merged[key] is None


# ── Retry / error handling ────────────────────────────────────────────────────

def test_retry_on_transient_error(extractor, mocker):
    """A 503 error on attempt 1 should be retried; 2nd attempt succeeds."""
    import time
    mocker.patch("src.extractor.time.sleep")  # don't actually sleep

    raw = _make_valid_raw({"bid_number": "RETRY-TEST"})
    # Raise 503 on first call, succeed on second
    extractor._client.models.generate_content.side_effect = [
        Exception("503 UNAVAILABLE: high demand"),
        _mock_response(raw),
    ]

    result = extractor.extract("short text", "retry.pdf")
    assert result["bid_number"] == "RETRY-TEST"
    assert extractor._client.models.generate_content.call_count == 2


def test_all_retries_exhausted_raises(extractor, mocker):
    """If all models + retries fail, RateLimitError is raised."""
    mocker.patch("src.extractor.time.sleep")
    extractor._client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")

    with pytest.raises(RateLimitError):
        extractor.extract("short text", "fail.pdf")


def test_invalid_json_raises_schema_error(extractor):
    """If the LLM returns non-JSON, a SchemaValidationError is raised."""
    mock_resp = MagicMock()
    mock_resp.text = "This is not JSON at all."
    extractor._client.models.generate_content.return_value = mock_resp

    with pytest.raises(SchemaValidationError):
        extractor.extract("short text", "bad_json.pdf")


# ── Multi-model union across chunks ───────────────────────────────────────────

def test_merge_model_no_union_across_chunks():
    """When two chunks each extract a different model number, both are preserved."""
    chunks_data = [
        _make_valid_raw({"model_no": "ModelA"}),
        _make_valid_raw({"model_no": "ModelB"}),
    ]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    assert "ModelA" in merged["model_no"]
    assert "ModelB" in merged["model_no"]


def test_merge_model_no_single_unchanged():
    """When only one chunk has a model number, the value is kept verbatim."""
    chunks_data = [
        _make_valid_raw({"model_no": "ModelX"}),
        _make_valid_raw({"model_no": None}),
    ]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    assert merged["model_no"] == "ModelX"


def test_merge_model_no_deduplication():
    """Duplicate model tokens from different chunks are not repeated."""
    chunks_data = [
        _make_valid_raw({"model_no": "ModelA, ModelB"}),
        _make_valid_raw({"model_no": "ModelB, ModelC"}),
    ]
    merged = LLMExtractor._merge_chunk_results(chunks_data)
    tokens = [t.strip() for t in merged["model_no"].split(",")]
    assert tokens.count("ModelB") == 1  # deduped
    assert "ModelA" in tokens
    assert "ModelC" in tokens


def test_pre_bid_meeting_virtual_credentials_preserved(extractor, mocker):
    """Virtual meeting credentials (URL, Meeting ID, Passcode) are preserved in pre_bid_meeting."""
    mock_data = _make_valid_raw({
        "pre_bid_meeting": "June 10, 2024 at 2:00 PM CST via TEAMS. Join: https://teams.microsoft.com Meeting ID: 123 456 Passcode: ABC"
    })
    mocker.patch.object(extractor, "_call_api", return_value=json.dumps(mock_data))
    result = extractor.extract("Some short RFP text", "solicitation.pdf")
    assert "Meeting ID: 123 456" in result["pre_bid_meeting"]
    assert "Passcode: ABC" in result["pre_bid_meeting"]


