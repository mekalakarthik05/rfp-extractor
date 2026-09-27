from unittest.mock import patch
from src.processor import RFPProcessor
from src.validators import Validator

@patch('src.processor.LLMExtractor')
def test_addendum_sort(mock_extractor):
    processor = RFPProcessor()
    files = [
        "Addendum 2 RFP JA-207652.pdf",
        "JA-207652 Student and Staff Computing Devices FINAL.pdf",
        "Addendum 1 RFP JA-207652.pdf"
    ]
    sorted_files = processor._sort_addenda(files)
    assert sorted_files[0] == "JA-207652 Student and Staff Computing Devices FINAL.pdf"
    assert sorted_files[1] == "Addendum 1 RFP JA-207652.pdf"
    assert sorted_files[2] == "Addendum 2 RFP JA-207652.pdf"

@patch('src.processor.LLMExtractor')
def test_addendum_merge(mock_extractor):
    processor = RFPProcessor()
    base = {
        "bid_number": "123",
        "due_date": "Oct 1",
        "additional_documentation_required": ["W-9"]
    }
    addendum = {
        "bid_number": None, # Should not overwrite
        "due_date": "Oct 15", # Should overwrite
        "additional_documentation_required": ["Insurance"] # Should append
    }
    merged = processor._merge_addendum(base, addendum, "Addendum 1")
    
    assert merged["bid_number"] == "123"
    assert merged["due_date"] == "Oct 15"
    assert "W-9" in merged["additional_documentation_required"]
    assert "Insurance" in merged["additional_documentation_required"]

@patch('src.processor.LLMExtractor')
def test_base_document_precedence_and_timezone_preservation(mock_extractor):
    """
    Test that merging a non-addendum base document (like an HTML summary portal export)
    does not overwrite detailed fields from the primary base PDF, preserving exact timezone representations.
    """
    processor = RFPProcessor()
    
    # Primary base document (e.g., official solicitation PDF)
    base_pdf_data = {
        "bid_number": "JA-207652",
        "due_date": "27-JUN-2024 14:00:00",
        "pre_bid_meeting": "June 10, 2024 at 2:00 PM CST via TEAMS",
        "additional_documentation_required": ["W-9 Form"]
    }
    
    # Secondary base document (e.g. portal summary HTML with EDT conversion)
    portal_html_data = {
        "bid_number": "168884",
        "due_date": "06/27/2024 03:00 PM EDT",
        "pre_bid_meeting": "06/10/2024 03:00 PM EDT",
        "additional_documentation_required": ["Form 1295"]
    }
    
    # Merge non-addendum document
    merged = processor._merge_addendum(base_pdf_data, portal_html_data, "BidNet Direct.html")
    
    # Base PDF fields must take precedence over portal export for primary scalar fields
    assert merged["bid_number"] == "JA-207652"
    assert merged["due_date"] == "27-JUN-2024 14:00:00"
    assert merged["pre_bid_meeting"] == "June 10, 2024 at 2:00 PM CST via TEAMS"
    # Lists should complement
    assert "W-9 Form" in merged["additional_documentation_required"]
    assert "Form 1295" in merged["additional_documentation_required"]


@patch('src.processor.LLMExtractor')
def test_primary_porfp_title_precedence_over_portal_html(mock_extractor):
    """
    Test that the primary solicitation/PORFP title is preferred over secondary portal commodity listings.
    """
    processor = RFPProcessor()
    
    primary_porfp_data = {
        "bid_number": "#E20P4600040",
        "title": "Hardware Master Contract",
        "model_no": "SI# CC7802, WD22TB4",
        "part_no": None
    }
    
    portal_html_data = {
        "bid_number": "E20P4600040",
        "title": "Dell Laptops w/Extended Warranty",
        "model_no": "CC7802, WD22TB4",
        "part_no": "WD22TB4"
    }
    
    merged = processor._merge_addendum(primary_porfp_data, portal_html_data, "BidNet Direct.html")
    validated = Validator.validate_and_normalize(merged)
    
    assert validated["title"] == "Hardware Master Contract"
    assert validated["model_no"] == "SI# CC7802, WD22TB4"
    assert validated["part_no"] is None


