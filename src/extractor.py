import re
"""
src/extractor.py

LLM-based field extractor for RFP documents.

Key design decisions:
- Uses google-genai SDK (google.genai) v2+, NOT google-generativeai.
- Tries the configured MODEL_NAME first, then FALLBACK_MODELS in order.
- Respects RetryInfo / Retry-After delays on 429 RESOURCE_EXHAUSTED.
- Falls back to exponential back-off (5s, 10s, 20s, 40s) for 503/transient errors.
- Chunks large documents via src.chunker and merges results deterministically.
- The final merged dict is returned for Pydantic validation upstream.
"""
import json
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from .chunker import chunk_text
from .config import (
    FALLBACK_MODELS,
    MAX_CHUNKS,
    MAX_CHUNK_CHARS,
    MAX_RETRIES,
    MODEL_NAME,
    RETRY_BASE_SLEEP,
    get_api_key,
    logger,
)
from .exceptions import LLMAPIError, RateLimitError, SchemaValidationError
from .schema import RFPData
from .utils import deduplicate_list_preserve_longest, deduplicate_sentences, split_top_level_delimiters

# ── Prompt constants ─────────────────────────────────────────────────────────

_SCHEMA_KEYS: List[str] = list(RFPData.model_fields.keys())

_NULL_TEMPLATE: str = json.dumps({k: None for k in _SCHEMA_KEYS}, indent=2)

SYSTEM_PROMPT = """You are a highly precise procurement-document extraction assistant.

RULES (non-negotiable):
1. Extract ONLY what is explicitly present in the provided text. Never infer, guess, or use background knowledge about typical procurement terms.
2. If a field is absent or uncertain, output null. A null is correct; a guess is a failure.
3. Preserve exact source strings for identifiers, numbers, codes, amounts, dates.
4. Distinguish confusable fields:
   - title: formal procurement, master contract, or project title as stated on the header/cover of the solicitation (i.e. the formal title appearing directly under or alongside the solicitation header on the cover/first page). Always extract the formal solicitation title from the document header. Do NOT return null if a header title is present, and do NOT extract secondary portal commodity listings or portal item descriptions. Do not include document-type prefix wrappers (like 'Purchase Order Request for Proposals (PORFP)' or 'Request for Proposals').
   - due_date: bid/proposal SUBMISSION deadline (with time + timezone). Not question deadline, not pre-bid meeting, not delivery date.
   - pre_bid_meeting: date, time, timezone, physical location, and/or virtual meeting details (platform name, join URL, Meeting ID, and Passcode). Note whether attendance is mandatory. Do NOT truncate or omit virtual meeting connection credentials (Meeting ID, Passcode, join URL) when present in the source. Return null if absent.
   - delivery_date: delivery deadline, delivery timeframe, or anticipated delivery schedule/timing explicitly stated in the source (e.g. 'Within 45 days of Award', 'anticipated starting Q4 2025', specific date). If only an anticipated quote/order start timeframe or delivery schedule is stated, extract that timing. Return null only if no delivery dates or schedule timing are mentioned.
   - term_of_bid: contract duration, performance period, renewal/extension options, and any maximum total duration limit (e.g. '3-year agreement with two 1-year extensions, not to exceed 5 years total'). Do NOT classify proposal/quote validity periods (e.g. 'proposals valid for 90 days', 'quotes valid for 60 days') as term_of_bid. If no contract duration or performance term is stated, return null.
   - bid_bond_requirement: exact percentage or flat amount, or explicit "not required". Never assume 5%.
   - payment_terms: null if not stated. Never default to "Net 30".
   - model_no: model name, model number, or SI system identifier (e.g. Model-A, SI# 12345). Join distinct models with ', '. Never guess.
   - part_no: manufacturer part number, part no., or catalog order code explicitly designated/labeled as 'Part Number', 'Part #', 'P/N', or 'MPN' for the overall procured product(s) in the solicitation. Do NOT extract internal sub-component build option codes or configuration breakdown lists (such as processor, memory, storage, or component SKU tables). Do NOT treat model numbers, SI identifiers, or accessory model codes as part numbers. Return null if no explicit overall product part number is designated in the source.
   - mfg_for_registration: only where bidder must be a registered/authorised partner. A brand name with "or equal" is NOT this field.
   - contract_or_cooperative_to_use: the purchasing cooperative or master contract vehicle (e.g. Master Contract number/name, NASPO, Sourcewell, OMNIA, GSA, state cooperative) that this procurement is being conducted under or that the bidder must use to submit/respond. Do NOT extract cooperatives, alliances, or entities that are merely mentioned as authorized to ride/piggyback or potentially use the resulting contract after award (e.g. interlocal agreement / rider clauses). If no cooperative vehicle is being used to procure this bid, return null.
   - bid_submission_type: submission mechanism and platform (e.g. portal name and URL, or sealed hard copy address, or email). When both the system/portal name and URL or submission instructions are present, preserve both (e.g. 'State eMMA portal (https://...)').
   - contact_info: procurement contact name + email + phone for bid questions. Only include details explicitly present in the source (e.g. 'Name, email, phone' or 'Name, email'). Do NOT insert literal 'null' or placeholder tokens for missing parts. Single person/department only.
   - company_name: issuing agency/municipality/school district. Not the consultant, not the incumbent.
   - additional_documentation_required: list each specific document, form, certification, supporting documentation (including competence/reference/project summaries), attachment, plan, worksheet, or affidavit explicitly required or requested for the bidder to submit, provide, or attach. Return as a JSON list of strings with each requirement as a separate list element (do not bundle distinct requirements into one item). When an addendum requires signing/acknowledging the addendum, include the specific addendum number/identifier from the header (e.g. 'Signed Addendum No. 1', 'Signed Addendum No. 2'). Keep parenthetical details and explanatory clauses intact as part of their respective item (do not drop parentheticals). Crucially preserve source qualifiers and conditions (e.g. 'Signed Addendum No. 1', 'Form A - OPTIONAL', 'credit application (if required)', 'Letter of Authorization (if requested)', 'Warranty certificate or Affidavit upon award'). Do not invent standard forms. Do NOT extract historical or prior affidavits (such as a 'Proposal Affidavit' merely referenced inside a Contract Affidavit clause affirming prior statements) unless the document explicitly requires submitting that affidavit.
   - bid_summary: 2-3 factual sentences capturing the core procurement scope: procurement purpose, quantities (e.g. unit counts), products/models, target department or use-case, and major commercial requirement (e.g. warranty/reseller requirement) when explicitly stated in the source. If an addendum changes an important condition (e.g. deadline), include that change. If the text is a short document lacking procurement scope, return null.
   - product_specification: capture important explicit technical/product requirements, specifications, standards, certifications, warranties (e.g. 3-year warranty, OEM warranty requirements, standard 1-year warranty), and required product characteristics (e.g. USB specification requirements, display requirements, Copilot ready, ENERGY STAR certified, new and unused equipment, no Accidental Damage Protection, etching, provisioning enrollment). Never infer missing specifications.
   - installation: capture explicit deployment, setup, or configuration requirements. This includes software installation, device deployment/setup, asset tagging/etching/decaling, asset control reporting, specialized deployment services, and deployment technical requirements (e.g. provisioning enrollment, on-site configuration). Do NOT infer from mere delivery without installation/deployment services. Return null if absent.
5. Output must be valid JSON with EXACTLY the schema keys provided. No extra keys.
"""


def _build_prompt(text: str, document_name: Optional[str] = None, chunk_index: Optional[int] = None, total_chunks: Optional[int] = None) -> str:
    """Build the user prompt for a single chunk (or the whole document)."""
    chunk_note = ""
    doc_info = f" from document '{document_name}'" if document_name else ""
    if chunk_index is not None:
        chunk_note = (
            f"\n[NOTE: This is chunk {chunk_index + 1} of {total_chunks}{doc_info}. "
            "Extract only fields that are clearly present in this chunk. "
            "Return null for fields not found here — they may appear in other chunks.]\n"
        )
    return (
        f"{chunk_note}"
        f"Return a JSON object with EXACTLY these keys (use null for absent fields):\n"
        f"{_NULL_TEMPLATE}\n\n"
        f"DOCUMENT TEXT:\n{text}"
    )


# ── Retry helpers ─────────────────────────────────────────────────────────────

def _get_retry_delay(exc: Exception, attempt: int) -> float:
    """
    Return the number of seconds to wait before the next attempt.
    Respects RetryInfo metadata from the Gemini SDK where available.
    Falls back to bounded exponential back-off.
    """
    # Try to read RetryInfo from google.api_core exception metadata
    retry_delay = None
    for attr in ("retry_info", "_retry_info", "details"):
        val = getattr(exc, attr, None)
        if val is not None:
            # RetryInfo may be a proto object with .retry_delay.seconds
            rd = getattr(val, "retry_delay", None) if not isinstance(val, list) else None
            if rd:
                retry_delay = getattr(rd, "seconds", None)
            break

    if retry_delay and retry_delay > 0:
        logger.info("  Respecting API RetryInfo delay: %ds", retry_delay)
        return float(retry_delay)

    # Exponential back-off: 5, 10, 20, 40 seconds, capped at 60
    return min(RETRY_BASE_SLEEP * (2 ** (attempt - 1)), 60.0)


def _is_retryable(exc: Exception) -> bool:
    """Return True if the error is transient and worth retrying."""
    err_str = str(exc)
    return any(code in err_str for code in ("429", "500", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


# ── Core LLM call ─────────────────────────────────────────────────────────────

class LLMExtractor:
    """Wraps the Gemini API with chunking, retry, and merge logic."""

    def __init__(self, max_chunk_chars: Optional[int] = None, max_chunks: Optional[int] = None):
        api_key = get_api_key("gemini")
        self._client = genai.Client(api_key=api_key)
        self._max_chunk_chars = max_chunk_chars or MAX_CHUNK_CHARS
        self._max_chunks = max_chunks or MAX_CHUNKS
        # Verify at least one model is usable (lightweight check)
        self._active_model = self._resolve_model()
        logger.info("LLMExtractor initialised. Active model: %s", self._active_model)

    def _resolve_model(self) -> str:
        """
        Return the first model in the preference list that the API recognises.
        Uses list_models() to avoid wasting quota on an invalid model call.
        """
        try:
            available = {m.name for m in self._client.models.list()}
        except Exception as e:
            logger.warning("Could not list models: %s. Using configured MODEL_NAME.", e)
            return MODEL_NAME

        preference = [MODEL_NAME] + [m for m in FALLBACK_MODELS if m != MODEL_NAME]
        for candidate in preference:
            # Model names may appear as bare name or with 'models/' prefix
            if candidate in available or f"models/{candidate}" in available:
                return candidate

        logger.warning("Could not confirm any preferred model via list_models(). Using %s.", MODEL_NAME)
        return MODEL_NAME

    def _call_api(self, prompt: str, document_name: str) -> str:
        """
        Make ONE Gemini API call with the current active model.
        Retries on transient errors (429, 503) with back-off.
        If the primary model consistently fails, tries FALLBACK_MODELS.
        Returns the raw response text.
        """
        models_to_try = [self._active_model] + [
            m for m in FALLBACK_MODELS if m != self._active_model
        ]

        last_exc: Optional[Exception] = None
        for model_name in models_to_try:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logger.info("  API call model=%s attempt=%d/%d", model_name, attempt, MAX_RETRIES)
                    resp = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    )
                    # Update active model on success so future calls skip failed models
                    if model_name != self._active_model:
                        logger.info("  Switching active model to %s", model_name)
                        self._active_model = model_name
                    return resp.text

                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc)
                    logger.warning("  model=%s attempt=%d error: %s", model_name, attempt, err_str[:200])

                    if not _is_retryable(exc):
                        # Non-transient error for this model (e.g. 404); skip to next model
                        logger.warning("  Non-retryable error for model %s. Trying next.", model_name)
                        break

                    if attempt < MAX_RETRIES:
                        delay = _get_retry_delay(exc, attempt)
                        logger.info("  Waiting %.1fs before retry...", delay)
                        time.sleep(delay)
                    else:
                        logger.warning("  Exhausted %d retries for model %s.", MAX_RETRIES, model_name)
                        break

        raise RateLimitError(
            f"All models failed for '{document_name}'. Last error: {last_exc}"
        )

    def _extract_single(self, text: str, document_name: str,
                         chunk_index: Optional[int] = None,
                         total_chunks: Optional[int] = None) -> Dict[str, Any]:
        """Extract fields from a single text block. Returns a raw dict."""
        prompt = _build_prompt(text, document_name, chunk_index, total_chunks)
        raw_text = self._call_api(prompt, document_name)

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            # Attempt to salvage: strip markdown code fences if model misbehaved
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
                if cleaned.endswith("```"):
                    cleaned = cleaned[: -3]
            try:
                data = json.loads(cleaned.strip())
            except json.JSONDecodeError:
                raise SchemaValidationError(
                    f"LLM returned non-JSON for '{document_name}': {e}. "
                    f"Raw (first 400 chars): {raw_text[:400]}"
                )

        # Sanitize types: only additional_documentation_required may be a list
        cleaned_data = {}
        for k, v in data.items():
            if k == "additional_documentation_required":
                if isinstance(v, str):
                    cleaned_data[k] = [s.strip() for s in re.split(r'[\n;•]+', v) if s.strip()]
                elif isinstance(v, list):
                    cleaned_data[k] = [str(x).strip() for x in v if x and str(x).strip()]
                else:
                    cleaned_data[k] = v
            else:
                if isinstance(v, list):
                    cleaned_data[k] = " ".join(str(x).strip() for x in v if x and str(x).strip())
                else:
                    cleaned_data[k] = v

        return cleaned_data

    # Fields whose per-chunk values should be unioned (comma-joined) rather than
    # using first-non-null-wins, because a single procurement may legitimately
    # contain multiple distinct values spread across chunks (e.g. two products
    # each with their own model number).
    _COMMA_UNION_FIELDS: frozenset = frozenset({"model_no", "part_no"})
    _TEXT_CONCAT_FIELDS: frozenset = frozenset({"installation", "product_specification"})

    @staticmethod
    def _merge_chunk_results(chunks_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Deterministic merge of per-chunk extraction dicts.

        Rules:
        - For list fields (e.g. additional_documentation_required): union + dedup.
        - For comma-union scalar fields (model_no, part_no): union distinct tokens
          joined with ', ' so that multiple models/parts from different chunks are
          all preserved rather than the later one being silently dropped.
        - For all other scalar fields: first non-null value wins.
          Conflicts are logged as warnings.

        Note: addendum-level overrides are handled separately in processor.py.
        """
        merged: Dict[str, Any] = {k: None for k in _SCHEMA_KEYS}

        for chunk_dict in chunks_data:
            for key in _SCHEMA_KEYS:
                new_val = chunk_dict.get(key)
                current_val = merged.get(key)

                if new_val is None:
                    continue  # Nothing to merge

                if key == "additional_documentation_required":
                    def _to_list(val):
                        if val is None:
                            return []
                        if isinstance(val, list):
                            return [str(v).strip() for v in val if v and str(v).strip()]
                        if isinstance(val, str):
                            return [s.strip() for s in re.split(r'[\n;•]+', val) if s.strip()]
                        return [str(val).strip()]

                    combined = _to_list(current_val) + _to_list(new_val)
                    if combined:
                        merged[key] = deduplicate_list_preserve_longest(combined)

                elif key in LLMExtractor._COMMA_UNION_FIELDS:
                    # Union distinct comma-separated tokens across chunks, preserving longest/most descriptive
                    if current_val is None:
                        merged[key] = new_val
                    else:
                        existing_tokens = [t.strip() for t in current_val.split(',') if t.strip()]
                        new_tokens = [t.strip() for t in new_val.split(',') if t.strip()]
                        combined = existing_tokens + new_tokens
                        deduped = deduplicate_list_preserve_longest(combined)
                        if deduped:
                            merged[key] = ', '.join(deduped)
                            logger.info(
                                "  Merged %s tokens into [%s]: '%s'",
                                key, key, merged[key]
                            )

                elif key in LLMExtractor._TEXT_CONCAT_FIELDS:
                    if current_val is None:
                        merged[key] = deduplicate_sentences(new_val) if isinstance(new_val, str) else new_val
                    elif new_val and isinstance(new_val, str) and isinstance(current_val, str):
                        merged[key] = deduplicate_sentences(f"{current_val} {new_val}")

                elif key == "bid_submission_type":
                    if current_val is None:
                        merged[key] = new_val
                    elif isinstance(new_val, str) and isinstance(current_val, str):
                        if len(new_val) > len(current_val) and (current_val.lower() in new_val.lower() or "http" in new_val.lower()):
                            merged[key] = new_val

                else:
                    if current_val is None:
                        merged[key] = new_val
                    elif current_val != new_val:
                        logger.warning(
                            "  Field conflict [%s]: keeping '%s', ignoring '%s' (from later chunk).",
                            key, str(current_val)[:80], str(new_val)[:80],
                        )
                        # Keep earlier value (first non-null wins within same document)

        return merged

    def extract(self, text: str, document_name: str) -> Dict[str, Any]:
        """
        Public interface.  Returns a raw dict ready for Pydantic validation.

        If the document is small, a single LLM call is made.
        If large, it is chunked and results are merged deterministically.
        """
        chunks = chunk_text(text, self._max_chunk_chars, self._max_chunks)
        total = len(chunks)
        logger.info("Extracting '%s': %d chunk(s), ~%d chars total.", document_name, total, len(text))

        if total == 1:
            return self._extract_single(text, document_name)

        chunk_results: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            logger.info("Processing chunk %d/%d for '%s'...", i + 1, total, document_name)
            result = self._extract_single(chunk, document_name, chunk_index=i, total_chunks=total)
            chunk_results.append(result)

        merged = self._merge_chunk_results(chunk_results)
        logger.info("Merged %d chunks for '%s'.", total, document_name)
        return merged
