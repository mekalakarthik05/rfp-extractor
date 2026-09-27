# Automated RFP Information Extraction with LLMs

## 1. Overview

This project provides an automated pipeline for extracting structured procurement and Request for Proposal (RFP) metadata from PDF and HTML documents.

The pipeline combines document parsing, table extraction, context-aware chunking, structured LLM extraction using Google Gemini models, deterministic multi-chunk and multi-file aggregation, normalization, and Pydantic schema validation to produce consistent 20-field procurement JSON outputs.

---

## 2. Project Structure

```text
rfp-extractor/
│
├── data/
│   ├── input/
│   │   ├── Bid1/
│   │   │   ├── JA-207652 Student and Staff Computing Devices FINAL.pdf
│   │   │   ├── Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html
│   │   │   ├── Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf
│   │   │   └── Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf
│   │   │
│   │   └── Bid2/
│   │       ├── PORFP_-_Dell_Laptop_Final.pdf
│   │       ├── Contract_Affidavit.pdf
│   │       ├── Dell_Laptop_Specs.pdf
│   │       ├── Mercury_Affidavit.pdf
│   │       └── Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html
│   │
│   └── output/
│       ├── Bid1/
│       │   └── Bid1_final.json
│       └── Bid2/
│           └── Bid2_final.json
│
├── src/
│   ├── __init__.py
│   ├── chunker.py
│   ├── config.py
│   ├── exceptions.py
│   ├── extractor.py
│   ├── parser.py
│   ├── processor.py
│   ├── schema.py
│   ├── utils.py
│   └── validators.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_chunker.py
│   ├── test_extractor.py
│   ├── test_parser.py
│   ├── test_pipeline.py
│   ├── test_processor.py
│   ├── test_schema.py
│   ├── test_utils.py
│   └── test_validators.py
│
├── main.py
├── requirements.txt
├── README.md
├── .env.example
└── .gitignore
````

---

## 3. Requirements

* **Python:** 3.10–3.12
* Dependencies are pinned in `requirements.txt`.

Key dependencies include:

* `pydantic==2.13.5`
* `pymupdf==1.27.2.3`
* `pdfplumber==0.11.10`
* `beautifulsoup4==4.15.0`
* `lxml==6.1.1`
* `python-dotenv==1.0.1`
* `google-genai==2.24.0`
* `pytest==9.1.1`
* `pytest-mock==3.15.1`

---

## 4. Setup

### Create and activate a virtual environment

```bash
python -m venv .venv
```

**Windows:**

```powershell
.venv\Scripts\activate
```

**Linux / macOS:**

```bash
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

---

## 5. API Key Configuration

The extraction pipeline requires a Gemini API key configured through environment variables.

Copy the example configuration file:

```bash
cp .env.example .env
```

Populate `.env` with the required configuration:

```env
GEMINI_API_KEY=your_gemini_api_key_here
LLM_PROVIDER=gemini
MODEL_NAME=gemini-flash-latest
```

The Gemini API key can be obtained from Google AI Studio:

[https://aistudio.google.com/](https://aistudio.google.com/)

Do not commit `.env` or any real API keys to version control.

---

## 6. Input Documents

Input documents are stored under:

```text
data/input/
├── Bid1/
└── Bid2/
```

The pipeline supports:

* **PDF (`.pdf`)** — parsed using PyMuPDF for document text/layout and pdfplumber for table extraction.
* **HTML (`.html`, `.htm`)** — cleaned and parsed using BeautifulSoup with lxml.

Multiple documents belonging to the same solicitation can be processed together using the grouped processing option.

---

## 7. Running the Extraction

### Process a complete solicitation directory

This is the recommended approach when a solicitation contains multiple documents or addenda.

```bash
python main.py --input data/input/Bid1 --output data/output/Bid1 --group
```

```bash
python main.py --input data/input/Bid2 --output data/output/Bid2 --group
```

### Process a single document

```bash
python main.py --input data/input/Bid2/PORFP_-_Dell_Laptop_Final.pdf --output data/output/Bid2
```

### Dry run

A dry run parses the documents and displays the chunking plan without making LLM API calls.

```bash
python main.py --input data/input/Bid1 --output data/output/Bid1 --group --dry-run
```

### CLI Options

| Option             | Description                                                              |
| ------------------ | ------------------------------------------------------------------------ |
| `--input`          | Input directory or individual PDF/HTML file                              |
| `--output`         | Output directory                                                         |
| `--group`          | Process all files in a directory as one solicitation and resolve addenda |
| `--dry-run`        | Inspect parsing and chunking without making LLM calls                    |
| `--verbose`        | Enable debug-level logging                                               |
| `--max-chunk-size` | Override the default character chunk limit                               |
| `--max-chunks`     | Override the maximum chunk budget per document                           |

---

## 8. Processing Pipeline

The extraction process follows a staged workflow:

```text
Input Document(s)
       │
       ▼
Document Parsing
(PyMuPDF / pdfplumber / BeautifulSoup)
       │
       ▼
Context Size Evaluation
       │
       ▼
Sentence-Boundary Chunking
(when required)
       │
       ▼
LLM Extraction
(Gemini structured extraction)
       │
       ▼
Chunk & File Aggregation
(Addendum ordering and precedence)
       │
       ▼
Normalization & Deduplication
       │
       ▼
Pydantic Schema Validation
       │
       ▼
Structured JSON Output
```

---

## 9. Context Handling / Chunking

Documents are evaluated against the configured context limits before extraction.

* Documents within the configured character limit can be processed as a single context.
* Larger documents are divided into logical chunks using sentence and paragraph boundaries.
* Chunks use overlap to reduce the possibility of losing information across boundaries.
* A maximum chunk budget is used to keep processing predictable.
* Chunk-level results are aggregated deterministically.
* List and multi-value fields are combined and deduplicated.
* Text fields are merged while preserving relevant source information.
* Addenda are processed with ordering and precedence rules.

The default CLI values are:

```text
Maximum chunk size: 6000 characters
Maximum chunks: 8
Overlap: 300 characters
```

These values can be overridden using the corresponding CLI options.

---

## 10. Output

The pipeline produces structured JSON files following the required 20-field `RFPData` schema.

Final outputs:

```text
data/output/Bid1/Bid1_final.json
data/output/Bid2/Bid2_final.json
```

### 20-Field Output Schema

1. `bid_number`
2. `title`
3. `due_date`
4. `bid_submission_type`
5. `term_of_bid`
6. `pre_bid_meeting`
7. `installation`
8. `bid_bond_requirement`
9. `delivery_date`
10. `payment_terms`
11. `additional_documentation_required`
12. `mfg_for_registration`
13. `contract_or_cooperative_to_use`
14. `model_no`
15. `part_no`
16. `product`
17. `contact_info`
18. `company_name`
19. `bid_summary`
20. `product_specification`

Fields that are not supported by the source documents are represented as `null` where applicable.

---

## 11. Validation and Tests

The test suite uses mocked LLM responses and does not require live Gemini API calls.

Run the complete test suite with:

```bash
pytest
```

The test suite covers:

* Chunking boundaries and overlap
* LLM extraction and retry behavior
* PDF and HTML parsing
* Pipeline processing
* Addendum ordering and merging
* Schema validation
* Field normalization
* List and sentence deduplication
