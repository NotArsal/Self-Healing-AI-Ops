use axum::{
    extract::State,
    http::StatusCode,
    response::Json,
    routing::post,
    Router,
};
use k8s_openapi::api::apps::v1::Deployment;
use kube::{
    api::{Api, DeleteParams, Patch, PatchParams, PostParams},
    Client,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::net::TcpListener;
use tracing::{error, info};

// ─── Request / Response types ─────────────────────────────────────────────────

#[derive(Deserialize, Debug, Clone)]
struct ExecuteRequest {
    action: String,          // "restart_deployment" | "scale_deployment" | "rollback"
    namespace: String,
    resource_name: String,
    #[serde(default)]
    replicas: Option<i32>,
    incident_id: String,
}

#[derive(Serialize)]
struct ExecuteResponse {
    success: bool,
    incident_id: String,
    action: String,
    message: String,
}

// ─── Shared application state ─────────────────────────────────────────────────

struct AppState {
    kube_client: Client,
}

// ─── Action handlers ──────────────────────────────────────────────────────────

/// Restart a deployment by deleting all its pods (rollout restart).
async fn restart_deployment(
    client: &Client,
    namespace: &str,
    name: &str,
) -> anyhow::Result<String> {
    let deploys: Api<Deployment> = Api::namespaced(client.clone(), namespace);

    // Annotate the deployment to trigger a rollout restart
    let patch = serde_json::json!({
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": chrono_now()
                    }
                }
            }
        }
    });
    deploys
        .patch(
            name,
            &PatchParams::apply("healing-executor").force(),
            &Patch::Merge(&patch),
        )
        .await?;
    Ok(format!("Deployment {}/{} restarted.", namespace, name))
}

/// Scale a deployment to a target replica count.
async fn scale_deployment(
    client: &Client,
    namespace: &str,
    name: &str,
    replicas: i32,
) -> anyhow::Result<String> {
    let deploys: Api<Deployment> = Api::namespaced(client.clone(), namespace);
    let patch = serde_json::json!({ "spec": { "replicas": replicas } });
    deploys
        .patch(
            name,
            &PatchParams::apply("healing-executor").force(),
            &Patch::Merge(&patch),
        )
        .await?;
    Ok(format!(
        "Deployment {}/{} scaled to {} replicas.",
        namespace, name, replicas
    ))
}

fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();
    format!("{}", secs)
}

// ─── Route handler ────────────────────────────────────────────────────────────

async fn execute_action(
    State(state): State<Arc<AppState>>,
    Json(req): Json<ExecuteRequest>,
) -> (StatusCode, Json<ExecuteResponse>) {
    info!("Received action: {:?}", req);

    let result = match req.action.as_str() {
        "restart_deployment" => {
            restart_deployment(&state.kube_client, &req.namespace, &req.resource_name).await
        }
        "scale_deployment" => {
            let replicas = req.replicas.unwrap_or(2);
            scale_deployment(&state.kube_client, &req.namespace, &req.resource_name, replicas).await
        }
        unknown => Err(anyhow::anyhow!("Unknown action: {}", unknown)),
    };

    match result {
        Ok(msg) => {
            info!("Action succeeded: {}", msg);
            (
                StatusCode::OK,
                Json(ExecuteResponse {
                    success: true,
                    incident_id: req.incident_id,
                    action: req.action,
                    message: msg,
                }),
            )
        }
        Err(e) => {
            error!("Action failed: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ExecuteResponse {
                    success: false,
                    incident_id: req.incident_id,
                    action: req.action,
                    message: format!("Error: {}", e),
                }),
            )
        }
    }
}

async fn health() -> StatusCode {
    StatusCode::OK
}

// ─── Main ─────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter("healing_executor=info,tower_http=debug")
        .init();

    // Discover the in-cluster Kubernetes client
    let client = Client::try_default().await?;
    info!("Connected to Kubernetes API.");

    let state = Arc::new(AppState { kube_client: client });

    let app = Router::new()
        .route("/execute", post(execute_action))
        .route("/health", axum::routing::get(health))
        .with_state(state);

    let addr = "0.0.0.0:9000";
    info!("Healing Executor listening on {}", addr);
    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
