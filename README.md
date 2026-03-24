# Podcast Intelligence Agent (Google ADK — take-home spec)

Implements the **Multi-Source Podcast Intelligence Agent** assignment: **`google-adk`** in Python, **`LlmAgent`** + two **`FunctionTool`**s, **Whisper** (tiny/base) on **3–5 minute** intro clips, **Gemini** (free tier) or **Groq** (free tier) via **`LiteLlm`**, output **`intelligence_briefing.md`**.

## What it does (assignment mapping)

| Requirement | Implementation |
| --- | --- |
| **Framework** | `InMemoryRunner` + `LlmAgent` + `FunctionTool` (`src/agent_pipeline.py`) |
| **Ingestion tool** | `ingest_latest_podcast_episodes` → `ingest_latest_episodes` in `src/tools.py` (3 RSS URLs, latest episode + **audio URL** each) |
| **Transcription tool** | `transcribe_intro_snippets` → clip **3–5 min**, **openai-whisper** |
| **Agent output** | Per show: **title, author, date**, **2 intro bullets**; **## Cross-Pollination** (one paragraph) — `src/prompts.py` |
| **Output file** | `intelligence_briefing.md` (config: `output_path` in `Settings`) |
| **$0 / free tier** | Groq + `USE_GROQ_ONLY=1`, or Gemini API key without Groq-only |
| **Scaling write-up** | `SCALING_NOTES.md` |

## Setup (Python 3.10+ recommended)

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- **Groq:** `USE_GROQ_ONLY=1` and `GROQ_API_KEY=...`
- **Gemini:** unset `USE_GROQ_ONLY`, set `GEMINI_API_KEY=...`

## Run (end-to-end ADK)

```bash
python main.py
```

Optional: `python main.py --debug-env` (prints non-secret key diagnostics).

Default feeds (three shows): Lex Fridman, Practical AI, Latent Space — replace by changing `DEFAULT_FEEDS` in `src/agent_pipeline.py` or extending `run_pipeline(..., feed_urls=[...])`.

## Project layout

- `main.py` — CLI entry
- `src/agent_pipeline.py` — ADK runner, tools, `run_pipeline`
- `src/tools.py` — RSS + clipped download + Whisper
- `src/prompts.py` — `ADK_SYSTEM_INSTRUCTION`, `build_user_task`
- `src/config.py` — env → `Settings`
- `src/models.py` — episode / transcript structs
- `src/report.py` — writes `intelligence_briefing.md`

## Dependencies

See `requirements.txt` (`google-adk`, `litellm`, `openai-whisper`, `feedparser`, etc.).
