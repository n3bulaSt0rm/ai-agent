#!/usr/bin/env python3
"""
Test script for Handler processing logic - Step 3 & Step 4
Tests the new chunking logic with markdown content
"""

import os
import sys
import json
import time
from pathlib import Path

# Add the project root directory to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.services.processing.rag.chunkers.markdown_chunker import MarkdownChunker
from backend.services.processing.rag.chunkers.recursive_chunker import RecursiveChunker, ChunkingConfig

def process_markdown_to_chunks():
    """
    Process markdown file through the complete chunking pipeline
    """
    # Input file path
    input_file = project_root / "data" / "converted_pdf_extraction_12f371bf-3fd8-4205-b06e-8346c8f40ad2.md"
    
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return False
    
    print(f"📁 Processing: {input_file.name}")
    
    # Step 1: Read markdown content
    with open(input_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    print(f"📄 Content length: {len(markdown_content)} characters")
    
    # Step 2: Create markdown chunks
    markdown_chunker = MarkdownChunker()
    raw_chunks = markdown_chunker.chunk_text(markdown_content)
    
    # Convert to handler.py format
    markdown_chunks = []
    for i, chunk in enumerate(raw_chunks, 1):
        markdown_chunks.append({
            "chunk_id": i,
            "content": chunk.page_content,
            "metadata": chunk.metadata
        })
    
    print(f"📊 Markdown chunks: {len(markdown_chunks)}")
    
    # Step 2.5: Save markdown chunks for debugging
    markdown_chunks_file = project_root / "data" / "markdown_chunks_debug.json"
    with open(markdown_chunks_file, 'w', encoding='utf-8') as f:
        json.dump(markdown_chunks, f, ensure_ascii=False, indent=2)
    print(f"💾 Markdown chunks saved to: {markdown_chunks_file}")
    
    # Show sample markdown chunks
    print(f"\n📋 Sample markdown chunks (first 3):")
    for i, chunk in enumerate(markdown_chunks[:3]):
        print(f"  Chunk {chunk['chunk_id']}: {len(chunk['content'])} chars")
        print(f"    Metadata: {chunk['metadata']}")
        print(f"    Content preview: {chunk['content'][:100]}...")
        print()
    
    # Step 3: Process with RecursiveChunker (new logic)
    config = ChunkingConfig(
        chunk_size=1000,
        chunk_overlap=150,
        model_name="AITeamVN/Vietnamese_Embedding_v2"
    )
    
    recursive_chunker = RecursiveChunker(config)
    file_id = "12f371bf-3fd8-4205-b06e-8346c8f40ad2"
    final_chunks = recursive_chunker.process_chunks(markdown_chunks, file_id)
    
    print(f"📊 Final chunks: {len(final_chunks)}")
    
    # Step 4: Save to JSON file in requested format
    output_file = project_root / "data" / "final_chunks_output.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_chunks, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Output saved to: {output_file}")
    
    # Show sample
    print(f"\n📋 Sample chunks (first 3):")
    for i, chunk in enumerate(final_chunks[:3]):
        print(f"  Chunk {chunk['chunk_id']}: {len(chunk['content'])} chars")
    
    return True

if __name__ == "__main__":
    print("🚀 Processing markdown with new chunking logic...")
    
    try:
        success = process_markdown_to_chunks()
        if success:
            print("\n✅ Processing completed successfully!")
        else:
            print("\n❌ Processing failed!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()