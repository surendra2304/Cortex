"""
Universal Memora Client for Cortex Autonomous Web Operations
"""
import os
import sys
from pathlib import Path

# Try importing from central Memora SDK first
try:
    MEMORA_ROOT = Path("d:/FRIDAY Universe/Memora")
    if str(MEMORA_ROOT) not in sys.path:
        sys.path.insert(0, str(MEMORA_ROOT))
    from sdk.memora_client import MemoraClient, memora_client
except Exception:
    import json
    import sqlite3
    import uuid
    import time
    from typing import Optional, Dict, Any, List

    class MemoraClient:
        def __init__(self):
            self.local_db_path = "d:/FRIDAY Universe/Memora/data/memora.db"

        def record_fact(self, agent_name: str, fact_text: str, category: str = "general", importance: float = 0.8, entities: Optional[List[str]] = None):
            if not os.path.exists(self.local_db_path):
                return
            try:
                with sqlite3.connect(self.local_db_path, timeout=5.0) as conn:
                    c = conn.cursor()
                    c.execute("SELECT id FROM agents WHERE name = 'cortex'")
                    row = c.fetchone()
                    aid = row[0] if row else str(uuid.uuid4())
                    c.execute("SELECT id FROM namespaces WHERE agent_id = ?", (aid,))
                    row_ns = c.fetchone()
                    nid = row_ns[0] if row_ns else str(uuid.uuid4())
                    now_iso = time.strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("""
                        INSERT INTO memory_records (id, namespace_id, owner_id, memory_type, content_text, source, confidence, importance, lifecycle_state, tenant_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (str(uuid.uuid4()), nid, aid, "semantic", fact_text, "agent:cortex", 1.0, importance, "active", "default", now_iso))
                    conn.commit()
            except Exception:
                pass

        def recall_memories(self, agent_name: str, query: str, limit: int = 5):
            return []

        def learn_from_outcome(self, agent_name: str, task_name: str, status: str, error_log: Optional[str] = None, actions_taken: Optional[str] = None, context: Optional[str] = None, domain: Optional[str] = None):
            if not os.path.exists(self.local_db_path):
                return {"status": "error", "message": "no db"}
            try:
                with sqlite3.connect(self.local_db_path, timeout=5.0) as conn:
                    c = conn.cursor()
                    c.execute("SELECT id FROM agents WHERE name = 'cortex'")
                    row = c.fetchone()
                    aid = row[0] if row else str(uuid.uuid4())
                    c.execute("SELECT id FROM namespaces WHERE agent_id = ?", (aid,))
                    row_ns = c.fetchone()
                    nid = row_ns[0] if row_ns else str(uuid.uuid4())
                    now_iso = time.strftime("%Y-%m-%d %H:%M:%S")
                    dom = domain or "web_operations"
                    if status.lower() in ("failure", "error", "crashed"):
                        content = f"[WEB OPS LESSON in '{dom}'] Task: {task_name}. Error: {error_log or 'Execution failed'}. Verify DOM selector and network timeout."
                    else:
                        content = f"[PROVEN WEB OPS PATTERN in '{dom}'] Task: {task_name}. Selector / operation succeeded."
                    mid = str(uuid.uuid4())
                    c.execute("""
                        INSERT INTO memory_records (id, namespace_id, owner_id, memory_type, content_text, source, confidence, importance, lifecycle_state, tenant_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (mid, nid, aid, "experience", content, "agent:cortex", 1.0, 0.99, "active", "default", now_iso))
                    conn.commit()
                return {"status": "success", "id": mid, "memory_type": "experience", "content": content}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        def recall_experience(self, agent_name: str, task_query: str, domain: Optional[str] = None, limit: int = 5):
            return []

        def build_self_upgrade_context(self, agent_name: str, task_query: str, domain: Optional[str] = None) -> str:
            return ""

    memora_client = MemoraClient()

__all__ = ["MemoraClient", "memora_client"]
