# Multi-stage build: compile in rust toolchain, then copy into slim image
FROM rust:1.88-slim AS builder

RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Cargo.toml .
# Create dummy main so cargo can cache dependency layer
RUN mkdir -p src && echo "fn main(){}" > src/main.rs
RUN cargo build --release 2>&1 || true   # cache deps
COPY src ./src
RUN touch src/main.rs && cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/healing-executor /usr/local/bin/healing-executor
EXPOSE 9000
ENTRYPOINT ["/usr/local/bin/healing-executor"]
