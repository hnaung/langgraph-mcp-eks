# Documentation Index

This folder contains all project documentation — from audience-facing architecture proposals to hands-on development guides.

---

## For Audiences & Stakeholders

| Document | Audience | Description |
|---|---|---|
| [AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md](AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md) | Executives, security reviewers, architects | Full security architecture proposal — purpose, threat model, controls, trade-offs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Engineers, architects | Technical system design and request lifecycle |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Platform / SRE teams | EKS deployment steps and production checklist |

## For Developers

| Document | Audience | Description |
|---|---|---|
| [CURSOR_DEVELOPMENT.md](CURSOR_DEVELOPMENT.md) | Application developers | Using Cursor IDE + MCP to build and test tools locally |
| [../README.md](../README.md) | All developers | Project overview, quick start, and repo structure |

## Source Documents

| Location | Description |
|---|---|
| [source/](source/) | Original Word/PDF source files (e.g. architecture proposal `.docx`) |

---

## Reading Guide by Role

**If you are a decision-maker or security reviewer**, start with the [Security Architecture Proposal](AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md) — it explains *why* this platform is designed the way it is and what risks it addresses.

**If you are an engineer joining the project**, start with the [README](../README.md), then [Architecture](ARCHITECTURE.md), then [Cursor Development](CURSOR_DEVELOPMENT.md) for local setup.

**If you are deploying to production**, read the [Deployment Guide](DEPLOYMENT.md) alongside the security proposal's production checklist.
