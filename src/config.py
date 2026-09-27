import os
import logging
from dotenv import load_dotenv
from .exceptions import ConfigurationError

load_dotenv()


def get_api_key(provider: str) -> str:
    key = os.getenv(f"{provider.upper()}_API_KEY", "").strip()
    if not key:
        raise ConfigurationError(
            f"Missing {provider.upper()}_API_KEY in environment. "
            "Please copy .env.example to .env and fill in your key."
        )
    return key


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
if LLM_PROVIDER != "gemini":
    logging.warning("Only 'gemini' is fully supported in this implementation.")

# Model – prefer what .env says; default to gemini-flash-latest (confirmed available).
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-flash-latest")

# Fallback models tried in order when the primary returns 503/overloaded.
# gemini-2.5-flash is 404 on free-tier new accounts; skip to flash-latest first.
FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]


# Chunking configuration
# Documents larger than this character count are chunked before LLM extraction.
# Soft target: a chunk aims to be <= MAX_CHUNK_CHARS.
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_SIZE", "6000"))

# Hard cap: never send more than this many LLM calls per document.
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", "8"))

# Retry configuration
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "4"))
RETRY_BASE_SLEEP = 5  # seconds

# Scanned-PDF heuristic: fewer than this many chars per page → probably scanned / no text layer
SCANNED_PDF_THRESHOLD_CHARS = 100

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("RFP_Extractor")
