.\helm.exe upgrade --install loki grafana/loki-stack --namespace observability --set promtail.enabled=true
.\helm.exe upgrade --install tempo grafana/tempo --namespace observability --set tempo.metricsGenerator.enabled=true --set tempo.metricsGenerator.remoteWriteUrl=http://prometheus-server.observability.svc.cluster.local:80

$otelValues = @"
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
"@
$otelValues | Out-File -FilePath "otel-values.yaml" -Encoding utf8
.\helm.exe upgrade --install opentelemetry-collector open-telemetry/opentelemetry-collector --namespace observability -f otel-values.yaml
