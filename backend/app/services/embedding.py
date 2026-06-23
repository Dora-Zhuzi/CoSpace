"""向量化服务。

优先用 sentence-transformers 加载真实模型；若未安装或加载失败，
降级为本地确定性哈希向量（基于字符 n-gram），保证零依赖也能跑通检索流程。
真实语义检索只需 `pip install sentence-transformers` 即可自动启用。
"""
import hashlib
import math
import re

import numpy as np

from app.core.config import settings


class Embedder:
    def __init__(self):
        self.dim = settings.embedding_dim
        self._model = None
        self._backend = "hash"
        self._try_load_model()

    def _try_load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(settings.embedding_model)
            self.dim = self._model.get_sentence_embedding_dimension()
            self._backend = "sentence-transformers"
        except Exception:
            self._model = None
            self._backend = "hash"

    @property
    def backend(self) -> str:
        return self._backend

    def _hash_embed(self, text: str) -> list[float]:
        """字符 trigram 哈希到固定维度，再 L2 归一化。提供轻量的词面相似度。"""
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = re.findall(r"\w+", text.lower())
        grams: list[str] = []
        for tok in tokens:
            padded = f"#{tok}#"
            grams.extend(padded[i : i + 3] for i in range(len(padded) - 2))
        if not grams:
            grams = [text[:3] or "_"]
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def encode(self, text: str) -> list[float]:
        text = (text or "").strip()
        if self._model is not None:
            emb = self._model.encode(text, normalize_embeddings=True)
            return np.asarray(emb, dtype=np.float32).tolist()
        return self._hash_embed(text)

    def encode_many(self, texts: list[str]) -> list[list[float]]:
        if self._model is not None:
            embs = self._model.encode(texts, normalize_embeddings=True)
            return [np.asarray(e, dtype=np.float32).tolist() for e in embs]
        return [self._hash_embed(t) for t in texts]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def centroid(vectors: list[list[float]]) -> list[float]:
    vecs = [v for v in vectors if v]
    if not vecs:
        return []
    arr = np.asarray(vecs, dtype=np.float32)
    mean = arr.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm > 0:
        mean = mean / norm
    return mean.tolist()
