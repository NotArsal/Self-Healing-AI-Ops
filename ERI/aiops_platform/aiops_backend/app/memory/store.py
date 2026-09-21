"""
AIOps Incident Memory Store.
Uses PostgreSQL + pgvector to persist incident history and allow
semantic similarity search over past incidents.
"""

import os
import logging
import json
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_HOST = os.environ.get("MEMORY_DB_HOST", "memory-db.memory.svc.cluster.local")
DB_USER = os.environ.get("MEMORY_DB_USER", "aiops")
DB_PASSWORD = os.environ.get("MEMORY_DB_PASSWORD", "aiopspassword")
DB_NAME = os.environ.get("MEMORY_DB_NAME", "incident_memory")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )


def init_db():
    """Create tables and enable pgvector extension on first run."""
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS incidents (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT,
                        affected_service TEXT,
                        failure_type TEXT,
                        severity TEXT,
                        symptoms JSONB,
                        hypothesis TEXT,
                        actions_attempted JSONB,
                        successful_action TEXT,
                        verification_result TEXT,
                        mttd_seconds FLOAT,
                        mttr_seconds FLOAT,
                        embedding vector(768)
                    );
                """)
        conn.close()
        logger.info("Memory DB initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize memory DB: {e}")


def store_incident(incident_record: dict, embedding: list):
    """Persist a resolved incident with its embedding for future retrieval."""
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO incidents (
                        id, timestamp, affected_service, failure_type, severity,
                        symptoms, hypothesis, actions_attempted, successful_action,
                        verification_result, mttd_seconds, mttr_seconds, embedding
                    ) VALUES (
                        %(id)s, %(timestamp)s, %(affected_service)s, %(failure_type)s,
                        %(severity)s, %(symptoms)s, %(hypothesis)s, %(actions_attempted)s,
                        %(successful_action)s, %(verification_result)s,
                        %(mttd_seconds)s, %(mttr_seconds)s, %(embedding)s
                    ) ON CONFLICT (id) DO UPDATE SET
                        verification_result = EXCLUDED.verification_result,
                        successful_action = EXCLUDED.successful_action,
                        mttr_seconds = EXCLUDED.mttr_seconds,
                        embedding = EXCLUDED.embedding;
                """, {
                    **incident_record,
                    "symptoms": json.dumps(incident_record.get("symptoms", {})),
                    "actions_attempted": json.dumps(incident_record.get("actions_attempted", [])),
                    "embedding": str(embedding)
                })
        conn.close()
    except Exception as e:
        logger.error(f"Failed to store incident: {e}")


def retrieve_similar_incidents(embedding: list, limit: int = 3) -> list:
    """Find the top-N most similar past incidents using cosine similarity."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, affected_service, failure_type, hypothesis,
                       successful_action, verification_result,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM incidents
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (str(embedding), str(embedding), limit))
            results = cur.fetchall()
        conn.close()
        return [dict(r) for r in results]
    except Exception as e:
        logger.error(f"Failed to retrieve similar incidents: {e}")
        return []
