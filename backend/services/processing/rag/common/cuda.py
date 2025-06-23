"""
CUDA Configuration and Memory Management
"""

import gc
import logging
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CudaMemoryManager:
    """Memory manager for CUDA devices"""
    
    def __init__(self, device_id: int = 0):
        self.device_id = device_id
        if not torch.cuda.is_available():
            logger.warning("CUDA is not available, using CPU")
            self.device = torch.device("cpu")
            self.is_cuda_available = False
            return
            
        self.is_cuda_available = True
        self.device = torch.device(f"cuda:{device_id}")
        torch.cuda.set_device(device_id)
        
        # Setup memory management
        self.total_memory = torch.cuda.get_device_properties(device_id).total_memory
        self.safe_memory_limit = int(self.total_memory * 0.75)  # Use only 75% of memory
        self.cleanup_threshold = int(self.total_memory * 0.65)  # Cleanup when > 65%
        
        # Batch configuration
        self.max_batch_size = 16
        self.embedding_batch_size = 12
        self.sequence_length_limit = 2048
        
        # CUDA optimizations
        self._setup_cuda_optimizations()
        
        logger.info(f"CUDA Memory Manager initialized:")
        logger.info(f"  - GPU: {torch.cuda.get_device_name(device_id)}")
        logger.info(f"  - Total VRAM: {self.total_memory / 1024**3:.1f} GB")
        logger.info(f"  - Max batch size: {self.max_batch_size}")
    
    def _setup_cuda_optimizations(self):
        """Setup CUDA optimizations"""
        if not self.is_cuda_available:
            return
            
        # Performance optimizations
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.enabled = True
        
        # Precision optimizations
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        
    def get_current_usage(self):
        """Get current memory usage"""
        if not self.is_cuda_available:
            return {"allocated_gb": 0, "reserved_gb": 0, "free_gb": 0, "usage_percent": 0}
            
        allocated = torch.cuda.memory_allocated(self.device_id)
        reserved = torch.cuda.memory_reserved(self.device_id)
        free = self.total_memory - reserved
        
        return {
            "allocated_gb": allocated / 1024**3,
            "reserved_gb": reserved / 1024**3,
            "free_gb": free / 1024**3,
            "usage_percent": (reserved / self.total_memory) * 100
        }
    
    def should_cleanup(self):
        """Check if memory cleanup is needed"""
        if not self.is_cuda_available:
            return False
        return torch.cuda.memory_reserved(self.device_id) > self.cleanup_threshold
    
    def cleanup_memory(self, force: bool = False):
        """Clean up CUDA memory"""
        if not self.is_cuda_available:
            return
            
        if force or self.should_cleanup():
            # Python garbage collection
            gc.collect()
            
            # CUDA memory cleanup
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            
            # Log memory status
            usage = self.get_current_usage()
            logger.info(f"Memory cleaned - Usage: {usage['usage_percent']:.1f}% ({usage['reserved_gb']:.2f}GB)")


def setup_cuda_device(cuda_device: int = 0):
    """Setup CUDA device and return the device"""
    if not torch.cuda.is_available():
        logger.warning("CUDA is not available, using CPU")
        return torch.device("cpu")
    
    device = torch.device(f"cuda:{cuda_device}")
    torch.cuda.set_device(cuda_device)
    
    # Log device info
    gpu_name = torch.cuda.get_device_name(cuda_device)
    gpu_memory = torch.cuda.get_device_properties(cuda_device).total_memory / 1024**3
    
    logger.info(f"✓ CUDA Setup Complete")
    logger.info(f"✓ GPU: {gpu_name}")
    logger.info(f"✓ VRAM: {gpu_memory:.1f} GB")
    logger.info(f"✓ CUDA Version: {torch.version.cuda}")
    
    return device
