import pytest
from pydantic import ValidationError
from src.schema import RFPData

def test_rfp_data_has_exactly_20_fields():
    fields = list(RFPData.model_fields.keys())
    assert len(fields) == 20
    expected = [
        "bid_number", "title", "due_date", "bid_submission_type", "term_of_bid",
        "pre_bid_meeting", "installation", "bid_bond_requirement", "delivery_date",
        "payment_terms", "additional_documentation_required", "mfg_for_registration",
        "contract_or_cooperative_to_use", "model_no", "part_no", "product",
        "contact_info", "company_name", "bid_summary", "product_specification"
    ]
    assert fields == expected

def test_rfp_data_valid(sample_rfp_dict):
    data = RFPData(**sample_rfp_dict)
    assert data.bid_number == "RFP-2024-TEST"
    assert data.model_no == "Latitude 5540"
    assert len(data.additional_documentation_required) == 2

def test_rfp_data_forbids_extra_fields(sample_rfp_dict):
    sample_rfp_dict["extra_field"] = "unexpected"
    with pytest.raises(ValidationError):
        RFPData(**sample_rfp_dict)

def test_rfp_data_allows_all_none():
    empty_data = {k: None for k in RFPData.model_fields.keys()}
    model = RFPData(**empty_data)
    dumped = model.model_dump()
    assert len(dumped) == 20
    assert all(v is None for v in dumped.values())
