"""
core/vector_store.py
=====================
Zoro Robot — Unified Embedder + Vector Store
Merges v1 ChunkEmbedder + KnowledgeIndex with v2 Embedder + VectorStore.

Single class handles: embed, build, search, save, load.
FAISS IndexFlatIP → IVFFlat for large corpora.
Falls back to numpy cosine search on Pi Zero / no-FAISS environments.
TF-IDF fallback when torch / sentence-transformers are unavailable.
"""

from __future__ import annotations

import logging
import pickle
import re
from collections import Counter
from math import log
from pathlib import Path
from typing import Optional

import numpy as np
from app.schemas.contracts import DocumentChunk

logger = logging.getLogger("zoro.vectorstore")


# ═════════════════════════════════════════════════════════════
# EMBEDDER
# ═════════════════════════════════════════════════════════════


class Embedder:
    """
    Wraps sentence-transformers (all-MiniLM-L6-v2, 22 MB, 384-dim).
    Falls back to TF-IDF when torch is unavailable (Pi Zero mode).
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL, fallback: bool = False):
        self.model_name = model_name
        self.model = None
        self.fallback = fallback
        self._dim = 384
        # TF-IDF state (fallback)
        self._vocab: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._load()

    def _load(self):
        if self.fallback:
            logger.info("Embedder: TF-IDF fallback mode")
            return
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name)
            self._dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"Embedder: {self.model_name} loaded | dim={self._dim}")
        except ImportError:
            logger.warning("sentence-transformers not found → TF-IDF fallback")
            self.fallback = True

    # ── Public API ───────────────────────────────────────────

    def embed_chunks(
        self, chunks: list[DocumentChunk], batch_size: int = 32
    ) -> list[DocumentChunk]:
        """Embed a list of DocumentChunks in place. Returns same list."""
        texts = [c.text for c in chunks]
        vecs = self._encode(texts, batch_size=batch_size)
        for chunk, vec in zip(chunks, vecs):
            chunk.embedding = vec
        logger.info(f"Embedded {len(chunks)} chunks | dim={self._dim}")
        return chunks

    def encode(self, texts: list[str], normalize: bool = True) -> np.ndarray:
        return self._encode(texts, normalize=normalize)

    def encode_single(self, text: str) -> np.ndarray:
        return self._encode([text])[0]

    # ── Internal ─────────────────────────────────────────────

    def _encode(
        self, texts: list[str], batch_size: int = 32, normalize: bool = True
    ) -> np.ndarray:
        if not self.fallback and self.model:
            return self.model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=normalize,
                show_progress_bar=False,
            ).astype(np.float32)
        return self._tfidf_encode(texts)

    def _tfidf_encode(self, texts: list[str]) -> np.ndarray:
        tokenized = [re.findall(r"\b\w+\b", t.lower()) for t in texts]

        if not self._vocab:
            df: Counter = Counter()
            for tokens in tokenized:
                df.update(set(tokens))
            N = len(texts)
            vocab = sorted(df.keys())[:512]
            self._vocab = {w: i for i, w in enumerate(vocab)}
            self._idf = {w: log((N + 1) / (df[w] + 1)) for w in vocab}
            self._dim = len(vocab)

        dim = len(self._vocab)
        vecs = np.zeros((len(texts), dim), dtype=np.float32)
        for i, tokens in enumerate(tokenized):
            tf = Counter(tokens)
            for w, cnt in tf.items():
                if w in self._vocab:
                    vecs[i, self._vocab[w]] = cnt * self._idf.get(w, 1.0)
            norm = np.linalg.norm(vecs[i])
            if norm > 0:
                vecs[i] /= norm
        return vecs


# ═════════════════════════════════════════════════════════════
# VECTOR STORE
# ═════════════════════════════════════════════════════════════


class VectorStore:
    """
    FAISS-backed vector index with numpy cosine fallback.
    Persists to disk: metadata.pkl + embeddings.npy + index.faiss.

    Unified from:
      v1  KnowledgeIndex (IndexFlatIP / IVFFlat selection)
      v2  VectorStore   (subject + grade metadata filtering)
    """

    def __init__(self, index_path: str = "data/zoro_index", fallback: bool = False):
        self.path = Path(index_path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.chunks: list[DocumentChunk] = []
        self._embs: Optional[np.ndarray] = None
        self._faiss = None
        self._fallback = fallback
        self._check_faiss()

    def _check_faiss(self):
        if self._fallback:
            return
        try:
            import faiss  # noqa: F401
        except ImportError:
            logger.warning("FAISS not found → numpy cosine search (slower)")
            self._fallback = True

    # ── Build ────────────────────────────────────────────────

    def build(self, chunks: list[DocumentChunk], embedder: Embedder) -> None:
        """Embed all chunks and build the FAISS index."""
        self.chunks = [c for c in chunks if c is not None]
        if not self.chunks:
            raise ValueError("No chunks to index.")

        # Embed any chunks not yet embedded
        unembedded = [c for c in self.chunks if c.embedding is None]
        if unembedded:
            embedder.embed_chunks(unembedded)

        embs = np.vstack([c.embedding for c in self.chunks]).astype(np.float32)
        self._embs = embs
        dim = embs.shape[1]

        if not self._fallback:
            import faiss

            if len(self.chunks) < 1000:
                self._faiss = faiss.IndexFlatIP(dim)
            else:
                nlist = min(64, len(self.chunks) // 10)
                q = faiss.IndexFlatIP(dim)
                self._faiss = faiss.IndexIVFFlat(
                    q, dim, nlist, faiss.METRIC_INNER_PRODUCT
                )
                self._faiss.train(embs)
            self._faiss.add(embs)

        self._save()
        logger.info(
            f"Index built: {len(self.chunks)} vectors | dim={dim} | faiss={not self._fallback}"
        )

    # ── Search ───────────────────────────────────────────────

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 10,
        subject_filter: str = "",
        grade_filter: int = 0,
    ) -> tuple[list[DocumentChunk], list[float]]:
        if not self.chunks:
            return [], []

        q = query_vec.reshape(1, -1).astype(np.float32)
        k = min(top_k * 4, len(self.chunks))

        if not self._fallback and self._faiss:
            scores, indices = self._faiss.search(q, k)
            candidates = [
                (self.chunks[i], float(s))
                for s, i in zip(scores[0], indices[0])
                if i >= 0
            ]
        else:
            sims = (self._embs @ q.T).flatten()
            top = np.argsort(sims)[::-1][:k]
            candidates = [(self.chunks[i], float(sims[i])) for i in top]

        # Metadata filtering
        filtered = [
            (c, s)
            for c, s in candidates
            if (not subject_filter or c.subject.lower() == subject_filter.lower())
            and (not grade_filter or c.grade == 0 or c.grade == grade_filter)
        ]
        if not filtered:
            filtered = candidates  # relax filters if nothing passes

        filtered = filtered[:top_k]
        for chunk, score in filtered:
            chunk.embedding_score = score

        return [c for c, _ in filtered], [s for _, s in filtered]

    # ── Persistence ──────────────────────────────────────────

    def _save(self):
        meta = [
            (
                c.chunk_id,
                c.source,
                c.source_type,
                c.subject,
                c.topic,
                c.grade,
                c.page,
                c.word_count,
                c.text,
            )
            for c in self.chunks
        ]
        with open(self.path / "metadata.pkl", "wb") as f:
            pickle.dump(meta, f)
        if self._embs is not None:
            np.save(str(self.path / "embeddings.npy"), self._embs)
        if not self._fallback and self._faiss:
            import faiss

            faiss.write_index(self._faiss, str(self.path / "index.faiss"))
        logger.info(f"Index saved → {self.path}")

    def load(self) -> bool:
        meta_f = self.path / "metadata.pkl"
        if not meta_f.exists():
            return False

        with open(meta_f, "rb") as f:
            meta = pickle.load(f)

        self.chunks = [
            DocumentChunk(
                chunk_id=m[0],
                source=m[1],
                source_type=m[2],
                subject=m[3],
                topic=m[4],
                grade=m[5],
                page=m[6],
                word_count=m[7],
                text=m[8],
            )
            for m in meta
        ]

        emb_f = self.path / "embeddings.npy"
        if emb_f.exists():
            self._embs = np.load(str(emb_f))

        if not self._fallback:
            faiss_f = self.path / "index.faiss"
            try:
                import faiss

                if faiss_f.exists():
                    self._faiss = faiss.read_index(str(faiss_f))
            except ImportError:
                self._fallback = True

        logger.info(f"Index loaded: {len(self.chunks)} chunks")
        return True

    def stats(self) -> dict:
        subjects: dict[str, int] = {}
        for c in self.chunks:
            subjects[c.subject] = subjects.get(c.subject, 0) + 1
        return {
            "total_chunks": len(self.chunks),
            "subjects": subjects,
            "index_path": str(self.path),
            "backend": "faiss" if (not self._fallback and self._faiss) else "numpy",
        }

