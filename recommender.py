import numpy as np
from sentence_transformers import SentenceTransformer
from paper import ArxivPaper
from datetime import datetime
from loguru import logger
import os
import requests
from typing import List, Dict, Any, Optional, Union

# Default vectorization model
DEFAULT_LOCAL_MODEL = 'avsolatorio/GIST-small-Embedding-v0'
DEFAULT_API_MODEL = 'text-embedding-3-small'
DEFAULT_API_BASE = 'https://api.openai.com/v1'

class EmbeddingProvider:
    """Base class for embedding providers"""
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode a list of texts into embeddings"""
        raise NotImplementedError()
    
    def similarity(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """Calculate cosine similarity between two sets of embeddings"""
        # Log embedding shapes for debugging
        logger.debug(f"Computing similarity between embeddings of shapes {embeddings1.shape} and {embeddings2.shape}")
        
        # Normalize embeddings for cosine similarity
        norm1 = np.linalg.norm(embeddings1, axis=1, keepdims=True)
        norm2 = np.linalg.norm(embeddings2, axis=1, keepdims=True)
        
        # Avoid division by zero
        norm1 = np.where(norm1 == 0, 1e-10, norm1)
        norm2 = np.where(norm2 == 0, 1e-10, norm2)
        
        embeddings1_normalized = embeddings1 / norm1
        embeddings2_normalized = embeddings2 / norm2
        
        # Calculate cosine similarity
        similarity_matrix = np.dot(embeddings1_normalized, embeddings2_normalized.T)
        
        # Log similarity matrix shape and sample values for debugging
        logger.debug(f"Similarity matrix shape: {similarity_matrix.shape}")
        if similarity_matrix.size > 0:
            logger.debug(f"Similarity range: min={similarity_matrix.min():.4f}, max={similarity_matrix.max():.4f}, mean={similarity_matrix.mean():.4f}")
        
        return similarity_matrix


class LocalEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using local sentence-transformers models"""
    
    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL):
        """Initialize with a local sentence transformer model"""
        logger.info(f"Initializing local embedding provider with model: {model_name}")
        self.model = SentenceTransformer(model_name)
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts using the local model"""
        return self.model.encode(texts)
    
    def similarity(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """Use the built-in similarity function if available, otherwise fall back to base implementation"""
        try:
            return self.model.similarity(embeddings1, embeddings2)
        except AttributeError:
            return super().similarity(embeddings1, embeddings2)


class APIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using external API (e.g., OpenAI)"""
    
    def __init__(self, api_key: str, model_name: str = DEFAULT_API_MODEL, base_url: str = DEFAULT_API_BASE):
        """Initialize with API credentials"""
        if not api_key:
            raise ValueError("API key is required for API embedding provider")
            
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip('/')
        self.embedding_url = f"{self.base_url}/embeddings"
        
        logger.info(f"Initializing API embedding provider with model: {model_name}")
        
        # Set up session with retry logic
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts using the API"""
        all_embeddings = []
        batch_size = 20  # Process in batches to avoid API limits
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            logger.debug(f"Processing batch {i//batch_size + 1} with {len(batch_texts)} texts")
            
            try:
                response = self.session.post(
                    self.embedding_url,
                    json={
                        "model": self.model_name,
                        "input": batch_texts
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract embeddings from response
                batch_embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(batch_embeddings)
                
            except Exception as e:
                logger.error(f"Error getting embeddings from API: {e}")
                # Return zero embeddings as fallback
                return np.zeros((len(texts), 1024))  # Most embedding models use 1024 dimensions
        
        return np.array(all_embeddings)


def get_embedding_provider(
    use_api: bool = False, 
    api_key: Optional[str] = None, 
    api_base: str = DEFAULT_API_BASE, 
    api_model: str = DEFAULT_API_MODEL,
    local_model: str = DEFAULT_LOCAL_MODEL
) -> EmbeddingProvider:
    """Factory function to get the appropriate embedding provider"""
    # 检查环境变量中是否有明确设置
    env_use_api = os.environ.get('USE_EMBEDDING_API', '').lower()
    if env_use_api in ['true', '1', 'yes', 'y']:
        use_api = True
        logger.info("Embedding API enabled via environment variable (USE_EMBEDDING_API=true)")
    elif env_use_api in ['false', '0', 'no', 'n']:
        use_api = False
        logger.info("Embedding API disabled via environment variable (USE_EMBEDDING_API=false)")
    
    # 从环境变量中获取API密钥（如果未提供）
    if use_api and not api_key:
        api_key = os.environ.get('EMBEDDING_API_KEY')
        if api_key:
            logger.info("Using embedding API key from environment variable")
    
    # 从环境变量中获取API基础URL（如果未提供）
    env_api_base = os.environ.get('EMBEDDING_API_BASE')
    if env_api_base:
        api_base = env_api_base
        logger.info(f"Using embedding API base from environment variable: {api_base}")
    
    # 从环境变量中获取API模型（如果未提供）
    env_api_model = os.environ.get('EMBEDDING_MODEL')
    if env_api_model:
        api_model = env_api_model
        logger.info(f"Using embedding model from environment variable: {api_model}")
    
    # 从环境变量中获取本地模型（如果未提供）
    env_local_model = os.environ.get('LOCAL_VECTORIZATION_MODEL')
    if env_local_model:
        local_model = env_local_model
        logger.info(f"Using local vectorization model from environment variable: {local_model}")
    
    if use_api:
        if not api_key:
            logger.warning("API key not provided for embedding API. Falling back to local model.")
            return LocalEmbeddingProvider(local_model)
        try:
            logger.info(f"Initializing API embedding provider with model '{api_model}' at '{api_base}'")
            return APIEmbeddingProvider(api_key, api_model, api_base)
        except Exception as e:
            logger.error(f"Failed to initialize API embedding provider: {e}. Falling back to local model.")
            return LocalEmbeddingProvider(local_model)
    else:
        logger.info(f"Using local embedding provider with model: {local_model}")
        return LocalEmbeddingProvider(local_model)


def rerank_paper(
    candidate: List[ArxivPaper], 
    corpus: List[Dict[str, Any]], 
    use_embedding_api: bool = False,
    embedding_api_key: Optional[str] = None,
    embedding_api_base: str = DEFAULT_API_BASE,
    embedding_model: str = DEFAULT_API_MODEL,
    local_vectorization_model: str = DEFAULT_LOCAL_MODEL
) -> List[ArxivPaper]:
    """
    Rerank papers based on their similarity to the user's Zotero corpus.
    
    Args:
        candidate: List of ArxivPaper objects to rank
        corpus: List of papers from Zotero
        use_embedding_api: Whether to use an external embedding API
        embedding_api_key: API key for the embedding API
        embedding_api_base: Base URL for the embedding API
        embedding_model: Model name to use with the API
        local_vectorization_model: Local model name or path
        
    Returns:
        Sorted list of ArxivPaper objects by relevance score
    """
    logger.info(f"Starting paper reranking with {len(candidate)} candidates and {len(corpus)} corpus papers")
    logger.debug(f"Initial parameters: use_api={use_embedding_api}, api_base={embedding_api_base}, model={embedding_model}, local_model={local_vectorization_model}")
    
    # Get embedding provider based on configuration
    try:
        provider = get_embedding_provider(
            use_api=use_embedding_api,
            api_key=embedding_api_key,
            api_base=embedding_api_base,
            api_model=embedding_model,
            local_model=local_vectorization_model
        )
        
        # Sort corpus by date, from newest to oldest
        corpus = sorted(corpus, key=lambda x: datetime.strptime(x['data']['dateAdded'], '%Y-%m-%dT%H:%M:%SZ'), reverse=True)
        
        # Calculate time decay weights - more recent papers get higher weights
        time_decay_weight = 1 / (1 + np.log10(np.arange(len(corpus)) + 1))
        time_decay_weight = time_decay_weight / time_decay_weight.sum()
        
        # Encode corpus and candidate papers
        logger.info(f"Encoding {len(corpus)} papers from Zotero corpus")
        corpus_feature = provider.encode([paper['data']['abstractNote'] for paper in corpus])
        
        logger.info(f"Encoding {len(candidate)} candidate papers from arXiv")
        candidate_feature = provider.encode([paper.summary for paper in candidate])
        
        # Calculate similarity scores
        sim = provider.similarity(candidate_feature, corpus_feature)  # [n_candidate, n_corpus]
        scores = (sim * time_decay_weight).sum(axis=1) * 10  # [n_candidate]
        
        # Assign scores to candidate papers
        for s, c in zip(scores, candidate):
            logger.info(f"Paper {c.title} - Score: {s:.6f}")
            c.score = s.item()
        
        # Sort papers by score in descending order
        candidate = sorted(candidate, key=lambda x: x.score, reverse=True)
        
        return candidate
    
    except Exception as e:
        logger.error(f"Error during paper vectorization: {e}")
        # In case of error, return unsorted papers
        for c in candidate:
            c.score = 0.0
        return candidate