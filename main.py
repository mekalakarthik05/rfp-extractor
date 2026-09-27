"""
main.py — RFP Document Information Extractor CLI

Usage examples:
    # Process Bid1 directory (group + addendum resolution)
    python main.py --input data/input/Bid1 --output data/output/Bid1 --group

    # Process Bid2 directory
    python main.py --input data/input/Bid2 --output data/output/Bid2 --group

    # Single file
    python main.py --input data/input/Bid1/RFP.pdf --output data/output/Bid1

    # Dry-run: show chunking plan without calling the LLM
    python main.py --input data/input/Bid1 --output data/output/Bid1 --group --dry-run

    # Override chunking parameters
    python main.py --input data/input/Bid1 --output data/output/Bid1 --group \\
        --max-chunk-size 8000 --max-chunks 6
"""
import argparse
import json
import os
import sys

from src.config import logger


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RFP Document Information Extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", required=True, help="Path to input directory or single file.")
    parser.add_argument("--output", required=True, help="Path to output directory.")
    parser.add_argument(
        "--group",
        action="store_true",
        help="Group all documents in the directory as one bid and apply addendum resolution.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG-level logging.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Parse documents and show chunking plan without making LLM calls. "
            "Useful for estimating API call count before a full run."
        ),
    )
    parser.add_argument(
        "--max-chunk-size",
        type=int,
        default=None,
        metavar="CHARS",
        help="Override soft chunk size in characters (default: from MAX_CHUNK_SIZE env var).",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        metavar="N",
        help="Override maximum LLM calls per document (default: from MAX_CHUNKS env var).",
    )

    args = parser.parse_args()

    if args.verbose:
        import logging
        logger.setLevel(logging.DEBUG)

    input_path = args.input
    output_path = args.output

    # ── Dry-run: parse + chunk only, no LLM calls ────────────────────────────
    if args.dry_run:
        from src.parser import DocumentParser
        from src.chunker import chunk_text
        from src.config import MAX_CHUNK_CHARS, MAX_CHUNKS

        max_chars = args.max_chunk_size or MAX_CHUNK_CHARS
        max_chunks = args.max_chunks or MAX_CHUNKS

        files_to_check: list[str] = []
        if os.path.isfile(input_path):
            files_to_check = [input_path]
        elif os.path.isdir(input_path):
            supported = {".pdf", ".html", ".htm"}
            for f in sorted(os.listdir(input_path)):
                if os.path.splitext(f)[1].lower() in supported:
                    files_to_check.append(os.path.join(input_path, f))

        print(f"\n{'='*60}")
        print(f"DRY-RUN CHUNKING PLAN  (max_chars={max_chars}, max_chunks={max_chunks})")
        print(f"{'='*60}")
        for fp in files_to_check:
            try:
                doc = DocumentParser.parse(fp)
                chunks = chunk_text(doc.text, max_chars, max_chunks)
                print(f"\n{os.path.basename(fp)}")
                print(f"  Total chars : {len(doc.text):,}")
                print(f"  Chunks      : {len(chunks)}")
                for i, c in enumerate(chunks):
                    preview = c[:80].replace("\n", " ").strip()
                    print(f"  [{i+1:02d}] {len(c):>6} chars — {preview!r}")
            except Exception as e:
                print(f"  ERROR parsing {fp}: {e}")
        print()
        return 0

    # ── Normal pipeline run ───────────────────────────────────────────────────
    from src.processor import RFPProcessor

    processor = RFPProcessor(
        max_chunk_chars=args.max_chunk_size,
        max_chunks=args.max_chunks,
    )

    if os.path.isfile(input_path):
        from src.parser import DocumentParser
        from src.validators import Validator

        logger.info("Processing single file: %s", input_path)
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        try:
            doc = DocumentParser.parse(input_path)
            raw = processor.extractor.extract(doc.text, os.path.basename(input_path))
            validated = Validator.validate_and_normalize(raw)
            out_file = os.path.join(
                output_path,
                f"{os.path.splitext(os.path.basename(input_path))[0]}.json",
            )
            with open(out_file, "w", encoding="utf-8") as fh:
                json.dump(validated, fh, indent=2, ensure_ascii=False)
            logger.info("Saved to %s", out_file)
        except Exception as e:
            logger.error("Failed processing %s: %s", input_path, e)
            return 1

    elif os.path.isdir(input_path):
        logger.info("Processing directory: %s", input_path)
        processor.process_directory(input_path, output_path, apply_grouping=args.group)

    else:
        logger.error("Input path does not exist: %s", input_path)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
