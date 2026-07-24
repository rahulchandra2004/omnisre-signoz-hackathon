# OmniSRE: Autonomous AI SRE Agent with Closed-Loop Self-Healing

> Self-hosted SigNoz + OpenTelemetry + Google Gemini + Telegram HITL — an autonomous agent that detects incidents, diagnoses root causes, and restarts containers in **under 40 seconds**, without waking you up.

![OmniSRE Banner](./assets/title.png)

**Track 01: AI & Agent Observability | WeMakeDevs x Agents of SigNoz Hackathon**

**Watch the 3-Minute Live Demo:** [youtube.com/watch?v=GMaUc4ksh6A](https://youtu.be/GMaUc4ksh6A)

---

## Results at a Glance

| Metric | During Chaos | After Self-Healing |
| :--- | :--- | :--- |
| P99 Latency | 3,420 ms | **840 ms** |
| HTTP 500 Rate | > 40% | **0%** |
| HTTP 200 Rate | < 60% | **100%** |
| MTTR | 15–45 min (human) | **< 40 seconds** |

---

## What OmniSRE Does

1. **Deploys a self-hosted SigNoz stack** via Foundry CLI — one command, six containers, fully reproducible
2. **Auto-instruments a FastAPI service** with OpenTelemetry SDKs — traces and error spans flow into ClickHouse
3. **Receives SigNoz alert webhooks** — no polling, event-driven pipeline from detection to diagnosis
4. **Queries ClickHouse logs** over a 15-minute sliding window via `/api/v1/query_range`
5. **Sends trace context to Google Gemini** (`gemini-1.5-flash` via LiteLLM) — structured JSON root-cause output
6. **Dispatches a Telegram diagnostic card** — halts all action until you reply `YES`
7. **Mutates `.env` configuration and restarts the container** via `/var/run/docker.sock` — zero-downtime healing
8. **Posts a post-mortem report** — latency and error rate proof after recovery

---

## System Architecture

```mermaid
graph TD
    subgraph AppLayer [" Target Application Container (buggy_service)"]
        A["FastAPI App: buggy_service<br/>Port 8000 - /checkout"] -->|1. Auto-Instrumented Traces and 500 Errors| B["OpenTelemetry SDK<br/>FastAPIInstrumentor"]
    end

    subgraph Observability [" Self-Hosted SigNoz Observability Stack"]
        B -->|host.docker.internal:4317| C["OTel Collector - OTLP Exporter"]
        C --> D[(ClickHouse Database)]
        D --> E["SigNoz Query Engine<br/>Port 3301"]
    end

    subgraph AgentContainer [" Autonomous SRE Container: omnisre_agent (Port 8001)"]
        E -->|2. Webhook Alert Trigger| F["FastAPI Webhook Receiver<br/>/webhook/signoz"]
        
        subgraph Classes ["Core Python SRE Modules"]
            F -->|3. Trigger process_alert| G["Investigator Class"]
            G -->|4. Call fetch_real_signoz_logs| E
            G -->|5. Send Trace and Error Context| H["LiteLLM Engine"]
            I["Notifier Class"]
            J["Healer Class"]
        end
    end

    subgraph ExternalAI [" External AI Reasoning Engine"]
        H -->|6. Prompt via LiteLLM| K["Google Gemini AI<br/>gemini-1.5-flash"]
        K -->|7. Return Diagnosis and Action| G
    end

    subgraph HumanLoop [" Human-in-the-Loop Guardrail (Telegram API)"]
        G -->|8. Pass Diagnosis| I
        I -->|9. Call send_telegram_alert| L["Telegram Bot Chat"]
        L -->|10. Polling wait_for_approval| I
    end

    subgraph SelfHealing [" Verified Self-Healing and ROI Pipeline"]
        I -->|11. Authorize Remediation| J
        J -->|12. Call tune_configuration| M["Update DB_POOL_SIZE=50<br/>in .env / Compose"]
        J -->|13. docker.from_env via socket| N["/var/run/docker.sock"]
        N -->|14. Call restart_target_service| A
        I -->|15. 15s Cooldown and Live Ping| A
        I -->|16. Send Recovery Alert Card| L
    end

    classDef primary fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef ai fill:#3b0764,stroke:#a855f7,stroke-width:2px,color:#fff;
    classDef telegram fill:#065f46,stroke:#10b981,stroke-width:2px,color:#fff;
    classDef docker fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fff;
    classDef signoz fill:#1e3a8a,stroke:#60a5fa,stroke-width:2px,color:#fff;

    class A,B primary;
    class C,D,E signoz;
    class F,G,H,I,J primary;
    class K ai;
    class L telegram;
    class M,N docker;
```

---

## Repository Layout

```
.
├── agent/
│   ├── main.py             # FastAPI webhook receiver and pipeline orchestrator
│   ├── investigator.py     # SigNoz log fetcher + Gemini RCA engine
│   ├── notifier.py         # Telegram HITL dispatcher and approval poller
│   ├── healer.py           # .env mutator + Docker socket restart executor
│   └── requirements.txt
├── app/
│   ├── buggy_service.py    # Monitored FastAPI app with chaos injection endpoints
│   ├── Dockerfile
│   └── requirements.txt
├── assets/                 # Screenshots and demo images
├── config/
│   └── docker-compose.yml  # Service topology with Docker socket binding
├── scripts/
│   ├── generate_traffic.ps1  # PowerShell baseline traffic generator
│   └── trigger_chaos.ps1     # One-click chaos injection script
├── casting.yaml            # SigNoz Foundry deployment manifest
├── run_demo_gui.py         # Tkinter GUI for live hackathon demonstration
└── README.md
```

---

## Prerequisites

| Tool | Purpose | Install | Verify |
| :--- | :--- | :--- | :--- |
| Docker & Docker Compose | Container runtime and service topology | [docs.docker.com](https://docs.docker.com/get-docker/) | `docker --version` |
| Foundry CLI | One-command SigNoz deployment | `curl -fsSL https://signoz.io/foundry.sh \| bash` | `foundryctl --version` |
| Python 3.12+ | Agent and application runtime | [python.org](https://www.python.org/downloads/) | `python --version` |
| Telegram Bot Token | HITL authorization channel | Create via [@BotFather](https://t.me/BotFather) | Send `/start` to your bot |
| Google Gemini API Key | LLM root-cause inference | [aistudio.google.com](https://aistudio.google.com/apikey) | Check quota dashboard |

---

## Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/rahulchandra2004/omnisre-signoz-hackathon.git
cd omnisre-signoz-hackathon
```

### 2. Configure Environment Variables
```bash
# Create .env in the project root
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id"
GEMINI_API_KEY="your_gemini_api_key"
DB_POOL_SIZE=10
```

### 3. Deploy the SigNoz Observability Stack
```bash
export PATH="$HOME/.local/bin:$PATH"
foundryctl cast -f casting.yaml
```
> **Alternative:** `docker-compose -f config/docker-compose.yml up --build -d`

SigNoz UI will be available at `http://localhost:3301` within ~3 minutes.

### 4. Run the Demo
```bash
# Generate baseline traffic
cd scripts && .\generate_traffic.ps1

# Inject chaos (database pool exhaustion)
curl -X POST http://localhost:8000/chaos/inject
```

Watch your **Telegram** receive the diagnostic card. Reply `YES` and the agent heals the service automatically.

---

## Demo Lifecycle

### Step 1: Inject Chaos → SigNoz Alerts Fire

```bash
curl -X POST http://localhost:8000/chaos/inject
```

Navigate to `http://localhost:3301` — P99 latency spikes to **3,420 ms**, error rate exceeds **40%**.

![SigNoz Outage Dashboard](./assets/The%20Outage%20%26%20Telemetry.png)

### Step 2: Gemini Diagnoses → Telegram Dispatches

The agent fetches 15 minutes of ClickHouse logs, passes them to Gemini, and sends a structured diagnosis card to Telegram.

![Telegram Diagnosis Card](./assets/AI%20Reasoning%20%26%20Guardrail.png)

Reply `YES` to authorize the remediation.

### Step 3: Container Self-Heals → Recovery Confirmed

The agent scales `DB_POOL_SIZE` to 50, restarts `buggy_service` via Docker socket, waits 15 seconds, and posts a recovery proof card.

![Self-Healing Proof](./assets/Self-Healing%20%26%20Proof.png)

---

## API Reference

### Target Application (`buggy_service:8000`)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/checkout` | GET | Simulates transactions. Returns `200 OK` (normal) or `500` with 1000–3000ms latency (chaos mode) |
| `/chaos/inject` | POST | Enables chaos mode — triggers database pool exhaustion simulation |
| `/chaos/revert` | POST | Disables chaos mode — restores nominal baseline |

### SRE Agent (`omnisre_agent:8001`)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/webhook/signoz` | POST | Receives SigNoz alert payloads. Returns `200 OK` immediately and offloads analysis to background thread |

---

## Telemetry Verification

Every `/checkout` request in chaos mode is indexed as a named `StatusCode.ERROR` span in ClickHouse — giving the AI structured, auditable evidence.

![Inspecting Spans in SigNoz Trace Explorer](./assets/Inspecting%20Spans.png)

```python
# Explicit span tagging in buggy_service.py
current_span.set_status(StatusCode.ERROR, "Chaos mode active: Database Pool Exhausted")
current_span.set_attribute("http.status_code", 500)
```

---

## Troubleshooting

| Symptom | Root Cause | Fix |
| :--- | :--- | :--- |
| Agent fails to fetch SigNoz logs | Container bridge resolves `localhost` to itself, not host | Agent auto-cycles through `localhost:3301` → `host.docker.internal:3301` → `signoz-frontend:3301` |
| Telegram bot auto-approves old incidents | Polling engine reads stale `YES` messages | Verify `notifier.py` timestamp filter: `msg_date >= start_time - 5` |
| Docker restart command fails | Socket not mounted into agent container | Check `docker-compose.yml`: `/var/run/docker.sock:/var/run/docker.sock` |
| Metrics show lingering errors after recovery | Rolling aggregation window buffer | 15-second stabilization cooldown is intentional — wait for window to flush |
| `foundryctl: command not found` | Installer puts it in `~/.local/bin` | `export PATH="$HOME/.local/bin:$PATH"` |

---

## Future Scope

- **Kubernetes Operator Native Architecture** — migrate from Docker socket to CRDs and `kubectl scale`
- **Multi-Agent Collaboration** — specialized LLM agents per domain (DB optimization, network routing)
- **Automated Rollback Engine** — revert `.env` mutations if post-healing health checks fail
- **Enterprise Alert Integration** — PagerDuty, Slack Enterprise Grid, Opsgenie webhook support

---

## AI Usage Disclosure

- **Development:** Google Gemini and GitHub Copilot were used for code refactoring, regex validation, and documentation layout.
- **Runtime:** `gemini-1.5-flash` is natively integrated via LiteLLM for automated log triage, hypothesis generation, and root-cause analysis during live incidents.

---

Built by **[Rahul Chandra Padamuttam](https://github.com/rahulchandra2004)** for the WeMakeDevs × Agents of SigNoz Hackathon.
