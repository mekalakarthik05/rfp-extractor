import re
from typing import Dict, Any, List
from pydantic import ValidationError
from .schema import RFPData
from .exceptions import SchemaValidationError
from .config import logger
from .utils import deduplicate_list_preserve_longest

def normalize_model_no(value: Any) -> Any:
    """
    Deduplicates model_no comma-separated tokens when one token is a less descriptive
    variant or substring of another (e.g. 'M100' vs 'SI# M100').
    """
    if not isinstance(value, str) or not value.strip():
        return value
    tokens = [t.strip() for t in value.split(',') if t.strip()]
    if len(tokens) <= 1:
        return value
    deduped = deduplicate_list_preserve_longest(tokens)
    return ', '.join(deduped) if deduped else value

def normalize_absent_marker(value: Any) -> Any:
    """
    Normalizes common LLM hallucinations for 'absent' to standard Python None (which translates to null in JSON).
    """
    if value is None:
        return None
        
    if isinstance(value, str):
        val_lower = value.strip().lower()
        absent_markers = ["n/a", "none", "not specified", "null", "undefined", "", "not applicable", "not explicitly stated"]
        if val_lower in absent_markers:
            return None
            
        # Clean up stray markdown artefacts (bullet points, dashes, etc.)
        val_cleaned = re.sub(r'^[\*\-•]+\s*', '', value.strip())
        val_cleaned = val_cleaned.strip()
        if not val_cleaned:
            return None

        # Clean up stray literal null tokens embedded in formatted strings (e.g. 'Name, email, null' -> 'Name, email')
        val_cleaned = re.sub(r',\s*(null|none|n/a|not specified)', '', val_cleaned, flags=re.IGNORECASE)
        val_cleaned = re.sub(r'(null|none|n/a|not specified)\s*,\s*', '', val_cleaned, flags=re.IGNORECASE)
        val_cleaned = val_cleaned.strip()
        if not val_cleaned:
            return None

        return val_cleaned

        
    if isinstance(value, list):
        # Normalize each item, filter out None/empty
        normalized_list = []
        for item in value:
            norm_item = normalize_absent_marker(item)
            if norm_item:
                normalized_list.append(norm_item)
        return normalized_list if normalized_list else None

    return value

def normalize_term_of_bid(value: Any) -> Any:
    """
    Ensure term_of_bid represents contract duration / renewals and does not capture
    proposal or quote validity periods (e.g. 'proposals valid for 90 days').
    """
    if not isinstance(value, str):
        return value
    val_clean = value.strip()
    # Check if value only states proposal/quote validity without contract duration
    is_proposal_validity = bool(
        re.search(r'\b(?:proposals?|quotes?|bids?|pricing)\s+.*?\bvalid\s+for\b', val_clean, re.IGNORECASE)
        or re.search(r'^\s*(?:valid\s+for\s+)?(?:\d+|at\s+least\s+\d+)\s+days(?:\s+after\s+(?:the\s+)?(?:set\s+)?due\s+date)?\.?\s*$', val_clean, re.IGNORECASE)
    )
    if is_proposal_validity and not re.search(r'\b(?:contract|agreement|renewal|performance|period|extensions?)\b', val_clean, re.IGNORECASE):
        return None
    return val_clean


def normalize_part_no(part_no_val: Any, model_no_val: Any) -> Any:
    """
    Ensure part_no is not populated with model identifiers that are already in model_no,
    unless explicitly distinct. If all tokens in part_no already match model_no, return None.
    """
    if not isinstance(part_no_val, str) or not part_no_val.strip():
        return part_no_val
    if not isinstance(model_no_val, str) or not model_no_val.strip():
        return part_no_val

    # Extract clean model tokens
    model_tokens = {m.strip().lower() for m in model_no_val.split(',') if m.strip()}
    model_words = set(re.findall(r'[A-Za-z0-9#-]+', model_no_val.lower()))

    part_tokens = [p.strip() for p in part_no_val.split(',') if p.strip()]
    distinct_parts = []
    for p in part_tokens:
        p_lower = p.lower()
        if p_lower in model_tokens or p_lower in model_words:
            continue
        distinct_parts.append(p)

    if not distinct_parts:
        return None
    return ', '.join(distinct_parts)


class Validator:
    """
    Validates and normalizes raw dictionary outputs from the LLM.
    """
    @staticmethod
    def validate_and_normalize(raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes raw dictionary from LLM, normalizes 'absent' markers to None,
        and validates it strictly against the RFPData schema.
        """
        normalized_data = {}
        for key, value in raw_data.items():
            norm_val = normalize_absent_marker(value)
            if key == "term_of_bid":
                norm_val = normalize_term_of_bid(norm_val)
            normalized_data[key] = norm_val

        # Normalize model_no tokens
        normalized_data["model_no"] = normalize_model_no(normalized_data.get("model_no"))

        # Disambiguate part_no vs model_no
        normalized_data["part_no"] = normalize_part_no(
            normalized_data.get("part_no"),
            normalized_data.get("model_no")
        )
            
        try:
            # Validate using Pydantic. strict=False allows some coercion (e.g. string to list of strings if configured),
            # but model_config forbid extra fields ensures no hallucinated keys.
            validated = RFPData(**normalized_data)
            
            # Convert back to dict, preserving order and None
            final_dict = validated.model_dump()
            
            # Double check all 20 keys are present in the final output
            schema_keys = list(RFPData.model_fields.keys())
            for key in schema_keys:
                if key not in final_dict:
                    logger.warning(f"Key {key} was dropped during validation. Re-inserting as None.")
                    final_dict[key] = None
                    
            return final_dict
            
        except ValidationError as e:
            raise SchemaValidationError(f"Validation failed: {e}")
