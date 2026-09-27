"""
src/chunker.py

Section-aware text chunker for large RFP documents.

Chunking strategy:
  1. Documents <= MAX_CHUNK_CHARS are NOT chunked (single LLM call).
  2. Larger documents are split at semantic boundaries: double newlines, section
     headings (Section / Article / Clause / EXHIBIT / APPENDIX), table edges.
  3. Individual blocks that exceed MAX_CHUNK_CHARS are split further on sentence
     boundaries, and as a last resort on character boundaries — always keeping
     field labels and their values in the same chunk whenever possible.
  4. The total number of chunks is capped at MAX_CHUNKS (default 8) to avoid
     excessive API usage.  If the document is too large even after maximum
     chunking, the last chunk is extended rather than generating extra calls.
"""
import re
from typing import List
from .config import MAX_CHUNK_CHARS, MAX_CHUNKS, logger


# Regex that matches heading-like lines typical in procurement documents.
# Matches both 'Section 1.' and 'SECTION 1 – ...' styles at the START of a line.
_HEADING_RE = re.compile(
    r"^[ \t]*(SECTION|Section|ARTICLE|Article|CLAUSE|Clause|EXHIBIT|Exhibit|"
    r"APPENDIX|Appendix|ATTACHMENT|Attachment|PART|Part|SCHEDULE|Schedule)"
    r"(?:\s|\.|\d|\:)",
    re.MULTILINE,
)

# Sentence boundary (. or ? or ! followed by whitespace + capital letter)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")


def estimate_tokens(text: str) -> int:
    """Rough 4-chars-per-token estimate for English text."""
    if not text:
        return 0
    return len(text) // 4


def _split_into_blocks(text: str) -> List[str]:
    """
    Primary split on double newlines (paragraph / section breaks).
    If a heading line is encountered, it starts a new block regardless.
    """
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Insert a guaranteed split point before each heading-like line
    text = _HEADING_RE.sub(r"\n\n\g<0>", text)

    # Split on double (or more) blank lines
    raw_blocks = re.split(r"\n\s*\n", text)
    blocks = [b.strip() for b in raw_blocks if b.strip()]
    return blocks


def _split_block_on_sentences(block: str, max_chars: int) -> List[str]:
    """Split a single block into sentence-boundary pieces, each <= max_chars."""
    sentences = _SENTENCE_RE.split(block)
    pieces: List[str] = []
    current = ""
    for sent in sentences:
        if not sent.strip():
            continue
        candidate = (current + " " + sent).strip() if current else sent
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            # If a single sentence is still too long, hard-split at word boundaries.
            if len(sent) > max_chars:
                # Split at space boundaries close to max_chars so words are never broken.
                remaining = sent
                while len(remaining) > max_chars:
                    # Find last space within the first max_chars chars
                    cut = remaining.rfind(" ", 0, max_chars)
                    if cut == -1:
                        cut = max_chars  # no space found: hard cut (very long token)
                    pieces.append(remaining[:cut].strip())
                    remaining = remaining[cut:].strip()
                if remaining:
                    pieces.append(remaining)
                current = ""

            else:
                current = sent
    if current:
        pieces.append(current)
    return pieces or [block]


def chunk_text(
    text: str,
    max_chars: int = MAX_CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
) -> List[str]:
    """
    Split *text* into semantically coherent chunks for LLM extraction.

    Parameters
    ----------
    text      : full document text
    max_chars : soft upper bound on characters per chunk
    max_chunks: hard cap on the total number of chunks returned

    Returns
    -------
    List of non-empty string chunks, at most *max_chunks* in length.
    If the document fits in one call it is returned as a single-element list.
    """
    if len(text) <= max_chars:
        logger.debug("Document fits in a single LLM call (%d chars).", len(text))
        return [text]

    logger.info(
        "Document too large for single call (%d chars). "
        "Chunking with soft limit %d chars, max %d chunks.",
        len(text), max_chars, max_chunks,
    )

    blocks = _split_into_blocks(text)

    # Greedily merge blocks into chunks that fit within max_chars
    chunks: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for block in blocks:
        if len(block) > max_chars:
            # Block is too large on its own — split on sentences first
            sub_pieces = _split_block_on_sentences(block, max_chars)
        else:
            sub_pieces = [block]

        for piece in sub_pieces:
            piece_len = len(piece)
            if current_len + piece_len <= max_chars:
                current_parts.append(piece)
                current_len += piece_len
            else:
                if current_parts:
                    chunks.append("\n\n".join(current_parts))
                current_parts = [piece]
                current_len = piece_len

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    # Enforce the chunk cap: merge tail chunks into the last allowed slot
    if len(chunks) > max_chunks:
        logger.warning(
            "Generated %d chunks exceeds MAX_CHUNKS=%d. "
            "Merging tail chunks to stay within budget.",
            len(chunks), max_chunks,
        )
        kept = chunks[: max_chunks - 1]
        overflow = "\n\n".join(chunks[max_chunks - 1 :])
        kept.append(overflow)
        chunks = kept

    logger.info("Chunking produced %d chunk(s).", len(chunks))
    return chunks
