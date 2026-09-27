import pytest
from src.validators import normalize_absent_marker, Validator
from src.schema import RFPData
from src.exceptions import SchemaValidationError

def test_normalize_absent_marker():
    assert normalize_absent_marker("N/A") is None
    assert normalize_absent_marker("None") is None
    assert normalize_absent_marker("not specified") is None
    assert normalize_absent_marker("") is None
    assert normalize_absent_marker("  ") is None
    assert normalize_absent_marker("Valid Data") == "Valid Data"
    assert normalize_absent_marker(["N/A", "Valid", ""]) == ["Valid"]
    assert normalize_absent_marker(["N/A"]) is None

def test_validator_success():
    raw = {
        "bid_number": "123",
        "title": "Test Bid",
        "due_date": "N/A",
        "additional_documentation_required": ["W-9", "None"]
    }
    validated = Validator.validate_and_normalize(raw)
    
    assert validated["bid_number"] == "123"
    assert validated["title"] == "Test Bid"
    assert validated["due_date"] is None
    assert validated["additional_documentation_required"] == ["W-9"]
    
    # Assert all 20 keys are present
    assert len(validated) == 20
    assert "company_name" in validated
    assert validated["company_name"] is None

def test_validator_extra_keys_removed_or_fail():
    raw = {
        "bid_number": "123",
        "hallucinated_key": "bad"
    }
    with pytest.raises(SchemaValidationError):
        Validator.validate_and_normalize(raw)


def test_normalize_term_of_bid_proposal_validity():
    raw = {
        "bid_number": "123",
        "term_of_bid": "valid for at least 90 days after the set due date"
    }
    validated = Validator.validate_and_normalize(raw)
    assert validated["term_of_bid"] is None

    raw_proposal_valid = {
        "bid_number": "123",
        "term_of_bid": "proposals provided in response to this PORFP to be valid for at least 90 days"
    }
    validated_proposal = Validator.validate_and_normalize(raw_proposal_valid)
    assert validated_proposal["term_of_bid"] is None

    raw_contract_term = {
        "bid_number": "123",
        "term_of_bid": "three (3) year agreement with two (2) successive one (1) year extensions"
    }
    validated_contract = Validator.validate_and_normalize(raw_contract_term)
    assert validated_contract["term_of_bid"] == "three (3) year agreement with two (2) successive one (1) year extensions"


def test_normalize_part_no_disambiguation():
    # Model code duplicated in part_no is normalized to None
    raw_dup = {
        "bid_number": "123",
        "model_no": "SI# CC7802, WD22TB4",
        "part_no": "WD22TB4"
    }
    validated_dup = Validator.validate_and_normalize(raw_dup)
    assert validated_dup["model_no"] == "SI# CC7802, WD22TB4"
    assert validated_dup["part_no"] is None

    # Distinct part number is preserved
    raw_distinct = {
        "bid_number": "123",
        "model_no": "Latitude 5540",
        "part_no": "210-BLYZ"
    }
    validated_distinct = Validator.validate_and_normalize(raw_distinct)
    assert validated_distinct["model_no"] == "Latitude 5540"
    assert validated_distinct["part_no"] == "210-BLYZ"


