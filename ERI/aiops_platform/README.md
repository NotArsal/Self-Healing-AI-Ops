# AIOps Platform Setup

## Prerequisites
- Docker Desktop with Kubernetes enabled
- `kubectl` installed and configured
- `helm` installed
- `docker` CLI available

## Phase 1: Deploy Target System
1. Apply namespaces:
   ```bash
   kubectl apply -f k8s/namespaces.yaml
   ```
2. Build local docker images for the target system:
   ```bash
   cd target_system/mock_llm
   docker build -t mock-llm-gateway:latest .
   cd ../rag_app
   docker build -t rag-api:latest .
   ```
3. Deploy to Kubernetes:
   ```bash
   kubectl apply -f k8s/target-system/pgvector.yaml
   kubectl apply -f k8s/target-system/mock-llm.yaml
   kubectl apply -f k8s/target-system/rag-api.yaml
   ```

## Phase 2: Deploy Observability Stack
Run the setup script (requires bash):
```bash
bash setup_observability.sh
```
