# Plan: Documentation Inquiry Chatbot on Enterprise-RAG

## TL;DR

Build a production-grade documentation inquiry chatbot by customizing and extending the existing Enterprise-RAG platform. The platform already provides >80% of required infrastructure (RAG pipeline, UI, auth, monitoring). Work is focused on documentation-specific enhancements: metadata-enriched ingestion, filtered retrieval, source citation, prompt engineering, and a polished admin/user UI — all deployed on the existing Kubernetes + Helm stack.

---

## Phase 1 — Foundation Configuration *(Days 1–3)*

**Goal:** Stand up the base RAG pipeline tuned for documentation workloads.

1. Create a new GMConnector YAML (`config/samples/docbot_xeon.yaml`) cloned from `chatQnA_xeon.yaml` with documentation-specific model selection and pipeline config
2. Configure LLM model to an instruction-following model suitable for Q&A (`mistralai/Mistral-7B-Instruct-v0.1` or `meta-llama/Llama-3.1-8B-Instruct`)
3. Set Redis index name to `docbot-index` to isolate the documentation knowledge base
4. Configure embedding model to `BAAI/bge-large-en-v1.5` for high-quality dense retrieval
5. Set reranker model to `BAAI/bge-reranker-large` for precision re-ranking
6. Create a dedicated Kubernetes namespace `docbot` and update APISIX route configs accordingly

**Files created/modified:**
- `deployment/microservices-connector/config/samples/docbot_xeon.yaml` ✅
- `deployment/auth/apis-crd-helm/values.yaml` ✅
- `deployment/microservices-connector/helm/envs/docbot.env` ✅
- `deployment/configs/docbot-namespace.yaml` ✅

---

## Phase 2 — Enhanced Document Ingestion Pipeline *(Days 3–6)*

**Goal:** Ingest documentation with rich metadata for filtered retrieval.

7. Extend `DataPrepInput` proto model in `src/comps/cores/proto/docarray.py` to accept metadata fields: `category`, `version`, `department`, `doc_title`, `source_url`
8. Modify `src/comps/dataprep/opea_dataprep_microservice.py` to:
   - Propagate metadata from input to each `TextDoc` chunk
   - Add document deduplication by content hash
   - Preserve section headings in chunk metadata
9. Modify `src/comps/ingestion/opea_ingestion_microservice.py` to store metadata fields as Redis hash attributes alongside embedding vectors
10. Create a **Document Registry** service (new microservice `src/comps/doc_registry/`) that:
    - Maintains a catalog of ingested documents (title, category, version, status, chunk count, ingestion timestamp)
    - Exposes `GET /v1/doc_registry/list`, `DELETE /v1/doc_registry/{doc_id}`, `GET /v1/doc_registry/{doc_id}/chunks`
    - Persists catalog to Redis Hash store
11. Add Kubernetes manifest `deployment/microservices-connector/config/manifests/doc_registry-usvc.yaml` and Helm values entry for the new service

**Files created/modified:**
- `src/comps/cores/proto/docarray.py` ✅ — added `DocMetadata`, `SourceDoc`; extended `DataPrepInput`
- `src/comps/dataprep/utils/utils.py` ✅ — metadata propagation, doc_id/doc_hash computation
- `src/comps/dataprep/utils/opea_dataprep.py` ✅ — forwarded `doc_metadata` parameter
- `src/comps/dataprep/opea_dataprep_microservice.py` ✅ — passes `doc_metadata` from input
- `src/comps/ingestion/opea_ingestion_microservice.py` ✅ — async doc_registry notification
- `src/comps/ingestion/impl/microservice/requirements.txt` ✅ — added `aiohttp`
- `src/comps/doc_registry/opea_doc_registry_microservice.py` ✅ — new FastAPI service
- `src/comps/doc_registry/utils/opea_doc_registry.py` ✅ — Redis-backed catalog logic
- `src/comps/doc_registry/impl/microservice/.env` ✅
- `src/comps/doc_registry/impl/microservice/requirements.txt` ✅
- `deployment/microservices-connector/config/manifests/doc_registry-usvc.yaml` ✅

---

## Phase 3 — Retrieval & Reranking Enhancement *(Days 6–8)*

**Goal:** Support metadata filtering and return source attribution with every answer.

12. Extend `EmbedDoc` in `docarray.py` to carry `filter_metadata: dict` (e.g., `{category: "API", version: "2.3"}`)
13. Modify `src/comps/retrievers/` Redis retriever to apply metadata pre-filters on the Redis index before vector similarity search (using Redis tag fields)
14. Modify `src/comps/reranks/` to pass through `retrieved_docs` metadata to `LLMParamsDoc` so sources are available downstream
15. Extend `LLMParamsDoc` with a `source_docs: List[SourceDoc]` field where `SourceDoc = {doc_title, source_url, chunk_text, relevance_score}`
16. Update the reranker to populate `source_docs` after scoring

---

## Phase 4 — Prompt Engineering & LLM Configuration *(Days 8–10)*

**Goal:** Accurate, citation-grounded documentation answers.

17. Create a documentation-specific system prompt template at `src/comps/llms/prompts/docbot_system_prompt.txt`:
    - Instructs LLM to answer ONLY from provided context
    - Instructs to cite source document titles  
    - Instructs to say "I don't have information about that in the documentation" when context is insufficient
    - Includes grounding instruction: "Base your answer strictly on the provided documentation excerpts"
18. Modify `src/comps/reranks/` to inject the system prompt before the reranked context when building `LLMParamsDoc.query`
19. Add a `DOCBOT_SYSTEM_PROMPT_PATH` env var for runtime override without code changes
20. Configure LLM parameters: `temperature=0.01` (deterministic), `max_new_tokens=1024`, `top_p=0.95`

---

## Phase 5 — Chat Gateway & API Enhancement *(Days 10–12)*

**Goal:** Expose clean API with source attribution in response.

21. Extend `ChatCompletionResponse` in `src/comps/cores/proto/api_protocol.py` to include `sources: List[SourceDoc]` in the response payload
22. Modify `src/comps/cores/mega/gateway.py` (ChatQnAGateway) to:
    - Extract `source_docs` from the final pipeline result_dict
    - Attach sources to the `ChatCompletionResponse`
    - Support streaming annotations (emit sources as a final SSE event after the streamed text)
23. Add `POST /v1/feedback` endpoint accepting `{query_id, rating: 1|-1, comment}` stored in Redis Stream for analytics

---

## Phase 6 — UI Enhancements *(Days 12–17)*

**Goal:** Polished documentation chatbot experience for end users and admins.

### 6A — User Chat Experience

24. Enhance `src/ui/src/pages/ChatPage.tsx` to:
    - Render a "Sources" accordion below each AI response (collapsible list of source doc titles + links)
    - Display a confidence indicator based on reranker scores
    - Add a "Was this helpful?" feedback widget (👍/👎) that POSTs to `/v1/feedback`
    - Add typing indicator during streaming
25. Add a `DocSourcesPanel` React component under `src/ui/src/components/` showing cited document excerpts

### 6B — Admin Document Management

26. Enhance `src/ui/src/pages/AdminPanelPage.tsx` to include:
    - Document catalog table: list all ingested docs with metadata (title, version, category, chunk count, last updated)
    - Per-document delete button calling `DELETE /v1/doc_registry/{doc_id}`
    - Metadata form on upload (category, version, department, title fields)
    - Upload progress tracking
    - Bulk upload support (drag-and-drop multiple files)
    - Document re-ingestion (update a document version while removing old chunks)
27. Add Redux slice `src/ui/src/store/docRegistrySlice.ts` for document catalog state management

### 6C — Configuration & Branding

28. Add a settings panel for admins to configure:
    - Active LLM model (via system_fingerprint API)
    - Guardrail toggle per scanner
    - Max retrieved documents (k parameter)
    - Chunk size override

---

## Phase 7 — Guardrails Configuration *(Days 17–18)*

**Goal:** Safe, policy-compliant documentation bot.

29. Enable documentation-appropriate input scanners in `src/comps/guardrails/` config:
    - `PROMPT_INJECTION_ENABLED=true`
    - `BAN_TOPICS_ENABLED=true` with custom banned topics list
    - `TOKEN_LIMIT_ENABLED=true` (max 512 input tokens)
    - `SECRETS_ENABLED=true` (prevent credentials from being ingested/returned)
30. Enable output scanners:
    - `FACTUAL_CONSISTENCY_ENABLED=true` (verify answer is grounded in retrieved context)
    - `URL_REACHABILITY_ENABLED=false` (avoid false positives on internal URLs)
    - `MALICIOUS_URLS_ENABLED=true`
31. Create guardrail configuration reference at `deployment/configs/docbot-guardrails.yaml`

---

## Phase 8 — Kubernetes Deployment *(Days 18–22)*

**Goal:** Production-ready Helm deployment.

32. Create `deployment/microservices-connector/helm/envs/docbot.env` with all docbot environment variables
33. Create `deployment/microservices-connector/config/manifests/doc_registry-usvc.yaml` (ConfigMap + Service + Deployment)
34. Add `doc_registry-usvc` image entry to `deployment/microservices-connector/helm/values.yaml`
35. Create `deployment/install_docbot.sh` installation script derived from `deployment/install_chatqna.sh`
36. Update APISIX API routes to expose `/api/v1/docbot` and `/api/v1/doc_registry`
37. Add Redis index initialization script that creates the documentation index schema with metadata tag fields

---

## Kubernetes Architecture — Deep Reference Guide

> This section is written for learning purposes. It explains every Kubernetes
> concept used by the project, why it is needed, and which open-source tool
> fulfils each role.

---

### K8s Primitives Used in This Project

#### 1. Namespace

A **Namespace** is a virtual cluster inside a physical Kubernetes cluster.
It provides scope for names (two Deployments can share the same name if they
are in different Namespaces), resource quotas, and network-policy boundaries.

```
chatqa      → main ChatQnA pipeline (existing)
dataprep    → document ingestion pipeline (existing)
auth-apisix → API gateway (APISIX + etcd)
auth        → Keycloak identity provider
rag-ui      → React frontend + system-fingerprint service
docbot      → this project's pipeline (new)
```

**In this project** every docbot service lives in the `docbot` namespace,
so its Redis, doc_registry, and LLM services are fully isolated.

```yaml
# deployment/configs/docbot-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: docbot
  labels:
    istio-injection: enabled   # enables Istio sidecar auto-injection
```

Apply: `kubectl apply -f deployment/configs/docbot-namespace.yaml`

---

#### 2. Deployment

A **Deployment** declares the *desired state* of a set of identical Pods.
The Deployment controller continuously reconciles actual state → desired state:
- If a Pod crashes, it is restarted automatically.
- Rolling updates change the image version with zero downtime.
- Rollbacks revert to the previous known-good `ReplicaSet`.

Key fields:
```yaml
spec:
  replicas: 1               # how many identical Pods to run
  selector:                 # how the Deployment finds "its" Pods
    matchLabels:
      app.kubernetes.io/name: doc-registry-usvc
  template:                 # the Pod template — every replica is built from this
    metadata:
      labels: ...
    spec:
      containers:
        - name: doc-registry-usvc
          image: localhost:5000/opea/doc-registry:latest
          ports:
            - containerPort: 6200
          envFrom:
            - configMapRef:     # inject all keys from the ConfigMap as env vars
                name: doc-registry-usvc-config
```

**Why not a StatefulSet?** Our Python microservices are stateless — all state
lives in Redis. So a `Deployment` (which manages stateless replicas) is the
right choice. If we had a service that needs stable network identity or
ordered Pod startup (e.g. a database), we'd use a `StatefulSet`.

---

#### 3. Service

A **Service** gives Pods a stable DNS name and virtual IP (ClusterIP) inside
the cluster. Pods come and go (crash/restart/roll), but the Service IP stays
constant.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: doc-registry-svc   # DNS: doc-registry-svc.docbot.svc.cluster.local
spec:
  type: ClusterIP           # only reachable inside the cluster
  ports:
    - port: 6200            # the port other services call
      targetPort: 6200      # the port the container actually listens on
  selector:
    app.kubernetes.io/name: doc-registry-usvc   # routes to matching Pods
```

DNS resolution inside the cluster: a service in namespace `docbot` named
`doc-registry-svc` is reachable at:
```
doc-registry-svc.docbot.svc.cluster.local:6200
```

**Service types used in the project:**
| Type | Where used | Explanation |
|------|-----------|-------------|
| `ClusterIP` | All internal microservices | Only reachable inside the cluster |
| `NodePort` | (not used here) | Exposes a port on every node — useful for dev/test |
| `LoadBalancer` | APISIX gateway ingress | Exposes a stable external IP via the cloud or MetalLB |

---

#### 4. ConfigMap

A **ConfigMap** stores non-secret configuration as key-value pairs. The
Deployment injects these as environment variables via `envFrom: configMapRef`.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: doc-registry-usvc-config
data:
  DOC_REGISTRY_REDIS_URL: "redis://redis-vector-db.docbot.svc.cluster.local:6379"
  DOC_REGISTRY_PORT: "6200"
```

**Rule:** ConfigMaps are for non-sensitive config. Never put passwords or API
tokens in a ConfigMap — use a **Secret** for those.

---

#### 5. Secret

A **Secret** holds sensitive data (base64-encoded). The project stores:
- Hugging Face token (`HF_TOKEN`)
- Keycloak admin password
- OIDC client secret

```bash
kubectl create secret generic hf-token \
  --from-literal=HF_TOKEN="hf_xxxx" \
  -n docbot
```

Reference in a Deployment:
```yaml
env:
  - name: HF_TOKEN
    valueFrom:
      secretKeyRef:
        name: hf-token
        key: HF_TOKEN
```

---

#### 6. PersistentVolumeClaim (PVC)

A **PVC** requests a slice of persistent storage from the cluster. The GMC
Helm chart creates a PVC for the model weights volume so the LLM/embedding
model files survive Pod restarts without re-downloading.

```yaml
# deployment/microservices-connector/helm/templates/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: model-volume
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 20Gi
```

**Storage provisioner required:** The project expects a CSI provisioner named
`local-path-provisioner` (checked in `check_prerequisites.sh`).
- Open-source option: **Rancher `local-path-provisioner`** — stores data on
  a node's local disk. Simple to install, no cloud dependency.
- For production: **Longhorn** (open-source distributed block storage for K8s).

---

#### 7. CustomResourceDefinition (CRD) + Controller Pattern

A **CRD** teaches Kubernetes about a new resource type. Once registered, you
can `kubectl apply -f` your custom object just like a native Deployment.

This project defines `GMConnector` (`gmc.opea.io/v1alpha3`):

```bash
kubectl get gmc -n docbot
# NAME      URL                              Ready
# docbot    http://router-service:8080/      True
```

The **GMC controller** (`gmc-manager` Deployment in the `system` namespace) is
a loop that watches `GMConnector` objects and, for each one, automatically:
1. Creates the `ConfigMap` for each pipeline step (from `.spec.nodes[*].steps[*].config`)
2. Creates the `Service` for each step
3. Creates the `Deployment` for each step (using manifests from `config/manifests/`)
4. Patches the `GMConnector` status with the router's access URL

This is the **Kubernetes Operator pattern** — a custom controller extending
Kubernetes to manage domain-specific applications declaratively.

**RBAC** (`ClusterRole` + `ClusterRoleBinding`): the GMC controller needs
permission to create/update/delete Deployments, Services, ConfigMaps, and
Secrets across namespaces. These are granted by the manifest in
`config/rbac/gmc-manager-rbac.yaml`.

---

#### 8. Ingress vs API Gateway

**Ingress** is a Kubernetes resource that routes external HTTP/HTTPS traffic
to internal Services based on hostnames and paths.

**Why APISIX instead of plain Ingress?** Plain K8s Ingress only does
path-based routing. APISIX adds: JWT/OIDC authentication, rate limiting,
request transformation, and plugin extensibility — all as Kubernetes CRDs.

```
Internet
    │
    ▼
APISIX Gateway (LoadBalancer Service, namespace: auth-apisix)
    │  validates Bearer token via Keycloak OIDC introspection
    ├─ /api/v1/docbot       → router-service.docbot:8080
    ├─ /api/v1/doc_registry → doc-registry-svc.docbot:6200
    └─ /api/v1/feedback     → doc-registry-svc.docbot:6200
```

**Route definition** (Kubernetes CRD `ApisixRoute`):
```yaml
apiVersion: apisix.apache.org/v2
kind: ApisixRoute
metadata:
  name: docbot-authenticated-endpoints
  namespace: docbot
spec:
  http:
  - name: docbot-query
    match:
      hosts: ["erag.com"]
      paths: ["/api/v1/docbot"]
    backends:
    - serviceName: router-service
      servicePort: 8080
    plugins:
    - name: openid-connect
      enable: true
      config:
        bearer_only: true
        discovery: http://keycloak.auth.svc.cluster.local/realms/EnterpriseRAG/.well-known/openid-configuration
```

**Open-source components used:**
| Component | Role | License |
|-----------|------|---------|
| [Apache APISIX](https://apisix.apache.org/) | API gateway + auth | Apache 2.0 |
| [etcd](https://etcd.io/) | APISIX config store | Apache 2.0 |
| [Keycloak](https://www.keycloak.org/) | Identity provider (OIDC/OAuth2) | Apache 2.0 |

---

#### 9. ServiceMonitor (Prometheus Operator CRD)

A **ServiceMonitor** tells Prometheus which Services to scrape for metrics.
The project uses the **Prometheus Operator** pattern — instead of editing
`prometheus.yml` manually, you declare your scrape targets as Kubernetes objects.

```yaml
# deployment/microservices-connector/config/prometheus/monitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: controller-manager-metrics-monitor
spec:
  endpoints:
    - path: /metrics
      port: https
  selector:
    matchLabels:
      control-plane: controller-manager
```

**Open-source observability stack (all 100% open-source):**
| Component | Role | License |
|-----------|------|---------|
| [Prometheus](https://prometheus.io/) | Metrics collection & alerting | Apache 2.0 |
| [Grafana](https://grafana.com/oss/) | Dashboards | AGPL 3.0 |
| [Grafana Loki](https://grafana.com/oss/loki/) | Log aggregation | AGPL 3.0 |
| [Grafana Tempo](https://grafana.com/oss/tempo/) | Distributed tracing | AGPL 3.0 |
| [OpenTelemetry Collector](https://opentelemetry.io/) | Trace/metrics pipeline | Apache 2.0 |

---

#### 10. Istio Service Mesh (optional but recommended)

The project's namespace labels include `istio-injection: enabled`. Istio
automatically injects a **sidecar proxy** (Envoy) into every Pod. This gives:
- mTLS between services (encrypted + authenticated traffic inside the cluster)
- Automatic Distributed Tracing (works with Tempo above)
- Traffic shaping (canary deployments, retries, timeouts)
- Observability without code changes

**Open-source:** [Istio](https://istio.io/) — Apache 2.0

To disable Istio (simpler setup for dev): remove `istio-injection: enabled`
from the namespace labels.

---

### Full Component Inventory — Open-Source Versions

All components below are **100% open-source** with no commercial license required.

| Layer | Component | Open-Source Project | License | Helm Chart |
|-------|-----------|-------------------|---------|------------|
| **Cluster** | Kubernetes | [k3s](https://k3s.io/) or [kind](https://kind.sigs.k8s.io/) (local) | Apache 2.0 | — |
| **Container Runtime** | containerd | [containerd](https://containerd.io/) | Apache 2.0 | — |
| **Storage** | PVC provisioner | [local-path-provisioner](https://github.com/rancher/local-path-provisioner) | Apache 2.0 | Rancher repo |
| **Packaging** | Helm | [Helm v3](https://helm.sh/) | Apache 2.0 | — |
| **Pipeline Orchestration** | GMC Controller CRD | [OPEA GMC](https://github.com/opea-project/GenAIInfra) | Apache 2.0 | In-repo |
| **Vector DB** | Redis Stack | [redis/redis-stack:7.2.0-v9](https://redis.io/docs/stack/) | Redis Source Available (free to use) | In-repo manifest |
| **API Gateway** | APISIX | [Apache APISIX 2.8.1](https://apisix.apache.org/) | Apache 2.0 | `apisix/apisix` |
| **Identity Provider** | Keycloak | [Keycloak](https://www.keycloak.org/) | Apache 2.0 | `bitnami/keycloak` |
| **Embedding Server** | TEI | [HuggingFace TEI](https://github.com/huggingface/text-embeddings-inference) | Apache 2.0 | In-repo manifest |
| **LLM Inference** | TGI | [HuggingFace TGI](https://github.com/huggingface/text-generation-inference) | Apache 2.0 | In-repo manifest |
| **Reranking Server** | TEI | same as embedding (dual mode) | Apache 2.0 | In-repo manifest |
| **Metrics** | Prometheus | [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts) | Apache 2.0 | `prometheus-community/kube-prometheus-stack` |
| **Dashboards** | Grafana | [Grafana OSS](https://grafana.com/oss/grafana/) | AGPL 3.0 | bundled in kube-prometheus-stack |
| **Logs** | Loki + Promtail | [Grafana Loki](https://grafana.com/oss/loki/) | AGPL 3.0 | `grafana/loki-stack` |
| **Traces** | Tempo + OTel Collector | [Grafana Tempo](https://grafana.com/oss/tempo/) | Apache 2.0 | `grafana/tempo` |
| **Service Mesh** | Istio | [Istio](https://istio.io/) | Apache 2.0 | `istio/base` + `istio/istiod` |

> **Redis Stack note:** Redis Stack (which includes the RediSearch / RedisJSON
> modules needed for vector search) uses the Redis Source Available License
> (RSAL). It is free for all use. The pure open-source alternative is
> **Valkey** (Linux Foundation fork, Apache 2.0), which is a drop-in replacement.

---

### Kubernetes Object Flow — How a Request Travels

```
User Browser
    │  HTTPS  (port 443)
    ▼
┌─────────────────────────────────────────────────────────────┐
│  APISIX Gateway  (LoadBalancer Service, namespace: auth-apisix)
│  - Verifies Bearer JWT against Keycloak OIDC endpoint       │
│  - Routes /api/v1/docbot → router-service.docbot:8080       │
└────────────────────────┬────────────────────────────────────┘
                         │  ClusterIP  (in-cluster only)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  GMC Router  (Deployment: router-service, namespace: docbot) │
│  - Reads GMConnector CRD spec                                │
│  - Executes the Sequence pipeline via HTTP calls             │
└──┬─────────────┬──────────────┬───────────────┬─────────────┘
   │             │              │               │
   ▼             ▼              ▼               ▼
embedding-svc  retriever-svc  reranking-svc  llm-svc
(port 6000)    (port 6620)    (port 8000)    (port 9000)
   │                               │
   ▼                               ▼
tei-embedding-svc           tei-reranking-svc
(BAAI/bge-large-en-v1.5)    (BAAI/bge-reranker-large)
                        ▲
                  redis-vector-db (port 6379)
                  index: docbot-index
```

---

### Kubernetes Workflow — Deploy the Docbot Stack Step by Step

```bash
# 1. Create the namespace
kubectl apply -f deployment/configs/docbot-namespace.yaml

# 2. Create the Hugging Face token Secret
kubectl create secret generic hf-token \
  --from-literal=HF_TOKEN="<your-token>" \
  -n docbot

# 3. Install the GMC controller (if not already installed)
helm upgrade --install gmc \
  deployment/microservices-connector/helm \
  -n system --create-namespace \
  -f deployment/microservices-connector/helm/values.yaml

# 4. Apply the custom GMConnector pipeline descriptor
kubectl apply -f deployment/microservices-connector/config/samples/docbot_xeon.yaml

# The GMC controller now auto-creates all Deployments, Services, and
# ConfigMaps for: embedding-svc, tei-embedding-svc, retriever-svc,
# redis-vector-db, reranking-svc, tei-reranking-svc, llm-svc, tgi-service-m

# 5. Deploy the doc_registry service (not managed by GMC)
kubectl apply -f deployment/microservices-connector/config/manifests/doc_registry-usvc.yaml -n docbot

# 6. Add the APISIX routes
helm upgrade --install docbot-routes \
  deployment/auth/apis-crd-helm \
  -n docbot \
  -f deployment/auth/apis-crd-helm/values.yaml

# 7. Verify all Pods are Running
kubectl get pods -n docbot
```

---

### Helm Chart Structure Explained

Helm is the package manager for Kubernetes. A **Chart** is a directory of
YAML templates + a `values.yaml` defaults file.

```
deployment/microservices-connector/helm/
├── Chart.yaml          # chart name, version, description
├── values.yaml         # default configuration values
└── templates/
    ├── configmap.yaml  # renders ConfigMaps from values
    ├── deployment.yaml # renders the GMC controller Deployment
    ├── service.yaml    # renders the GMC controller Service
    ├── pvc.yaml        # renders PersistentVolumeClaims for model storage
    └── rbac.yaml       # renders ServiceAccount, ClusterRole, ClusterRoleBinding
```

**How values flow:**
```
values.yaml  →  helm install --set key=value  →  template rendering  →  kubectl apply
```

```bash
# Override the LLM model at install time without editing files:
helm upgrade --install gmc deployment/microservices-connector/helm \
  --set images.tgi.envs.LLM_TGI_MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
```

---

### RBAC (Role-Based Access Control) Explained

Kubernetes RBAC controls **what** a service account **can do** in the cluster.

The GMC controller needs broad permissions because it creates K8s objects on
behalf of users who apply `GMConnector` manifests:

```yaml
# ClusterRole: what actions are allowed
rules:
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["create", "delete", "get", "list", "patch", "update", "watch"]
- apiGroups: [""]             # core API group
  resources: ["services", "configmaps", "secrets"]
  verbs: ["create", "delete", "get", ...]
```

```yaml
# ClusterRoleBinding: who gets the ClusterRole
subjects:
- kind: ServiceAccount
  name: gmc-controller
  namespace: system
```

**Principle of least privilege:** give each ServiceAccount only the verbs
it actually needs. The doc_registry microservice, for example, needs no K8s
API access at all — it only talks to Redis — so it does not need a custom
ClusterRole.

---

### Local Development Setup (no cloud account needed)

For learning and development, run a full K8s cluster on your laptop:

```bash
# Option A: kind (Kubernetes-in-Docker) — recommended for development
brew install kind
kind create cluster --name erag

# Option B: k3s — lightweight K8s, single binary
curl -sfL https://get.k3s.io | sh -

# Install Helm
brew install helm

# Install local-path-provisioner (storage for PVCs)
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml

# Verify cluster
kubectl get nodes
kubectl get storageclass
```

---

## Phase 9 — Observability & Analytics *(Days 22–24)*

**Goal:** Monitor quality and usage of the documentation bot.

38. Add Grafana dashboard `deployment/telemetry/helm/docbot-dashboard.json` with panels:
    - Query volume over time
    - Average response latency per pipeline stage
    - Retrieval hit rate (queries with ≥1 retrieved doc)
    - Top queried document categories
    - Guardrail trigger frequency
39. Apply `@traceable` Prometheus decorator to doc_registry microservice
40. Implement query logging to Redis Stream: each query + retrieved sources + feedback score stored for analytics replay

---

## Relevant Files

| File | Role |
|------|------|
| `deployment/microservices-connector/config/samples/chatQnA_xeon.yaml` | Template for docbot GMConnector YAML |
| `src/comps/cores/proto/docarray.py` | Data models to extend (EmbedDoc, LLMParamsDoc, TextDoc) |
| `src/comps/cores/proto/api_protocol.py` | API contract to extend (ChatCompletionResponse + sources) |
| `src/comps/cores/mega/gateway.py` | Gateway to update for source extraction |
| `src/comps/cores/mega/orchestrator.py` | DAG scheduler (understand but likely no change) |
| `src/comps/dataprep/opea_dataprep_microservice.py` | Extend for metadata handling |
| `src/comps/ingestion/opea_ingestion_microservice.py` | Extend for metadata persistence |
| `src/comps/retrievers/` | Add metadata filtering |
| `src/comps/reranks/` | Pass source metadata downstream |
| `src/comps/llms/` | System prompt injection |
| `src/ui/src/pages/ChatPage.tsx` | Add sources panel + feedback |
| `src/ui/src/pages/AdminPanelPage.tsx` | Document catalog + metadata upload |
| `src/ui/src/services/dataIngestionService.ts` | Extend for metadata fields |
| `deployment/auth/apis-crd-helm/values.yaml` | Add new API routes |
| `deployment/microservices-connector/helm/values.yaml` | Add doc_registry image |

---

## Verification

1. **Unit tests:** Add tests in `src/tests/unit/` for metadata propagation through dataprep → ingestion → retriever chain
2. **Integration test:** Create `src/tests/test_workflow_docbot.py` — upload a sample PDF with metadata, query it, assert `sources[]` is populated in response
3. **E2E test:** Extend `src/tests/e2e/` pattern to verify the full Kubernetes pipeline end-to-end
4. **Guardrail test:** Send a prompt injection attempt → expect HTTP 400 blocked response
5. **UI smoke test:** Verify sources accordion renders, feedback POST fires, admin catalog loads
6. **Load test:** Use `src/tests/benchmark/` to validate <3s p95 latency at 10 concurrent users

---

## Decisions & Scope Boundaries

- **In scope:** All 9 phases using the existing Kubernetes + Helm deployment model
- **Out of scope v1:** Multi-tenant knowledge base isolation (separate Redis indexes per tenant) — addressable in v2
- **Out of scope v1:** Native mobile app — responsive web UI covers mobile browsers
- **Vector store:** Redis with tag-field metadata filters (already the platform default; no Milvus/Qdrant required)
- **LLM default:** `mistralai/Mistral-7B-Instruct-v0.1` on CPU Xeon; Gaudi builds available via the existing Gaudi GMConnector pattern
- **Source citation format:** Inline `[DocTitle]` markers in LLM text + structured `sources[]` array in JSON response
