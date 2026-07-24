---
cover_image: https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/title.png
---

# How I Built an Autonomous AI SRE Agent with SigNoz (and the Telegram Kill Switch That Keeps It Safe)

![OmniSRE Banner](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/title.png)

**Track 01: AI & Agent Observability | WeMakeDevs x Agents of SigNoz Hackathon**


---

It was late at night, and I was watching my terminal with a mixture of excitement and genuine dread.

I had just injected simulated database chaos into my own service and handed an AI agent full, unchecked access to my Docker socket. The agent had 2 minutes to read the SigNoz traces, call Google Gemini, diagnose the root cause, and send an approval request to my Telegram before I would call it a failure.

No human was going to fix this. Either the agent worked, or the container stayed broken.

That's when I understood the real problem with modern observability. SigNoz was already showing me everything: P99 latency spiking to 3,420ms, HTTP 500 errors flooding in above 40%. The dashboard was perfect. But a dashboard can only tell you what is on fire. It cannot put the fire out.

> **If Large Language Models are smart enough to write code, shouldn't they be smart enough to read telemetry, find the root cause, and restart the container themselves?**

I built **OmniSRE** to answer exactly that question. But the moment I gave my AI agent the keys to my Docker socket, I realized that an autonomous agent with unchecked infrastructure access is genuinely terrifying. One bad LLM response, one stale approval message—and it starts restarting production containers on its own.

I needed a kill switch. So I built one into Telegram.

In this post, I'll walk you through the exact code—from deploying a self-hosted SigNoz stack, to wiring OpenTelemetry traces into a Gemini-powered root-cause engine, to the timestamp-guarded Telegram gate that keeps the whole system from going rogue.

{% youtube GMaUc4ksh6A %}
*(Alternatively, [Click Here to Watch the 3-Minute Live Demo](https://youtu.be/GMaUc4ksh6A))*

---

> **By the end of this post, you will have:**
> - A self-hosted SigNoz observability stack running in 2 minutes
> - A FastAPI service emitting real OTLP traces to ClickHouse
> - An autonomous Gemini-powered SRE agent that diagnoses incidents
> - A Telegram bot that acts as your production kill switch
> - A system that achieves < 40 second MTTR with zero human wake-ups

---

## The Problem in One Sentence

Modern observability tells you **what** broke. OmniSRE tells the AI **why** it broke, then fixes it—with your approval.

| Phase | Traditional On-Call | OmniSRE |
| :--- | :--- | :--- |
| **Detection** | SigNoz Alert fires | SigNoz Alert fires |
| **Diagnosis** | Engineer wakes up, reads logs | Gemini reads ClickHouse logs autonomously |
| **Authorization** | Engineer decides | Telegram HITL gate — YOU decide |
| **Remediation** | SSH + manual restart | Docker socket heal in < 40 seconds |
| **MTTR** | 15–45 minutes | **Under 40 seconds** |

---

## 1. Deploying the Observability Stack with Foundry

I wanted a completely reproducible observability environment. Instead of manually wiring up ClickHouse and the OpenTelemetry Collector, I used **SigNoz Foundry CLI** to spin up the entire self-hosted stack in under 2 minutes.

> **Why self-hosted SigNoz over a managed cloud tool?** Two reasons: full ClickHouse query access (critical for the agent to pull raw logs programmatically), and zero data egress costs. The agent's entire log-extraction pipeline depends on direct `/api/v1/query_range` access—which you only get with self-hosted.

First, define the deployment manifest:

```yaml
# casting.yaml - SigNoz Foundry Deployment Specification
apiVersion: v1alpha1
kind: Installation
metadata:
  name: signoz
spec:
  deployment:
    mode: docker
    flavor: compose
  mcp:
    spec:
      enabled: true
```

Then deploy the entire stack with a single command:

```bash
# Install Foundry and cast the infrastructure stack
curl -fsSL https://signoz.io/foundry.sh | bash
export PATH="$HOME/.local/bin:$PATH"

foundryctl cast -f casting.yaml
```

Within moments, six isolated core containers are live:
- **Port 3301** — SigNoz UI & Query Engine
- **Port 4317/4318** — OTLP gRPC/HTTP ingestion endpoints

---

## 2. The Architecture: Every Container Has One Job

OmniSRE relies on a strict multi-container isolation model. Telemetry flows **upstream** into SigNoz. Remediation commands flow **downstream** via host-level socket bindings. The SRE Agent is completely decoupled from the application it monitors.

![Architecture Blueprint](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/The%20Blueprint.png)

> **Key Design Principle:** If `buggy_service` crashes and burns, `omnisre_agent` stays alive to fix it. They share zero runtime dependencies.

Here is the critical `docker-compose.yml` section showing the socket mount:

```yaml
# config/docker-compose.yml
version: '3.8'

services:
  buggy_service:
    build:
      context: ..
      dockerfile: docker/Dockerfile.buggy
    container_name: buggy_service
    ports:
      - "8000:8000"
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318
      - DB_POOL_SIZE=10

  omnisre_agent:
    build:
      context: ..
      dockerfile: docker/Dockerfile.agent
    container_name: omnisre_agent
    ports:
      - "8001:8001"
    volumes:
      # This single line gives the agent surgical control over host containers
      - /var/run/docker.sock:/var/run/docker.sock
      - ../.env:/app/.env
    environment:
      - SIGNOZ_ENDPOINT=http://host.docker.internal:3301
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
```

---

## 3. Setting the Trap: Auto-Instrumentation & Chaos Injection

To give the AI real, structured data to reason about, I instrumented the `/checkout` endpoint with OpenTelemetry SDKs and wired up explicit error span tagging. When chaos fires, the spans going into ClickHouse are not generic—they carry precise failure context.

```python
# app/buggy_service.py
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.trace import StatusCode

app = FastAPI(title="Buggy E-Commerce Checkout")
chaos_mode_enabled = False

@app.get("/checkout")
def checkout():
    global chaos_mode_enabled
    if chaos_mode_enabled:
        current_span = trace.get_current_span()
        if current_span.is_recording():
            current_span.set_status(StatusCode.ERROR, "Chaos mode active: Database Pool Exhausted")
            current_span.set_attribute("http.status_code", 500)
            
        raise HTTPException(status_code=500, detail="500 Internal Server Error: Connection pool exhausted.")
    return {"status": "success", "latency_ms": 25}

@app.post("/chaos/inject")
def inject_chaos():
    global chaos_mode_enabled
    chaos_mode_enabled = True
    return {"status": "chaos_injected", "message": "Simulated DB pool failure active."}
```

One `curl -X POST http://localhost:8000/chaos/inject` later, the SigNoz Dashboard lights up:

- P99 latency spikes to **3,420 ms**
- HTTP 500 error rate climbs above **40%**
- SigNoz Alert Manager fires a webhook to `omnisre_agent:8001`

![Live Anomaly Outage Spike](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/The%20Outage%20%26%20Telemetry.png)

Every chaos-mode `/checkout` request is fully indexed as a named error span in ClickHouse, giving the AI structured, auditable evidence to reason against.

![OpenTelemetry Granular Traces](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/Inspecting%20Spans.png)

---

## 4. Wiring Up SigNoz: Alerts, Dashboards, and the Webhook

This is where SigNoz becomes the central nervous system of OmniSRE. After traces start flowing in, I configured four things inside the SigNoz UI:

**Metrics Panels (Query Builder):** Four custom panels on a single dashboard track the incident lifecycle in real time — a P99 latency time-series, an HTTP 500 rate panel using `signoz_calls_total` filtered by `status_code=500`, a pie chart showing the live 200/500 traffic health ratio, and a recovery curve showing 200 OK requests restoring after healing.

**Alert Rule:** I created a threshold alert on P99 latency in the SigNoz Alerts UI. When `p99 > 2000ms` for 2 consecutive minutes, SigNoz fires:

```
Alert Name: High Checkout Latency
Condition:  p99_duration_ms > 2000
For:        2 minutes
Labels:     severity=critical, service=buggy_service
```

**Webhook Channel:** In SigNoz → Settings → Alert Channels, I configured a Webhook notification channel pointing to `http://host.docker.internal:8001/webhook/signoz`. The moment the alert fires, SigNoz POSTs a JSON payload directly to the SRE agent's receiver endpoint — no polling, no cron jobs.

> **This is the key integration point:** SigNoz is not just a dashboard in this system. It is the event source that kicks off the entire autonomous remediation pipeline. Without the alert channel, nothing moves.

---

## 5. The Debugging Nightmare Nobody Talks About: Container Networking

This was the hardest part of the entire build, and I guarantee you will hit this wall too.

Everything worked perfectly in my local Python environment. But the moment I containerized the agent, the observability pipeline went blind. The agent received the webhook, then crashed trying to query ClickHouse logs.

The error log: `Connection Refused: localhost:3301`

> **The Insight:** `localhost` inside a Docker container is the container itself—not your host machine. SigNoz was running fine on `host:3301`, but the agent was knocking on its own door.

To fix this resiliently across any deployment environment, I built an automatic fallback engine:

```python
# agent/investigator.py
import requests

class SigNozInvestigator:
    # Ordered priority matrix for cross-container bridge resolution
    FALLBACK_ENDPOINTS = [
        "http://localhost:3301",
        "http://host.docker.internal:3301",
        "http://signoz-frontend:3301"
    ]

    def fetch_real_signoz_logs(self, query_payload: dict) -> dict:
        for base_url in self.FALLBACK_ENDPOINTS:
            try:
                url = f"{base_url}/api/v1/query_range"
                response = requests.post(url, json=query_payload, timeout=3)
                if response.status_code == 200:
                    return response.json()
            except requests.exceptions.ConnectionError:
                continue
        raise ConnectionError("Failed to reach SigNoz ClickHouse backend across all bridges.")
```

The agent now auto-resolves the correct network bridge every single time. No manual configuration required.

> **SigNoz features used in this project:** Distributed Tracing (Trace Explorer), ClickHouse Log Querying (`/api/v1/query_range`), Custom Metrics Dashboards (Query Builder), Threshold Alert Rules, and Webhook Alert Channels. Every feature worked together as an integrated pipeline, not as isolated tools.

---

## 5. The Gemini Prompt: How the AI Actually Thinks

Here is the exact prompt that is sent to `gemini-1.5-flash` via LiteLLM during a live incident. This is the core "brain" of the entire system:

```python
# agent/investigator.py — the exact prompt sent to Gemini
prompt = f"""
You are an autonomous Site Reliability Engineer (OmniSRE).
An alert has been triggered: {alert_payload}

Context gathered from observability tools:
{context}  # <-- Real ClickHouse log data injected here

Determine the root cause and the required action.
Respond with ONLY raw JSON, with no markdown formatting or backticks.
It must contain:
- "root_cause": string, your hypothesis
- "action": string, either "RESTART_SERVICE", "SCALE_UP", or "NO_ACTION"
- "target_service": string, the name of the service to act on (e.g., "buggy_service")
"""
```

And here is a real example of the structured JSON response Gemini returns:

```json
{
  "root_cause": "The /checkout endpoint is experiencing connection pool exhaustion. ClickHouse logs show a sustained spike of StatusCode.ERROR spans over the last 15 minutes, consistent with DB_POOL_SIZE being undersized for current traffic volume.",
  "action": "RESTART_SERVICE",
  "target_service": "buggy_service"
}
```

> **Why this prompt works:** Forcing a strict JSON schema eliminates ambiguous, prose-based responses entirely. The agent's downstream `healer.py` can then deterministically parse `action` and `target_service` without any fragile string matching.

---

## 6. The Killer Feature: The Telegram Kill Switch

Having an AI that can diagnose a problem is amazing. Having an AI that can **unilaterally modify `.env` files and execute container restarts** is a recipe for a career-ending incident.

> **I needed a "Financial Kill Switch" for my infrastructure. So I built one into Telegram.**

When SigNoz fires the alert, the pipeline executes like this:

```
SigNoz Alert → Webhook → Gemini RCA → Telegram HITL Gate → (YES) → Docker Heal
                                                          ↓
                                                     (NO / Timeout)
                                                          ↓
                                                  Abort. Log. Done.
```

The agent halts completely at the Telegram gate and sends a formatted diagnostic card showing exactly what it found and exactly what it plans to do. You reply `YES` or you walk away.

To prevent the agent from reading **stale `YES` messages** from previous incidents—a real bug I hit during testing that caused phantom auto-restarts—I implemented timestamp-filtered polling:

```python
# agent/notifier.py
import time, requests

def wait_for_human_approval(bot_token: str, chat_id: str, alert_start_time: float) -> bool:
    """Polls Telegram updates and strictly filters against alert trigger timestamp."""
    timeout = 120
    start_poll = time.time()
    
    while time.time() - start_poll < timeout:
        updates = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates").json()
        for result in updates.get("result", []):
            msg = result.get("message", {})
            msg_date = msg.get("date", 0)
            text = msg.get("text", "").strip().upper()
            
            # Only process messages sent AFTER the incident started
            if msg_date >= (alert_start_time - 5) and text == "YES":
                return True
        time.sleep(3)
    return False
```

![Telegram Diagnosis Approval](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/AI%20Reasoning%20%26%20Guardrail.png)

Once authorized, `healer.py` programmatically mutates the `.env` config and restarts the container via the Docker socket:

```python
# agent/healer.py
import docker

def apply_remediation_and_restart(service_name: str, key: str, value: str):
    # Step 1: Mutate the configuration parameter
    with open(".env", "r") as f:
        lines = f.readlines()
    with open(".env", "w") as f:
        for line in lines:
            f.write(f"{key}={value}\n" if line.startswith(f"{key}=") else line)

    # Step 2: Execute the Docker restart via host socket binding
    client = docker.from_env()
    container = client.containers.get(service_name)
    container.restart()
    return True
```

![Telegram Remediation Proof](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/Self-Healing%20%26%20Proof.png)

---

## The Results: Before vs. After

| Metric | During Chaos | After Self-Healing |
| :--- | :--- | :--- |
| **P99 Latency** | 3,420 ms | **840 ms** |
| **HTTP 500 Rate** | > 40% | **0%** |
| **HTTP 200 Rate** | < 60% | **100%** |
| **MTTR** | N/A (no human awake) | **< 40 seconds** |

---

## 3 Things I Learned That Nobody Tells You

**1. Deterministic context is what separates useful AI agents from hallucinating ones.**
By explicitly tagging OpenTelemetry spans with `StatusCode.ERROR` and `http.status_code`, I gave Gemini real, structured facts instead of ambiguous log strings. The quality of the root-cause analysis was night and day.

**2. Always timestamp your HITL guardrails.**
During testing, the agent was auto-restarting my containers the instant it received a new alert. Why? It was polling Telegram and finding the `YES` I had sent 10 minutes earlier for a different incident. A 5-second timestamp offset filter completely solved it.

**3. Observability is the missing link that makes AI agents trustworthy.**
Without SigNoz bridging raw OTLP traces into a queryable ClickHouse backend, the agent would have nothing factual to feed the LLM. Observability infrastructure is not optional for autonomous agents—it is the foundation they run on.

**What I'd do differently:** If I rebuilt this today, I'd replace the Telegram polling loop with SigNoz's own webhook payload as the authorization token, creating a cryptographically verifiable approval chain instead of plain-text `YES` matching. I'd also expose a `/status` endpoint on the agent so SigNoz dashboards can display the current remediation state in real time, closing the visual feedback loop entirely inside the observability platform.

---

## Try It Yourself in 5 Minutes

- [ ] Clone the repo: `git clone https://github.com/rahulchandra2004/omnisre-signoz-hackathon.git`
- [ ] Create `.env` with your Gemini API key and Telegram Bot Token
- [ ] Run `foundryctl cast -f casting.yaml` to spin up SigNoz
- [ ] Run `docker-compose -f config/docker-compose.yml up --build -d`
- [ ] Hit `curl -X POST http://localhost:8000/chaos/inject`
- [ ] Watch your Telegram light up with a live incident diagnosis

---

## Future Scope

* **Kubernetes Operator Native Architecture:** Transitioning from Docker socket bindings to Kubernetes Custom Resource Definitions (CRDs) and `kubectl scale` deployments.
* **Multi-Agent Networks:** Delegating tasks across independent LLMs (e.g., Query Optimization Agent vs. Network Routing Agent).
* **Automated Rollback Engine:** If post-healing metrics fail health checks, automatically revert the `.env` mutation.

---

## AI Usage Disclosure

In compliance with hackathon transparency guidelines, Gemini and GitHub Copilot were used during development for code refactoring and documentation layout. At runtime, `gemini-1.5-flash` is natively integrated via LiteLLM for log triage, hypothesis generation, and root-cause analysis during live incidents.

---

Check out the full source code, clone it, and try injecting chaos yourself:
👉 **[OmniSRE GitHub Repository](https://github.com/rahulchandra2004/omnisre-signoz-hackathon)**

Have you ever built an autonomous remediation system? How do you handle the Human-in-the-Loop problem at scale? Let me know in the comments—I'd love to hear your approach.

*Built by Rahul Chandra Padamuttam for the Agents of SigNoz Hackathon.*

#devops #python #ai #opensource
