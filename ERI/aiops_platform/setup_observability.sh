#!/bin/bash
set -e

echo "Setting up Observability Stack in namespace: observability"

# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

# Install Prometheus
helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace observability \
  --set server.persistentVolume.enabled=false \
  --set alertmanager.enabled=false

# Install Loki
helm upgrade --install loki grafana/loki-stack \
  --namespace observability \
  --set promtail.enabled=true

# Install Tempo
helm upgrade --install tempo grafana/tempo \
  --namespace observability \
  --set tempo.metricsGenerator.enabled=true \
  --set tempo.metricsGenerator.remoteWriteUrl=http://prometheus-server.observability.svc.cluster.local:80

# Install OpenTelemetry Collector
# We use a custom values.yaml for the OTEL collector to route traces to tempo and metrics to prometheus
cat <<EOF > /tmp/otel-values.yaml
mode: deployment
config:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
  exporters:
    otlp:
      endpoint: "tempo.observability.svc.cluster.local:4317"
      tls:
        insecure: true
    prometheus:
      endpoint: "0.0.0.0:8889"
  service:
    pipelines:
      traces:
        receivers: [otlp]
        exporters: [otlp]
      metrics:
        receivers: [otlp]
        exporters: [prometheus]
EOF

helm upgrade --install opentelemetry-collector open-telemetry/opentelemetry-collector \
  --namespace observability \
  -f /tmp/otel-values.yaml

echo "Observability stack installed successfully."
