from fastapi import FastAPI, HTTPException
import httpx
import logging
import time
import os
import psycopg2
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Setup OpenTelemetry
resource = Resource.create({"service.name": "rag-api"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

otlp_exporter = OTLPSpanExporter(endpoint="http://opentelemetry-collector.observability:4317", insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

app = FastAPI(title="Target RAG Application")

FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()
Psycopg2Instrumentor().instrument()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LLM_GATEWAY_URL = os.environ.get("LLM_GATEWAY_URL", "http://mock-llm-gateway.target-system.svc.cluster.local:8000")
DB_HOST = os.environ.get("DB_HOST", "vector-db.target-system.svc.cluster.local")
DB_USER = os.environ.get("DB_USER", "user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_NAME = os.environ.get("DB_NAME", "rag_db")

def get_db_connection():
    try:
        conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/query")
async def query_rag(q: str):
    with tracer.start_as_current_span("rag_pipeline"):
        # 1. Retrieve from Vector DB
        with tracer.start_as_current_span("vector_db_retrieval"):
            conn = get_db_connection()
            if not conn:
                raise HTTPException(status_code=503, detail="Database unavailable")
            time.sleep(0.1) # Simulate query time
            conn.close()
            context = "Mock retrieved context based on pgvector similarity."

        # 2. Call LLM Gateway
        with tracer.start_as_current_span("llm_gateway_call"):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{LLM_GATEWAY_URL}/v1/chat/completions",
                        json={"messages": [{"role": "user", "content": f"{context}\n\n{q}"}]}
                    )
                    resp.raise_for_status()
                    llm_response = resp.json()
            except httpx.RequestError as exc:
                logger.error(f"Error calling LLM Gateway: {exc}")
                raise HTTPException(status_code=502, detail="LLM Gateway Error")
            except httpx.HTTPStatusError as exc:
                logger.error(f"HTTP Error from LLM Gateway: {exc}")
                raise HTTPException(status_code=502, detail="LLM Gateway Error")

        return {"answer": llm_response["choices"][0]["message"]["content"]}
