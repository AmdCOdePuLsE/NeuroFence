"""NeuroFence SimpleIsolationEngine - Agent Isolation & Forensic Logging.

Production notes:
- Uses in-memory O(1) isolation cache guarded by a lock.
- Persists events to the database via SQLAlchemy.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update

from backend.db import Database, db_session, safe_commit

logger = logging.getLogger(__name__)


class SimpleIsolationEngine:
    def __init__(self, db: Database):
        self.db = db
        self._lock = threading.RLock()
        self.isolated: Dict[str, Dict[str, Any]] = {}

        self._load_active_isolations()
        logger.info("✅ Isolation engine initialized. Active isolations: %d", len(self.isolated))

    def _load_active_isolations(self) -> None:
        table = self.db.tables["isolation_log"]

        with db_session(self.db) as session:
            rows = session.execute(
                select(table.c.agent_name, table.c.isolated_at)
                .where(table.c.status == "ISOLATED")
            ).all()

        with self._lock:
            for agent_name, isolated_at in rows:
                self.isolated[str(agent_name)] = {
                    "isolated_at": isolated_at or datetime.now(timezone.utc),
                    "messages_blocked": 0,
                }

    def is_isolated(self, agent_name: str) -> bool:
        with self._lock:
            return agent_name in self.isolated

    def isolate(self, agent_name: str, reason: str) -> bool:
        table = self.db.tables["isolation_log"]

        with self._lock:
            if agent_name in self.isolated:
                logger.warning("%s is already isolated", agent_name)
                return False
            self.isolated[agent_name] = {
                "isolated_at": datetime.now(timezone.utc),
                "messages_blocked": 0,
            }

        try:
            with db_session(self.db) as session:
                session.execute(
                    table.insert().values(
                        agent_name=agent_name,
                        reason=reason,
                        status="ISOLATED",
                    )
                )
                safe_commit(session)
            logger.warning("🚨 ISOLATION: %s isolated. Reason: %s", agent_name, reason)
            return True
        except Exception:
            logger.exception("Error isolating %s", agent_name)
            with self._lock:
                self.isolated.pop(agent_name, None)
            return False

    def block_message(
        self,
        sender: str,
        recipient: Optional[str],
        score: float,
        layers: Optional[Dict[str, Any]] = None,
    ) -> bool:
        table = self.db.tables["blocked_messages"]

        with self._lock:
            if sender in self.isolated:
                self.isolated[sender]["messages_blocked"] += 1

        try:
            with db_session(self.db) as session:
                session.execute(
                    table.insert().values(
                        sender=sender,
                        recipient=recipient,
                        score=float(score),
                        layers=layers,
                    )
                )
                safe_commit(session)

            logger.warning("⛔ BLOCKED: %s → %s (score: %.1f)", sender, recipient, float(score))
            return True
        except Exception:
            logger.exception("Error recording blocked message")
            return False

    def record_clean_message(self, sender: str, recipient: Optional[str], score: float) -> None:
        table = self.db.tables["clean_messages"]
        try:
            with db_session(self.db) as session:
                session.execute(
                    table.insert().values(sender=sender, recipient=recipient, score=float(score))
                )
                safe_commit(session)
        except Exception:
            # Non-critical
            logger.debug("Failed to record clean message", exc_info=True)

    def release(self, agent_name: str) -> bool:
        table = self.db.tables["isolation_log"]

        with self._lock:
            if agent_name not in self.isolated:
                logger.warning("%s is not isolated", agent_name)
                return False
            self.isolated.pop(agent_name, None)

        try:
            with db_session(self.db) as session:
                session.execute(
                    update(table)
                    .where((table.c.agent_name == agent_name) & (table.c.status == "ISOLATED"))
                    .values(status="RELEASED")
                )
                safe_commit(session)
            logger.info("✅ RELEASED: %s is now free to operate", agent_name)
            return True
        except Exception:
            logger.exception("Error releasing %s", agent_name)
            # best-effort restore cache
            with self._lock:
                self.isolated.setdefault(agent_name, {"isolated_at": datetime.now(timezone.utc), "messages_blocked": 0})
            return False

    def get_stats(self) -> Dict[str, Any]:
        blocked_table = self.db.tables["blocked_messages"]
        isolation_table = self.db.tables["isolation_log"]

        try:
            with db_session(self.db) as session:
                total_blocks = session.execute(select(func.count()).select_from(blocked_table)).scalar_one()
                total_unique_isolated = session.execute(
                    select(func.count(func.distinct(isolation_table.c.agent_name))).select_from(isolation_table)
                ).scalar_one()

            with self._lock:
                isolated_agents = list(self.isolated.keys())
                total_active = len(self.isolated)

            return {
                "total_isolated_active": total_active,
                "isolated_agents": isolated_agents,
                "total_blocks_all_time": int(total_blocks),
                "total_unique_agents_isolated": int(total_unique_isolated),
            }
        except Exception:
            logger.exception("Error getting stats")
            return {
                "total_isolated_active": len(self.isolated),
                "isolated_agents": list(self.isolated.keys()),
                "total_blocks_all_time": 0,
                "total_unique_agents_isolated": 0,
                "error": "stats_query_failed",
            }

    def get_forensics(self, agent_name: str, limit: int = 50) -> Dict[str, Any]:
        blocked_table = self.db.tables["blocked_messages"]
        isolation_table = self.db.tables["isolation_log"]

        try:
            with db_session(self.db) as session:
                blocked_rows = session.execute(
                    select(
                        blocked_table.c.sender,
                        blocked_table.c.recipient,
                        blocked_table.c.score,
                        blocked_table.c.layers,
                        blocked_table.c.blocked_at,
                    )
                    .where(blocked_table.c.sender == agent_name)
                    .order_by(blocked_table.c.blocked_at.desc())
                    .limit(int(limit))
                ).all()

                isolation_row = session.execute(
                    select(
                        isolation_table.c.isolated_at,
                        isolation_table.c.reason,
                        isolation_table.c.status,
                    )
                    .where(isolation_table.c.agent_name == agent_name)
                    .order_by(isolation_table.c.isolated_at.desc())
                    .limit(1)
                ).first()

            blocked_messages: List[Dict[str, Any]] = []
            for sender, recipient, score, layers, blocked_at in blocked_rows:
                blocked_messages.append(
                    {
                        "sender": sender,
                        "recipient": recipient,
                        "score": float(score) if score is not None else None,
                        "layers": layers,
                        "blocked_at": blocked_at.isoformat() if blocked_at else None,
                    }
                )

            isolation_event: Optional[Dict[str, Any]] = None
            if isolation_row is not None:
                isolated_at, reason, status = isolation_row
                isolation_event = {
                    "isolated_at": isolated_at.isoformat() if isolated_at else None,
                    "reason": reason,
                    "status": status,
                }

            return {
                "agent": agent_name,
                "blocked_messages": blocked_messages,
                "isolation_event": isolation_event,
            }
        except Exception:
            logger.exception("Error getting forensics for %s", agent_name)
            return {"error": "forensics_query_failed", "agent": agent_name, "blocked_messages": [], "isolation_event": None}
