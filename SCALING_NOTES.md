# Scaling to 50 podcasts (take-home deliverable)

If this ran every morning for **50 feeds**, I would keep **Google ADK** but split responsibilities across agents or a **SequentialAgent** / coordinator flow:

1. **Coordinator** — validates the feed list, shards work (e.g. 10 feeds per batch), and enqueues jobs.
2. **Per-feed or per-batch workers** — each worker is still an `LlmAgent` *or* a thin runner that only executes **FunctionTools** (ingestion + transcription) without a large LLM call, writing structured results (JSON) to object storage keyed by `feed_url` + episode id.
3. **Synthesizer agent** — one final `LlmAgent` that reads only the **aggregated JSON** (titles, authors, dates, short intro transcripts) and emits the single Markdown brief. That minimizes repeated LLM tool orchestration and caps token use.

**Transcription compute:** run Whisper on **GPU workers** or a **job queue** (Cloud Run jobs, Celery, etc.) with **one clip per job**, **idempotent caching** (reuse transcript if `episode_id` + clip length unchanged), and strict **3–5 minute** caps.

**LLM rate limits:** central **token bucket** / retry with exponential backoff for Gemini or Groq; **batch** feed processing with **bounded concurrency** (e.g. 5–10 parallel LLM calls); optionally **pre-summarize each show** with a small model, then **one** merge call for Cross-Pollination to stay under TPM/RPM.
