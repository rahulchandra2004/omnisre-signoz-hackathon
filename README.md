# OmniSRE: Autonomous AI SRE Agent with Closed-Loop Self-Healing

> Self-hosted SigNoz + OpenTelemetry + Google Gemini + Telegram HITL — an autonomous agent that detects incidents, diagnoses root causes, and restarts containers in **under 40 seconds**, without waking you up.

![OmniSRE Banner](./assets/title.png)

**Track 01: AI & Agent Observability | WeMakeDevs x Agents of SigNoz Hackathon**

![License](https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SigNoz](https://img.shields.io/badge/observability-SigNoz-F46800?style=for-the-badge)
![Gemini](https://img.shields.io/badge/AI-gemini--1.5--flash-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Docker](https://img.shields.io/badge/runtime-Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

**Watch the 3-Minute Live Demo:**

[![Watch the Live Demo on YouTube](./assets/title.png)](https://youtu.be/GMaUc4ksh6A)

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

### Incident Response Sequence (with Timing)

```mermaid
sequenceDiagram
    autonumber
    participant S as SigNoz Alert Manager
    participant W as omnisre_agent Webhook
    participant I as Investigator (Gemini)
    participant T as Telegram HITL Gate
    participant H as Healer (Docker Socket)
    participant A as buggy_service

    Note over S,A: t+0s — Chaos injected, P99 > 2000ms for 2 minutes
    S->>W: POST /webhook/signoz (alert payload)
    W->>I: spawn background thread: process_alert()
    Note over I: t+3s — Fetch 15-min ClickHouse log window
    I->>S: GET /api/v1/query_range (ERROR spans)
    S-->>I: Raw ClickHouse log context
    Note over I: t+8s — Send trace context to Gemini
    I->>I: gemini-1.5-flash via LiteLLM → JSON diagnosis
    Note over T: t+12s — Halt pipeline, dispatch Telegram card
    I->>T: send_telegram_alert(root_cause, proposed_fix)
    T-->>I: Polling every 3s for YES (120s timeout)
    Note over T: t+22s — Human replies YES
    T->>H: authorize_remediation()
    Note over H: t+24s — Mutate .env, restart via Docker socket
    H->>A: container.restart() via /var/run/docker.sock
    Note over A: t+26s — Container restarts, DB_POOL_SIZE=50
    H->>T: 15s stabilization cooldown
    Note over H: t+38s — Verify recovery, post proof card
    H->>T: send_recovery_card(p99=840ms, mttr=38s)
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

Create a `.env` file in the project root:

| Variable | Required | Description | Example |
| :--- | :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | ✅ | Token from [@BotFather](https://t.me/BotFather) | `123456:ABC-xyz...` |
| `TELEGRAM_CHAT_ID` | ✅ | Your Telegram user or group ID | `987654321` |
| `GEMINI_API_KEY` | ✅ | Google AI Studio key for Gemini inference | `AIzaSy...` |
| `DB_POOL_SIZE` | ✅ | Initial connection pool size (agent scales this to 50) | `10` |

```bash
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id"
GEMINI_API_KEY="your_gemini_api_key"
DB_POOL_SIZE=10
```

### 3. Deploy the SigNoz Observability Stack

> **Why self-hosted SigNoz?** OmniSRE requires direct access to the ClickHouse backend via `/api/v1/query_range` to programmatically extract raw error spans. Managed cloud observability platforms do not expose this API. Self-hosting also eliminates data egress costs and gives the agent full query control with zero rate limiting.

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

## How the Gemini Inference Works

This is the exact prompt sent to `gemini-1.5-flash` via LiteLLM during a live incident. Forcing a strict JSON schema eliminates ambiguous prose responses and makes the downstream healer fully deterministic.

```python
# agent/investigator.py — exact runtime prompt
prompt = f"""
You are an autonomous Site Reliability Engineer (OmniSRE).
An alert has been triggered: {alert_payload}

Context gathered from observability tools:
{context}  # <-- Real ClickHouse ERROR span data injected here

Determine the root cause and the required action.
Respond with ONLY raw JSON, with no markdown formatting or backticks.
It must contain:
- "root_cause": string, your hypothesis
- "action": string, either "RESTART_SERVICE", "SCALE_UP", or "NO_ACTION"
- "target_service": string, the name of the service to act on
"""
```

Example Gemini response during a real incident:

```json
{
  "root_cause": "Sustained StatusCode.ERROR spans on /checkout over 15 minutes, consistent with DB_POOL_SIZE exhaustion under current traffic load.",
  "action": "RESTART_SERVICE",
  "target_service": "buggy_service"
}
```

---

## Human-in-the-Loop Guardrail

The Telegram gate is the only thing standing between Gemini's diagnosis and your running infrastructure. The pipeline is hard-wired to halt at this point with no bypass:

```
SigNoz Alert fires
       │
       ▼
 Gemini RCA complete
       │
       ▼
┌─────────────────────────────┐
│   TELEGRAM HITL GATE        │  ← Pipeline halts here
│   Diagnostic card sent      │
│   Polling for YES every 3s  │
│   Timeout: 120 seconds      │
└─────────────────────────────┘
       │                  │
    YES ▼              NO / Timeout ▼
 Docker Heal          Abort. Log. Done.
```

Timestamp filtering (`msg_date >= alert_start_time - 5`) prevents stale approval messages from previous incidents triggering unintended restarts.

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

## License

This project is licensed under the **MIT License** — see the [LICENSE](./LICENSE) file for details. You are free to use, modify, and distribute this project with attribution.

## Contributing

Contributions, issues, and feature requests are welcome. If you deploy OmniSRE and hit a new networking edge case or extend the healing actions, open a PR — especially for:
- New `action` types beyond `RESTART_SERVICE` and `SCALE_UP`
- Kubernetes operator support
- Additional alert channel integrations (PagerDuty, Opsgenie)

---

Built by **[Rahul Chandra Padamuttam](https://github.com/rahulchandra2004)** for the WeMakeDevs × Agents of SigNoz Hackathon.
