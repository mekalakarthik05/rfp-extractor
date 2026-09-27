import pytest

@pytest.fixture
def sample_rfp_dict():
    return {
        "bid_number": "RFP-2024-TEST",
        "title": "IT Equipment and Maintenance",
        "due_date": "2024-11-15 14:00 EST",
        "bid_submission_type": "Electronic via Vendor Portal",
        "term_of_bid": "3 years",
        "pre_bid_meeting": "2024-10-20 10:00 EST",
        "installation": "Not required",
        "bid_bond_requirement": "5%",
        "delivery_date": "Within 30 days of PO",
        "payment_terms": "Net 30",
        "additional_documentation_required": ["W-9", "Certificate of Insurance"],
        "mfg_for_registration": "Dell",
        "contract_or_cooperative_to_use": "NASPO ValuePoint",
        "model_no": "Latitude 5540",
        "part_no": "210-BFKX",
        "product": "Laptops and Accessories",
        "contact_info": "Jane Doe, jdoe@example.gov, 555-0199",
        "company_name": "State Department of Transportation",
        "bid_summary": "Solicitation for commercial laptops and accessories for state agency staff.",
        "product_specification": "Intel Core i7, 16GB RAM, 512GB NVMe SSD, 15.6 inch FHD display."
    }

@pytest.fixture
def sample_html_content():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test RFP Portal</title></head>
    <body>
        <nav><a href="/home">Home</a></nav>
        <h1>Solicitation: Student Computing Devices</h1>
        <div class="meta">Bid Number: JA-207652</div>
        <table>
            <tr><th>Item</th><th>Qty</th></tr>
            <tr><td>Chromebook</td><td>500</td></tr>
        </table>
        <footer>Copyright 2024</footer>
    </body>
    </html>
    """
