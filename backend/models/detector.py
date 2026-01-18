"""NeuroFence SimpleDetector - 5-Layer Contamination Analysis Engine.

Production notes:
- Supports pluggable embedding model (for tests/offline usage).
- Maintains in-memory baselines and optionally persists them via SQLAlchemy.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Tuple

import difflib
import numpy as np
from scipy.spatial.distance import cosine
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EmbeddingModel(Protocol):
    def encode(self, text: str) -> np.ndarray: ...

    def get_sentence_embedding_dimension(self) -> int: ...


@dataclass(frozen=True)
class BaselineRecord:
    centroid: np.ndarray
    samples: int


class SimpleDetector:
    """Multi-layer contamination detector for AI agent messages.

    Layers:
    1) Signature Detection (0-25 points)
    2) Semantic Anomaly (0-40 points)
    3) Statistical Analysis (0-15 points)
    4) Risk Keywords (0-10 points)
    5) Adversarial Detection (0-10 points)

    Total score: 0-100 points
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        embedding_model: Optional[EmbeddingModel] = None,
        alpha: float = 0.7,
        agent_baselines_table=None,
    ):
        self.alpha = float(alpha)
        self._agent_baselines_table = agent_baselines_table

        if embedding_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", model_name)
            embedding_model = SentenceTransformer(model_name)

        self.model: EmbeddingModel = embedding_model
        self.embedding_dim = int(self.model.get_sentence_embedding_dimension())

        self.agent_baselines: Dict[str, BaselineRecord] = {}
        logger.info("✅ Detector ready. Embedding dimension: %d", self.embedding_dim)

    # ---------------------------------------------------------------------
    # Layer scoring
    # ---------------------------------------------------------------------

    def _detect_signatures(self, content: str) -> float:
        attack_signatures = [
            "INSTRUCTION FOR",
            "SYSTEM PROMPT",
            "JAILBREAK",
            "IGNORE",
            "OVERRIDE",
            "EXECUTE",
            "COMMAND",
            "FORGET",
            "BYPASS",
            "DISABLE",
            "UNLOCK",
        ]

        content_upper = content.upper()
        matches = sum(1 for sig in attack_signatures if sig in content_upper)

        # Fuzzy matching for slight variations
        for sig in attack_signatures:
            for line in content_upper.splitlines() or [content_upper]:
                if difflib.SequenceMatcher(None, sig, line).ratio() > 0.85:
                    matches += 0.5

        return float(min(matches * 5.0, 25.0))

    def _detect_semantic_anomaly(self, agent_name: str, content: str) -> float:
        try:
            embedding = np.asarray(self.model.encode(content), dtype=np.float32)
            baseline = self.agent_baselines.get(agent_name)
            if baseline is None:
                return 0.0

            distance = float(cosine(embedding, baseline.centroid))

            if distance > 0.7:
                return 40.0
            if distance > 0.5:
                return 20.0
            if distance > 0.3:
                return 10.0
            return 0.0
        except Exception:
            logger.exception("Semantic anomaly detection error")
            return 0.0

    def _detect_statistical_anomaly(self, content: str) -> float:
        attack_keywords = ["steal", "exfiltrate", "leak", "send", "data", "unauthorized", "export"]

        content_lower = content.lower()
        total_words = len(content_lower.split())
        if total_words == 0:
            return 0.0

        keyword_count = sum(content_lower.count(kw) for kw in attack_keywords)
        keyword_density = keyword_count / total_words

        if keyword_density > 0.10:
            density_score = 15.0
        elif keyword_density > 0.05:
            density_score = 10.0
        elif keyword_density > 0.02:
            density_score = 5.0
        else:
            density_score = 0.0

        entropy = self._calculate_entropy(content)
        entropy_score = 5.0 if entropy > 5.0 else 0.0

        return float(min(density_score + entropy_score, 15.0))

    def _detect_risk_keywords(self, content: str) -> float:
        content_lower = content.lower()

        # High-confidence exfiltration / sensitive-data indicators.
        high_risk_phrases = [
            "exfiltrate",
            "steal",
            "leak",
            "export database",
            "dump database",
            "patient records",
            "system prompt",
        ]
        if any(p in content_lower for p in high_risk_phrases):
            return 10.0

        # Destination hints (URL or email).
        if ("http://" in content_lower) or ("https://" in content_lower) or ("@" in content_lower):
            return 10.0

        risk_keywords = ["attacker", "malicious", "evil", "pastebin", "dropbox"]
        risk_count = sum(content_lower.count(kw) for kw in risk_keywords)
        return float(min(risk_count * 2.0, 10.0))

    def _detect_adversarial(self, content: str) -> float:
        adversarial_indicators = ["base64", "rot13", "cipher", "encode", "decode", "obfuscate"]
        obfuscation_sequences = ["***", "!!!!", "%%%%", "####", "===="]

        content_lower = content.lower()
        encoding_score = sum(2.0 for ind in adversarial_indicators if ind in content_lower)

        obfuscation_score = 0.0
        for seq in obfuscation_sequences:
            if seq in content:
                obfuscation_score += 3.0

        return float(min(encoding_score + obfuscation_score, 10.0))

    @staticmethod
    def _calculate_entropy(text: str) -> float:
        if not text:
            return 0.0

        frequencies: Dict[str, int] = {}
        for ch in text:
            frequencies[ch] = frequencies.get(ch, 0) + 1

        entropy = 0.0
        text_len = len(text)
        for freq in frequencies.values():
            p = freq / text_len
            if p > 0:
                entropy -= p * float(np.log2(p))

        return float(entropy)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def analyze(self, agent_name: str, content: str) -> Tuple[float, Dict[str, float]]:
        layer1 = self._detect_signatures(content)
        layer2 = self._detect_semantic_anomaly(agent_name, content)
        layer3 = self._detect_statistical_anomaly(content)
        layer4 = self._detect_risk_keywords(content)
        layer5 = self._detect_adversarial(content)

        total = float(layer1 + layer2 + layer3 + layer4 + layer5)
        layers = {
            "signature_detection": layer1,
            "semantic_anomaly": layer2,
            "statistical_analysis": layer3,
            "risk_keywords": layer4,
            "adversarial_detection": layer5,
            "total": total,
        }

        logger.info("Analysis complete - %s: %.1f points", agent_name, total)
        return total, layers

    def update_baseline(self, agent_name: str, content: str, session: Optional[Session] = None) -> bool:
        try:
            embedding = np.asarray(self.model.encode(content), dtype=np.float32)

            existing = self.agent_baselines.get(agent_name)
            if existing is None:
                new_centroid = embedding
                samples = 1
            else:
                new_centroid = self.alpha * existing.centroid + (1.0 - self.alpha) * embedding
                samples = int(existing.samples) + 1

            self.agent_baselines[agent_name] = BaselineRecord(centroid=new_centroid, samples=samples)

            if session is not None and self._agent_baselines_table is not None:
                self._upsert_baseline(session, agent_name)

            logger.info("✅ Baseline updated for %s (samples=%d)", agent_name, samples)
            return True
        except Exception:
            logger.exception("Error updating baseline")
            return False

    def load_baselines_from_db(self, session: Session) -> None:
        if self._agent_baselines_table is None:
            return

        stmt = select(
            self._agent_baselines_table.c.agent_name,
            self._agent_baselines_table.c.centroid,
            self._agent_baselines_table.c.samples,
        )
        rows = session.execute(stmt).all()

        loaded = 0
        for agent_name, centroid_text, samples in rows:
            if not centroid_text:
                continue
            try:
                centroid_list = json.loads(centroid_text)
                centroid = np.asarray(centroid_list, dtype=np.float32)
                self.agent_baselines[str(agent_name)] = BaselineRecord(centroid=centroid, samples=int(samples or 0))
                loaded += 1
            except Exception:
                logger.exception("Failed to load baseline for %s", agent_name)

        logger.info("Loaded %d baselines from DB", loaded)

    def _upsert_baseline(self, session: Session, agent_name: str) -> None:
        record = self.agent_baselines.get(agent_name)
        if record is None:
            return

        centroid_text = json.dumps([float(x) for x in record.centroid.tolist()])

        # DB-agnostic upsert: try update first; if no rows affected, insert.
        table = self._agent_baselines_table
        upd = (
            table.update()
            .where(table.c.agent_name == agent_name)
            .values(centroid=centroid_text, samples=record.samples)
        )
        result = session.execute(upd)
        if result.rowcount and result.rowcount > 0:
            return

        ins = table.insert().values(agent_name=agent_name, centroid=centroid_text, samples=record.samples)
        session.execute(ins)

    def get_baseline(self, agent_name: str) -> Optional[np.ndarray]:
        record = self.agent_baselines.get(agent_name)
        return None if record is None else record.centroid
