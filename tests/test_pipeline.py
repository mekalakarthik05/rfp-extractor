import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.processor import RFPProcessor
from src.schema import RFPData

@patch("src.extractor.genai.Client")
def test_full_pipeline_mocked(mock_client_cls, sample_rfp_dict):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_model = MagicMock()
    mock_model.name = "gemini-flash-latest"
    mock_client.models.list.return_value = [mock_model]

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.text = json.dumps(sample_rfp_dict)
    mock_client.models.generate_content.return_value = mock_response

    with tempfile.TemporaryDirectory() as in_dir, tempfile.TemporaryDirectory() as out_dir:
        # Create a mock html file
        sample_file = Path(in_dir) / "sample_rfp.html"
        sample_file.write_text("<html><body><h1>RFP Document</h1></body></html>", encoding="utf-8")

        processor = RFPProcessor()
        result = processor.process_directory(in_dir, out_dir, apply_grouping=True)

        assert result is not None
        # Verify schema validity
        validated = RFPData.model_validate(result)
        assert validated.bid_number == "RFP-2024-TEST"

        # Check final output file written
        dir_name = Path(in_dir).name
        final_file = Path(out_dir) / f"{dir_name}_final.json"
        assert final_file.exists()
        with open(final_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert len(disk_data) == 20
