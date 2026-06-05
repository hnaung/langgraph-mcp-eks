# Deployment Guide

Steps to deploy the LangGraph agent platform to AWS EKS in production.

---

## Prerequisites

| Tool | Purpose |
|---|---|
| `aws` CLI | AWS authentication and ECR |
| `eksctl` | EKS cluster management |
| `kubectl` | Kubernetes operations |
| `helm` | Package deployment |
| `docker` | Build container images |
| `cosign` | Sign images for supply chain security |

Configure AWS credentials with permissions for EKS, ECR, IAM, and Secrets Manager.

---

## 1. Create the EKS Cluster

```bash
eksctl create cluster \
  --name ai-platform \
  --region ap-southeast-1 \
  --nodegroup-name standard \
  --node-type m5.large \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 6 \
  --with-oidc \
  --managed
```

The `--with-oidc` flag is required for IRSA (IAM Roles for Service Accounts).

---

## 2. Build and Push the Container Image

```bash
export ECR_REGISTRY=123456789.dkr.ecr.ap-southeast-1.amazonaws.com
export AWS_REGION=ap-southeast-1

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

docker build -t $ECR_REGISTRY/langgraph-agent:latest .
docker push $ECR_REGISTRY/langgraph-agent:latest
```

### Sign the image with Cosign

```bash
DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' \
  $ECR_REGISTRY/langgraph-agent:latest)

cosign sign $ECR_REGISTRY/langgraph-agent@$DIGEST
```

Update `k8s/deployment.yaml` with your ECR registry URL and image digest.

---

## 3. Configure IRSA (IAM Roles for Service Accounts)

Create the IAM policy from `iam/irsa-policy.json`, then attach it to a service account:

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws iam create-policy \
  --policy-name langgraph-agent-policy \
  --policy-document file://iam/irsa-policy.json

eksctl create iamserviceaccount \
  --name langgraph-agent-sa \
  --namespace ai-workloads \
  --cluster ai-platform \
  --attach-policy-arn arn:aws:iam::$ACCOUNT_ID:policy/langgraph-agent-policy \
  --approve
```

This allows pods to read secrets from AWS Secrets Manager without static credentials.

---

## 4. Store Production Secrets

Create the weather API key secret in Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name prod/weather/api-key \
  --secret-string '{"api_key":"YOUR_OPENWEATHER_KEY"}' \
  --region ap-southeast-1
```

---

## 5. Deploy with Helm

```bash
helm upgrade --install langgraph-agent ./helm \
  --namespace ai-workloads \
  --create-namespace \
  -f helm/values-prod.yaml \
  --set image.tag=$(git rev-parse HEAD)
```

Or apply raw Kubernetes manifests:

```bash
kubectl apply -f k8s/namespace.yaml   # if needed
kubectl apply -f k8s/
```

---

## 6. Verify Deployment

```bash
kubectl get pods -n ai-workloads
kubectl logs -l app=langgraph-agent -n ai-workloads --tail=50
kubectl get ingress -n ai-workloads
```

Test the health endpoint:

```bash
kubectl port-forward svc/langgraph-agent 8080:8080 -n ai-workloads
curl http://localhost:8080/health
```

---

## Production Checklist

- [ ] Image pinned by digest, not `:latest`
- [ ] Cosign signature verified in admission policy
- [ ] IRSA configured — no static AWS keys in pods or ConfigMaps
- [ ] Secrets in AWS Secrets Manager, not environment variables
- [ ] NetworkPolicy applied — default deny, explicit allows only
- [ ] WAF rules on ALB ingress
- [ ] HPA configured for expected load
- [ ] Structured logging and trace IDs enabled
- [ ] Bedrock accessed via VPC endpoint (no public internet)
- [ ] `.env` and local keys are **not** used in production manifests

---

## Scaling

The HPA manifest (`k8s/hpa.yaml`) scales the agent deployment based on CPU utilization. Adjust min/max replicas and target CPU in that file or in `helm/values-prod.yaml`.

MCP server pods (weather, search, ServiceNow) can be scaled independently — each tool is a separate deployment in a full production setup.

---

## Rollback

```bash
helm rollback langgraph-agent -n ai-workloads
```

Or revert to a previous image digest in the deployment manifest and re-apply.
