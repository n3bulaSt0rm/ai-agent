import os
import fitz  # PyMuPDF
import logging
import io
import json
import re
from PIL import Image
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from backend.core.config import settings
from backend.services.processing.pdf.ocr import get_ocr_processor
from backend.db.vector_store import get_vector_store

logger = logging.getLogger(__name__)

class PDFProcessor:
    """
    PDF processor for extracting text and structure from PDF documents.
    Combines PyMuPDF text extraction with OCR for image-based content.
    """
    
    def __init__(self):
        """Initialize the PDF processor with settings."""
        # Set up parameters
        self.min_text_length = 100
        self.dpi = 300
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        
        # Get OCR processor
        self.ocr_processor = get_ocr_processor()
    
    def _extract_text(self, pdf_path: str) -> List[Dict]:
        """
        Extract text from PDF with OCR fallback.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of text blocks with metadata
        """
        # Extract text using PyMuPDF
        doc = fitz.open(pdf_path)
        text_blocks = []
        
        logger.info(f"Processing PDF with {len(doc)} pages")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Try normal text extraction first
            text = page.get_text()
            
            # If insufficient text, try OCR
            if len(text) < self.min_text_length:
                logger.info(f"Page {page_num+1}: Insufficient text ({len(text)} chars). Using OCR.")
                text = self._extract_with_ocr(page)
            
            # Extract text blocks
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if "lines" in block:
                    # Handle text blocks
                    text = ""
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text += span["text"] + " "
                    
                    # If text is too short, try OCR
                    if len(text.strip()) < 10:
                        bbox = block["bbox"]
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=bbox)
                        img_bytes = pix.tobytes()
                        ocr_text = self.ocr_processor.process_image_bytes(img_bytes)
                        text = ocr_text if ocr_text else text
                    
                    if text.strip():
                        # Get block position for structural detection
                        y0 = block["bbox"][1]  # top y position
                        
                        text_blocks.append({
                            "text": text.strip(),
                            "page": page_num + 1,
                            "type": "text",
                            "bbox": block["bbox"],
                            "y_pos": y0,
                            "level": self._detect_hierarchy_level(text.strip(), y0)
                        })
                
                # Handle tables by looking for table structures
                elif "table" in block or "image" in block:
                    # Extract region as image and OCR
                    bbox = block["bbox"]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=bbox)
                    
                    # Use OCR processor for table extraction
                    table_text = self.ocr_processor.process_image_bytes(pix.tobytes())
                    
                    if table_text.strip():
                        text_blocks.append({
                            "text": table_text.strip(),
                            "page": page_num + 1,
                            "type": "table",
                            "bbox": bbox
                        })
        
        doc.close()
        return text_blocks
    
    def _extract_with_ocr(self, page: fitz.Page) -> str:
        """
        Extract text from image-based page using OCR.
        
        Args:
            page: PyMuPDF page object
        
        Returns:
            Extracted text
        """
        try:
            pix = page.get_pixmap(dpi=self.dpi)
            img_bytes = pix.tobytes()
            
            # Use OCR processor
            text = self.ocr_processor.process_image_bytes(img_bytes)
            
            logger.info(f"Used OCR to extract text from page {page.number+1}")
            return text
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}")
            return ""
    
    def _detect_hierarchy_level(self, text: str, y_pos: float) -> str:
        """
        Detect hierarchy level of text (title, heading, subheading, paragraph).
        
        Args:
            text: The text to classify
            y_pos: Y position on page
            
        Returns:
            Hierarchy level as string
        """
        # Check for common title/heading patterns
        if re.match(r'^(Chương|CHƯƠNG|Phần|PHẦN|MỤC)\s+\d+', text):
            return "chapter"
            
        if re.match(r'^(Điều|ĐIỀU)\s+\d+', text):
            return "article"
            
        if re.match(r'^(Khoản|KHOẢN)\s+\d+', text):
            return "section"
        
        # Check for common numbering patterns
        if re.match(r'^\d+\.\s+[A-ZĐÁÀẢÃẠÂẤẦẨẪẬĂẮẰẲẴẶÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴ]', text):
            return "heading"
            
        if re.match(r'^[a-z]\)\s+', text) or re.match(r'^\d+\.\d+\.\s+', text):
            return "subsection"
        
        # If short text and starts with capital letter, likely a heading
        if len(text) < 100 and text[0].isupper() and y_pos < 200:
            return "heading"
            
        return "paragraph"
    
    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: Text to clean
            
        Returns:
            Cleaned text
        """
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Fix common OCR errors
        text = text.replace('l.', '1.')
        text = text.replace('l)', '1)')
        
        # Fix Vietnamese diacritics that might have been misrecognized
        replacements = {
            'oe': 'ơ',
            'aé': 'ae',
            'oà': 'oá',
            'ddi': 'đi',
            'dd': 'đ',
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
            
        return text
    
    def _split_into_chunks(self, text_blocks: List[Dict]) -> List[Dict]:
        """
        Split text blocks into chunks based on hierarchy and max chunk size.
        
        Args:
            text_blocks: List of text blocks with metadata
            
        Returns:
            List of chunks
        """
        chunks = []
        current_chunk = {"text": "", "page": None, "sections": []}
        current_size = 0
        
        for i, block in enumerate(text_blocks):
            text = self._clean_text(block["text"])
            
            # Start a new chunk if this is a major section or current chunk is too large
            if (block["level"] in ["chapter", "article"] or 
                current_size + len(text) > self.chunk_size and current_size > 0):
                
                # Save current chunk if not empty
                if current_chunk["text"]:
                    chunks.append(current_chunk)
                
                # Start new chunk
                current_chunk = {
                    "text": text,
                    "page": block["page"],
                    "sections": [{"title": text, "level": block["level"]}] if block["level"] in ["chapter", "article", "heading"] else []
                }
                current_size = len(text)
            else:
                # Add to current chunk
                if current_chunk["page"] is None:
                    current_chunk["page"] = block["page"]
                
                # Add a separator if necessary
                if current_chunk["text"]:
                    current_chunk["text"] += " "
                    
                current_chunk["text"] += text
                current_size += len(text)
                
                # Track sections for better searching
                if block["level"] in ["chapter", "article", "heading"]:
                    current_chunk["sections"].append({"title": text, "level": block["level"]})
        
        # Add the last chunk if not empty
        if current_chunk["text"]:
            chunks.append(current_chunk)
            
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks
    
    def process_file(self, file_id: int, file_path: str, s3_url: str, callback_url: str = None) -> Dict:
        """
        Process a PDF file: extract text, split into chunks, index in vector store.
        
        Args:
            file_id: Database ID of the file
            file_path: Path to the PDF file
            s3_url: Amazon S3 URL for the file
            callback_url: Optional URL to call with status updates
            
        Returns:
            Processing results
        """
        try:
            logger.info(f"Processing PDF file: {file_path} (ID: {file_id})")
            
            # Extract text from PDF
            text_blocks = self._extract_text(file_path)
            
            if not text_blocks:
                logger.error(f"No text extracted from {file_path}")
                return {
                    "file_id": file_id,
                    "status": "error",
                    "error": "No text could be extracted from the PDF",
                    "indexed_pages": 0,
                    "total_pages": 0
                }
            
            # Get number of pages
            doc = fitz.open(file_path)
            total_pages = len(doc)
            doc.close()
            
            # Split into chunks
            chunks = self._split_into_chunks(text_blocks)
            
            # Create document structure for vector store
            filename = os.path.basename(file_path)
            document = {
                "file_id": file_id,
                "filename": filename,
                "source": s3_url,
                "pages": []
            }
            
            # Add chunks as pages
            for i, chunk in enumerate(chunks):
                document["pages"].append({
                    "page_num": chunk["page"],
                    "text": chunk["text"],
                    "sections": chunk.get("sections", [])
                })
            
            # Index document in vector store
            vector_store = get_vector_store()
            document_id = vector_store.index_document(document)
            
            logger.info(f"Successfully processed {filename} (ID: {file_id}), indexed {len(chunks)} chunks")
            
            return {
                "file_id": file_id,
                "status": "processed",
                "document_id": document_id,
                "indexed_pages": total_pages,
                "total_pages": total_pages,
                "chunk_count": len(chunks)
            }
            
        except Exception as e:
            logger.error(f"Error processing file {file_id}: {str(e)}")
            return {
                "file_id": file_id,
                "status": "error",
                "error": str(e),
                "indexed_pages": 0,
                "total_pages": 0
            }

# Create singleton instance
_pdf_processor = None

def get_pdf_processor() -> PDFProcessor:
    """Get the PDF processor instance."""
    global _pdf_processor
    if _pdf_processor is None:
        _pdf_processor = PDFProcessor()
    return _pdf_processor 

    