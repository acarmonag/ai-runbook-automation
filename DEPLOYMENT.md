# Cloud Deployment Guide — ECS & EKS

This document describes how to deploy AI Runbook Automation on AWS ECS (Fargate) or Kubernetes (EKS). The architecture is the same in both cases; the difference is the control plane.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Load Balancer (ALB)                   │
└────────────┬────────────────────────────────┬───────────────┘
             │ :80/:443                        │ :8000 (internal)
    ┌────────▼────────┐               ┌────────▼────────┐
    │   ui (nginx)    │               │   agent-api     │
    │  React SPA      │──/api/──────▶ │   FastAPI       │
    │  port 80        │  /ws/         │   port 8000     │
    └─────────────────┘               └────────┬────────┘
                                               │ Redis pub/sub
                                               │ PostgreSQL reads
                                      ┌────────▼────────┐
                                      │  agent-worker    │
                                      │  ARQ + LLM loop  │
                                      │  (no public port)│
                                      └────────┬────────┘
                                               │
              ┌────────────────────────────────┼──────────────┐
              │                                │              │
    ┌─────────▼──────┐            ┌────────────▼────┐  ┌─────▼──────┐
    │   PostgreSQL   │            │     Redis        │  │  Ollama /  │
    │   RDS / Aurora │            │  ElastiCache     │  │  Bedrock   │
    └────────────────┘            └─────────────────┘  └────────────┘
```

### Services

| Service | Role | Replicas | CPU | Memory |
|---------|------|----------|-----|--------|
| `ui` | React dashboard (nginx) | 1–2 | 256 CPU | 512 MB |
| `agent-api` | Alert intake, incident API, WebSocket | 2–4 | 512 CPU | 1 GB |
| `agent-worker` | LLM reasoning loop (ARQ) | 1–4 | 2048 CPU | 4 GB |
| `mock-prometheus` | (dev only — replace with real Prometheus in prod) | 1 | 256 CPU | 512 MB |

---

## AWS ECS (Fargate)

### Prerequisites

```bash
# Install tools
brew install awscli terraform
aws configure  # set access key, secret, region

# ECR repositories
aws ecr create-repository --repository-name runbook-agent-api
aws ecr create-repository --repository-name runbook-agent-worker
aws ecr create-repository --repository-name runbook-ui
```

### Build & Push Images

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
export ECR_BASE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Login
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_BASE

# Build and push
docker build -t $ECR_BASE/runbook-agent-api:latest -f Dockerfile .
docker build -t $ECR_BASE/runbook-agent-worker:latest -f Dockerfile.worker .
docker build -t $ECR_BASE/runbook-ui:latest ./ui

docker push $ECR_BASE/runbook-agent-api:latest
docker push $ECR_BASE/runbook-agent-worker:latest
docker push $ECR_BASE/runbook-ui:latest
```

### Infrastructure

Use the managed services instead of running databases in containers:

- **PostgreSQL** → Amazon RDS (Aurora PostgreSQL Serverless v2 recommended)
- **Redis** → Amazon ElastiCache for Redis (cluster mode off, 1 shard)
- **LLM** → Amazon Bedrock (`anthropic.claude-sonnet-4-6`) or keep Ollama on a GPU instance

### Task Definitions

Each service maps to a Fargate task definition. Key environment variables:

```json
// agent-api task
{
  "environment": [
    {"name": "DATABASE_URL", "value": "postgresql+asyncpg://sre:${DB_PASS}@rds-host:5432/runbooks"},
    {"name": "REDIS_URL", "value": "redis://elasticache-host:6379"},
    {"name": "LLM_BACKEND", "value": "claude"},
    {"name": "ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."},
    {"name": "APPROVAL_MODE", "value": "AUTO"},
    {"name": "CORS_ORIGINS", "value": "https://your-domain.com"}
  ]
}

// agent-worker task (needs Secrets Manager for LLM key)
{
  "environment": [
    {"name": "DATABASE_URL", "value": "postgresql+asyncpg://sre:${DB_PASS}@rds-host:5432/runbooks"},
    {"name": "REDIS_URL", "value": "redis://elasticache-host:6379"},
    {"name": "LLM_BACKEND", "value": "claude"},
    {"name": "ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."},
    {"name": "NUM_WORKERS", "value": "4"},
    {"name": "USE_MOCK_LOGS", "value": "false"}
  ]
}
```

### ECS Service Configuration

```hcl
# Terraform snippet (simplified)
resource "aws_ecs_service" "agent_api" {
  name            = "agent-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.agent_api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.agent_api.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.agent_api.arn
    container_name   = "agent-api"
    container_port   = 8000
  }
}

resource "aws_ecs_service" "agent_worker" {
  name            = "agent-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.agent_worker.arn
  desired_count   = 1   # scale up during incident storms
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.agent_worker.id]
  }
  # No load balancer — worker pulls jobs from Redis
}
```

### Auto-Scaling

The worker should scale based on Redis queue depth:

```hcl
resource "aws_appautoscaling_policy" "worker_scale" {
  name               = "worker-queue-depth"
  resource_id        = "service/${aws_ecs_cluster.main.name}/agent-worker"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type = "ChangeInCapacity"
    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}
```

---

## Kubernetes / EKS

### Prerequisites

```bash
# Create EKS cluster
eksctl create cluster \
  --name runbook-automation \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type m5.xlarge \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 8

# Configure kubectl
aws eks update-kubeconfig --name runbook-automation --region us-east-1
```

### Secrets

Store sensitive values in Kubernetes Secrets (or AWS Secrets Manager via External Secrets Operator):

```bash
kubectl create secret generic runbook-secrets \
  --from-literal=anthropic-api-key=$ANTHROPIC_API_KEY \
  --from-literal=db-password=$DB_PASSWORD \
  --from-literal=api-key=$API_KEY
```

### Manifests

#### agent-api Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: agent-api
  template:
    metadata:
      labels:
        app: agent-api
    spec:
      containers:
      - name: agent-api
        image: <ECR_URI>/runbook-agent-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: runbook-secrets
              key: database-url
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        - name: LLM_BACKEND
          value: "claude"
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: runbook-secrets
              key: anthropic-api-key
        - name: APPROVAL_MODE
          value: "AUTO"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 15
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "1000m"
            memory: "1Gi"
---
apiVersion: v1
kind: Service
metadata:
  name: agent-api-service
spec:
  selector:
    app: agent-api
  ports:
  - port: 8000
    targetPort: 8000
```

#### agent-worker Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: agent-worker
  template:
    metadata:
      labels:
        app: agent-worker
    spec:
      containers:
      - name: agent-worker
        image: <ECR_URI>/runbook-agent-worker:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: runbook-secrets
              key: database-url
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        - name: LLM_BACKEND
          value: "claude"
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: runbook-secrets
              key: anthropic-api-key
        - name: NUM_WORKERS
          value: "4"
        - name: USE_MOCK_LOGS
          value: "false"
        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
```

#### KEDA Auto-Scaling (Redis Queue Depth)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: agent-worker-scaler
spec:
  scaleTargetRef:
    name: agent-worker
  minReplicaCount: 1
  maxReplicaCount: 8
  triggers:
  - type: redis
    metadata:
      address: redis-service:6379
      listName: arq:queue:default
      listLength: "1"   # 1 pending job = 1 worker
```

#### Ingress (nginx-ingress)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: runbook-ingress
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - runbook.your-domain.com
    secretName: runbook-tls
  rules:
  - host: runbook.your-domain.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: agent-api-service
            port:
              number: 8000
      - path: /ws
        pathType: Prefix
        backend:
          service:
            name: agent-api-service
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ui-service
            port:
              number: 80
```

---

## Production Checklist

### Security
- [ ] Store all secrets in AWS Secrets Manager or Kubernetes Secrets (never in env vars committed to git)
- [ ] Enable RDS encryption at rest and in transit
- [ ] Use VPC private subnets for all backend services
- [ ] Set `API_KEY` to require auth on all API endpoints
- [ ] Enable HTTPS-only via ALB or ingress TLS termination
- [ ] Restrict worker's IAM role to only what it needs (CloudWatch logs, Secrets Manager)

### Reliability
- [ ] RDS Multi-AZ enabled
- [ ] ElastiCache with automatic failover
- [ ] `agent-api` behind ALB with health-check-based routing
- [ ] `agent-worker` auto-scales on queue depth (KEDA or CloudWatch → AppAutoScaling)
- [ ] ARQ job retries configured (`max_tries = 3`) for transient LLM failures

### Observability
- [ ] Forward container logs to CloudWatch Logs or Datadog
- [ ] Expose `/metrics` endpoint from `agent-api` to Prometheus (or use CloudWatch EMF)
- [ ] Alert on `incident_processing_duration_seconds` p99 > 5 minutes
- [ ] Alert on `active_incidents` gauge > `NUM_WORKERS` (queue backup)

### LLM Backend
- **Local (dev)**: Ollama on a GPU EC2 instance, accessed via private IP
- **Managed (prod)**: Amazon Bedrock (`anthropic.claude-sonnet-4-6`) — no GPU EC2 needed, pay per token
- Set `LLM_BACKEND=claude` and `ANTHROPIC_API_KEY` from Secrets Manager

### Real Prometheus Integration
Replace `mock-prometheus` with your actual Prometheus:
```yaml
# agent-api + agent-worker env
PROMETHEUS_URL=http://prometheus.monitoring.svc.cluster.local:9090
USE_MOCK_LOGS=false
```

Update `agent/actions/prometheus.py` to query real PromQL metrics (the `get_metrics` action already accepts arbitrary PromQL queries).

---

## Cost Estimate (AWS, us-east-1)

| Resource | Spec | Est. Monthly |
|----------|------|-------------|
| ECS Fargate — agent-api (2×) | 0.5 vCPU, 1 GB | ~$25 |
| ECS Fargate — agent-worker (1×) | 2 vCPU, 4 GB | ~$65 |
| ECS Fargate — ui (1×) | 0.25 vCPU, 0.5 GB | ~$8 |
| RDS Aurora PostgreSQL Serverless | 0.5–2 ACU | ~$20–80 |
| ElastiCache Redis t3.micro | 1 node | ~$15 |
| ALB | per LCU | ~$20 |
| Bedrock Claude Sonnet | ~100 incidents/day × 5k tokens | ~$50 |
| **Total** | | **~$200–260/mo** |

Bedrock cost scales linearly with incident volume. Ollama on a `g4dn.xlarge` spot instance (~$0.16/hr) is cheaper at scale.
