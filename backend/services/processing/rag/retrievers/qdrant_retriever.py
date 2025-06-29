import logging
from typing import List, Dict, Any
from dataclasses import dataclass
import torch
import os
import json
import math

from backend.common.config import settings
from backend.services.processing.rag.common.cuda import CudaMemoryManager
from backend.services.processing.rag.common.qdrant import QdrantManager
from backend.services.processing.rag.common.utils import create_deepseek_client
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    chunk_id: int
    content: str
    score: float
    metadata: Dict[str, Any]

@dataclass
class EmailQueryResult:
    original_query: str
    results: List[Dict[str, Any]]
    total_found: int
    context_summary: str = ""

class VietnameseQueryModule:    
    def __init__(self, 
                 embedding_module,
                 deepseek_api_key: str,
                 memory_manager=None,
                 deepseek_model: str = "deepseek-chat",
                 reranker_model_name: str = "AITeamVN/Vietnamese_Reranker",
                 dense_model_name: str = "AITeamVN/Vietnamese_Embedding_v2",
                 sparse_model_name: str = "Qdrant/bm25",
                 limit: int = 5,
                 candidates_limit: int = 10,
                 dense_weight: float = 0.8,
                 sparse_weight: float = 0.2,
                 normalization: str = "min_max",
                 candidates_multiplier: int = 3):
        
        self.embedding_module = embedding_module
        self.limit = limit
        self.candidates_limit = candidates_limit
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.normalization = normalization
        self.candidates_multiplier = candidates_multiplier
        self.reranker_model_name = reranker_model_name
        self.dense_model_name = dense_model_name
        self.sparse_model_name = sparse_model_name
        
        if not deepseek_api_key:
            raise ValueError("DeepSeek API key is required for query extraction")
            
        self.deepseek = create_deepseek_client(
            deepseek_api_key=deepseek_api_key,
            deepseek_api_url=settings.DEEPSEEK_API_URL,
            deepseek_model=deepseek_model
        )
        
        self.memory_manager = memory_manager
        
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            logger.info("Using CUDA for Vietnamese Query Module")
        else:
            self.device = torch.device("cpu")
            logger.warning("CUDA not available, using CPU for Vietnamese Query Module")
        
        if not hasattr(self.embedding_module, 'qdrant_manager'):
            raise ValueError("Embedding module must have a qdrant_manager attribute")
        
        self.qdrant_manager = self.embedding_module.qdrant_manager
    
    def min_max_normalize(self, score: float, min_val: float, max_val: float) -> float:
        """Min-max normalization to range 0-1"""
        if max_val == min_val:
            return 0.0
        return (score - min_val) / (max_val - min_val)
    
    def z_score_normalize(self, score: float, mean: float, std: float) -> float:
        """Z-score normalization"""
        if std == 0:
            return 0.0
        return (score - mean) / std
    
    def weighted_score_fusion(
        self, 
        dense_results: List, 
        sparse_results: List,
        candidates_limit: int,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        normalization: str = "min_max"
    ) -> List[Dict[str, Any]]:
        """Process dense and sparse search results with weighted fusion"""
        import math
        
        # If both searches failed, return empty results
        if not dense_results and not sparse_results:
            logger.warning("Both dense and sparse searches failed")
            return []
            
        # If one result set is empty, return the other with appropriate formatting
        if not dense_results and sparse_results:
            logger.warning("Dense search failed, using only sparse results")
            return self._format_search_results(sparse_results[:candidates_limit])
            
        if not sparse_results and dense_results:
            logger.warning("Sparse search failed, using only dense results")
            return self._format_search_results(dense_results[:candidates_limit])
        
        # For both dense and sparse results, collect all unique chunks
        all_chunks = {}
        
        # Extract score arrays for normalization
        dense_scores = [r.score for r in dense_results]
        sparse_scores = [r.score for r in sparse_results]
        
        # Calculate normalization parameters
        if normalization == "min_max" and dense_scores and sparse_scores:
            dense_min, dense_max = min(dense_scores), max(dense_scores)
            sparse_min, sparse_max = min(sparse_scores), max(sparse_scores)
        elif normalization == "z_score" and dense_scores and sparse_scores:
            dense_mean = sum(dense_scores) / len(dense_scores)
            dense_std = math.sqrt(sum((x - dense_mean)**2 for x in dense_scores) / len(dense_scores))
            sparse_mean = sum(sparse_scores) / len(sparse_scores)
            sparse_std = math.sqrt(sum((x - sparse_mean)**2 for x in sparse_scores) / len(sparse_scores))
        else:
            # Fallback normalization
            normalization = "none"
        
        # Process dense results
        for result in dense_results:
            chunk_id = result.payload.get("chunk_id", 0)
            score = result.score
            
            # Normalize score based on selected method
            if normalization == "min_max" and dense_scores:
                score = self.min_max_normalize(score, dense_min, dense_max)
            elif normalization == "z_score" and dense_scores:
                score = self.z_score_normalize(score, dense_mean, dense_std)
            
            # Store result data
            all_chunks[chunk_id] = {
                "payload": result.payload,
                "dense_score": score, 
                "sparse_score": 0.0,
                "raw_dense_score": result.score,
                "raw_sparse_score": 0.0
            }
        
        # Process sparse results
        for result in sparse_results:
            chunk_id = result.payload.get("chunk_id", 0)
            score = result.score
            
            # Normalize score based on selected method
            if normalization == "min_max" and sparse_scores:
                score = self.min_max_normalize(score, sparse_min, sparse_max)
            elif normalization == "z_score" and sparse_scores:
                score = self.z_score_normalize(score, sparse_mean, sparse_std)
            
            # Update existing entry or add new one
            if chunk_id in all_chunks:
                all_chunks[chunk_id]["sparse_score"] = score
                all_chunks[chunk_id]["raw_sparse_score"] = result.score
            else:
                all_chunks[chunk_id] = {
                    "payload": result.payload,
                    "dense_score": 0.0,
                    "sparse_score": score,
                    "raw_dense_score": 0.0,
                    "raw_sparse_score": result.score
                }
        
        # Combine scores and prepare final results
        final_results = []
        for chunk_id, data in all_chunks.items():
            # Calculate weighted final score
            final_score = (data["dense_score"] * dense_weight + 
                          data["sparse_score"] * sparse_weight)
            
            # Create result dictionary
            payload = data["payload"]
            result = {
                "chunk_id": chunk_id,
                "content": payload.get("content", ""),
                "score": final_score,
                "normalized_dense_score": data["dense_score"],
                "normalized_sparse_score": data["sparse_score"],
                "raw_dense_score": data["raw_dense_score"],
                "raw_sparse_score": data["raw_sparse_score"],
                "metadata": {
                    "file_id": payload.get("file_id", "unknown"),
                    "parent_chunk_id": payload.get("parent_chunk_id", 0),
                    "file_created_at": payload.get("file_created_at", None),
                    "source": payload.get("source", None)
                }
            }
            
            # Add any additional metadata from payload
            for key, value in payload.items():
                if key not in ["chunk_id", "content", "file_id", "parent_chunk_id", "file_created_at", "source", "is_deleted"]:
                    result["metadata"][key] = value
            
            final_results.append(result)
        
        # Sort by combined score (descending) and limit results
        sorted_results = sorted(final_results, key=lambda x: x["score"], reverse=True)
        return sorted_results[:candidates_limit]

    def _format_search_results(self, search_results: List) -> List[Dict[str, Any]]:
        """Format single search results to match hybrid output format"""
        results = []
        for hit in search_results:
            # Create metadata dictionary
            metadata = {
                "file_id": hit.payload.get("file_id", "unknown"),
                "parent_chunk_id": hit.payload.get("parent_chunk_id", 0),
                "file_created_at": hit.payload.get("file_created_at", None),
                "source": hit.payload.get("source", None)
            }
            
            # Add any additional metadata fields from the payload
            for key, value in hit.payload.items():
                if key not in ["chunk_id", "content", "file_id", "parent_chunk_id", "file_created_at", "source"]:
                    metadata[key] = value
            
            # Format result
            result = {
                "chunk_id": hit.payload.get("chunk_id", 0),
                "content": hit.payload.get("content", ""),
                "score": hit.score,
                "metadata": metadata
            }
            results.append(result)
        
        return results
    
    def rerank_results(self, query: str, results: List[Dict[str, Any]], top_k: int = None) -> List[Dict[str, Any]]:
        """Rerank results using the CrossEncoder model"""
        if not self.qdrant_manager.reranker or not results:
            return results[:top_k] if top_k else results
        
        if top_k is None:
            top_k = len(results)
        
        try:
            # Prepare query-document pairs
            query_doc_pairs = [(query, result["content"]) for result in results]
            
            # Get scores from reranker
            with torch.no_grad():
                reranker_scores = self.qdrant_manager.reranker.predict(query_doc_pairs)
                if hasattr(reranker_scores, 'tolist'):
                    reranker_scores = reranker_scores.tolist()
            
            # Add scores to results
            reranked = []
            for i, result in enumerate(results):
                result_copy = result.copy()
                result_copy["reranker_score"] = float(reranker_scores[i])
                result_copy["original_rank"] = i + 1
                reranked.append(result_copy)
            
            # Sort by reranker score
            reranked.sort(key=lambda x: x["reranker_score"], reverse=True)
            return reranked[:top_k]
            
        except Exception as e:
            logger.error(f"Error in reranking: {e}")
            return results[:top_k]
        
    def retrieve(self, query: str, limit: int = 5, candidates_limit: int = 10, 
               dense_weight: float = 0.7, sparse_weight: float = 0.3, 
               normalization: str = "min_max", candidates_multiplier: int = 3) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        
        try:
            search_results = self.qdrant_manager.hybrid_search(
                query=query,
                candidates_limit=candidates_limit,
                candidates_multiplier=candidates_multiplier
            )
            
            dense_results = search_results.get("dense_results", [])
            sparse_results = search_results.get("sparse_results", [])
            
            candidates = self.weighted_score_fusion(
                dense_results, sparse_results, candidates_limit,
                dense_weight, sparse_weight, normalization
            )
            
            if not candidates:
                return []
            
            if self.qdrant_manager.reranker:
                return self.rerank_results(query, candidates, limit)
            else:
                return candidates[:limit]
            
        except Exception as e:
            logger.error(f"Error in search: {e}")
            return []  # Return empty list to maintain API compatibility
    


    def process_single_query(self, query_text: str) -> List[Dict[str, Any]]:
        if not query_text or not query_text.strip():
            return []
        
        try:
            search_results = self.retrieve(
                query=query_text.strip(),
                limit=self.limit,
                candidates_limit=self.candidates_limit,
                dense_weight=self.dense_weight,
                sparse_weight=self.sparse_weight,
                normalization=self.normalization,
                candidates_multiplier=self.candidates_multiplier
            )
            

            return search_results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def extract_queries_and_summary_from_email(self, email_content: str) -> tuple[List[str], str, object]:
        """Start a conversation with DeepSeek and extract queries and summary from email"""
        if not email_content or not email_content.strip():
            return ["Không có nội dung email"], "Email trống", None
        
        first_line_fallback = email_content.strip().split('\n')[0][:100]
        basic_summary = f"Email về: {first_line_fallback}"
        
        conversation = None
        try:
            system_message = "Bạn là trợ lý AI chuyên nghiệp hỗ trợ phòng công tác sinh viên. Bạn sẽ giúp phân tích email, tìm kiếm thông tin và soạn thảo phản hồi."
            conversation = self.deepseek.start_conversation(system_message)
            logger.info("Successfully started DeepSeek conversation")
        except Exception as e:
            logger.error(f"Failed to start DeepSeek conversation: {e}")
            return [first_line_fallback], basic_summary, None
        
        try:
            prompt = f"""Hãy phân tích đoạn hội thoại email sau và:
1. Trích xuất tất cả các câu hỏi/yêu cầu thông tin mà sinh viên chưa có câu trả lời
2. Tạo một tóm tắt thông tin một cách đẩy đủ, súc tích về nội dung đoạn hội thoại email

Trả về kết quả dưới dạng JSON với format sau:
{{
    "queries": [
        "câu hỏi 1",
        "câu hỏi 2"
    ],
    "summary": "tóm tắt thông tin về nội dung hội thoại email, đảm bảo đủ thông tin để trả lời các câu hỏi, súc tích, không quá 700 từ"
}}

Lưu ý:
- Mỗi query phải là một câu hỏi hoàn chỉnh và rõ ràng
- Đảm bảo đúng chính tả tiếng Việt
- Chỉ trả về JSON, không thêm giải thích

Email cần phân tích:
{email_content}"""
            
            response_text = self.deepseek.send_message(
                conversation=conversation, 
                message=prompt,
                temperature=0.4,
                max_tokens=4000,
                error_default=None  # Use None to raise exception on error
            )
            
            # If no response or empty, return fallback but keep conversation
            if not response_text or not response_text.strip():
                logger.warning("DeepSeek returned empty response, using fallback")
                return [first_line_fallback], basic_summary, conversation
            
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            parsed_response = json.loads(response_text.strip())
            
            queries = [q.strip() for q in parsed_response.get("queries", []) if isinstance(q, str) and q.strip()]
            
            summary = parsed_response.get("summary", "").strip()
            if not summary:
                summary = basic_summary
            
            logger.info(f"Successfully extracted {len(queries)} queries from email")
            return (queries if queries else [first_line_fallback]), summary, conversation
                
        except Exception as e:
            logger.error(f"Error in DeepSeek message processing: {e}")
            # Return fallback but keep conversation for future use
            return [first_line_fallback], basic_summary, conversation

    def process_email(self, email_content: str) -> tuple[List[EmailQueryResult], object]:
        """Process an entire email with multiple queries and return results with conversation"""
        if not email_content or not email_content.strip():
            return [], None
        
        try:
            queries, summary, conversation = self.extract_queries_and_summary_from_email(email_content)
            if not queries:
                return [], conversation
            
            results = []
            for i, query in enumerate(queries):
                try:
                    query_results = self.process_single_query(query)
                    results.append(EmailQueryResult(
                        original_query=query,
                        results=query_results,
                        total_found=len(query_results),
                        context_summary=summary if i == 0 else ""
                    ))
                except Exception as e:
                    logger.error(f"Error processing query '{query}': {e}")
                    results.append(EmailQueryResult(
                        original_query=query,
                        results=[],
                        total_found=0,
                        context_summary=summary 
                    ))
            
            # Clean up resources
            if self.memory_manager:
                self.memory_manager.cleanup_memory()
            
            return results, conversation
            
        except Exception as e:
            logger.error(f"Email processing error: {e}")
            if self.memory_manager:
                self.memory_manager.cleanup_memory()
            return [], None

    def extract_queries_from_text(self, text_content: str) -> tuple[List[str], object]:
        """Extract queries from general text content (no summary needed)"""
        if not text_content or not text_content.strip():
            return ["Không có nội dung"], None
        
        first_line_fallback = text_content.strip().split('\n')[0][:100]
        
        conversation = None
        try:
            system_message = "Bạn là trợ lý AI chuyên nghiệp hỗ trợ phòng công tác sinh viên. Bạn sẽ giúp phân tích text, tìm kiếm thông tin và trả lời câu hỏi."
            conversation = self.deepseek.start_conversation(system_message)
            logger.info("Successfully started DeepSeek conversation for text processing")
        except Exception as e:
            logger.error(f"Failed to start DeepSeek conversation: {e}")
            return [first_line_fallback], None
        
        try:
            prompt = f"""
<instructions>
**VAI TRÒ:**
Bạn là một AI chuyên gia phân tích và chuyển đổi ý định người dùng thành các truy vấn tìm kiếm (search queries) hiệu quả cho một hệ thống RAG.

**NHIỆM VỤ:**
Phân tích đoạn văn bản do người dùng cung cấp. Thay vì chỉ trích xuất các câu hỏi có sẵn, hãy xác định **ý định tìm kiếm cốt lõi** và tạo ra một hoặc nhiều câu hỏi rõ ràng, mạch lạc, có thể dùng để truy vấn vào một cơ sở dữ liệu tri thức.

**QUY TRÌNH SUY LUẬN:**
1.  Đọc kỹ văn bản và xác định các chủ đề chính mà người dùng quan tâm.
2.  Với mỗi chủ đề, hãy hình thành một câu hỏi hoàn chỉnh, tập trung vào bản chất của thông tin cần tìm.
3.  Nếu người dùng đưa ra một câu lệnh (ví dụ: "so sánh A và B"), hãy chuyển nó thành một hoặc nhiều câu hỏi (ví dụ: "A là gì?", "B là gì?", "Điểm khác biệt giữa A và B là gì?").
4.  Luôn đảm bảo câu hỏi được viết bằng tiếng Việt chuẩn, không chứa lỗi chính tả.

**ĐIỀU CẦN TRÁNH:**
*   Không bịa đặt câu hỏi không liên quan đến nội dung.
*   Không trích xuất các câu chào hỏi, cảm ơn.

**ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):**
Chỉ trả về một đối tượng JSON hợp lệ.
</instructions>

<example>
**Văn bản đầu vào:** "thủ tục thôi học và điều kiện tốt nghiệp"
**Kết quả JSON đầu ra:**
```json
{{
    "queries": [
        "thủ tục xin thôi học cho sinh viên là gì?",
        "điều kiện để được xét tốt nghiệp là gì?"
    ]
}}
```
</example>

<text_to_analyze>
{text_content}
</text_to_analyze>

Trả về kết quả dưới dạng JSON với format sau:
```json
{{
    "queries": [
        "câu hỏi 1",
        "câu hỏi 2"
    ]
}}
```"""
            
            response_text = self.deepseek.send_message(
                conversation=conversation, 
                message=prompt,
                temperature=0.4,
                max_tokens=4000,
                error_default=None
            )
            
            if not response_text or not response_text.strip():
                logger.warning("DeepSeek returned empty response for text, using fallback")
                return [first_line_fallback], conversation
            
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            parsed_response = json.loads(response_text.strip())
            
            queries = [q.strip() for q in parsed_response.get("queries", []) if isinstance(q, str) and q.strip()]
            
            logger.info(f"Successfully extracted {len(queries)} queries from text")
            return (queries if queries else [first_line_fallback]), conversation
                
        except Exception as e:
            logger.error(f"Error in DeepSeek text processing: {e}")
            return [first_line_fallback], conversation

    def process_text(self, text_content: str) -> tuple[List[EmailQueryResult], object]:
        """Process general text content with multiple queries and return results with conversation"""
        if not text_content or not text_content.strip():
            return [], None
        
        try:
            queries, conversation = self.extract_queries_from_text(text_content)
            if not queries:
                return [], conversation
            
            results = []
            for query in queries:
                try:
                    query_results = self.process_single_query(query)
                    results.append(EmailQueryResult(
                        original_query=query,
                        results=query_results,
                        total_found=len(query_results),
                        context_summary=""  # No summary needed for text processing
                    ))
                except Exception as e:
                    logger.error(f"Error processing query '{query}': {e}")
                    results.append(EmailQueryResult(
                        original_query=query,
                        results=[],
                        total_found=0,
                        context_summary=""
                    ))
            
            # Clean up resources
            if self.memory_manager:
                self.memory_manager.cleanup_memory()
            
            return results, conversation
            
        except Exception as e:
            logger.error(f"Text processing error: {e}")
            if self.memory_manager:
                self.memory_manager.cleanup_memory()
            return [], None


def create_query_module(
    embedding_module,
    deepseek_api_key: str,
    memory_manager=None,
    deepseek_model: str = "deepseek-chat",
    reranker_model_name: str = "AITeamVN/Vietnamese_Reranker",
    dense_model_name: str = "AITeamVN/Vietnamese_Embedding_v2",
    sparse_model_name: str = "Qdrant/bm25",
    limit: int = 5,
    candidates_limit: int = 10,
    dense_weight: float = 0.8,
    sparse_weight: float = 0.2,
    normalization: str = "min_max",
    candidates_multiplier: int = 3
) -> VietnameseQueryModule:
    return VietnameseQueryModule(
        embedding_module=embedding_module,
        deepseek_api_key=deepseek_api_key,
        memory_manager=memory_manager,
        deepseek_model=deepseek_model,
        reranker_model_name=reranker_model_name,
        dense_model_name=dense_model_name,
        sparse_model_name=sparse_model_name,
        limit=limit,
        candidates_limit=candidates_limit,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        normalization=normalization,
        candidates_multiplier=candidates_multiplier
    )
