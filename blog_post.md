# How I Built an Autonomous AI SRE Agent with SigNoz (and the Telegram Kill Switch That Keeps It Safe)

![OmniSRE Banner](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/title.png)

**Track 01: AI & Agent Observability | WeMakeDevs x Agents of SigNoz Hackathon**

It was 3:00 AM, and my hypothetical pager was going off.

If you’ve ever been on-call for a modern microservice architecture, you know the feeling. A database connection pool gets exhausted, tail latency spikes to 3,000ms, and HTTP 500 errors start raining down. Observability dashboards are great—they tell you exactly what is burning. But they still rely entirely on a bleary-eyed human to wake up, SSH into a server, read the logs, diagnose the root cause, and apply a fix.

I realized something: If Large Language Models are smart enough to write code, shouldn't they be smart enough to read telemetry, find the root cause, and restart the container themselves?

I built OmniSRE for the Agents of SigNoz Hackathon to answer exactly that. But as I gave my AI agent the keys to my Docker socket, I quickly realized that letting an autonomous agent mutate infrastructure is terrifying. I needed a fail-safe.

In this blog, I’ll show you how I deployed self-hosted SigNoz, wired up OpenTelemetry, and built an autonomous SRE agent powered by Google Gemini—along with the exact code and Telegram "Human-in-the-Loop" architecture that keeps it safe.

{% youtube GMaUc4ksh6A %}
*(Alternatively, [Click Here to Watch the 3-Minute Demo](https://youtu.be/GMaUc4ksh6A))*

---

## 1. Deploying the Observability Stack with Foundry

I wanted my entire observability environment to be completely reproducible. Instead of manually setting up ClickHouse and OpenTelemetry Collector instances, I used SigNoz Foundry CLI to spin up the entire self-hosted stack in under 2 minutes.

First, create the deployment configuration file:

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

Then trigger the stack with a single command:

```bash
# Install Foundry and cast the infrastructure stack
curl -fsSL https://signoz.io/foundry.sh | bash
export PATH="$HOME/.local/bin:$PATH"

foundryctl cast -f casting.yaml
```

Within moments, six isolated core containers are live on ports 3301 (SigNoz UI) and 4317/4318 (OTLP gRPC/HTTP ingestion).

---

## 2. System Architecture & Docker Topology

OmniSRE relies on a multi-container network topology where telemetry flows upstream into SigNoz storage, while remediation actions flow downstream via host-level socket bindings.

![Architecture Blueprint](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/c71hs0s06t6bvqgnwdof.png)

To ensure that the SRE Agent (`omnisre_agent`) remains functional even when the target app crashes, it runs as an independent container with direct host daemon access.

Here is the trimmed `docker-compose.yml` snippet showing the socket mount and port mapping:

```yaml
# config/docker-compose.yml
version: '3.8'

services:
  # Monitored Target Application
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

  # Autonomous SRE Agent Runtime
  omnisre_agent:
    build:
      context: ..
      dockerfile: docker/Dockerfile.agent
    container_name: omnisre_agent
    ports:
      - "8001:8001"
    volumes:
      # CRITICAL: Host socket mounted for zero-downtime container healing
      - /var/run/docker.sock:/var/run/docker.sock
      - ../.env:/app/.env
    environment:
      - SIGNOZ_ENDPOINT=http://host.docker.internal:3301
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
```

---

## 3. Auto-Instrumentation & Chaos Injection

To test the AI, I built a `/checkout` endpoint in FastAPI and instrumented it with OpenTelemetry SDKs. When chaos mode is toggled, it injects explicit `StatusCode.ERROR` attributes directly into ClickHouse span tags.

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
            # Inject explicit exception status for SigNoz indexing
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

Triggering chaos causes latency to spike to 3,420 ms and error rates to exceed 40%, instantly firing an alert in SigNoz.

![Live Anomaly Outage Spike](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/7ggx0gj1yhipc9se3y8h.png)

---

## 4. The Network Hurdle: Multi-Bridge Fallback Engine

When containerizing `omnisre_agent`, it received alert webhooks from SigNoz, but failed when trying to pull ClickHouse logs: `Connection Refused: localhost:3301`.

Because `localhost` inside a Docker container points to itself rather than the host, I built a resilient fallback engine inside `investigator.py` to auto-resolve network bridges:

```python
# agent/investigator.py
import requests

class SigNozInvestigator:
    # Priority fallback matrix for cross-container bridge resolution
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

---

## 5. The Killer Feature: Telegram HITL & Docker Healing

Having an AI that can diagnose a problem is amazing. Having an AI that can unilaterally modify production files and execute container restarts is terrifying.

OmniSRE introduces a Human-in-the-Loop (HITL) authorization gate via Telegram. When SigNoz alerts fire, the agent queries ClickHouse logs, sends the trace context to Google Gemini (`gemini-1.5-flash`), formats the diagnosis, and halts execution until human approval is received.

To prevent the bot from reading old `YES` approvals from past incidents, I implemented timestamp-filtered polling:

```python
# agent/notifier.py
import time, requests

def wait_for_human_approval(bot_token: str, chat_id: str, alert_start_time: float) -> bool:
    """Polls Telegram updates and filters messages against alert trigger timestamp."""
    timeout = 120  # 2 minute window
    start_poll = time.time()
    
    while time.time() - start_poll < timeout:
        updates = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates").json()
        for result in updates.get("result", []):
            msg = result.get("message", {})
            msg_date = msg.get("date", 0)
            text = msg.get("text", "").strip().upper()
            
            # STRICT GUARDRAIL: Ignore messages sent before the alert started
            if msg_date >= (alert_start_time - 5) and text == "YES":
                return True
        time.sleep(3)
    return False
```

![Telegram Diagnosis Approval](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/xew23r8qr7metoon4zji.png)

Once the user replies `YES`, the agent invokes `healer.py`, which programmatically updates `.env` configuration files and triggers a container restart directly via `/var/run/docker.sock`:

```python
# agent/healer.py
import docker

def apply_remediation_and_restart(service_name: str, key: str, value: str):
    # 1. Mutate configuration state
    with open(".env", "r") as f:
        lines = f.readlines()
    with open(".env", "w") as f:
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
            else:
                f.write(line)

    # 2. Programmatic Docker Daemon Socket Execution
    client = docker.from_env()
    container = client.containers.get(service_name)
    container.restart()
    return True
```

![Telegram Remediation Proof](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/491u6vkvvtr9u822a07x.png)

Latency drops back to 840 ms, HTTP 200 responses recover, and the Mean Time To Recovery (MTTR) is clocked under 40 seconds.

---

## Key Takeaways

* **Deterministic Context Eliminates Hallucinations:** By programmatically tagging OpenTelemetry spans (`StatusCode.ERROR`), Gemini receives pure, factual trace data, completely avoiding hallucinated root causes.
* **Timestamp Your Human-in-the-Loop Bot:** Always filter approval messages against event start times (`msg_date >= alert_start_time`), or your agent will process stale approval commands!
* **Observability is Essential for AI Agents:** Raw telemetry and open standards like OpenTelemetry are what allow AI agents to move from passive chatbots to active infrastructure software.

---

## Future Scope

* **Kubernetes Operator Native Architecture:** Transitioning from Docker socket bindings to Kubernetes Custom Resource Definitions (CRDs) and `kubectl scale` deployments.
* **Multi-Agent Networks:** Delegating tasks across independent LLMs (e.g., Query Optimization Agent vs. Network Routing Agent).

---

## AI Usage Disclosure

In compliance with hackathon rules, Gemini and GitHub Copilot were used during development to refactor code and format layouts. At runtime, `gemini-1.5-flash` is natively integrated via LiteLLM to perform log analysis and root-cause diagnosis.

---

Check out the full source code and deploy it yourself:  
👉 **[OmniSRE GitHub Repository](https://github.com/rahulchandra2004/omnisre-signoz-hackathon)**

Have you ever tried building autonomous remediation tools? Let me know in the comments below!

*Built by Rahul Chandra Padamuttam for the Agents of SigNoz Hackathon.*
