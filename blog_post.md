# OmniSRE: Closed-Loop AI Observability and Autonomous Self-Healing

![OmniSRE Banner](./assets/title.png)

**Track 01: AI & Agent Observability | Agents of SigNoz Hackathon**

**Watch the 3-Minute Live Demo on YouTube:** [Click Here to Watch](https://youtube.com/your-video-link-here) 

OmniSRE is a deterministic, autonomous Site Reliability Engineering agent that utilizes self-hosted SigNoz traces via OpenTelemetry, dynamically injects ClickHouse logs from backend APIs, and executes zero-downtime container recovery through docker host socket binding with Telegram HITL authorization, powered by Gemini (`gemini-1.5-flash`) root-cause analysis of production incidents.

---

## Executive Summary

Modern microservices suffer from alert fatigue and human-induced delay in case of severe incidents. Observability dashboards only notify the engineers about the failure state; it is then up to humans to determine the root-cause and perform the required maintenance to the infrastructure.

OmniSRE eliminates the need for human intervention during incident response while providing end-to-end observability. By running separately from SigNoz and the application itself as isolated services, OmniSRE is able to consume OTLP metrics and traces, reason about the root-cause of the incident using LLM and materialize the necessary configuration changes and container lifecycle hooks directly in ClickHouse logs under human supervision.

---

## System Architecture & Component Mapping

The system relies on a multi-container network topology where telemetry flows upstream into SigNoz storage, while remediation actions flow downstream via host-level socket bindings.

![Architecture Blueprint](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/c71hs0s06t6bvqgnwdof.png)

### Component Responsibility Matrix

| Component Name | Service / Image | Responsibilities & Boundary Protocols |
| :--- | :--- | :--- |
| **`buggy_service`** | FastAPI / Python 3.12 | Monitored target application. Emits OTLP HTTP traces to SigNoz over gRPC/HTTP (`4317`/`4318`). Includes endpoints for normal checkout transactions and chaos injection. |
| **SigNoz Stack** | OTel Collector / ClickHouse / Query Engine | Ingests telemetry, indexes spans in ClickHouse, computes rolling metric aggregations, renders dashboard visuals, and dispatches webhook alerts on threshold breaches. |
| **`omnisre_agent`** | FastAPI / Python 3.12 | Autonomous SRE agent runtime (`port 8001`). Processes incoming webhooks, queries SigNoz backend APIs, invokes Google Gemini via LiteLLM, polls Telegram for authorization, and triggers container healing. |
| **Telegram Guardrail** | Telegram Bot API | External Human-in-the-Loop authorization gate. Displays formatted diagnostic cards and polls user feedback before authorizing infrastructure mutation. |
| **Docker Socket** | `/var/run/docker.sock` | Host daemon interface mounted into `omnisre_agent` authorizing programmatic container restarts and health checks. |

---

## Deep-Dive API Contract Specifications

### 1. Target Application Endpoints (`buggy_service:8000`)

#### `GET /checkout`
* **Description:** Simulates transactional backend operations.
* **Normal Mode:** Returns `200 OK` with latency between `10ms` and `50ms`.
* **Chaos Mode:** Triggers simulated database pool exhaustion resulting in a `70%` error rate (`500 Internal Server Error`) and elevated latency (`1000ms`–`3000ms`).
* **OpenTelemetry Behavior:** Injects explicit span status tags (`StatusCode.ERROR`) and status attributes on failure.

#### `POST /chaos/inject`
* **Description:** Toggles global service state to `chaos_mode_enabled = True`.
* **Response Body:**
```json
{
  "status": "chaos_injected",
  "message": "Chaos mode is now active."
}
```

#### `POST /chaos/revert`
* **Description:** Resets global service state to nominal baseline.
* **Response Body:**
```json
{
  "status": "chaos_reverted",
  "message": "Chaos mode is now inactive."
}
```

### 2. SRE Agent Endpoints (`omnisre_agent:8001`)

#### `POST /webhook/signoz`
* **Description:** Receives firing alert payloads from SigNoz Alert Manager.
* **Input Payload (Flexible Schema):**
```json
{
  "status": "firing",
  "alert_name": "High Checkout Latency",
  "description": "P99 duration exceeded threshold on /checkout"
}
```
* **Response:** Immediate `200 OK` acknowledgment (`{"message": "Alert received and investigation started"}`) while offloading analysis to background worker threads.

---

## SigNoz Dashboard Query Specifications

The primary SigNoz control room utilizes four distinct ClickHouse and OTLP metric queries to visualize operational state transitions during an incident lifecycle:

![SigNoz Dashboard View](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/i51xafg5856q6fr7aqmm.png)

#### Panel 1: Live HTTP 500 Outage Spike
* **Query Type:** ClickHouse Log / Trace Rate
* **Purpose:** Measures error frequency across the target application.
* **Metric Expression:**
```sql
SELECT count() 
FROM signoz_traces.main_spans 
WHERE serviceName = 'buggy_service' 
  AND stringTagMap['http.status_code'] = '500' 
  AND timestamp >= NOW() - INTERVAL 5 MINUTE
```

#### Panel 2: P99 Latency Duration
* **Query Type:** Distribution Quantile
* **Purpose:** Tracks tail latency spikes caused by resource contention.
* **Metric Expression:**
```sql
SELECT quantile(0.99)(durationNano) / 1000000 AS p99_ms 
FROM signoz_traces.main_spans 
WHERE serviceName = 'buggy_service' 
  AND name = 'GET /checkout'
```

#### Panel 3: Live Traffic Health Ratio
* **Query Type:** Aggregate Pie / Donut
* **Purpose:** Visualizes proportional distribution of HTTP 200 vs HTTP 500 status codes across active connections.

#### Panel 4: Live Successful Requests (200 OK Recovery Curve)
* **Query Type:** Time-Series Rate
* **Purpose:** Validates throughput recovery following self-healing execution.

---

## Core Capabilities & Fail-Safe Mechanisms

The agent modifies configuration files, restarts the `buggy_service`, checks the status of the container, and posts a post-mortem performance card with reduced latency to 840 ms and MTTR under 40 seconds. 

* **Deterministic Tracing:** Programmatic tagging of active OpenTelemetry spans ensures that anomalies are annotated in ClickHouse with full exception context.
* **Dynamic Log Extraction:** Querying the SigNoz `/api/v1/query_range` API endpoint automates the extraction of relevant error events within a sliding 15-minute window after a webhook trigger.
* **Generative AI Inference:** The `gemini-1.5-flash` model, proxied through LiteLLM, parses unstructured log lines and traces into JSON execution hypotheses.
* **Human-in-the-Loop Guardrails:** A Telegram bot confirms the root cause analysis with a timestamped manual approval before any infrastructure changes are committed.
* **Zero-Downtime Healing:** Mutating `.env` files and restarting the container via native Docker socket bindings performs the platform healing without service disruption.

---

## Security, Isolation, and Hardening

* **Least-Privilege Container Scope:** The application container (`buggy_service`) runs in complete isolation without access to host infrastructure or Docker sockets.
* **Docker Socket Binding Isolation:** Only the `omnisre_agent` container maintains read/write permissions to `/var/run/docker.sock`.
* **Environment Variable Redaction:** Secret credentials (`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`) are injected exclusively via environment configuration files and excluded from repository version control via `.gitignore`.
* **Timestamp-Filtered Polling:** The Telegram approval engine filters incoming user confirmation messages against alert dispatch timestamps (`msg_date >= start_time - 5`), preventing legacy messages from executing unintended container restarts.

---

## Prerequisites

To deploy and test OmniSRE locally, ensure the following tools are installed on your host system:
* Docker & Docker Compose (Daemon must be active)
* Foundry CLI (For reproducible SigNoz deployment)
* Python 3.12+
* Telegram Bot Token (Generated via `@BotFather`)
* Google Gemini API Key (Generated via Google AI Studio)

---

## Installation and Deployment

### 1. Clone the Repository
```bash
git clone https://github.com/rahulchandra2004/omnisre-signoz-hackathon.git
cd omnisre-signoz-hackathon
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```bash
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id"
GEMINI_API_KEY="your_gemini_api_key"
DB_POOL_SIZE=10
```

### 3. Deploy the Infrastructure Stack (Foundry)
Deploy the entire infrastructure stack using SigNoz Foundry specifications:
```bash
foundryctl cast -f casting.yaml
```
**Alternative Deployment:** If Foundry CLI is not installed, trigger the stack via Docker Compose:
```bash
docker-compose -f config/docker-compose.yml up --build -d
```

---

## Step-by-Step Demonstration Lifecycle

### Step 1: Generate Baseline Traffic
Execute the PowerShell traffic generator to simulate consistent baseline consumer requests:
```bash
cd scripts
.\generate_traffic.ps1
```

### Step 2: Inject Chaos
Trigger simulated connection pool exhaustion on the backend service:
```bash
curl -X POST http://localhost:8000/chaos/inject
```

### Step 3: Observe Metric Anomalies
Navigate to `http://localhost:3301` to view SigNoz Dashboard alerts. Observe latency spiking to 3,420 ms and error rates rising above 40%.

![Live Anomaly Outage Spike](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/7ggx0gj1yhipc9se3y8h.png)

### Step 4: Autonomous Diagnosis & Telegram Approval
The SRE agent queries ClickHouse logs, passes context to Google Gemini, and dispatches an interactive card to Telegram:

![Telegram Diagnosis Approval](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/xew23r8qr7metoon4zji.png)

* **User Action:** Reply `YES` in Telegram to authorize the remediation plan (Scale `DB_POOL_SIZE` to 50 and restart container).

### Step 5: Verification of Recovery
The agent tunes configuration files, restarts `buggy_service`, verifies container health, and posts a post-mortem performance card confirming latency reduction to 840 ms and MTTR resolution in under 40 seconds.

![Telegram Remediation Proof](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/491u6vkvvtr9u822a07x.png)

---

## Telemetry and Verification

OmniSRE prioritizes granular telemetry verification. By using OpenTelemetry SDKs natively, individual spans across the `/checkout` endpoint are recorded inside ClickHouse for auditability.

![OpenTelemetry Granular Traces](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/2g4nijcv6x9rkvoflfrt.png)

```python
# Instrumentation snippet inside buggy_service.py
@app.get("/checkout")
def checkout():
    global chaos_mode_enabled
    if chaos_mode_enabled:
        current_span = trace.get_current_span()
        if current_span.is_recording():
            current_span.set_status(StatusCode.ERROR, "Chaos mode active: Simulated 500 Outage")
            current_span.set_attribute("http.status_code", 500)
            current_span.set_attribute("http.response.status_code", 500)
            
        raise HTTPException(status_code=500, detail="Internal Server Error during checkout.")
```

---

## Troubleshooting & Diagnostic Playbook

| Issue / Symptom | Root Cause | Resolution Procedure |
| :--- | :--- | :--- |
| **Agent fails to fetch real SigNoz logs** | Network interface resolution failure across container bridge. | The agent automatically cycles through fallback URLs (`localhost:3301`, `host.docker.internal:3301`, `signoz-frontend:3301`). Ensure port 3301 is exposed in `docker-compose.yml`. |
| **Telegram approval auto-triggers** | Polling engine reading stale historical `YES` messages. | Verify that `notifier.py` includes timestamp filtering (`msg_date >= start_time - 5`) prior to parsing message strings. |
| **Docker restart command fails** | Docker host socket not mounted correctly into agent container. | Verify volume mapping in `docker-compose.yml`: `/var/run/docker.sock:/var/run/docker.sock`. |
| **Post-recovery metrics show lingering errors** | Time-series rolling aggregation window buffer. | The agent implements a 15-second stabilization cooldown before executing post-recovery health metrics extraction. |

---

## Future Scope and Roadmap

* **Kubernetes Operator Native Architecture:** Moving from Docker socket binding to Kubernetes controllers for managing custom resources definitions (CRDs) and `kubectl scale` operations as the new default.
* **Multi-Agent Collaboration:** Distributing tasks between different Language Model agents that specialize in certain areas, such as Query Optimization and Network Routing.
* **Automated Rollback Engine:** Augmenting current state verification loops to also perform rollback of `.env` changes during healing if post healing performance metrics don't pass.
* **Enterprise Alerting Integration:** Adding PagerDuty, Slack Enterprise Grid and Opsgenie webhook support.

---

## AI Usage Disclosure

In the development and runtimes of this agent model, the following AI tools were used, in accordance with hackathon transparency rules:

* **Development:** Gemini and GitHub Copilot were used to refactor code, test regular expressions, and design documentation layouts.
* **Runtime SRE Engine:** `gemini-1.5-flash` is natively available in the agent runtime via LiteLLM - used for log triage, hypothesis generation, and root-cause analysis during production incident response.

---
**Built by Rahul Chandra Padamuttam for the Agents of SigNoz Hackathon.**
