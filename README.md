> [!NOTE]
> This is a fork of [intel/Enterprise-RAG](https://github.com/intel/Enterprise-RAG) extended to build a **Documentation Inquiry Chatbot** (DocBot) — a production-grade RAG chatbot specialised for querying enterprise documentation. See [`docs/docbot_plan.md`](docs/docbot_plan.md) for the full development plan.

# DocBot — Documentation Inquiry Chatbot

**Built on Intel® AI for Enterprise RAG**

DocBot is a production-ready documentation inquiry chatbot that extends the Intel® Enterprise-RAG platform. It allows teams to ingest their technical documentation (PDFs, Markdown, web pages) and ask natural-language questions, receiving accurate, citation-grounded answers drawn exclusively from that documentation corpus.

The upstream platform already provides >80% of the required infrastructure (RAG pipeline, UI, auth, monitoring). This project contributes documentation-specific enhancements: metadata-enriched ingestion, filtered retrieval, source citation, prompt engineering, a document registry service, and a polished admin/user UI — all running on the existing Kubernetes + Helm stack.

---

## Architecture Overview

```
User Query
    │
    ▼
APISIX Gateway  ──────────────────────────────────  Keycloak (AuthN/AuthZ)
    │
    ▼
GMC Router  (GenAI Microservices Connector)
    │
    ├──► Embedding Service  (TEI / BAAI/bge-large-en-v1.5)
    │         │
    │         ▼
    ├──► Redis Retriever  (Redis Stack 7.2+ / docbot-index)
    │         │  metadata-filtered vector search
    │         ▼
    ├──► Reranker  (TEI / BAAI/bge-reranker-large)
    │         │  populates SourceDoc attribution
    │         ▼
    └──► LLM  (TGI / Mistral-7B-Instruct-v0.1)
              │  documentation-specific system prompt
              ▼
         ChatCompletionResponse  +  sources[]

Document Ingestion Path
    │
    └──► DataPrep  (chunk + metadata + doc_id/hash)
              │
              ▼
         Ingestion  (embed + store in Redis)
              │
              ▼
         Doc Registry  (catalog: title, version, category, chunk count)
```

Full microservices architecture diagram: [docs/microservices_architecture.png](./docs/microservices_architecture.png)

---

## Table of Contents

- [Project Objectives](#project-objectives)
- [Development Phases & Status](#development-phases--status)
- [Key Components](#key-components)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Development Setup](#development-setup)
- [Repository Structure](#repository-structure)
- [Support](#support)
- [License](#license)
- [Security](#security)
- [Upstream Attribution](#upstream-attribution)

---

## Project Objectives

1. **Metadata-enriched ingestion** — Documents are ingested with structured metadata (`category`, `version`, `department`, `doc_title`, `source_url`). Every chunk carries this metadata into the vector store for filtered retrieval.
2. **Document Registry** — A new microservice maintains a catalog of all ingested documents: title, version, chunk count, ingestion timestamp, and status. Provides CRUD API for admin document management.
3. **Filtered retrieval** — Users (or the UI) can scope queries to a specific documentation category or version using Redis tag-field pre-filters before vector similarity search.
4. **Source attribution** — Every answer includes a `sources[]` list: the document title, URL, and the exact chunk text that was used, so answers are fully traceable.
5. **Documentation-tuned prompting** — A custom system prompt instructs the LLM to answer strictly from retrieved context and to cite sources, preventing hallucination.
6. **Admin document management UI** — The React frontend is extended with a document catalog view, per-document deletion, metadata fields on upload, and re-ingestion support.
7. **User feedback loop** — A 👍/👎 feedback widget on every response posts to a Redis Stream for quality monitoring and future fine-tuning.
8. **Production Kubernetes deployment** — All components run in a dedicated `docbot` namespace using the existing Helm chart infrastructure with Istio service mesh, Prometheus/Grafana observability, and APISIX auth gateway.

---

## Development Phases & Status

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Foundation Configuration — GMConnector pipeline, `docbot` namespace, APISIX routes, Helm env vars | ✅ Complete |
| **Phase 2** | Enhanced Ingestion Pipeline — DocMetadata model, doc_id/hash dedup, Doc Registry microservice | ✅ Complete |
| **Phase 3** | Retrieval & Reranking Enhancement — metadata pre-filters, `SourceDoc` attribution chain | 🔄 In Progress |
| **Phase 4** | Prompt Engineering — documentation system prompt, deterministic LLM config | ⬜ Planned |
| **Phase 5** | Chat Gateway & API Enhancement — `sources[]` in response, feedback endpoint | ⬜ Planned |
| **Phase 6** | UI Enhancements — sources panel, admin document catalog, feedback widget | ⬜ Planned |
| **Phase 7** | Guardrails — prompt injection, topic banning, factual consistency checking | ⬜ Planned |
| **Phase 8** | Production K8s Deployment — install script, Redis schema init, full Helm values | ⬜ Planned |
| **Phase 9** | Observability — Grafana dashboards for query quality, feedback analytics, ingestion metrics | ⬜ Planned |

See [docs/docbot_plan.md](docs/docbot_plan.md) for the full detailed plan including implementation notes, file lists, and the Kubernetes architecture reference guide.

---

## Key Components

### New / Extended Microservices

| Service | Port | Description |
|---------|------|-------------|
| `doc_registry` | 6200 | **New** — document catalog CRUD + feedback endpoint |
| `dataprep` | 9399 | **Extended** — accepts `DocMetadata`, computes `doc_id`/`doc_hash` |
| `ingestion` | 6120 | **Extended** — async notification to `doc_registry` after embedding |

### New Data Models (`src/comps/cores/proto/docarray.py`)

| Model | Purpose |
|-------|---------|
| `DocMetadata` | Structured metadata attached at ingest time: `category`, `version`, `department`, `doc_title`, `source_url` |
| `SourceDoc` | Source attribution record returned with answers: `doc_title`, `source_url`, `chunk_text`, `relevance_score` |

### New Deployment Artifacts

| File | Purpose |
|------|---------|
| `deployment/microservices-connector/config/samples/docbot_xeon.yaml` | GMConnector CRD wiring the docbot RAG pipeline |
| `deployment/configs/docbot-namespace.yaml` | Kubernetes Namespace with Istio injection label |
| `deployment/microservices-connector/helm/envs/docbot.env` | All docbot environment variables |
| `deployment/microservices-connector/config/manifests/doc_registry-usvc.yaml` | ConfigMap + Service + Deployment for the doc_registry service |

### Open-Source Stack (all Apache 2.0 / MIT / BSD licensed)

| Component | Role | License |
|-----------|------|---------|
| Redis Stack 7.2+ | Vector store + metadata filtering + catalog | RSAL (free tier) / Redis Stack EULA — or use [Redis OSS](https://github.com/redis/redis) with [RediSearch module](https://github.com/RediSearch/RediSearch) |
| Apache APISIX 2.8 | API gateway, auth enforcement | Apache 2.0 |
| Keycloak | Identity provider, OIDC | Apache 2.0 |
| HuggingFace TGI | LLM inference server | Apache 2.0 |
| HuggingFace TEI | Embedding + reranking inference | MIT |
| Prometheus + Grafana OSS | Metrics + dashboards | Apache 2.0 |
| Loki + Tempo | Log aggregation + distributed tracing | Apache 2.0 |
| Istio | Service mesh, mTLS | Apache 2.0 |
| Kubernetes 1.29 | Container orchestration | Apache 2.0 |

---

## System Requirements

| | |
|--------------------|------|
| Operating System | Ubuntu 22.04 |
| Kubernetes Version | 1.29 |
| Hardware (GPU) | Intel® Gaudi® 2 AI Accelerator (recommended) |
| Hardware (CPU-only) | 4th/5th Gen Intel® Xeon® Scalable processors |

### Software Prerequisites

Refer to [docs/prerequisites.md](./docs/prerequisites.md) for full installation instructions.

- **Kubernetes cluster** v1.29 with [local-path-provisioner](https://github.com/rancher/local-path-provisioner) CSI driver
- **Helm** v3.x
- **kubectl** configured to reach your cluster
- **Hugging Face Hub token** — required to pull `mistralai/Mistral-7B-Instruct-v0.1` (free, request access at [huggingface.co/mistralai/Mistral-7B-Instruct-v0.1](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.1))
- **Disk Space** — ~50 GB for Mistral-7B; ~260 GB if using Mixtral-8x7B
- **RAM** — 32 GB minimum for CPU-only; 16 GB + Gaudi/GPU memory for accelerated inference

---

## Installation

### Quick Start (DocBot)

```bash
git clone https://github.com/simolamine/Enterprise-RAG.git
cd Enterprise-RAG

# 1. Create the docbot namespace
kubectl apply -f deployment/configs/docbot-namespace.yaml

# 2. Deploy the full docbot stack via the one-click installer
cd deployment
./one_click_chatqna.sh \
  -g HUGGINGFACEHUB_API_TOKEN \
  -z GRAFANA_PASSWORD \
  -k KEYCLOAK_ADMIN_PASSWORD \
  -i NODE_IP \
  -d docbot_xeon

# Optional proxy vars: -p HTTP_PROXY -u HTTPS_PROXY -n NO_PROXY
```

### Deploy Doc Registry Service Separately

```bash
kubectl apply -f deployment/microservices-connector/config/manifests/doc_registry-usvc.yaml -n docbot
kubectl rollout status deployment/doc-registry-usvc -n docbot
```

### Ingest Documentation

```bash
# Ingest a PDF with metadata
curl -X POST http://<NODE_IP>/api/v1/docbot/dataprep \
  -F "files=@./my_api_guide.pdf" \
  -F 'doc_metadata={"category":"API","version":"2.3","doc_title":"API Guide","department":"Engineering"}'

# List ingested documents
curl http://<NODE_IP>/api/v1/doc_registry
```

Refer to [deployment/README.md](deployment/README.md) for full configuration options and multi-node deployment.

---

## Development Setup

```bash
# Clone your fork
git clone https://github.com/simolamine/Enterprise-RAG.git
cd Enterprise-RAG

# Track upstream Intel repo for updates
git remote add upstream https://github.com/intel/Enterprise-RAG.git

# Create a feature branch
git checkout -b feature/my-enhancement

# Python dependencies (per microservice)
pip install -r src/comps/doc_registry/impl/microservice/requirements.txt

# Run the doc_registry service locally
DOC_REGISTRY_ENDPOINT=http://localhost:6200 \
REDIS_URL=redis://localhost:6379 \
uvicorn src.comps.doc_registry.opea_doc_registry_microservice:app --port 6200 --reload
```

Branch naming convention: `feature/<description>`, `fix/<description>`, `docs/<description>`

---

## Repository Structure

```
Enterprise-RAG/
├── docs/
│   ├── docbot_plan.md          # Full 9-phase development plan + K8s reference guide
│   └── prerequisites.md        # Cluster setup guide
├── src/
│   └── comps/
│       ├── cores/proto/
│       │   └── docarray.py     # Data models (DocMetadata, SourceDoc added)
│       ├── dataprep/           # Document chunking + metadata propagation
│       ├── ingestion/          # Embedding storage + doc_registry notification
│       ├── doc_registry/       # NEW: document catalog microservice
│       ├── retrievers/         # Vector similarity search (metadata filters — Phase 3)
│       ├── reranks/            # Reranker + source attribution (Phase 3)
│       ├── llms/               # LLM inference + prompt engineering (Phase 4)
│       └── guardrails/         # Input/output safety scanners (Phase 7)
├── deployment/
│   ├── microservices-connector/
│   │   ├── config/samples/
│   │   │   └── docbot_xeon.yaml        # GMConnector CRD for docbot pipeline
│   │   ├── config/manifests/
│   │   │   └── doc_registry-usvc.yaml  # K8s ConfigMap + Service + Deployment
│   │   └── helm/envs/
│   │       └── docbot.env              # All docbot environment variables
│   ├── configs/
│   │   └── docbot-namespace.yaml       # K8s Namespace (docbot)
│   └── auth/apis-crd-helm/
│       └── values.yaml                 # APISIX routes (docbot + doc_registry)
└── src/ui/                             # React 18 + TypeScript frontend (Phase 6)
```

---

## Support

Submit questions, feature requests, and bug reports on the [GitHub Issues page](https://github.com/simolamine/Enterprise-RAG/issues).

For upstream Enterprise-RAG issues, use the [Intel upstream repository](https://github.com/intel/Enterprise-RAG/issues).

---

## License

This project is licensed under [Apache License Version 2.0](LICENSE). Refer to the "[LICENSE](LICENSE)" file for the full license text and copyright notice.

This distribution includes third party software governed by separate license terms as set forth in the "[THIRD-PARTY-PROGRAMS](THIRD-PARTY-PROGRAMS)" file.

---

## Security

[Security Policy](SECURITY.md) outlines guidelines and procedures for responsible disclosure and secure use of this software.

---

## Upstream Attribution

DocBot is built on top of **Intel® AI for Enterprise RAG**, which is built on the [OPEA (Open Platform for Enterprise AI)](https://opea.dev/) framework.

<div align="left">
    <a href="https://opea.dev/" target="_blank">
        <img src="./images/logo.png" alt="Powered by Open Platform for Enterprise AI" height=100 width=280>
    </a>
</div>

Intel, the Intel logo, Gaudi, and Xeon are trademarks of Intel Corporation or its subsidiaries.

\* Other names and brands may be claimed as the property of others.

(C) Intel Corporation
