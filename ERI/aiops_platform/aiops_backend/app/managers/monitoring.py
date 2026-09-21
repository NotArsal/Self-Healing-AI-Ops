import httpx
import logging
from prometheus_api_client import PrometheusConnect
import os

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus-server.observability.svc.cluster.local:80")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki.observability.svc.cluster.local:3100")

class MonitoringManager:
    def __init__(self):
        self.prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
    
    def query_metrics(self, query: str):
        try:
            return self.prom.custom_query(query=query)
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return []

    async def query_logs(self, query: str, limit: int = 100):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{LOKI_URL}/loki/api/v1/query",
                    params={"query": query, "limit": limit}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Loki query failed: {e}")
            return {}

    # Traces would typically be retrieved via Tempo API.
    async def get_trace(self, trace_id: str):
        # Placeholder for Tempo API integration
        pass

monitoring_manager = MonitoringManager()
