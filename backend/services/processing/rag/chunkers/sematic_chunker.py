import nltk
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import json
import os
import re
from typing import List, Dict, Any

# Đặt đường dẫn đến thư mục NLTK data
nltk.data.path.append("/home/n3bulast0rm/Documents/Projects/DATN/ai-agent/.venv.production/nltk_data")

# Simple Vietnamese sentence tokenizer function to avoid NLTK issues
def simple_tokenize(text):
    """Simple sentence tokenizer for Vietnamese text"""
    # This regex pattern matches Vietnamese sentences ending with punctuation
    pattern = r'(?<=[.!?;])\s+'
    sentences = re.split(pattern, text)
    # Further clean and filter empty strings
    return [s.strip() for s in sentences if s.strip()]

class ProtonxSemanticChunker:
    def __init__(self, threshold=0.3, model="bkai-foundation-models/vietnamese-bi-encoder"):
        self.threshold = threshold
        self.model = SentenceTransformer(model)
        # Download punkt for sentence tokenization, ensuring it's only done when class is initialized
        try:
            nltk.download("punkt", quiet=True)
        except:
            pass # Suppressed because we'll use simple_tokenize as fallback

    def embed_function(self, sentences):
        """
        Embeds sentences using SentenceTransformer.
        """
        return self.model.encode(sentences)

    def split_text(self, text):
        """
        Split text into semantic chunks.
        """
        try:
            # Try NLTK first
            sentences = nltk.sent_tokenize(text)
        except:
            # Fall back to simple tokenizer on any error
            sentences = simple_tokenize(text)
            
        sentences = [item for item in sentences if item and item.strip()]
        if not len(sentences):
            return []

        # Vectorize the sentences for similarity checking
        vectors = self.embed_function(sentences)
        # Calculate pairwise cosine similarity between sentences
        similarities = cosine_similarity(vectors)
        # Initialize chunks with the first sentence
        chunks = [[sentences[0]]]
        # Group sentences into chunks based on similarity threshold
        for i in range(1, len(sentences)):
            sim_score = similarities[i-1, i]
            if sim_score >= self.threshold:
                # If the similarity is above the threshold, add to the current chunk
                chunks[-1].append(sentences[i])
            else:
                # Start a new chunk
                chunks.append([sentences[i]])
        # Join the sentences in each chunk to form coherent paragraphs
        return [' '.join(chunk) for chunk in chunks]
    
    def process_chunks(self, chunks: List[Dict], file_id: str) -> List[Dict]:
        """
        Process a list of chunks by further breaking them down semantically.
        
        Args:
            chunks: List of chunk dictionaries with content and metadata
            file_id: The file ID extracted from the filename
            
        Returns:
            List of refined chunks with semantic divisions and sequential chunk_ids
        """
        refined_chunks = []
        global_chunk_id = 1
        
        for parent_chunk in chunks:
            content = parent_chunk.get('content', '')
            metadata = parent_chunk.get('metadata', {})
            parent_chunk_id = parent_chunk.get('chunk_id', 0)
            
            # Skip empty content
            if not content.strip():
                continue
                
            # Apply semantic chunking to break down the content further
            semantic_chunks = self.split_text(content)
            
            # Create new refined chunks with sequential IDs
            for sem_chunk in semantic_chunks:
                sem_chunk = sem_chunk.strip()
                # Filter out chunks with content length <= 8
                if sem_chunk and len(sem_chunk) > 8:
                    # Create minimal metadata for Qdrant storage
                    clean_metadata = {
                        "file_id": file_id,
                        "parent_chunk_id": parent_chunk_id
                    }
                    
                    refined_chunks.append({
                        "chunk_id": global_chunk_id,
                        "content": sem_chunk,
                        "metadata": clean_metadata
                    })
                    global_chunk_id += 1
                    
        return refined_chunks

def extract_file_id_from_filename(filename: str) -> str:
    """
    Extract file_id from filename like 'markdown_9d631398-eae9-4493-8a48-575cb2b92ab0.json'
    
    Args:
        filename: The input filename
        
    Returns:
        The extracted file_id
    """
    # Extract the UUID pattern from filename
    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', filename)
    if match:
        return match.group(1)
    else:
        # Fallback: try to extract from filename without extension
        basename = os.path.splitext(os.path.basename(filename))[0]
        if 'markdown_' in basename:
            return basename.replace('markdown_', '')
        return basename

def process_markdown_semantic_chunks(
    input_file: str,
    output_file: str,
    threshold: float = 0.3,
    model: str = "bkai-foundation-models/vietnamese-bi-encoder"
) -> int:
    """
    Process markdown chunks and further split them semantically.
    
    Args:
        input_file: Path to the input JSON file with markdown chunks.
        output_file: Path to save the output semantic chunks.
        threshold: Similarity threshold for semantic chunking.
        model: Name of the transformer model to use.
        
    Returns:
        Number of chunks created.
    """
    # Check if input file exists
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    # Extract file_id from filename
    file_id = extract_file_id_from_filename(input_file)
    print(f"Extracted file_id: {file_id}")
    
    # Read the input chunks
    with open(input_file, 'r', encoding='utf-8') as f:
        markdown_chunks = json.load(f)
    
    print(f"Loaded {len(markdown_chunks)} markdown chunks from {input_file}")
    
    # Create semantic chunker
    chunker = ProtonxSemanticChunker(
        threshold=threshold,
        model=model
    )
    
    final_chunks = chunker.process_chunks(markdown_chunks, file_id)
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_chunks, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(final_chunks)} semantic chunks to {output_file}")
    return len(final_chunks)

if __name__ == "__main__":
    # Example usage
    input_file = "src/data/markdown_12f371bf-3fd8-4205-b06e-8346c8f40ad2.json"
    output_file = "src/data/final_chunks_12f371bf-3fd8-4205-b06e-8346c8f40ad2.json"
    
    try:
        num_chunks = process_markdown_semantic_chunks(
            input_file=input_file,
            output_file=output_file,
            threshold=0.3,
            model="bkai-foundation-models/vietnamese-bi-encoder"
        )
        
        print(f"Successfully processed chunks and created {num_chunks} semantic chunks.")
        print(f"Output file: {os.path.abspath(output_file)}")
        
    except Exception as e:
        print(f"Error processing chunks: {str(e)}")