"""
tests/test_chunker.py

Unit tests for src.chunker — section-aware text chunking.
All tests are offline; no LLM calls are made.
"""
import pytest
from src.chunker import chunk_text, estimate_tokens


# ── estimate_tokens ──────────────────────────────────────────────────────────

def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0

def test_estimate_tokens_rough():
    # 400 chars ≈ 100 tokens
    assert estimate_tokens("a" * 400) == 100


# ── chunk_text: small document ────────────────────────────────────────────────

def test_small_doc_no_chunking():
    """Documents smaller than max_chars must not be split."""
    text = "Hello world. This is a short document."
    chunks = chunk_text(text, max_chars=5000)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_single_char_threshold():
    text = "A" * 100
    chunks = chunk_text(text, max_chars=100)
    assert len(chunks) == 1


# ── chunk_text: large document ────────────────────────────────────────────────

def test_large_doc_is_split():
    """A document clearly exceeding max_chars must produce multiple chunks."""
    # Build a document with clear paragraph breaks
    paragraphs = [f"Paragraph {i}: " + "word " * 30 for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=500, max_chunks=8)
    assert len(chunks) > 1


def test_chunks_cover_all_content():
    """No content should be silently dropped during chunking."""
    words = [f"word{i}" for i in range(200)]
    text = " ".join(words)
    chunks = chunk_text(text, max_chars=300, max_chunks=8)
    # Join chunks; words at hard-split boundaries may have whitespace inserted
    reconstructed = " ".join(chunks)
    # Every word must appear somewhere in the reconstructed text.
    # We search by word with optional surrounding whitespace/newline.
    import re as _re
    for word in words:
        assert _re.search(rf'\b{word}\b', reconstructed) is not None, (
            f"'{word}' lost during chunking"
        )


def test_max_chunks_enforced():
    """Chunk count must never exceed max_chunks."""
    # 100 tiny paragraphs that would naturally produce many chunks
    paragraphs = [f"Para {i}: " + "x " * 20 for i in range(100)]
    text = "\n\n".join(paragraphs)
    for cap in [2, 4, 8]:
        chunks = chunk_text(text, max_chars=200, max_chunks=cap)
        assert len(chunks) <= cap, f"Expected <= {cap} chunks, got {len(chunks)}"


def test_heading_starts_new_chunk():
    """A Section/Article heading should be preserved in the output (not silently dropped)."""
    part_a = "Introduction text. " * 10   # ~190 chars
    heading = "Section 2. Scope of Work"
    part_b = "Scope details go here. " * 10  # ~230 chars
    text = part_a + "\n\n" + heading + "\n\n" + part_b
    chunks = chunk_text(text, max_chars=300, max_chunks=8)
    all_text = " ".join(chunks)
    # The heading must appear somewhere in the reconstructed chunks
    assert "Section 2" in all_text, "Section heading was dropped during chunking"
    # And it should NOT be merged mid-sentence with unrelated text
    # (i.e., 'Introduction text.Section 2' must not appear)
    import re as _re
    assert not _re.search(r'[a-z]\.Section', all_text), (
        "Heading was concatenated mid-sentence without whitespace"
    )


def test_no_empty_chunks():
    """No chunk in the output should be empty or whitespace-only."""
    paragraphs = [f"Para {i}: content here." for i in range(30)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=100, max_chunks=8)
    for i, c in enumerate(chunks):
        assert c.strip(), f"Chunk {i} is empty"


def test_single_giant_paragraph_split():
    """A single paragraph exceeding max_chars must still be chunked."""
    long_para = "This is sentence number {}. " * 100
    long_para = long_para.format(*range(100))
    chunks = chunk_text(long_para, max_chars=500, max_chunks=8)
    assert len(chunks) > 1
    assert all(len(c) > 0 for c in chunks)


# ── chunk_text: table preservation heuristic ─────────────────────────────────

def test_table_rows_not_split_at_boundary():
    """
    A table block should preferably land in the same chunk as its header
    when the total size fits within max_chars.
    """
    header = "Product | Model | Part No | Price\n"
    rows = "".join([f"Widget {i} | MOD-{i:03d} | PN-{i:04d} | ${i*10}\n" for i in range(5)])
    table_block = header + rows   # ~250 chars
    preamble = "Some introductory text.\n\n"
    text = preamble + table_block
    chunks = chunk_text(text, max_chars=800, max_chunks=8)
    # Both header and at least one row should appear in the same chunk
    header_chunk = next((c for c in chunks if "Product | Model" in c), None)
    assert header_chunk is not None
    assert "MOD-000" in header_chunk  # first row kept with header
