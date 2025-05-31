import logging
from typing import List, Dict, Any, Tuple, Optional, Set
from dataclasses import dataclass, field
import torch
import numpy as np
import os
from collections import defaultdict
import json
import sys

# Add the project root to the Python path
# Get absolute path to project root
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # rag directory
processing_dir = os.path.dirname(src_dir)  # processing directory
services_dir = os.path.dirname(processing_dir)  # services directory
backend_dir = os.path.dirname(services_dir)  # backend directory
project_root = os.path.dirname(backend_dir)  # project root

# Ensure the project root is in sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import from the central config
from backend.core.config import settings

# Import common modules using absolute imports
from backend.services.processing.rag.common.cuda import CudaMemoryManager
from backend.services.processing.rag.common.qdrant import ChunkData, QueryResult as QdrantQueryResult, QdrantManager
from backend.services.processing.rag.models.deepseek.main import DeepSeekModel
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get DeepSeek API key from settings
deepseek_api_key = settings.DEEPSEEK_API_KEY
if deepseek_api_key:
    masked_key = f"{deepseek_api_key[:5]}...{deepseek_api_key[-5:]}" if len(deepseek_api_key) > 10 else "***"
    logger.info(f"DeepSeek API key loaded from settings: {masked_key}")
else:
    logger.error("DeepSeek API key is missing in settings")

@dataclass
class QueryWithKeywords:
    """Data class for query and its keywords"""
    query: str
    keywords: List[str]
    

@dataclass
class SearchResult:
    """Search result with chunk information"""
    chunk_id: int
    content: str
    score: float
    metadata: Dict[str, Any]


@dataclass
class EmailQueryResult:
    """Enhanced query result with query information for email processing"""
    original_query: str
    keywords: List[str]
    results: List[str]  # Top 3 fulltext results
    total_found: int


@dataclass
class RankingConfig:
    """Configuration for ranking results"""
    similarity_threshold: float = 0.7
    min_score_threshold: float = 0.3
    
    # Boosting factors (manual post-processing)
    content_keyword_boost: float = 1.2
    metadata_keyword_boost: float = 1.8
    original_chunk_boost: float = 0.1
    multi_chunk_boost: float = 0.05
    
    # Adjacent chunk retrieval
    adjacent_before: int = 3
    adjacent_after: int = 3
    
    # Results per query
    results_per_query: int = 3


class VietnameseQueryModule:    
    def __init__(self, 
                 embedding_module,
                 deepseek_api_key: str,  # Required now
                 deepseek_model: str = "deepseek-chat",
                 config: Optional[RankingConfig] = None):
        """
        Initialize query module
        
        Args:
            embedding_module: Initialized embedding module
            deepseek_api_key: API key for DeepSeek (required)
            deepseek_model: DeepSeek model name
            config: Ranking configuration
        """
        self.embedding_module = embedding_module
        self.config = config or RankingConfig()
        
        # Setup deepseek model - required
        if not deepseek_api_key:
            raise ValueError("DeepSeek API key is required for query extraction")
            
        # Log masked API key for debugging
        masked_key = f"{deepseek_api_key[:5]}...{deepseek_api_key[-5:]}" if len(deepseek_api_key) > 10 else "***"
        logger.info(f"Using DeepSeek API key: {masked_key} for model: {deepseek_model}")
        
        self.deepseek = DeepSeekModel(api_key=deepseek_api_key, model_name=deepseek_model)
        logger.info(f"Initialized DeepSeek model: {deepseek_model}")
        
        # Setup CUDA memory manager
        self.memory_manager = CudaMemoryManager()
        
        # Ensure GPU is available
        if not torch.cuda.is_available():
            raise RuntimeError("GPU không khả dụng. Hệ thống yêu cầu GPU để hoạt động.")
            
        self.device = torch.device("cuda")

        
    def extract_queries_from_email(self, email_content: str) -> List[QueryWithKeywords]:
        """Extract multiple queries with keywords from email content using DeepSeek API"""
        if not email_content or not email_content.strip():
            raise ValueError("Email content cannot be empty")
        
        try:
            # Construct prompt for DeepSeek to extract queries and keywords
            prompt = f"""Hãy phân tích email sau và trích xuất tất cả các câu hỏi/yêu cầu thông tin cùng với từ khóa tìm kiếm cho mỗi câu hỏi.

Trả về kết quả dưới dạng JSON với format sau:
{{
    "queries": [
        {{
            "query": "câu hỏi được viết lại một cách rõ ràng",
            "keywords": ["từ khóa 1", "từ khóa 2", "từ khóa 3"]
        }},
        {{
            "query": "câu hỏi thứ 2",
            "keywords": ["từ khóa A", "từ khóa B"]
        }}
    ]
}}

Lưu ý:
- Mỗi query phải là một câu hỏi hoàn chỉnh và rõ ràng
- Keywords phải là những từ khóa quan trọng để tìm kiếm thông tin liên quan
- Đảm bảo đúng chính tả tiếng Việt
- Chỉ trả về JSON, không thêm giải thích

Email cần phân tích:
{email_content}

JSON:"""
            
            # Use DeepSeek to generate queries and keywords
            response_text = self.deepseek.generate_answer("", prompt)
            
            # Add debug logging for the raw response
            logger.info(f"DeepSeek raw response length: {len(response_text) if response_text else 0}")
            if not response_text or not response_text.strip():
                logger.error("Empty response from DeepSeek API")
                raise ValueError("Empty response from DeepSeek API")
            
            # Log first 100 characters of response for debugging
            preview = response_text[:100] + "..." if len(response_text) > 100 else response_text
            logger.debug(f"Response preview: {preview}")
            
            # Parse JSON response
            try:
                # Clean response text (remove any extra text before/after JSON)
                response_text = response_text.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                # Additional check for empty response after cleaning
                if not response_text:
                    logger.error("Empty JSON content after cleaning response")
                    raise ValueError("Empty JSON content from DeepSeek")
                
                try:
                    parsed_response = json.loads(response_text)
                except json.JSONDecodeError as je:
                    # Try to extract JSON using regex as a fallback
                    logger.warning(f"JSON decode error: {je}. Attempting to extract JSON with regex...")
                    import re
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        try:
                            parsed_response = json.loads(json_match.group(0))
                            logger.info("Successfully extracted JSON using regex")
                        except:
                            logger.error(f"Failed to parse JSON after regex extraction")
                            raise ValueError(f"Invalid JSON response from DeepSeek after fallback extraction")
                    else:
                        # If no JSON-like structure found, fallback to a simple format
                        logger.error("No JSON structure found in response. Creating fallback format.")
                        # Create a simple query from the email content
                        query = email_content.strip().split('\n')[0][:100]  # First line, truncated
                        keywords = query.split()[:5]  # First 5 words as keywords
                        
                        return [QueryWithKeywords(query=query, keywords=keywords)]
                
                queries_data = parsed_response.get("queries", [])
                
                if not queries_data:
                    logger.warning("No queries found in DeepSeek response, using fallback")
                    # Create a fallback query
                    query = email_content.strip().split('\n')[0][:100]  # First line, truncated
                    keywords = query.split()[:5]  # First 5 words as keywords
                    return [QueryWithKeywords(query=query, keywords=keywords)]
                
                # Convert to QueryWithKeywords objects
                extracted_queries = []
                for item in queries_data:
                    query = item.get("query", "").strip()
                    keywords = [kw.strip() for kw in item.get("keywords", []) if kw.strip()]
                    
                    if query and keywords:
                        extracted_queries.append(QueryWithKeywords(query=query, keywords=keywords))
                
                if not extracted_queries:
                    logger.warning("No valid queries with keywords extracted, using fallback")
                    # Create a fallback query
                    query = email_content.strip().split('\n')[0][:100]  # First line, truncated
                    keywords = query.split()[:5]  # First 5 words as keywords
                    return [QueryWithKeywords(query=query, keywords=keywords)]
                
                logger.info(f"Extracted {len(extracted_queries)} queries from email")
                for i, q in enumerate(extracted_queries):
                    logger.info(f"Query {i+1}: '{q.query}' - Keywords: {q.keywords}")
                
                return extracted_queries
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse DeepSeek JSON response: {e}")
                logger.error(f"Response text: {response_text}")
                raise ValueError(f"Invalid JSON response from DeepSeek: {e}")
                
        except Exception as e:
            logger.error(f"Error extracting queries from email with DeepSeek: {e}")
            raise RuntimeError(f"Failed to extract queries using DeepSeek API: {e}")
            
    def _normalize_embedding(self, embedding):
        """Normalize embedding to numpy array"""
        if isinstance(embedding, torch.Tensor):
            if embedding.is_cuda:
                embedding = embedding.cpu()
            embedding = embedding.detach().numpy()
        elif isinstance(embedding, list):
            embedding = np.array(embedding)
        elif isinstance(embedding, np.ndarray):
            pass  # Already numpy array
        else:
            raise ValueError(f"Unsupported embedding type: {type(embedding)}")
        
        if embedding.ndim > 1:
            embedding = embedding.flatten()
        
        return embedding
    
    def semantic_search(self, query: str, keywords: List[str], top_k: int = 10) -> List[SearchResult]:
        """
        Semantic search with keyword boosting using standard Qdrant API
        
        Args:
            query: User query
            keywords: List of keywords for boosting (required)
            top_k: Number of results to return
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if not keywords:
            raise ValueError("Keywords are required for search")
        
        query = query.strip()
        
        # Generate embedding
        try:
            query_embedding = self.embedding_module.generate_embedding(query)
            
            # Use standard vector search first, then apply keyword boosting manually
            search_results = self._vector_search_with_keywords(query_embedding, keywords, top_k)
            logger.info(f"Performed vector search with keyword filtering: {keywords}")
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            raise RuntimeError(f"Semantic search failed: {e}")
            
    def _vector_search_with_keywords(self, query_vector: List[float], keywords: List[str], top_k: int = 10) -> List[SearchResult]:
        """Perform vector search with keyword filtering using standard Qdrant API"""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchText, MatchAny, SearchParams
            
            # Get access to the Qdrant client
            client = self.embedding_module.qdrant_manager.client
            collection_name = self.embedding_module.qdrant_manager.collection_name
            
            # Create keyword filters for content and metadata
            content_conditions = []
            metadata_conditions = []
            
            for keyword in keywords:
                if keyword.strip():
                    # Content matching
                    content_conditions.append(
                        FieldCondition(key="content", match=MatchText(text=keyword.strip()))
                    )
                    # Metadata keywords matching
                    metadata_conditions.append(
                        FieldCondition(key="keywords", match=MatchAny(any=[keyword.strip()]))
                    )
            
            # Perform vector search using standard API
            vector_results = client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k * 2,  # Get more results for filtering
                with_payload=True,
                with_vectors=False,
                score_threshold=self.config.min_score_threshold
            )
            
            # Convert to SearchResult and apply manual keyword boosting
            all_results = []
            for hit in vector_results:
                content = str(hit.payload.get("content", ""))
                metadata = {
                    "file_id": hit.payload["file_id"],
                    "parent_chunk_id": hit.payload["parent_chunk_id"],
                }
                
                # Calculate keyword boost manually
                boost_factor = 1.0
                
                # Check content for keywords
                content_lower = content.lower()
                content_matches = 0
                for keyword in keywords:
                    if keyword.lower() in content_lower:
                        content_matches += 1
                
                if content_matches > 0:
                    boost_factor *= (self.config.content_keyword_boost ** content_matches)
                
                # Check metadata keywords
                chunk_keywords = hit.payload.get("keywords", [])
                if chunk_keywords:
                    metadata_matches = 0
                    for keyword in keywords:
                        keyword_lower = keyword.lower()
                        # Handle different types of chunk_keywords
                        for k in chunk_keywords:
                            if isinstance(k, str):
                                # If k is a string, compare directly
                                if keyword_lower in k.lower():
                                    metadata_matches += 1
                                    break
                            elif isinstance(k, list):
                                # If k is a list, check all items in the list
                                for item in k:
                                    if isinstance(item, str) and keyword_lower in item.lower():
                                        metadata_matches += 1
                                        break
                            else:
                                # For other types, convert to string and compare
                                try:
                                    k_str = str(k).lower()
                                    if keyword_lower in k_str:
                                        metadata_matches += 1
                                        break
                                except:
                                    # Skip items that can't be converted to string
                                    pass
                    
                    if metadata_matches > 0:
                        boost_factor *= (self.config.metadata_keyword_boost ** metadata_matches)
                
                # Apply boost to score
                boosted_score = hit.score * boost_factor
                
                result = SearchResult(
                    chunk_id=hit.payload["chunk_id"],
                    content=content,
                    score=boosted_score,
                    metadata=metadata
                )
                all_results.append(result)
            
            # Sort by boosted score and return top_k
            all_results.sort(key=lambda x: x.score, reverse=True)
            return all_results[:top_k]
            
        except Exception as e:
            logger.error(f"Error in vector search with keywords: {e}")
            raise RuntimeError(f"Vector search with keywords failed: {e}")
    
    def get_adjacent_chunks(self, 
                          chunk_id: int, 
                          file_id: str, 
                          parent_chunk_id: int,
                          before: Optional[int] = None, 
                          after: Optional[int] = None) -> List[ChunkData]:
        """Get adjacent chunks to provide more context"""
        before = before if before is not None else self.config.adjacent_before
        after = after if after is not None else self.config.adjacent_after
        
        try:
            return self.embedding_module.qdrant_manager.get_adjacent_chunks(
                chunk_id=chunk_id,
                file_id=file_id,
                parent_chunk_id=parent_chunk_id,
                before=before,
                after=after
            )
        except Exception as e:
            logger.error(f"Error getting adjacent chunks: {e}")
            return []
    
    def collect_and_group_chunks(self, search_results: List[SearchResult]) -> Dict[str, List[ChunkData]]:
        """Collect all chunks (original + expanded) and group by file_id + parent_chunk_id"""
        if not search_results:
            return {}
        
        # Collect all unique chunks
        all_chunks_dict = {}  # chunk_id -> ChunkData
        self._chunk_metadata = {}  # chunk_id -> metadata
        
        # Process original search results
        for result in search_results:
            try:
                # Extract metadata
                file_id = result.metadata["file_id"]
                parent_chunk_id = result.metadata["parent_chunk_id"]
                chunk_id = result.chunk_id
                
                # Store original chunk
                original_chunk = ChunkData(
                    chunk_id=chunk_id,
                    content=result.content,
                    file_id=file_id,
                    parent_chunk_id=parent_chunk_id
                )
                
                all_chunks_dict[chunk_id] = original_chunk
                self._chunk_metadata[chunk_id] = {
                    'is_original': True,
                    'boosted_score': result.score,  # Score with keyword boosts
                    'file_id': file_id,
                    'parent_chunk_id': parent_chunk_id
                }
                
                # Get adjacent chunks
                adjacent_chunks = self.get_adjacent_chunks(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    parent_chunk_id=parent_chunk_id
                )
                
                # Add adjacent chunks
                for adj_chunk in adjacent_chunks:
                    adj_id = adj_chunk.chunk_id
                    if adj_id not in all_chunks_dict:
                        all_chunks_dict[adj_id] = adj_chunk
                        self._chunk_metadata[adj_id] = {
                            'is_original': False,
                            'boosted_score': 0.0,
                            'file_id': adj_chunk.file_id,
                            'parent_chunk_id': adj_chunk.parent_chunk_id,
                            'expanded_from': chunk_id
                        }
                    else:
                        # Track multiple expansions
                        if 'expanded_from' in self._chunk_metadata[adj_id]:
                            if isinstance(self._chunk_metadata[adj_id]['expanded_from'], list):
                                self._chunk_metadata[adj_id]['expanded_from'].append(chunk_id)
                            else:
                                self._chunk_metadata[adj_id]['expanded_from'] = [
                                    self._chunk_metadata[adj_id]['expanded_from'], 
                                    chunk_id
                                ]
                        else:
                            self._chunk_metadata[adj_id]['expanded_from'] = chunk_id
            except Exception as e:
                logger.error(f"Error processing search result {result.chunk_id}: {e}")
                continue
        
        # Group chunks by file_id + parent_chunk_id
        grouped_chunks = defaultdict(list)
        
        for chunk_data in all_chunks_dict.values():
            group_key = f"{chunk_data.file_id}_{chunk_data.parent_chunk_id}"
            grouped_chunks[group_key].append(chunk_data)
        
        # Sort and filter groups
        final_groups = {}
        for group_key, chunks in grouped_chunks.items():
            try:
                # Sort chunks
                sorted_chunks = sorted(chunks, key=lambda x: x.chunk_id)
                
                # Check if group has original chunk
                has_original = any(
                    self._chunk_metadata.get(chunk.chunk_id, {}).get('is_original', False) 
                    for chunk in sorted_chunks
                )
                
                if has_original:
                    final_groups[group_key] = sorted_chunks
            except Exception as e:
                logger.error(f"Error finalizing group {group_key}: {e}")
                continue
        
        return dict(final_groups)
    
    def calculate_group_score(self, chunks: List[ChunkData]) -> float:
        """Calculate final score for a chunk group using boosted scores"""
        if not chunks:
            return 0.0
        
        try:
            # Get original chunks and their boosted scores
            original_scores = []
            for chunk in chunks:
                chunk_meta = self._chunk_metadata.get(chunk.chunk_id, {})
                if chunk_meta.get('is_original', False):
                    boosted_score = chunk_meta.get('boosted_score', 0.0)
                    # Add small boost for original chunks
                    final_score = boosted_score + self.config.original_chunk_boost
                    original_scores.append(final_score)
            
            if not original_scores:
                return 0.0
            
            # Use max score from original chunks as base
            max_score = max(original_scores)
            
            # Add boost for multiple original chunks
            if len(original_scores) > 1:
                multi_chunk_boost = self.config.multi_chunk_boost * (len(original_scores) - 1)
                max_score += multi_chunk_boost
            
            return float(max_score)
            
        except Exception as e:
            logger.error(f"Error calculating group score: {e}")
            return 0.0
    
    def rank_groups(self, grouped_chunks: Dict[str, List[ChunkData]]) -> List[Tuple[str, List[ChunkData], float]]:
        """Rank groups using boosted scores"""
        if not grouped_chunks:
            return []
        
        ranked_results = []
        
        for group_key, chunks in grouped_chunks.items():
            try:
                # Calculate group score using boosted scores
                group_score = self.calculate_group_score(chunks)
                ranked_results.append((group_key, chunks, group_score))
                
            except Exception as e:
                logger.error(f"Error ranking group {group_key}: {e}")
                continue
        
        # Sort by score descending
        ranked_results.sort(key=lambda x: x[2], reverse=True)
        
        return ranked_results
    
    def process_single_query(self, query_text: str, keywords: List[str]) -> List[str]:
        """Process a single query with its keywords, returning top 3 fulltext results"""
        if not query_text or not query_text.strip():
            raise ValueError("Query text cannot be empty")
        
        if not keywords:
            raise ValueError("Keywords are required for search")
        
        query_text = query_text.strip()
        
        try:
            # Semantic search with keyword boost
            search_results = self.semantic_search(query_text, keywords, self.config.results_per_query * 3)
            
            if not search_results:
                logger.warning(f"No search results found for query: '{query_text}'")
                return []
            
            # Group chunks
            grouped_chunks = self.collect_and_group_chunks(search_results)
            
            if not grouped_chunks:
                logger.warning(f"No grouped chunks found for query: '{query_text}'")
                return []
            
            # Rank using boosted scores
            ranked_results = self.rank_groups(grouped_chunks)
            
            # Get only top results and extract just the combined text
            full_texts = []
            for _, chunks, _ in ranked_results[:self.config.results_per_query]:
                # Create combined content
                chunk_texts = []
                for chunk in chunks:
                    chunk_texts.append(chunk.content)
                
                combined_content = "\n\n".join(chunk_texts)
                full_texts.append(combined_content)
            
            logger.info(f"Query '{query_text}' returned {len(full_texts)} results")
            return full_texts
            
        except Exception as e:
            logger.error(f"Error processing query '{query_text}': {e}")
            raise RuntimeError(f"Query processing failed: {e}")
    
    def process_email(self, email_content: str) -> List[EmailQueryResult]:
        """
        Complete email processing pipeline:
        1. Extract queries and keywords from email
        2. Process each query individually 
        3. Return results for all queries
        """
        if not email_content or not email_content.strip():
            raise ValueError("Email content cannot be empty")
        
        try:
            # Step 1: Extract queries and keywords from email
            queries_with_keywords = self.extract_queries_from_email(email_content)
            
            if not queries_with_keywords:
                logger.warning("No queries extracted from email")
                return []
            
            # Step 2: Process each query
            all_results = []
            for query_data in queries_with_keywords:
                try:
                    # Process single query
                    results = self.process_single_query(query_data.query, query_data.keywords)
                    
                    # Create result object
                    query_result = EmailQueryResult(
                        original_query=query_data.query,
                        keywords=query_data.keywords,
                        results=results,
                        total_found=len(results)
                    )
                    
                    all_results.append(query_result)
                    
                except Exception as e:
                    logger.error(f"Error processing query '{query_data.query}': {e}")
                    # Add empty result for failed query
                    query_result = EmailQueryResult(
                        original_query=query_data.query,
                        keywords=query_data.keywords,
                        results=[],
                        total_found=0
                    )
                    all_results.append(query_result)
                    continue
            
            # Clean up memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info(f"Email processing completed. Processed {len(queries_with_keywords)} queries, "
                       f"found results for {sum(1 for r in all_results if r.total_found > 0)} queries")
            
            return all_results
            
        except Exception as e:
            logger.error(f"Error in email processing pipeline: {e}")
            raise RuntimeError(f"Email processing pipeline failed: {e}")


# Factory function
def create_query_module(
    embedding_module,
    deepseek_api_key: str,  # Required now
    deepseek_model: str = "deepseek-chat",
    config: Optional[RankingConfig] = None
) -> VietnameseQueryModule:
    """Factory function to create query module"""
    return VietnameseQueryModule(
        embedding_module=embedding_module,
        deepseek_api_key=deepseek_api_key,
        deepseek_model=deepseek_model,
        config=config
    )


# Example usage
if __name__ == "__main__":
    try:
        print("Initializing Vietnamese Query Module for Email Processing...")
        
        # Create simplified config
        config = RankingConfig(
            similarity_threshold=0.7,
            min_score_threshold=0.3,
    
            content_keyword_boost=1.2,
            metadata_keyword_boost=1.8,
            original_chunk_boost=0.1,
            multi_chunk_boost=0.05,
    
            # Adjacent chunk retrieval
            adjacent_before=3,
            adjacent_after=3,
            
            # Results per query
            results_per_query=3
        )
        
        # Create embedding module
        embedding_module = VietnameseEmbeddingModule(
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name="vietnamese_chunks_test",
            model_name="bkai-foundation-models/vietnamese-bi-encoder"
        )
        
        query_module = create_query_module(
            embedding_module=embedding_module,
            deepseek_api_key=deepseek_api_key,
            deepseek_model="deepseek-chat",
            config=config
        )
        
        # Test email
        test_email = """
Xin chào,

Tôi là sinh viên năm cuối và có một số câu hỏi về đồ án tốt nghiệp:

1. Cách tính điểm quá trình đồ án tốt nghiệp như thế nào?
2. Thời gian nộp báo cáo đồ án cuối kỳ là khi nào?
3. Có cần đăng ký chương trình kỹ sư tài năng không?

Cảm ơn thầy/cô!
        """
        
        results = query_module.process_email(test_email)
        
        print(f"\n=== EMAIL PROCESSING RESULTS ===")
        print(f"Extracted and processed {len(results)} queries")
        
        for i, result in enumerate(results):
            print(f"\n--- QUERY {i+1} ---")
            print(f"Query: {result.original_query}")
            print(f"Keywords: {result.keywords}")
            print(f"Found {result.total_found} results")
            
            for j, text in enumerate(result.results):
                print(f"\n** Result {j+1} **")
                print(text)
        
        
    except Exception as e:
        print(f"Error testing query module: {e}")
        import traceback
        traceback.print_exc()