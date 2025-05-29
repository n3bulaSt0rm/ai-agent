import os
import re
import torch
from pathlib import Path

# Import docling
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

def extract_text_from_pdf(pdf_path, output_path, preserve_tables=True):
    """
    Extract text from PDF files (including scanned PDFs with tables) using Docling.
    Tables are preserved in Markdown format, regular text is plain text.
    Optimized for Vietnamese language content.
    
    Args:
        pdf_path (str): Path to the PDF file
        output_path (str): Path to the output file
        preserve_tables (bool): Whether to preserve tables in Markdown format
    
    Returns:
        str: Path to the output file
    """
    print(f"Processing: {pdf_path}")
    
    # Configure GPU/CPU acceleration
    if torch.cuda.is_available():
        print("CUDA is available! Using GPU acceleration.")
        print(f"CUDA version: {torch.version.cuda}")
        acc_device = AcceleratorDevice.CUDA
    else:
        print("CUDA is NOT available. Using CPU.")
        acc_device = AcceleratorDevice.CPU

    # Initialize the document converter with minimal configuration
    # Only adding GPU acceleration to the default setup
    try:
        # Cấu hình GPU đúng cách thông qua AcceleratorOptions
        accelerator_options = AcceleratorOptions(
            num_threads=8,
            device=acc_device
        )
        
        pipeline_options = PdfPipelineOptions()
        pipeline_options.accelerator_options = accelerator_options
        
        # Cấu hình để xử lý tốt bảng
        pipeline_options.do_table_structure = True
        pipeline_options.images_scale = 6.0  # Tăng scale lên 6.0 để cải thiện nhận diện ô gộp
        pipeline_options.generate_page_images = True  # Tạo ảnh trang để xử lý bảng tốt hơn
        
        # Cấu hình tối ưu cho việc xử lý ô gộp
        table_structure_options = TableStructureOptions(
            do_cell_matching=False,  # Tắt matching với PDF cells để tránh vấn đề với ô gộp
            mode=TableFormerMode.ACCURATE  # Sử dụng mode chính xác để xử lý tốt hơn
        )
        pipeline_options.table_structure_options = table_structure_options
        
        # Khởi tạo DocumentConverter với cấu hình GPU
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                )
            }
        )
        
        # Convert the PDF
        result = converter.convert(pdf_path)
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Get content in Markdown format to access tables
        markdown_content = result.document.export_to_markdown()
        
        if preserve_tables:
            # Write the markdown content directly
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        else:
            # Just write the markdown content as is
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        
        print(f"Extracted content saved to: {output_path}")
        return output_path
    
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        
        # Create output directory if needed
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Write error message to output file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Error extracting content from {pdf_path}: {str(e)}")
        
        return output_path


def main():
    """
    Main function to extract text from PDF file.
    Uses fixed paths for input and output files.
    """
    # Define fixed paths
    INPUT_PATH = r"D:\DATN_HUST\test\data\raw\pdf\Bachelor-Computer-Engineering-program.pdf"
    OUTPUT_PATH = r"D:\DATN_HUST\test\text_output_2.txt"
    
    # Check if input file exists
    if not os.path.exists(INPUT_PATH):
        print(f"Error: Input file does not exist: {INPUT_PATH}")
        return
    
    # Process the PDF file using standard docling method
    try:
        extract_text_from_pdf(
            INPUT_PATH, 
            OUTPUT_PATH, 
            preserve_tables=True,
        )
        print(f"Docling conversion completed! Check the output at: {OUTPUT_PATH}")
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")

if __name__ == "__main__":
    main() 