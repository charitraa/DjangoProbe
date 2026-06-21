# Multi-Provider AI System Summary

DjangoProbe uses a multi-provider AI system with automatic fallback. **NVIDIA NIM
is always first priority;** the other providers are fallbacks that only run when
their API key is configured.

## Providers (`ai_tester/providers/`)

All providers subclass `BaseProvider` (`generate_text`, `is_available`,
`get_model_info`). `ProviderManager` initializes the configured ones and rotates
to the next on any error or rate limit (a provider is skipped after 3 failures).

| Provider | File | Key | Default model |
|----------|------|-----|---------------|
| NVIDIA NIM (1st priority) | `nvidia_provider.py` | `NVIDIA_API_KEY` | `qwen/qwen3.5-122b-a10b` |
| Anthropic | `anthropic_provider.py` | `ANTHROPIC_API_KEY` | `claude-3.5-sonnet` |
| Groq | `groq_provider.py` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Gemini | `gemini_provider.py` | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| Together AI | `together_provider.py` | `TOGETHER_API_KEY` | `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` |

NVIDIA NIM is OpenAI-compatible (`NVIDIA_BASE_URL`, default
`https://integrate.api.nvidia.com/v1`). The Ollama provider was removed.

## Priority & fallback

- Order: **NVIDIA → Anthropic → Groq → Gemini → Together**.
- A provider only initializes if its API key is present; otherwise it's skipped.
- `AI_PREFERRED_PROVIDER` can move a non-NVIDIA provider up, but NVIDIA is always first.
- On error/rate-limit the manager rotates to the next available provider.

## Integration

`AIHelper` (`ai_helper.py`) wraps `ProviderManager`, parses the target's
`INSTALLED_APPS` into `self.installed_apps`, and exposes `call_with_retry`
returning an OpenAI-shaped response (`.choices[0].message.content`).

## Configuration

```bash
AI_PREFERRED_PROVIDER=nvidia            # auto | nvidia | anthropic | groq | gemini | together
NVIDIA_API_KEY=nvapi-...                # free key: https://build.nvidia.com
NVIDIA_MODEL=qwen/qwen3.5-122b-a10b     # copy exact id from the model page
AI_MAX_RETRIES=3
AI_RETRY_DELAY=60
```

See [MULTI_PROVIDER_SETUP.md](MULTI_PROVIDER_SETUP.md) for full setup and
troubleshooting, and [QUICK_START.md](QUICK_START.md) for the fastest path.

## Adding a provider

Extend `BaseProvider` (use `nvidia_provider.py` as an OpenAI-compatible template),
then register it in `ProviderManager._initialize_providers` and export it from
`providers/__init__.py`.
