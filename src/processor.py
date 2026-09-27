"""
src/processor.py

Directory-level pipeline orchestrator.

Responsibilities:
- Discover supported documents (.pdf, .html, .htm) in a directory.
- Sort base documents before addenda so merging applies in correct order.
- Call LLMExtractor per document, validate output, save individual JSONs.
- Merge all documents into a single final JSON when --group is active.
- Apply addendum precedence rules: later non-null values override earlier ones;
  later null values do NOT erase earlier valid values.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .config import logger
from .exceptions import RFPError
from .extractor import LLMExtractor
from .parser import DocumentParser
from .validators import Validator
from .utils import deduplicate_list_preserve_longest, deduplicate_sentences, split_top_level_delimiters


class RFPProcessor:
    def __init__(
        self,
        max_chunk_chars: Optional[int] = None,
        max_chunks: Optional[int] = None,
    ):
        self.extractor = LLMExtractor(
            max_chunk_chars=max_chunk_chars,
            max_chunks=max_chunks,
        )

    # ── Public entry point ────────────────────────────────────────────────────

    def process_directory(
        self,
        input_dir: str,
        output_dir: str,
        apply_grouping: bool = True,
        save_intermediates: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Process all supported documents in *input_dir*.

        Parameters
        ----------
        input_dir          : directory containing RFP PDFs / HTMLs
        output_dir         : where merged (or individual) JSONs are written
        apply_grouping     : when True, merge all docs + addenda into one final JSON
        save_intermediates : when True, save per-document JSONs alongside final result
        """
        os.makedirs(output_dir, exist_ok=True)

        supported_exts = {".pdf", ".html", ".htm"}
        files = []
        for f in sorted(os.listdir(input_dir)):
            fp = os.path.join(input_dir, f)
            if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in supported_exts:
                files.append(fp)
            elif os.path.isfile(fp):
                logger.warning("Skipping unsupported file: %s", f)

        if not files:
            logger.warning("No supported documents found in %s", input_dir)
            return None

        files_sorted = self._sort_addenda(files)
        merged_data: Dict[str, Any] = {}
        processed_files = 0

        for filepath in files_sorted:
            filename = os.path.basename(filepath)
            try:
                logger.info("── Processing: %s", filename)

                # 1. Parse
                parsed_doc = DocumentParser.parse(filepath)
                logger.info(
                    "   Parsed: %d pages, %d chars, has_tables=%s",
                    parsed_doc.page_count, len(parsed_doc.text), parsed_doc.has_tables,
                )

                # 2. Extract (handles chunking internally)
                raw_json = self.extractor.extract(parsed_doc.text, filename)

                # 3. Validate & normalise
                validated_json = Validator.validate_and_normalize(raw_json)

                # 4. Save individual file extraction result only if requested or not grouping
                if save_intermediates or not apply_grouping:
                    stem = os.path.splitext(filename)[0]
                    ind_out = os.path.join(output_dir, f"{stem}.json")
                    with open(ind_out, "w", encoding="utf-8") as fh:
                        json.dump(validated_json, fh, indent=2, ensure_ascii=False)
                    logger.info("   Saved individual: %s", ind_out)

                # 5. Merge into running result
                if apply_grouping:
                    merged_data = self._merge_addendum(merged_data, validated_json, filename)
                else:
                    merged_data = validated_json

                processed_files += 1
                logger.info("   Done: %s", filename)

            except RFPError as e:
                logger.error("RFP pipeline error on %s: %s", filename, e)
            except Exception as e:
                logger.error("Unexpected error on %s: %s", filename, e, exc_info=True)

        if apply_grouping and processed_files > 0:
            dir_name = os.path.basename(os.path.normpath(input_dir))
            final_out = os.path.join(output_dir, f"{dir_name}_final.json")
            merged_data = Validator.validate_and_normalize(merged_data)
            with open(final_out, "w", encoding="utf-8") as fh:
                json.dump(merged_data, fh, indent=2, ensure_ascii=False)
            logger.info("Saved merged output: %s", final_out)

        logger.info(
            "Directory processing complete. %d/%d files succeeded.",
            processed_files, len(files_sorted),
        )
        return merged_data if processed_files > 0 else None

    # ── Sorting ───────────────────────────────────────────────────────────────

    def _sort_addenda(self, filepaths: List[str]) -> List[str]:
        """
        Sort files according to procurement document precedence:
        1. Primary solicitation PDFs (main RFP/PORFP PDFs sort before supporting PDFs)
        2. Secondary portal summaries (.html/.htm exports) complement base facts
        3. Official Addenda / Amendments (sort by addendum/amendment number)
        """
        def get_sort_key(filepath: str) -> Tuple[int, int, int, str]:
            name = os.path.basename(filepath).lower()
            ext = os.path.splitext(name)[1].lower()

            if "addendum" in name or "amendment" in name:
                match = re.search(r"(addendum|amendment)\s*(\d+)", name)
                num = int(match.group(2)) if match else 999
                return (2, num, 0, name)

            if ext in {".html", ".htm"}:
                return (1, 0, 0, name)

            is_main_rfp = bool(re.search(r"(rfp|porfp|solicitation)", name))
            sub_tier = 0 if is_main_rfp else 1
            return (0, sub_tier, 0, name)

        return sorted(filepaths, key=get_sort_key)

    # ── Merging ───────────────────────────────────────────────────────────────

    def _merge_addendum(
        self,
        base: Dict[str, Any],
        addendum: Dict[str, Any],
        addendum_name: str,
    ) -> Dict[str, Any]:
        """
        Merge *addendum* dict into *base* following addendum precedence rules:
        - If *addendum_name* is an official Addendum/Amendment (contains 'addendum' or 'amendment'):
          A non-null value in *addendum* overrides the base value.
        - If *addendum_name* is another base/supporting document (e.g. HTML web listing or companion spec):
          Base documents complement each other: first non-null value from base documents is preserved.
        - List fields (e.g. additional_documentation_required) are unioned and de-duplicated.
        """
        if not base:
            return addendum.copy()

        is_addendum = bool(re.search(r"(addendum|amendment)", addendum_name.lower()))
        merged = base.copy()

        for key, new_val in addendum.items():
            if new_val is None:
                continue

            old_val = merged.get(key)

            if key == "additional_documentation_required":
                def _to_list(val):
                    if val is None:
                        return []
                    if isinstance(val, list):
                        return [str(v).strip() for v in val if v and str(v).strip()]
                    if isinstance(val, str):
                        return [s.strip() for s in re.split(r'[\n;•]+', val) if s.strip()]
                    return [str(val).strip()]

                combined = _to_list(old_val) + _to_list(new_val)
                if combined:
                    merged[key] = deduplicate_list_preserve_longest(combined)
            else:
                if old_val is None:
                    merged[key] = new_val
                elif is_addendum:
                    if key == "bid_summary" and old_val is not None:
                        if new_val and new_val not in old_val:
                            logger.info(
                                "Addendum append [%s]: '%s' + '%s' (source: %s)",
                                key, str(old_val)[:40], str(new_val)[:40], addendum_name,
                            )
                            merged[key] = f"{old_val} {new_val}"
                    elif key in {"installation", "product_specification"} and old_val is not None:
                        if new_val and isinstance(new_val, str) and isinstance(old_val, str):
                            merged[key] = deduplicate_sentences(f"{old_val} {new_val}")
                    else:
                        if old_val != new_val:
                            logger.info(
                                "Addendum override [%s]: '%s' → '%s' (source: %s)",
                                key, str(old_val)[:80], str(new_val)[:80], addendum_name,
                            )
                        merged[key] = new_val
                else:
                    logger.debug(
                        "Base merge [%s]: keeping existing '%s', ignoring secondary '%s' from %s",
                        key, str(old_val)[:80], str(new_val)[:80], addendum_name,
                    )

        return merged
