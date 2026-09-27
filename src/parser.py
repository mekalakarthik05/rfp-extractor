import os
import fitz  # PyMuPDF
import pdfplumber
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional

from .exceptions import UnsupportedFormatError, EmptyDocumentError, ScannedPDFError, ParsingError
from .config import SCANNED_PDF_THRESHOLD_CHARS, logger
from .utils import clean_text

@dataclass
class ParsedDocument:
    text: str
    page_count: int
    tables: List[str]
    is_probably_scanned: bool
    source: str
    has_tables: bool

class DocumentParser:
    """
    Parser layer to handle PDF and HTML documents.
    """
    @staticmethod
    def _parse_pdf(filepath: str) -> ParsedDocument:
        logger.info(f"Parsing PDF: {filepath}")
        try:
            doc = fitz.open(filepath)
            page_count = len(doc)
            
            if page_count == 0:
                raise EmptyDocumentError(f"PDF {filepath} has 0 pages.")
                
            text_blocks = []
            total_chars = 0
            
            # Extract basic text using PyMuPDF
            for page in doc:
                page_text = page.get_text()
                total_chars += len(page_text)
                text_blocks.append(page_text)
                
            raw_text = "\n\n".join(text_blocks)
            cleaned_text = clean_text(raw_text)
            
            avg_chars = total_chars / page_count if page_count > 0 else 0
            is_scanned = avg_chars < SCANNED_PDF_THRESHOLD_CHARS
            
            if is_scanned:
                logger.warning(f"PDF {filepath} appears to be scanned (avg {avg_chars:.1f} chars/page). OCR not implemented as per assignment scope.")
                
            # Extract tables using pdfplumber to append markdown representations
            tables_md = []
            has_tables = False
            
            try:
                with pdfplumber.open(filepath) as pdf:
                    for i, page in enumerate(pdf.pages):
                        extracted_tables = page.extract_tables()
                        for table in extracted_tables:
                            if not table:
                                continue
                            has_tables = True
                            # Convert table to simple markdown
                            md_table = f"\n--- Table on Page {i+1} ---\n"
                            for row in table:
                                clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                                md_table += "| " + " | ".join(clean_row) + " |\n"
                            tables_md.append(md_table)
            except Exception as e:
                logger.warning(f"Failed to extract tables via pdfplumber from {filepath}: {e}")
                
            final_text = cleaned_text
            if tables_md:
                final_text += "\n\n=== EXTRACTED TABLES ===\n" + "\n".join(tables_md)
                
            if not final_text.strip() and not is_scanned:
                raise EmptyDocumentError(f"PDF {filepath} yielded no extractable text.")
                
            return ParsedDocument(
                text=final_text,
                page_count=page_count,
                tables=tables_md,
                is_probably_scanned=is_scanned,
                source=filepath,
                has_tables=has_tables
            )
            
        except Exception as e:
            if isinstance(e, (EmptyDocumentError, ScannedPDFError)):
                raise e
            raise ParsingError(f"Failed to parse PDF {filepath}: {e}")

    @staticmethod
    def _parse_html(filepath: str) -> ParsedDocument:
        logger.info(f"Parsing HTML: {filepath}")
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            soup = BeautifulSoup(content, 'lxml')
            
            # Remove boilerplate
            for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                element.decompose()
                
            # Remove hidden elements
            hidden = soup.find_all(style=lambda value: value and ('display:none' in value.replace(' ', '') or 'visibility:hidden' in value.replace(' ', '')))
            for element in hidden:
                element.decompose()
                
            # Extract meta tags if they have useful content
            meta_text = []
            for meta in soup.find_all('meta'):
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                if name and content:
                    meta_text.append(f"META {name}: {content}")
                    
            # Extract tables to markdown format before they lose structure in get_text()
            tables_md = []
            has_tables = False
            for i, table in enumerate(soup.find_all('table')):
                has_tables = True
                md_table = f"\n--- HTML Table {i+1} ---\n"
                for row in table.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    clean_row = [cell.get_text(strip=True).replace('\n', ' ') for cell in cells]
                    md_table += "| " + " | ".join(clean_row) + " |\n"
                tables_md.append(md_table)
                
            raw_text = soup.get_text(separator='\n').strip()
            
            # Re-assemble
            parts = []
            if meta_text:
                parts.append("=== META TAGS ===\n" + "\n".join(meta_text))
            
            if raw_text:
                parts.append("=== CONTENT ===\n" + raw_text)
                
            if tables_md:
                parts.append("=== EXTRACTED TABLES ===\n" + "\n".join(tables_md))
                
            final_text = clean_text("\n\n".join(parts))
            
            if not final_text.strip():
                raise EmptyDocumentError(f"HTML {filepath} yielded no extractable text.")
                
            return ParsedDocument(
                text=final_text,
                page_count=1,
                tables=tables_md,
                is_probably_scanned=False,
                source=filepath,
                has_tables=has_tables
            )
            
        except Exception as e:
            if isinstance(e, EmptyDocumentError):
                raise e
            raise ParsingError(f"Failed to parse HTML {filepath}: {e}")

    @classmethod
    def parse(cls, filepath: str) -> ParsedDocument:
        """Entry point for parsing a document based on its extension."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pdf':
            return cls._parse_pdf(filepath)
        elif ext in ['.html', '.htm']:
            return cls._parse_html(filepath)
        else:
            raise UnsupportedFormatError(f"Unsupported file format: {ext}")
