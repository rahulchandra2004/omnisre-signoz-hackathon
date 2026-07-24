# How I Built an Autonomous AI SRE Agent with SigNoz (and the Telegram Kill Switch That Keeps It Safe)

![OmniSRE Banner](https://raw.githubusercontent.com/rahulchandra2004/omnisre-signoz-hackathon/main/assets/title.png)

**Track 01: AI & Agent Observability | WeMakeDevs x Agents of SigNoz Hackathon**

It was 3:00 AM, and my hypothetical pager was going off.

If you’ve ever been on-call for a modern microservice architecture, you know the feeling. A database connection pool gets exhausted, tail latency spikes to 3,000ms, and HTTP 500 errors start raining down. Observability dashboards are great—they tell you exactly what is burning. But they still rely entirely on a bleary-eyed human to wake up, SSH into a server, read the logs, diagnose the root cause, and apply a fix.

I realized something: If Large Language Models are smart enough to write code, shouldn't they be smart enough to read telemetry, find the root cause, and restart the container themselves?

I built OmniSRE for the Agents of SigNoz Hackathon to answer exactly that. But as I gave my AI agent the keys to my Docker socket, I quickly realized that letting an autonomous agent mutate infrastructure is terrifying. I needed a fail-safe.

In this blog, I’ll show you how I built an autonomous, closed-loop Site Reliability Engineering (SRE) agent using self-hosted SigNoz, OpenTelemetry, and Google Gemini—and the crucial Telegram "Human-in-the-Loop" architecture that keeps it from accidentally destroying my infrastructure.

{% youtube GMaUc4ksh6A %}
*(Alternatively, [Click Here to Watch the 3-Minute Demo](https://youtu.be/GMaUc4ksh6A))*

---

## The Architecture: A Closed-Loop Pipeline

I wanted OmniSRE to run entirely isolated from the target application. If the application crashes, the agent needs to stay alive to fix it. The system relies on a multi-container network topology where telemetry flows upstream into SigNoz storage, while remediation actions flow downstream via host-level socket bindings.

![Architecture Blueprint](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/c71hs0s06t6bvqgnwdof.png)

### Component Breakdown

* **buggy_service (FastAPI):** The monitored target application. It emits OTLP HTTP traces to SigNoz. I built normal endpoints (`/checkout`) and a chaos injection endpoint (`/chaos/inject`) to simulate a database pool exhaustion.
* **SigNoz Stack:** Ingests telemetry, indexes spans in ClickHouse, computes rolling metric aggregations, and dispatches webhook alerts on threshold breaches.
* **omnisre_agent:** The autonomous runtime. It processes webhooks, queries SigNoz backend APIs, invokes Google Gemini via LiteLLM, polls Telegram for authorization, and triggers container healing.
* **Docker Socket (`/var/run/docker.sock`):** The host daemon interface mounted into the SRE agent, authorizing programmatic container restarts.

---

## Setting the Trap: Auto-Instrumentation & Chaos

To test the AI, I needed granular data. OmniSRE prioritizes deterministic tracing. By using OpenTelemetry SDKs natively, individual spans across the `/checkout` endpoint are recorded inside ClickHouse for auditability.

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

When I hit the `/chaos/inject` endpoint, error rates rise above 40%, and the SigNoz Dashboard lights up.

![Live Anomaly Outage Spike](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/7ggx0gj1yhipc9se3y8h.png)

---

## The Hurdle: The Ghost in the Container Bridge

Everything worked perfectly in my local Python environment. But when I containerized the SRE Agent, my observability pipeline suddenly went entirely blind. The agent was receiving the alert webhook from SigNoz, but when it tried to query the ClickHouse logs to feed the AI, it crashed.

**The Moment:** I spent hours assuming my ClickHouse query syntax was wrong, or that the LLM context window was blowing up. I checked the agent logs: `Connection Refused: localhost:3301`.

**The Fix:** Container networking strikes again. SigNoz was running on my host machine's port 3301, but inside the isolated `omnisre_agent` Docker container, `localhost` referred to the container itself, not the host!

To fix this resiliently, I programmed the agent to automatically cycle through fallback network interfaces. If `localhost:3301` fails, it tries `host.docker.internal:3301`, and finally `signoz-frontend:3301`. Within seconds, the agent was successfully pulling 15-minute sliding windows of error logs natively from ClickHouse.

---

## The Killer Feature: Telegram Human-in-the-Loop (HITL)

Having an AI that can diagnose a problem is amazing. Having an AI that can unilaterally modify `.env` files and execute container restarts is a recipe for a career-ending disaster.

I needed a "Financial Kill Switch" for my infrastructure.

When SigNoz detects the P99 latency spike, it fires a webhook to the SRE Agent. The agent extracts the ClickHouse logs and passes them to Google Gemini (`gemini-1.5-flash`). But before it touches the Docker socket, it halts execution and fires a diagnostic card to my Telegram.

![Telegram Diagnosis Approval](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/xew23r8qr7metoon4zji.png)

The Telegram bot acts as an authorization gate. It tells me:
1. What the alert is.
2. The root cause identified by Gemini.
3. The proposed remediation step (e.g., Scale `DB_POOL_SIZE` to 50 and restart container).

It polls my chat waiting for a simple `YES`.

Once authorized, the agent programmatically mutates the `.env` configuration, restarts the container via native Docker socket bindings, implements a 15-second cooldown, and verifies the recovery.

![Telegram Remediation Proof](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/491u6vkvvtr9u822a07x.png)

Latency drops back to 840ms, the HTTP 200 curve recovers, and MTTR (Mean Time To Recovery) clocks in under 40 seconds.

---

## What I Learned From This Project

* **Deterministic Context is Everything:** LLMs hallucinate when they lack context. By programmatically tagging OpenTelemetry spans (`StatusCode.ERROR`), I ensured Gemini had strict, factual trace data to reason about, practically eliminating hallucinations.
* **Timestamp Your Guardrails:** During testing, the agent kept auto-restarting my containers immediately. Why? The polling engine was reading stale, historical `YES` messages from my Telegram chat. Adding a timestamp filter (`msg_date >= start_time - 5`) saved my sanity.
* **Observability is the missing link for AI Agents:** If you cannot observe your system, an AI cannot fix it. SigNoz bridging the gap between raw telemetry and programmatic extraction made this entire autonomous loop possible.

---

## Future Scope

* **Kubernetes Operator Native Architecture:** Moving from Docker socket binding to Kubernetes controllers for managing custom resources definitions (CRDs) and `kubectl scale` operations.
* **Multi-Agent Collaboration:** Distributing tasks between different LLMs that specialize in certain areas, such as Database Query Optimization vs. Network Routing.

---

## AI Usage Disclosure

In accordance with hackathon transparency rules, Gemini and GitHub Copilot were used during development to refactor code and design layouts. At runtime, `gemini-1.5-flash` is natively integrated via LiteLLM for log triage and root-cause analysis.

---

If you want to poke around the code and try injecting chaos into the agent yourself, check out the full repository here:  
**[OmniSRE on GitHub](https://github.com/rahulchandra2004/omnisre-signoz-hackathon)**

Have you ever tried building autonomous remediation tools? Let me know in the comments—I’d love to hear how you tackle the Human-in-the-Loop problem!

*Built by Rahul Chandra Padamuttam for the Agents of SigNoz Hackathon.*
