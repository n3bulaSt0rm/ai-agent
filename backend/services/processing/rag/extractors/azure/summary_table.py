"""
Convert HTML tables to descriptive text using DeepSeek API

This script reads a text file containing HTML tables, extracts the tables,
converts each table to a descriptive text using DeepSeek API, and saves the result.
"""

import os
import re
import sys
import json
import logging
import requests
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import numpy as np
from tabulate import tabulate

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_deepseek import ChatDeepSeek
from langchain_core.documents import Document

# Get the project root directory for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(os.path.dirname(current_dir))  # src directory
project_root = os.path.dirname(src_dir)  # project root
sys.path.append(project_root)  # Add project root to Python path

# Import from the central config
from backend.core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

# Get DeepSeek API key from settings
DEEPSEEK_API_KEY = settings.DEEPSEEK_API_KEY

# Output directory configuration
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def clean_document_content(content):
    """
    Clean the document content by:
    1. Removing lines with page markers (PageBreak, PageNumber, PageFooter, PageHeader)
       including empty lines around them
    2. Removing consecutive empty lines, keeping at most one
    
    Args:
        content (str): Original text content
        
    Returns:
        str: Cleaned text content without page markers
    """
    # Step 1: Remove lines with page markers and surrounding empty lines
    lines = content.split('\n')
    cleaned_lines = []
    i = 0
    
    while i < len(lines):
        # Check if current line contains a page marker
        is_page_marker = any(marker in lines[i] for marker in 
                            ['PageBreak', 'PageNumber', 'PageFooter', 'PageHeader'])
        
        if is_page_marker:
            # Skip one line before PageBreak if it's empty
            if 'PageBreak' in lines[i] and i > 0 and lines[i-1].strip() == '':
                if len(cleaned_lines) > 0:
                    cleaned_lines.pop()  # Remove the empty line before PageBreak
            
            # Skip the page marker line
            i += 1
            
            # Skip one line after PageNumber if it's empty
            if i < len(lines) and 'PageNumber' in lines[i-1] and lines[i].strip() == '':
                i += 1
                
            # Skip any consecutive empty lines between page markers
            while i < len(lines) and lines[i].strip() == '' and i+1 < len(lines) and any(
                marker in lines[i+1] for marker in ['PageBreak', 'PageNumber', 'PageFooter', 'PageHeader']):
                i += 1
        else:
            # Keep non-page-marker lines
            cleaned_lines.append(lines[i])
            i += 1
    
    # Step 2: Remove consecutive empty lines, keeping at most one
    condensed_lines = []
    prev_empty = False
    
    for line in cleaned_lines:
        is_empty = not line.strip()
        
        if is_empty and prev_empty:
            # Skip if this is a second consecutive empty line
            continue
        
        condensed_lines.append(line)
        prev_empty = is_empty
    
    # Rejoin content after cleaning
    content = '\n'.join(condensed_lines)
    
    return content


def format_html_table(table_text):
    """
    Format HTML table by removing whitespace, line breaks, and indentation
    
    Args:
        table_text (str): HTML table text with potential whitespace and line breaks
        
    Returns:
        str: Formatted HTML table with no whitespace between tags
    """
    # Save table name/marker if present
    table_lines = table_text.split('\n')
    table_marker = ""
    if table_lines and '--- Table ' in table_lines[0]:
        table_marker = table_lines[0] + '\n'
        table_text = '\n'.join(table_lines[1:])
    
    # Remove whitespace between HTML tags
    # First, remove line breaks and spaces between tags
    formatted_table = re.sub(r'>\s+<', '><', table_text)
    # Then, remove any remaining whitespace at the beginning or end of lines
    formatted_table = re.sub(r'^\s+|\s+$', '', formatted_table, flags=re.MULTILINE)
    # Finally, join all lines together
    formatted_table = ''.join(formatted_table.split('\n'))
    
    # Reattach table marker if it was present
    if table_marker:
        formatted_table = table_marker + formatted_table
        
    return formatted_table


def extract_html_tables(text):
    """
    Extract HTML tables from text
    
    Args:
        text (str): Text that may contain HTML tables
        
    Returns:
        list: List of tuples (table_start_pos, table_end_pos, table_text)
    """
    table_patterns = []
    
    # Find all HTML tables in the text
    table_pattern = re.compile(r'<table>.*?</table>', re.DOTALL)
    for match in table_pattern.finditer(text):
        start_pos = match.start()
        end_pos = match.end()
        table_text = match.group(0)
        
        # Determine if this is a "--- Table N ---" marked table
        lines = text[:start_pos].split('\n')
        if lines and '--- Table ' in lines[-1]:
            # Add the marker to the table text
            table_marker = lines[-1]
            start_pos = start_pos - len(table_marker) - 1  # -1 for newline
            table_text = table_marker + '\n' + table_text
        
        table_patterns.append((start_pos, end_pos, table_text))
    
    return table_patterns


def convert_table_to_text(table_text, model):
    """
    Convert a table (markdown or HTML) to descriptive text using DeepSeek
    
    Args:
        table_text (str): Table in markdown or HTML format
        model: DeepSeek model to use for conversion
        
    Returns:
        str: Descriptive text of the table content
    """
    try:
        # Create the prompt template
        prompt_template = PromptTemplate(
            input_variables=["table"],
            template="""
            Biểu diễn bảng sau bằng văn bản bình thường thay vì bảng html hoặc markdown, đảm bảo rõ ràng, dễ hiểu, không mất thông tin. 
            Không dùng kí tự đặc biệt, hãy suy luận để dùng văn bản thay cho kí tự đặc biệt.
            Trả lời bằng tiếng việt, không được sai chính tả.
            Không giải thích gì thêm.
            {table}
            """
        )
        
        # Use LangChain for converting table to text
        chain = prompt_template | model | StrOutputParser()
        description = chain.invoke({"table": table_text})
        
        # Return in a formatted way with the original table name if present
        if table_text.split('\n')[0].strip().startswith("--- Table "):
            table_name = table_text.split('\n')[0]
            description = f"{table_name}\n\n{description}"
        
        return description
    
    except Exception as e:
        print(f"Error converting table to text: {str(e)}")
        return table_text  # Return the original table on error


def process_tables_in_conversation(tables, model):
    """
    Process all tables in a single conversation with DeepSeek to maintain context and consistency
    
    Args:
        tables (list): List of tuples (start_pos, end_pos, table_text)
        model: DeepSeek model to use for conversion
        
    Returns:
        list: List of tuples (start_pos, end_pos, table_description)
    """
    # Initialize conversation with system message
    messages = [
        {
            "role": "system", 
            "content": """Bạn sẽ nhận được nhiều bảng HTML để chuyển đổi thành văn bản mô tả.
            Hãy nhớ các bảng đã xử lý trước đó và đảm bảo tính nhất quán.
            Nếu bảng mới tương tự với bảng nào đã xử lý, hãy sử dụng cùng cấu trúc mô tả.
            Nếu các bảng là các phần của cùng một bảng lớn bị chia do khác trang, hãy nối chúng lại.
            Biểu diễn bảng bằng văn bản bình thường thay vì bảng HTML hoặc markdown, đảm bảo rõ ràng, dễ hiểu.
            Không dùng kí tự đặc biệt, hãy suy luận để dùng văn bản thay cho kí tự đặc biệt.
            Với những từ viết tắt thì hãy dựa vào nội dung để suy luận đưa ra từ đầy đủ.
            Trả lời bằng tiếng Việt, không được sai chính tả.
            Chỉ trả về mô tả văn bản, không thêm giải thích."""
        }
    ]
    
    # Results will store tuples of (start_pos, end_pos, description)
    results = []
    
    # Process tables sequentially
    for i, (start_pos, end_pos, table_text) in enumerate(tables):
        # Format the table
        formatted_table = format_html_table(table_text)
        
        # Extract table marker if present
        table_marker = ""
        lines = formatted_table.split('\n')
        if lines and '--- Table ' in lines[0]:
            table_marker = lines[0]
        
        # Add user message to conversation
        messages.append({"role": "user", "content": formatted_table})
        
        # Get response from model
        response = model.invoke(messages)
        
        # Add model response to conversation history
        messages.append({"role": "assistant", "content": response.content})
        
        # Add table marker if it was present
        description = response.content
        if table_marker:
            description = f"{table_marker}\n\n{description}"
        
        # Store result
        results.append((start_pos, end_pos, description))
        
        print(f"Processed table {i+1}/{len(tables)}")
    
    return results


def process_file(input_content, output_file=None):
    """
    Process markdown content containing tables and convert them to descriptive text
    
    Args:
        input_content (str): Markdown content to process, either a file path or content string
        output_file (str, optional): Path to the output file. If provided, saves output to file.
    
    Returns:
        str: Processed markdown content with tables converted to descriptive text
    """
    try:
        # Validate inputs
        if not input_content:
            raise ValueError("Input content cannot be empty")
        
        if not DEEPSEEK_API_KEY:
            raise ValueError("DeepSeek API key not found. Set DEEPSEEK_API_KEY environment variable.")
        
        # Check if input_content is a file path or content string
        content = ""
        if isinstance(input_content, str) and os.path.exists(input_content):
            # It's a file path
            input_path = Path(input_content)
            print(f"Processing file: {input_content}")
            
            # Read the input file
            with open(input_path, 'r', encoding='utf-8') as file:
                content = file.read()
        else:
            # It's content string
            content = input_content
            print("Processing markdown content directly")
        
        # Initialize the DeepSeek model
        model = ChatDeepSeek(
            model="deepseek-chat",
            api_key=DEEPSEEK_API_KEY,
            temperature=0.3,
            max_tokens=8192
        )
        
        # Clean document content
        content = clean_document_content(content)
        
        # Extract tables from the cleaned content
        html_tables = extract_html_tables(content)
        all_tables = html_tables
        all_tables.sort(key=lambda x: x[0])
        
        print(f"Found {len(all_tables)} tables in the document")
        
        if all_tables:
            # Process all tables in a single conversation to maintain context
            processed_tables = process_tables_in_conversation(all_tables, model)
            
            # Replace tables with their descriptions in reverse order to avoid shifting positions
            processed_tables.sort(reverse=True, key=lambda x: x[0])
            
            for start_pos, end_pos, description in processed_tables:
                content = content[:start_pos] + description + content[end_pos:]
        
        # Write output to file if specified
        if output_file:
            output_path = Path(output_file)
            with open(output_path, 'w', encoding='utf-8') as file:
                file.write(content)
            print(f"Output saved to: {output_file}")
        
        print("Table conversion completed successfully")
        # Return processed content
        return content
    
    except Exception as e:
        print(f"Error processing content: {str(e)}")
        return None


if __name__ == "__main__":
    # Check if we need to install langchain-deepseek
    try:
        import langchain_deepseek
    except ImportError:
        print("Installing langchain-deepseek...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "langchain-deepseek"])
        print("Installation complete.")
    
    # Get input file path
    input_file = sys.argv[1] if len(sys.argv) > 1 else str(DATA_DIR / "pdf_extraction_12f371bf-3fd8-4205-b06e-8346c8f40ad2.txt")
    
    # Process the file
    output_file = process_file(input_file)
    
    if output_file:
        print(f"Output saved to: {output_file}")
    else:
        print("Processing failed.")
