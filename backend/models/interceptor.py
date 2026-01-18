"""NeuroFence MessageInterceptor - Decision Engine.

Routes messages through:
1) Isolation check
2) 5-layer contamination analysis
3) Decision matrix (PASS / ESCALATE / BLOCK)
4) Enforcement (block, and optionally isolate)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.config import Settings
from backend.db import db_session, safe_commit
from backend.models.detector import SimpleDetector
from backend.models.isolation import SimpleIsolationEngine

logger = logging.getLogger(__name__)


class MessageInterceptor:
    def __init__(self, detector: SimpleDetector, isolation: SimpleIsolationEngine, settings: Settings):
        self.detector = detector
        self.isolation = isolation
        self.settings = settings

        # Keep the original semantics: points out of 100
        self.safe_threshold_points = 40.0
        self.block_threshold_points = float(self.settings.contamination_threshold) * 100.0

        logger.info(
            "✅ MessageInterceptor initialized (safe<%.1f, block>=%.1f)",
            self.safe_threshold_points,
            self.block_threshold_points,
        )

    def intercept(self, sender: str, recipient: Optional[str], content: str) -> Dict[str, Any]:
        # Fast O(1) isolation check
        if self.isolation.is_isolated(sender):
            self.isolation.block_message(sender, recipient, 100.0, layers={"isolation": True})
            logger.warning("⚡ Fast block for isolated agent: %s", sender)
            return {
                "allowed": False,
                "action": "BLOCKED",
                "reason": "Sender is isolated",
                "score": 100.0,
                "layers": {"isolation": True},
                "agent_isolated": None,
                "flagged": False,
            }

        score, layers = self.detector.analyze(sender, content)

        if score < self.safe_threshold_points:
            decision = "PASS"
        elif score < self.block_threshold_points:
            decision = "ESCALATE"
        else:
            decision = "BLOCK"

        logger.info("Decision for %s: %s (score=%.1f)", sender, decision, score)

        if decision == "PASS":
            self.isolation.record_clean_message(sender, recipient, score)
            return {
                "allowed": True,
                "action": "PASSED",
                "reason": "Message within safe parameters",
                "score": float(score),
                "layers": layers,
                "agent_isolated": None,
                "flagged": False,
            }

        if decision == "ESCALATE":
            self.isolation.record_clean_message(sender, recipient, score)
            return {
                "allowed": True,
                "action": "ESCALATED",
                "reason": "Message flagged for review",
                "score": float(score),
                "layers": layers,
                "agent_isolated": None,
                "flagged": True,
            }

        # BLOCK
        self.isolation.block_message(sender, recipient, score, layers=layers)

        agent_isolated = None
        if self.settings.isolation_enabled:
            if self.isolation.isolate(sender, f"High contamination score: {score:.1f} points"):
                agent_isolated = sender

        return {
            "allowed": False,
            "action": "BLOCKED_AND_ISOLATED" if agent_isolated else "BLOCKED",
            "reason": (
                f"Contamination {score:.1f} points detected - IMMEDIATE ISOLATION"
                if agent_isolated
                else f"Contamination {score:.1f} points detected - BLOCKED"
            ),
            "score": float(score),
            "layers": layers,
            "agent_isolated": agent_isolated,
            "flagged": False,
        }

    def update_agent_baseline(self, agent_name: str, content: str) -> bool:
        # Persist baseline if DB table is configured and reachable
        try:
            with db_session(self.isolation.db) as session:
                ok = self.detector.update_baseline(agent_name, content, session=session)
                safe_commit(session)
                return ok
        except Exception:
            logger.debug("Baseline DB persistence failed; falling back to memory", exc_info=True)
            return self.detector.update_baseline(agent_name, content)

    def get_isolation_summary(self) -> Dict[str, Any]:
        return self.isolation.get_stats()

    def get_forensics(self, agent_name: str) -> Dict[str, Any]:
        return self.isolation.get_forensics(agent_name)
