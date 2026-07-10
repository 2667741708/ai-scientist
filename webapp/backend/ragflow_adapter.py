from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests


DEFAULT_RAGFLOW_DELIMITER = "\n!?。；！？"


def _env_float(name: str, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int = 100_000) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _endpoint(base_url: str, suffix: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith(suffix):
        return normalized
    return f"{normalized}/{suffix.lstrip('/')}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def approx_token_count(text: str) -> int:
    """Cheap multilingual token estimate used only for chunk budgeting."""
    ascii_words = re.findall(r"[A-Za-z0-9_]+", text)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    other = max(0, len(text) - sum(len(word) for word in ascii_words) - len(cjk_chars))
    return max(1, len(ascii_words) + math.ceil(len(cjk_chars) / 1.7) + math.ceil(other / 6))


@dataclass(frozen=True)
class RagflowAdapterConfig:
    chunk_token_num: int
    delimiter: str
    overlapped_percent: float
    embedding_provider: str
    embedding_model: str
    embedding_endpoint: str
    embedding_api_key: str
    embedding_timeout_seconds: float
    embedding_batch_size: int
    rerank_provider: str
    rerank_model: str
    rerank_endpoint: str
    rerank_api_key: str
    rerank_timeout_seconds: float
    vector_similarity_weight: float
    similarity_threshold: float
    candidate_multiplier: int

    @property
    def embedding_enabled(self) -> bool:
        provider = self.embedding_provider.lower()
        return provider in {"hash", "local_hash"} or bool(self.embedding_model and self.embedding_endpoint)

    @property
    def rerank_enabled(self) -> bool:
        provider = self.rerank_provider.lower()
        return provider in {"http", "openai-compatible", "jina", "cohere", "voyage"} and bool(self.rerank_endpoint)

    @property
    def retrieval_mode(self) -> str:
        if self.embedding_enabled and self.rerank_enabled:
            return "hybrid_vector_rerank"
        if self.embedding_enabled:
            return "hybrid_vector"
        return "sqlite_fts"


def load_ragflow_adapter_config() -> RagflowAdapterConfig:
    embedding_base = os.getenv("COSCIENTIST_RAG_EMBEDDING_BASE_URL", "")
    embedding_endpoint = os.getenv("COSCIENTIST_RAG_EMBEDDING_ENDPOINT", "")
    if not embedding_endpoint and embedding_base:
        embedding_endpoint = _endpoint(embedding_base, "/embeddings")

    rerank_base = os.getenv("COSCIENTIST_RAG_RERANK_BASE_URL", "")
    rerank_endpoint = os.getenv("COSCIENTIST_RAG_RERANK_ENDPOINT", "")
    if not rerank_endpoint and rerank_base:
        rerank_endpoint = _endpoint(rerank_base, "/rerank")

    return RagflowAdapterConfig(
        chunk_token_num=_env_int("COSCIENTIST_RAG_CHUNK_TOKEN_NUM", 512, minimum=64, maximum=4096),
        delimiter=os.getenv("COSCIENTIST_RAG_CHUNK_DELIMITER", DEFAULT_RAGFLOW_DELIMITER),
        overlapped_percent=_env_float("COSCIENTIST_RAG_CHUNK_OVERLAP_PERCENT", 0.0, minimum=0.0, maximum=40.0),
        embedding_provider=os.getenv("COSCIENTIST_RAG_EMBEDDING_PROVIDER", "openai-compatible"),
        embedding_model=os.getenv("COSCIENTIST_RAG_EMBEDDING_MODEL", ""),
        embedding_endpoint=embedding_endpoint,
        embedding_api_key=os.getenv("COSCIENTIST_RAG_EMBEDDING_API_KEY", ""),
        embedding_timeout_seconds=float(os.getenv("COSCIENTIST_RAG_EMBEDDING_TIMEOUT_SECONDS", "45")),
        embedding_batch_size=_env_int("COSCIENTIST_RAG_EMBEDDING_BATCH_SIZE", 32, minimum=1, maximum=256),
        rerank_provider=os.getenv("COSCIENTIST_RAG_RERANK_PROVIDER", "openai-compatible"),
        rerank_model=os.getenv("COSCIENTIST_RAG_RERANK_MODEL", ""),
        rerank_endpoint=rerank_endpoint,
        rerank_api_key=os.getenv("COSCIENTIST_RAG_RERANK_API_KEY", ""),
        rerank_timeout_seconds=float(os.getenv("COSCIENTIST_RAG_RERANK_TIMEOUT_SECONDS", "30")),
        vector_similarity_weight=_env_float("COSCIENTIST_RAG_VECTOR_WEIGHT", 0.3, minimum=0.0, maximum=1.0),
        similarity_threshold=_env_float("COSCIENTIST_RAG_SIMILARITY_THRESHOLD", 0.05, minimum=0.0, maximum=1.0),
        candidate_multiplier=_env_int("COSCIENTIST_RAG_CANDIDATE_MULTIPLIER", 8, minimum=2, maximum=50),
    )


def ragflow_merge_paragraphs(
    paragraphs: Iterable[str],
    *,
    chunk_token_num: int,
    delimiter: str = DEFAULT_RAGFLOW_DELIMITER,
    overlapped_percent: float = 0.0,
) -> list[list[str]]:
    """RAGFlow-style merge: split by delimiters, then merge to token budget."""
    pieces: list[str] = []
    split_pattern = f"([{re.escape(delimiter)}])"
    for paragraph in paragraphs:
        text = str(paragraph or "").strip()
        if not text:
            continue
        if text.lower().startswith(("table ", "|")) or "\t" in text:
            pieces.append(text)
            continue
        parts = re.split(split_pattern, text)
        sentence = ""
        for part in parts:
            if not part:
                continue
            sentence += part
            if part in delimiter:
                if sentence.strip():
                    pieces.append(sentence.strip())
                sentence = ""
        if sentence.strip():
            pieces.append(sentence.strip())

    groups: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    max_tokens = max(1, chunk_token_num)
    for piece in pieces:
        piece_tokens = approx_token_count(piece)
        if current and current_tokens + piece_tokens > max_tokens:
            groups.append(current)
            if overlapped_percent > 0:
                overlap_tokens = max(1, int(max_tokens * overlapped_percent / 100.0))
                tail: list[str] = []
                tail_tokens = 0
                for old_piece in reversed(current):
                    tail.insert(0, old_piece)
                    tail_tokens += approx_token_count(old_piece)
                    if tail_tokens >= overlap_tokens:
                        break
                current = tail
                current_tokens = tail_tokens
            else:
                current = []
                current_tokens = 0
        current.append(piece)
        current_tokens += piece_tokens
    if current:
        groups.append(current)
    return groups


class RagflowEmbeddingClient:
    def __init__(self, config: Optional[RagflowAdapterConfig] = None):
        self.config = config or load_ragflow_adapter_config()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        provider = self.config.embedding_provider.lower()
        safe_texts = [text if str(text or "").strip() else "None" for text in texts]
        if provider in {"hash", "local_hash"}:
            return [self._hash_embedding(text) for text in safe_texts]
        if not self.config.embedding_endpoint or not self.config.embedding_model:
            return []

        headers = {"Content-Type": "application/json"}
        if self.config.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.config.embedding_api_key}"
        payload = {
            "model": self.config.embedding_model,
            "input": safe_texts,
        }
        response = requests.post(
            self.config.embedding_endpoint,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.config.embedding_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data", body.get("embeddings", []))
        if isinstance(data, list) and data and isinstance(data[0], list):
            return [[float(x) for x in item] for item in data]
        ordered = sorted(data, key=lambda item: int(item.get("index", 0))) if isinstance(data, list) else []
        vectors = []
        for item in ordered:
            vector = item.get("embedding") or item.get("vector")
            if vector is None:
                continue
            vectors.append([float(x) for x in vector])
        return vectors

    @staticmethod
    def _hash_embedding(text: str, *, dimensions: int = 384) -> list[float]:
        vector = [0.0] * dimensions
        tokens = re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", text.lower())
        if not tokens:
            tokens = ["none"]
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class RagflowRerankClient:
    def __init__(self, config: Optional[RagflowAdapterConfig] = None):
        self.config = config or load_ragflow_adapter_config()

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents or not self.config.rerank_enabled:
            return []
        headers = {"Content-Type": "application/json"}
        if self.config.rerank_api_key:
            headers["Authorization"] = f"Bearer {self.config.rerank_api_key}"
        payload: Dict[str, Any] = {
            "query": query,
            "documents": documents,
            "top_n": len(documents),
        }
        if self.config.rerank_model:
            payload["model"] = self.config.rerank_model
        response = requests.post(
            self.config.rerank_endpoint,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.config.rerank_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        raw_results = body.get("results") or body.get("data") or body.get("rankings") or []
        scores = [0.0] * len(documents)
        for order, item in enumerate(raw_results):
            index = int(item.get("index", item.get("document_index", order)))
            if index < 0 or index >= len(documents):
                continue
            score = item.get("relevance_score", item.get("score", item.get("similarity", 0.0)))
            scores[index] = float(score or 0.0)
        return scores


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def normalize_cosine(value: float) -> float:
    return max(0.0, min(1.0, (value + 1.0) / 2.0))


def now_ts() -> float:
    return time.time()
