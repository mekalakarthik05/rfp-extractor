"""
tests/test_utils.py

Unit tests for src.utils functions.
"""
from src.utils import deduplicate_list_preserve_longest

def test_deduplicate_list_preserve_longest_basic():
    """Exact duplicates are removed, preserving order of first appearance."""
    items = ["A", "B", "A", "C"]
    assert deduplicate_list_preserve_longest(items) == ["A", "B", "C"]

def test_deduplicate_list_preserve_longest_substring():
    """If one item is a substring of another, keep the longer one."""
    items = ["Mercury Affidavit", "Signed Mercury Affidavit", "W-9", "Form W-9"]
    result = deduplicate_list_preserve_longest(items)
    assert result == ["Signed Mercury Affidavit", "Form W-9"]

def test_deduplicate_list_preserve_longest_case_insensitive():
    """Substring check is case-insensitive."""
    items = ["mercury affidavit", "Signed Mercury Affidavit"]
    assert deduplicate_list_preserve_longest(items) == ["Signed Mercury Affidavit"]

def test_deduplicate_list_preserve_longest_whitespace_normalized():
    """Whitespace is normalized before checking and in the output."""
    items = ["Mercury   Affidavit", "Signed\tMercury\nAffidavit"]
    assert deduplicate_list_preserve_longest(items) == ["Signed Mercury Affidavit"]

def test_deduplicate_list_preserve_longest_empty():
    """Empty lists or lists of empty strings return an empty list."""
    assert deduplicate_list_preserve_longest([]) == []
    assert deduplicate_list_preserve_longest(["", "   ", None]) == []

def test_deduplicate_list_preserve_longest_multiple_substrings():
    """If an item is a substring of multiple others, the longest ones are kept."""
    items = ["Affidavit", "Mercury Affidavit", "Signed Mercury Affidavit"]
    assert deduplicate_list_preserve_longest(items) == ["Signed Mercury Affidavit"]


def test_deduplicate_list_warranty_certificate_variation():
    """Equivalent requirement phrasings merge into the single longer/more descriptive item."""
    items = [
        "Letter of Authorization (if requested)",
        "Mercury Affidavit",
        "Warranty certificate or Affidavit upon award",
        "Warranty certificate or Affidavit to be presented upon award"
    ]
    result = deduplicate_list_preserve_longest(items)
    assert result == [
        "Letter of Authorization (if requested)",
        "Mercury Affidavit",
        "Warranty certificate or Affidavit to be presented upon award"
    ]


def test_deduplicate_sentences_overlapping_specs():
    """Overlapping product specification sentences from different chunks are cleanly deduplicated."""
    from src.utils import deduplicate_sentences
    chunk1 = "Purchase new and unused equipment. ENERGY STAR certified product. Laptops must be Microsoft Copilot ready."
    chunk2 = "Purchase new and unused equipment. ENERGY STAR certified product. Dell Limited Hardware Warranty Extended for all machines purchased - 3 Years."
    merged = deduplicate_sentences(f"{chunk1} {chunk2}")
    assert merged == "Purchase new and unused equipment. ENERGY STAR certified product. Laptops must be Microsoft Copilot ready. Dell Limited Hardware Warranty Extended for all machines purchased - 3 Years."


def test_deduplicate_list_supporting_documentation_variation():
    """Modal variations of supporting documentation merge into the parenthesized canonical requirement."""
    items = [
        "demonstrated competencies and references in delivering the magnitude of devices listed on the price sheet",
        "supporting documentation (may include details of past projects, statements in reference letters, and/or project plans)",
        "Supporting documentation including details of past projects, statements in reference letters, and/or project plans"
    ]
    result = deduplicate_list_preserve_longest(items)
    assert result == [
        "demonstrated competencies and references in delivering the magnitude of devices listed on the price sheet",
        "supporting documentation (may include details of past projects, statements in reference letters, and/or project plans)"
    ]


def test_deduplicate_sentences_addendum_qualified_preservation():
    """Unqualified installation sentence merges into more specific addendum-qualified sentence."""
    from src.utils import deduplicate_sentences
    text = (
        "All deliveries and deployments must incorporate white glove services, which include asset decaling, asset reporting, etching, and delivery to varied locations. "
        "software installation, asset tagging and etching, device deployment and setup, and asset control reporting. "
        "All deliveries and deployments must incorporate white glove services, which include asset decaling, asset reporting, etching (only required on Laptops), and delivery to varied locations. "
        "Any awarded vendor will need to coordinate a schedule of deliveries with the Dallas ISD ED TECH department."
    )
    result = deduplicate_sentences(text)
    assert "(only required on Laptops)" in result
    assert "software installation, asset tagging and etching, device deployment and setup, and asset control reporting." in result
    assert "coordinate a schedule of deliveries" in result
    assert result.count("All deliveries and deployments must incorporate white glove services") == 1


