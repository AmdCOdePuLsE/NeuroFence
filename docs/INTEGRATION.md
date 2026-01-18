# NeuroFence Integration Guide

This guide is written so you can integrate NeuroFence “like a framework”: copy one small pattern into your system, and all agent-to-agent messages get enforced.

NeuroFence runs as an HTTP service (FastAPI). Your application calls it as a **policy decision point**.

Core endpoint:

- `POST /intercept` → returns a decision you must enforce (allow / flag / escalate).

## 5-minute integration (recommended path)

1) Run NeuroFence (service)

- Docker (Windows): run `./run-neurofence.cmd` from the repo root
- Confirm it’s up: `http://localhost:8000/health`

2) Install the SDK into your project

You can install the SDK like other Python libraries (from VS Code terminal):

Option A (recommended for local development): editable install

```powershell
cd C:\path\to\NeuroFence
pip install -e .
```

Option B: regular local install

```powershell
cd C:\path\to\NeuroFence
pip install .
```

Option C: install from a Git URL (what most teams do once it’s in a repo)

```powershell
pip install "neurofence-sdk @ git+https://github.com/<org>/<repo>.git#subdirectory=."
```

This installs `neurofence_sdk` (the integration wrapper + HTTP client).

3) Wrap your message send function

Find the **single function** that every agent-to-agent message eventually passes through (message bus, chat router, “send”, “publish”, etc.). Wrap it once.

```python
from neurofence_sdk import wrap_send

def send_message(sender: str, recipient: str, content: str):
    # Your real delivery logic here
    deliver(sender, recipient, content)

send_message = wrap_send(
    send_message,
    base_url="http://localhost:8000",
    timeout_s=5,
    block_flagged=True,  # strict mode (recommended)
)
```

That’s it: every message is checked via `POST /intercept` before it’s delivered.

## Pick your enforcement point (coverage vs effort)

### Option A: Message bus / `send()` wrapper (best coverage)

Use this whenever possible.

- Covers *all* channels (LLM prompts, internal chat, tools, memory bus)
- Framework-agnostic
- Hardest to bypass

Reference implementation:

- Example: `examples/framework_agnostic_integration.py`
- SDK: `neurofence_sdk/guard.py`

### Option B: LLM call interception (good if everything goes through one client)

Intercept prompts right before your LLM call (or at your “LLM gateway”).

Use this if you truly don’t have a central message bus.

Limitations:

- Only covers content that goes through the LLM call path
- Does not cover non-LLM internal agent messaging

### Option C: Backend middleware (only if your backend is already the router)

If agent messages are posted to your backend first, call `POST /intercept` in middleware or your route handler, then forward/persist only if allowed.

## How to enforce decisions

Treat NeuroFence output as the source of truth:

1) Call `POST /intercept` with `{sender, recipient, content}`
2) Read the returned decision
3) Enforce consistently

Typical policies:

- **ALLOW**: deliver
- **FLAG**: deliver + mark for review (and/or reduce privileges)
- **ESCALATE**: block delivery and isolate the sender

The provided wrapper supports strict mode:

- `block_flagged=True` → raise on flagged/escalated decisions

### Optional: automatic isolation

If you want immediate isolation on escalation:

- call `POST /isolate/{agent_name}` (and optionally store a reason)

## Node.js / TypeScript example (no SDK required)

You can integrate with plain HTTP.

```ts
type InterceptResponse = {
  action: string; // e.g. "ALLOW" | "FLAG" | "ESCALATE"
};

async function guardedSend(sender: string, recipient: string, content: string) {
  const res = await fetch("http://localhost:8000/intercept", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sender, recipient, content }),
  });
  if (!res.ok) throw new Error(`NeuroFence intercept failed: ${res.status}`);

  const decision = (await res.json()) as InterceptResponse;
  if (decision.action === "ESCALATE") throw new Error("Blocked by NeuroFence");

  return deliver(sender, recipient, content);
}
```

## Failure mode: fail-closed vs fail-open

Decide what should happen if NeuroFence is unreachable:

- **Fail-closed** (secure default): block until NeuroFence is reachable
- **Fail-open** (availability): allow but emit telemetry and alerts

Recommended:

- Fail-closed for high-risk channels
- Fail-open only if you have strong auditing and a compensating control

## Production checklist

- Put NeuroFence behind TLS (reverse proxy)
- Restrict access (private network / allowlist callers)
- Add auth if needed (mTLS / JWT / API key at proxy)
- Decide redaction policy for logged content

## Reference

- SDK: `neurofence_sdk/client.py`, `neurofence_sdk/guard.py`
- Example: `examples/framework_agnostic_integration.py`
- API docs (interactive): open `http://localhost:8000/docs`
