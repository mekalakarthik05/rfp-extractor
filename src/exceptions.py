class RFPError(Exception):
    """Base exception for RFP Extractor."""
    pass

class UnsupportedFormatError(RFPError):
    """Raised when a file format is not supported."""
    pass

class EmptyDocumentError(RFPError):
    """Raised when a document yields no extractable text."""
    pass

class ScannedPDFError(RFPError):
    """Raised when a PDF is determined to be scanned (needs OCR)."""
    pass

class ParsingError(RFPError):
    """Raised when an error occurs during parsing (e.g., corrupt PDF)."""
    pass

class LLMAPIError(RFPError):
    """Raised when the LLM API fails completely."""
    pass

class RateLimitError(RFPError):
    """Raised when rate limits are exhausted and retries fail."""
    pass

class SchemaValidationError(RFPError):
    """Raised when the final JSON output fails Pydantic validation."""
    pass

class ConfigurationError(RFPError):
    """Raised when environment variables or configurations are missing."""
    pass
