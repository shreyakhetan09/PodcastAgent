# Scaling to 50 podcasts (take-home deliverable)

This note answers: *If we scaled this to process 50 different podcasts concurrently every morning, how would you architect the ADK multi-agent workflow, and how would you handle transcription compute and LLM API rate limits?*

---

## 1. ADK multi-agent shape

A single root **`LlmAgent`** that repeatedly calls tools for dozens of feeds will hit **latency**, **rate limits**, and **fragile context** long before 50 shows finish. A better pattern splits **muscle** (deterministic tools) from **brain** (one or few summarization calls).

### 1.1 Coordinator + `SequentialAgent`

Use a **`SequentialAgent`** (or custom runner) as the **coordinator** stage:

1. Validate inputs (exactly N feeds, URL shape, denylist).
2. Shard into batches (e.g. 10 feeds per batch) and enqueue work.
3. Wait for each batch’s **structured results** (JSON in object storage or a message queue) before advancing.

`SequentialAgent` fits **strict pipelines**: *validate → shard → wait on batch 1 → wait on batch 2 → … → synthesize*. That keeps ordering explicit for morning jobs and retries.

### 1.2 Parallel fan-out with `ParallelAgent`

For **independent** batches (no ordering between batch A and batch B), wrap worker agents in **`ParallelAgent`**:

- Each **worker** is either a thin **`LlmAgent`** whose only job is **tool use** (ingest + transcribe), or **no LLM at all**—just Python invoking the same `FunctionTool` handlers behind a small ADK `Agent` wrapper for observability.
- **Do not** run 50 full prose generations in parallel on the free tier; cap **concurrent LLM calls** (see §3).

`ParallelAgent` is appropriate when failures in one shard must not block others, and you merge results later.

### 1.3 Optional `LoopAgent` / retry policy

Wrap ingestion or transcription calls in a **`LoopAgent`** (or tool-level retry) when RSS or CDN errors are bursty: bounded retries with exponential backoff before marking a feed failed.

### 1.4 Synthesizer `LlmAgent` (single “brain”)

After all 50 intros exist as **JSON** (`title`, `author`, `published`, `transcript`, `feed_url`), run **one** summarizer **`LlmAgent`** that:

- Takes **no ingest/transcribe tools** (or only a `load_artifact` tool), and
- Emits the **single Markdown** briefing and Cross-Pollination.

That minimizes **tool round-trips per token** and keeps the expensive model focused on synthesis.

---

## 2. Transcription compute

| Concern | Approach |
| --- | --- |
| **GPU** | Run Whisper on **GPU workers** (GCE with L4/T4, or managed “gpu + job” runners). Keep **one clip per job** (3–5 minutes) to bound VRAM and time. |
| **Caching** | Key: `hash(feed_url, episode_id or guid, clip_seconds, whisper_model_version)`. Store transcript blobs in **GCS/S3**; skip re-encode if the episode unchanged. |
| **Queue** | **Cloud Run jobs**, **Celery + Redis**, or **Pub/Sub** workers; scale replicas on queue depth, not on raw feed count. |
| **Cost / $0 lab** | For a take-home, **serial** or **small process pool** on one machine is fine; at 50 feeds, **batch size 5–10** parallel Whisper jobs** is a practical starting point before adding GPUs. |

This repo already uses **FFmpeg time trimming** (wall-clock) plus a **bounded download**, which scales better than byte-only caps when bitrates vary.

---

## 3. LLM API rate limits (verify in your account)

Limits **change by model, tier, and Google Cloud project**. Treat numbers below as **planning anchors**—always confirm in:

- **Gemini:** [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) and **AI Studio** rate-limit panel for your project.
- **Groq:** [Groq rate limits](https://console.groq.com/docs/rate-limits) for your org and model.

### 3.1 Order-of-magnitude examples (free / dev tiers)

| Provider | Typical guardrails (examples only) | Implication for agents |
| --- | --- | --- |
| **Groq** | On the order of **~30 RPM** org-wide for many models; **TPM/TPD** caps vary by model (check console). | One briefing run may cost **several** requests (tool chatter + final). **Cap parallel Groq agents** (e.g. 2–4) and **serialize** summarization if you see `429`. |
| **Gemini (free tier)** | Often **single-digit to low tens RPM** per model tier, plus **TPM** and **RPD** caps (see official matrix). | Prefer **one** synthesis call with **aggregated JSON** instead of 50 per-feed LLM calls. |

### 3.2 Practical mitigations

1. **Token bucket** in your coordinator: shared limiter keyed by `provider + api_key`.
2. **Exponential backoff + jitter** on `429` / `RESOURCE_EXHAUSTED`.
3. **Batch writes** to storage so workers do not block on the LLM.
4. **Separate API keys / projects** only where policy allows—**some** providers aggregate limits per project, so splitting keys does not help.

---

## 4. Summary diagram (logical)

```text
[Feeds 1..50]
     │
     ▼
[Coordinator: SequentialAgent]  ──► shard into batches
     │
     ▼
[ParallelAgent: batch workers]  ──► ingest + transcribe tools only (or pure Python)
     │                                      │
     ▼                                      ▼
                    [Object storage: episode + transcript JSON]
                                        │
                                        ▼
                    [Single LlmAgent: synthesizer] ──► intelligence_briefing.md
```

This keeps **Google ADK** at the center, uses **native multi-agent primitives** where they help, and aligns **compute** and **quotas** with how providers actually bill and throttle.
