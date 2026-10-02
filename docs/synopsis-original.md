> # SUPERSEDED - ARCHIVED REFERENCE ONLY
>
> **This is the original academic synopsis. It is NOT the implementation
> specification and carries no authority.**
>
> The specification is `PRD.md` + `ARCHITECTURE.md` + `AGENTS.md` +
> `DESIGN_SYSTEM.md` + `ROADMAP.md`. Where this document disagrees with them,
> they win.
>
> It is kept because it is the registered project submission and the record of
> original intent. It is retained verbatim below - nothing has been edited.
>
> **Known contradictions with the specification**, so they are not mistaken for
> current scope:
>
> | This document says | The specification says |
> |---|---|
> | Kubernetes in the stack | Kubernetes is out of scope (`PRD.md` 11, ADR 0003) |
> | MongoDB alongside Postgres and Redis | One database: Postgres + pgvector (`ARCHITECTURE.md` 2.2) |
> | PyTorch, TensorFlow, Scikit-learn | No DL framework in the control plane; anomaly detection is statistical |
> | Grafana | Prometheus as a query engine only; the console is the dashboard |
> | LangChain / CrewAI alongside LangGraph | LangGraph alone |
> | Multi-cloud (AWS/Azure/GCP), Vercel/Render/Netlify | Out of scope |
> | Predictive failure forecasting, RL for healing | Out of scope |
> | "~all types of AI systems", nine layers | One docker-compose target, eight fault classes, seven injectable |
> | "Should this action be executed automatically? Yes/No" | Never a `noul` question - a two-option `choice` (`PRD.md` 7.1) |
>
> **Agents: do not load this file alongside the specification.** Both in context
> means the two get averaged. See `ROADMAP.md` section "Working with Claude Code".

---
# Vishwakarma Institute of Technology 
**FF180**


## Title: Project Registration & Progress Review

| Field | Details |
|---|---|
| **Department** | CSE-AI (E) |
| **Academic Year** | 2026-2027 |
| **Semester** | 5th |
| **Group No.** | 14 |
| **Project Title** | Autonomous Self-Healing AI Operations Platform |
| **Project Area** | Artificial Intelligence, MLOps and Cloud Infrastructure Automation |

---

### Group Members Details

| Sr. No. | Class & Div. | Roll No. | G.R. No. | Name of Student | Contact No. | Email ID |
|:---:|:---:|:---:|:---:|---|:---:|---|
| 1 | E | 58 | 12412806 | Shadab Hussain | 7248916781 | hussain.shadab24@vit.edu |
| 2 | E | 59 | 12413301 | Shaikh Ahmed Ali | 7558255165 | ahmed.shaikh24@vit.edu |
| 3 | E | 60 | 12414029 | Shaikh Hunain | 9156699791 | shaikh.hunainshaikhzaheerabbas24@vit.edu |
| 4 | E | 62 | 12413457 | Swaraj Shedge | 8652104287 | swaraj.shedge24@vit.edu |

---

### Guide Details

- **Name of Internal Guide:** Prof. Rajendra Pawar
- **Contact No:** 9689890844
- **Email ID:** [rajendra.pawar@vit.edu](mailto:rajendra.pawar@vit.edu)

---

### Approval Status

**Project approved / Not approved**

| Guide | Project Coordinator | Head of Department |
|:---:|:---:|:---:|
| &nbsp;<br>&nbsp; | &nbsp;<br>&nbsp; | &nbsp;<br>&nbsp; |

---

# Project Synopsis

## Introduction
Modern organizations increasingly rely on Large Language Models (LLMs), AI agents, Retrieval-Augmented Generation (RAG) systems, and machine learning pipelines to power business-critical applications. However, these AI systems are prone to failures such as API outages, hallucinations, increased latency, model drift, prompt failures, infrastructure issues, and unexpected workflow interruptions. Existing monitoring tools primarily generate alerts, requiring engineers to manually investigate, diagnose, and resolve incidents, resulting in increased downtime and operational costs. The proposed **Autonomous Self-Healing AI Operations Platform** aims to address this challenge by combining AI observability, automated evaluation, intelligent root cause analysis, and self-healing mechanisms into a unified platform. The system continuously monitors AI services, evaluates their performance, predicts potential failures, executes automated recovery actions, verifies system health after recovery, and learns from previous incidents to improve future decision-making.

## Problem Statement
Modern AI applications operate across distributed cloud environments involving multiple LLM providers, vector databases, APIs, microservices, and containerized workloads. Failures within these components often propagate across the system, making manual diagnosis slow and error-prone. Current observability platforms provide monitoring dashboards and alerts but lack autonomous decision-making capabilities. They cannot automatically determine the root cause of failures, perform recovery actions, or validate whether the system has successfully recovered. Therefore, there is a need for an intelligent AI Operations platform capable of continuously monitoring AI applications, evaluating system quality, diagnosing failures, executing autonomous recovery actions, and verifying system health without requiring continuous human intervention.

## Objectives
* To continuously monitor AI applications, infrastructure, APIs, and deployed models in real time.
* To evaluate AI responses using automated quality metrics such as latency, accuracy, hallucination rate, & reliability.
* To detect anomalies, infrastructure failures, model degradation, and abnormal system behavior.
* To perform AI-assisted root cause analysis using logs, metrics, traces, and historical incidents.
* To automatically execute self-healing strategies including retry, restart, rollback, model switching, cache refresh, & service scaling.
* To verify system stability after every recovery through automated evaluation tests.
* To maintain a centralized incident knowledge base to continuously improve future diagnosis and recovery accuracy.
* To provide a real-time dashboard for monitoring system health, recovery history, and operational insights.
* TO make it self improving system

## Methodology / Working Principle
The proposed platform consists of seven intelligent layers that work together to ensure autonomous AI operations:

1. **Monitoring Layer:** Continuously collects logs, traces, metrics, application events, API responses, infrastructure statistics, and AI inference data using Prometheus and OpenTelemetry.
2. **AI Evaluation Engine:** Automatically evaluates AI responses using predefined benchmark datasets and quality metrics including latency, response accuracy, hallucination rate, groundedness, token consumption, and response consistency.
3. **Failure Detection Layer:** Uses machine learning models and anomaly detection techniques to identify infrastructure failures, API errors, abnormal latency, model degradation, prompt failures, and unusual system behavior.
4. **Root Cause Analysis Engine:** Utilizes LLMs together with historical incident data, logs, traces, and dependency graphs to identify the underlying cause of detected failures and recommend appropriate recovery strategies.
5. **Autonomous Self-Healing Engine:** Executes recovery actions such as: Restart failed services, Retry failed requests, Roll back faulty prompt versions, Switch to backup AI models, Scale cloud resources, Refresh cache, Restart containers based on the diagnosed root cause.
6. **Verification Layer:** Automatically validates whether the recovery action successfully restored system health by executing evaluation tests and monitoring performance metrics.
7. **Learning Layer:** Stores incident history, recovery actions, and verification results in a knowledge base to improve future failure detection, diagnosis, and recovery decisions through continuous learning.

1. Project Onboarding
2. Monitoring & Observability
3. AI Evaluation
4. Failure Detection
5. RCA & Investigation
6. Decision & Safety
7. Self-Healing
8. Verification
9. Learning & Memory

## Tools and Technologies
- **Frontend:** React, Next.js, Tailwind CSS, Chart.js / Recharts
- **Backend:** FastAPI (Python)
- **AI:** LangGraph, LangChain / CrewAI, OpenAI-compatible LLM
- **ML:** PyTorch, TensorFlow, Scikit-learn
- **Database:** PostgreSQL, MongoDB, Redis
- **Monitoring:** Prometheus, Grafana, OpenTelemetry
- **DevOps:** Docker, Kubernetes, Git, GitHub
- Context7  ,  Laya AI system decsion model
- FastAPI now has built-in OpenTelemetry support 
--- we can add or remove  Tools and Technologies according to needs


## Expected Outcome / Result
* Autonomous monitoring of AI applications with real-time observability.
* Faster failure detection and significantly reduced Mean Time To Detect (MTTD).
* Reduced Mean Time To Recovery (MTTR) through automated self-healing.
* Improved reliability and availability of AI services.
* Automated AI evaluation to ensure response quality after recovery.
* Reduced operational costs by minimizing manual intervention.
* Centralized incident history and recovery analytics for continuous optimization.
* A scalable AI Operations platform suitable for enterprise AI deployments.
* Should be able to 

## Limitations
* The accuracy of root cause analysis depends on the quality and completeness of the monitoring data available.
* Novel or previously unseen failure types may still require human oversight before full automation is possible.

## Applications
* AI-powered SaaS platforms
* Enterprise AI Operations (AIOps)
* LLM-based customer support systems
* MLOps pipelines
* Retrieval-Augmented Generation (RAG) systems
* AI agent orchestration platforms
* Cloud-native microservices
* DevOps automation
* Financial AI systems
* Healthcare AI platforms
* ~all types of AI systems



## Future Scope
--- first we will make it everything locally 
* Integration with multiple cloud providers such as AWS, Azure, and Google Cloud.
* Predictive failure analysis using time-series forecasting models.
* Reinforcement learning for adaptive self-healing strategies.
* Multi-agent collaboration for distributed incident management.
* Support for edge AI and IoT deployments.
* Integration with CI/CD pipelines for automated deployment validation.
* Explainable AI (XAI) for transparent root cause analysis and recovery decisions.

## Conclusion
The Autonomous Self-Healing AI Operations Platform demonstrates that AI systems can be monitored, diagnosed, and recovered with minimal human intervention through a layered architecture of monitoring, detection, diagnosis, healing, verification, and learning. While the platform offers a scalable path towards reliable, low-downtime AI operations, further validation under real-world production conditions remains necessary before large-scale deployment.


## More Stuff By Arsal

- I think if the AI system that we are monitoring has not initialize git  it should tell the user to do it also i think the our self healing platform should has another git branch 
- Also The Self-Healing Platform  Dashboard has to show what is happening like status of the monitering project 
- Project onboarding and preflight validation:
The system shall verify Git initialization, repository accessibility, runtime availability, telemetry connectivity, required permissions, health endpoints, and supported recovery actions before enabling self-healing.
- To continuously improve failure diagnosis and recovery decisions using verified incident history, repair outcomes, and similarity-based incident retrieval.
- Add an Unknown Failure mode
Unknown Failure
      ↓
Collect Evidence
      ↓
Generate Hypotheses
      ↓
Test Candidate Repairs
      ↓
Risk Assessment
      ↓
Sandbox
      ↓
Canary / Human Approval
      ↓
Verification
      ↓
Store Experience

- Add audit history 
Every autonomous action should be recorded.
INC-104

AI Diagnosis:
Vector DB configuration regression

Proposed Action:
Rollback configuration

Risk:
MEDIUM

Approved:
Safety Engine

Executed:
10:42:34

Verification:
PASSED

Result:
RESOLVED

- 12. Add a Human Approval mode
Use three operating modes:
SIMULATION
    ↓
No real changes

APPROVAL
    ↓
AI proposes → human approves

AUTONOMOUS
    ↓
Only low-risk actions execute automatically


- Our first thing is first project for local then we wil go for deployment

- also about Laya AI if we need we can finetune that 
                 AI / LLM
                    │
                    ▼
             Investigation
                    │
                    ▼
                  RCA
                    │
                    ▼
           Candidate Repairs
                    │
                    ▼
             ┌─────────────┐
             │ LAYA        │
             │ Decision    │
             │ Engine      │
             └──────┬──────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
        AUTO     SANDBOX    HUMAN
        LOW       MEDIUM     HIGH
        RISK       RISK      RISK
          │         │         │
          ▼         ▼         ▼
       Execute    Test      Approve

       Question 1:
Which repair should be selected?

Options:
- restart
- rollback
- scale

Question 2:
What is the risk?

Options:
- low
- medium
- high

Question 3:
Should this action be executed automatically?

Yes / No



# Refrences

| Project | Link | Relevance |
|---|---|---|
| 
| Context7 | https://context7.com/docs/api-guide | Current documentation source for code/config repair. |
| Vercel REST API | https://vercel.com/docs/rest-api | Reference for Vercel project, deployment, environment variable, and API integration. |
| Vercel Deployments | https://vercel.com/docs/deployments/overview | Reference for Git, CLI, deploy hook, and REST API deployment workflows. |
| Render API | https://render.com/docs/api | Reference for Render services, deploys, logs, metrics, projects, environments, and API integration. |
| Render Deploys | https://render.com/docs/deploys | Reference for Render deploy hooks, redeploys, and deploy triggering. |
| Netlify API | https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/ | Reference for Netlify sites, deploys, and API integration. |
| Netlify Environment Variables | https://docs.netlify.com/build/environment-variables/get-started/ | Reference for Netlify environment variable management through UI, CLI, and API. |
| Kubernaut | https://github.com/jordigilh/kubernaut | Close reference for Kubernetes alert-to-remediation flow. |
| aiops-agent | https://github.com/JoelJosy/aiops-agent | Reference for chaos injection, LangGraph RCA, and evaluation. |
| SelfHealOps | https://github.com/amitdevx/Self-HealOps | Reference for LangGraph multi-agent DevOps remediation. |
| HolmesGPT | https://github.com/robusta-dev/holmesgpt | Reference for AI SRE investigation and Kubernetes diagnostics. |
| K8sGPT | https://github.com/k8sgpt-ai/k8sgpt | Reference for explainable Kubernetes issue analysis. |
| Langfuse | https://github.com/langfuse/langfuse | Reference for LLM tracing, prompt tracking, cost, and evals. |
| Arize Phoenix | https://github.com/Arize-ai/phoenix | Reference for LLM/RAG observability and evaluation. |
| OpenLLMetry | https://github.com/traceloop/openllmetry | Reference for OpenTelemetry instrumentation for LLMs and vector DBs. |
| RCAEval | https://github.com/phamquiluan/RCAEval | Reference for RCA benchmarking. |
| OpenRCA | https://github.com/microsoft/OpenRCA | Reference for LLM RCA evaluation. |