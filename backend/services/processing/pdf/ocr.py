import pytesseract
import logging
import io
import numpy as np
from PIL import Image, ImageEnhance
from backend.core.config import settings

logger = logging.getLogger(__name__)

class OCRProcessor:
    """
    OCR processor for Vietnamese documents.
    Optimized for Vietnamese text extraction using Tesseract with preprocessing.
    """
    
    def __init__(self):
        """Initialize the OCR processor."""
        # Configure Tesseract
        self.tesseract_cmd = settings.TESSERACT_CMD
        self.tesseract_lang = settings.TESSERACT_LANG
        self.tesseract_config = f'--oem 3 --psm 6 -l {self.tesseract_lang}'
        self.dpi = 300
        
        # Set Tesseract path if specified
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        
        logger.info("OCR processor initialized")
    
    def enhance_image(self, image: Image) -> Image:
        """
        Enhance image quality for better OCR results with Vietnamese text.
        
        Args:
            image: PIL Image object
        
        Returns:
            Enhanced PIL Image
        """
        # Convert to grayscale
        img_gray = image.convert('L')
        
        # Increase contrast
        enhancer = ImageEnhance.Contrast(img_gray)
        img_contrast = enhancer.enhance(1.5)
        
        # Apply adaptive thresholding
        img_np = np.array(img_contrast)
        h, w = img_np.shape
        
        # Simple block-based adaptive thresholding
        block_size = 25
        img_thresholded = np.zeros_like(img_np)
        
        for i in range(0, h, block_size):
            for j in range(0, w, block_size):
                block = img_np[i:min(i+block_size, h), j:min(j+block_size, w)]
                if block.size > 0:
                    threshold = np.mean(block) - 10  # Slightly lower threshold
                    img_thresholded[i:min(i+block_size, h), j:min(j+block_size, w)] = \
                        (block > threshold) * 255
        
        return Image.fromarray(img_thresholded)
    
    def process_image(self, image: Image, region=None) -> str:
        """
        Extract text from an image using Tesseract OCR with preprocessing.
        
        Args:
            image: PIL Image object
            region: Optional region to extract (left, top, right, bottom)
            
        Returns:
            Extracted text
        """
        try:
            # Crop if region is specified
            if region:
                image = image.crop(region)
                
            # Resize if image is too small
            if min(image.size) < 300:
                ratio = 300 / min(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, Image.LANCZOS)
            
            # Enhance image
            enhanced_img = self.enhance_image(image)
            
            # Extract text with Tesseract
            text = pytesseract.image_to_string(enhanced_img, config=self.tesseract_config)
            
            return text
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}")
            return ""
    
    def process_image_bytes(self, image_bytes: bytes, region=None) -> str:
        """
        Extract text from image bytes using Tesseract OCR.
        
        Args:
            image_bytes: Raw image bytes
            region: Optional region to extract (left, top, right, bottom)
            
        Returns:
            Extracted text
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return self.process_image(img, region)
            
        except Exception as e:
            logger.error(f"OCR extraction from bytes failed: {str(e)}")
            return ""
    
    def detect_table(self, text: str) -> bool:
        """
        Detect if text contains a table structure.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains a table
        """
        import re
        
        # Common table patterns in Vietnamese documents
        table_patterns = [
            r'\+[-+]+\+',                  # ASCII table borders
            r'\|.*\|',                      # Pipe separated values
            r'^\s*[-+|=]{3,}\s*$',         # Table dividers
            r'^\s*\d+\s+\|\s+\w+',         # Numbered list with pipe separators
            r'((^|\n)\s*\d+(\.\d+)*\s+\S+.*\s+\d+(\.\d+)*\s+\S+)',  # Aligned numbers and text
            r'(^|\n)(\s*[A-Za-z0-9]+\s{2,}){2,}',  # Multiple columns with aligned spacing
        ]
        
        return any(re.search(p, text, re.MULTILINE) for p in table_patterns)

# Singleton instance
_ocr_processor = None

def get_ocr_processor() -> OCRProcessor:
    """Get the OCR processor instance."""
    global _ocr_processor
    if _ocr_processor is None:
        _ocr_processor = OCRProcessor()
    return _ocr_processor 