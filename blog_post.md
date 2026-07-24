# How I Built an Autonomous AI SRE Agent with SigNoz (and the Telegram Kill Switch That Keeps It Safe)

![OmniSRE Banner](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/title.png)

**Track 01: AI & Agent Observability | WeMakeDevs x Agents of SigNoz Hackathon**

---

It was 3:00 AM, and my hypothetical pager was going off.

If you've ever been on-call for a modern microservice architecture, you know the feeling. A database connection pool gets exhausted, tail latency spikes to 3,000ms, and HTTP 500 errors start raining down. Observability dashboards are great—they tell you exactly what is burning. But they still rely entirely on a bleary-eyed human to wake up, SSH into a server, read the logs, diagnose the root cause, and apply a fix.

I realized something:

> **If Large Language Models are smart enough to write code, shouldn't they be smart enough to read telemetry, find the root cause, and restart the container themselves?**

I built **OmniSRE** for the Agents of SigNoz Hackathon to answer exactly that. But as I gave my AI agent the keys to my Docker socket, I quickly realized that letting an autonomous agent mutate infrastructure is terrifying. I needed a fail-safe.

In this blog, I'll walk you through the exact code—from deploying a self-hosted SigNoz observability stack, to wiring up OpenTelemetry, to building the Telegram "Human-in-the-Loop" kill switch that keeps the whole thing from going rogue.

{% youtube GMaUc4ksh6A %}
*(Alternatively, [Click Here to Watch the 3-Minute Live Demo](https://youtu.be/GMaUc4ksh6A))*

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

![Architecture Blueprint](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/c71hs0s06t6bvqgnwdof.png)

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

![Live Anomaly Outage Spike](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/7ggx0gj1yhipc9se3y8h.png)

---

## 4. The Debugging Nightmare Nobody Talks About: Container Networking

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

---

## 5. The Killer Feature: The Telegram Kill Switch

Here is where OmniSRE goes from impressive to genuinely production-worthy.

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

To prevent the agent from reading **stale `YES` messages** from previous incidents—a bug I hit during testing that caused phantom auto-restarts—I implemented timestamp-filtered polling:

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

![Telegram Diagnosis Approval](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/xew23r8qr7metoon4zji.png)

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

---

## The Results: Before vs. After

![Telegram Remediation Proof](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/491u6vkvvtr9u822a07x.png)

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

---

## Future Scope

* **Kubernetes Native Architecture:** Moving from Docker socket bindings to custom Kubernetes Controllers managing CRDs and `kubectl scale` operations.
* **Multi-Agent Collaboration:** Routing diagnosis tasks to specialized sub-agents (e.g., a Database Optimizer Agent vs. a Network Routing Agent).
* **Automated Rollback Engine:** If post-healing metrics fail health checks, automatically revert the `.env` mutation.

---

## AI Usage Disclosure

In compliance with hackathon transparency guidelines, Gemini and GitHub Copilot were used during development for code refactoring and documentation layout. At runtime, `gemini-1.5-flash` is natively integrated via LiteLLM for log triage, hypothesis generation, and root-cause analysis during live incidents.

---

Check out the full source code, clone it, and try injecting chaos yourself:
👉 **[OmniSRE GitHub Repository](https://github.com/rahulchandra2004/omnisre-signoz-hackathon)**

Have you ever built an autonomous remediation system? How do you handle the Human-in-the-Loop problem at scale? Let me know in the comments—I'd love to hear your approach.

*Built by Rahul Chandra Padamuttam for the Agents of SigNoz Hackathon.*
