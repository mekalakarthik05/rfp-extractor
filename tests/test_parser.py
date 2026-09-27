import tempfile
import pytest
from pathlib import Path
from src.parser import DocumentParser
from src.exceptions import UnsupportedFormatError, EmptyDocumentError

def test_parse_html(sample_html_content):
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(sample_html_content)
        temp_path = f.name

    try:
        doc = DocumentParser.parse(temp_path)
        assert "Student Computing Devices" in doc.text
        assert "JA-207652" in doc.text
        assert "Home" not in doc.text  # Nav tag decomposed
        assert "Copyright 2024" not in doc.text  # Footer tag decomposed
        assert doc.has_tables is True
        assert "Chromebook" in doc.text
    finally:
        Path(temp_path).unlink(missing_ok=True)

def test_unsupported_format():
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False, mode="w") as f:
        f.write("Some text")
        temp_path = f.name

    try:
        with pytest.raises(UnsupportedFormatError):
            DocumentParser.parse(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)

def test_empty_html():
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        f.write("<html><body>   </body></html>")
        temp_path = f.name

    try:
        with pytest.raises(EmptyDocumentError):
            DocumentParser.parse(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
