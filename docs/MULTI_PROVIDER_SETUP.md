# Multi-Provider AI System Setup Guide

DjangoProbe supports multiple AI providers with automatic fallback. **NVIDIA NIM
is always first priority.** The other providers are fallbacks and only run when
their API key is configured in the environment.

## Supported Providers

### 1. NVIDIA NIM (recommended, first priority)
- **Cost**: Free tier
- **API**: OpenAI-compatible (`https://integrate.api.nvidia.com/v1`)
- **Setup**: Get a key (starts with `nvapi-`) at [build.nvidia.com](https://build.nvidia.com)
- **Models**: e.g. `qwen/qwen3.5-122b-a10b` (coding/reasoning, default), `qwen/qwen3-next-80b-a3b-instruct`
- **Note**: copy the exact model id from the model's page; a wrong id returns a 404

### 2. Groq (remote API)
- **Cost**: Free tier
- **Setup**: Get an API key from [console.groq.com](https://console.groq.com/)
- **Models**: `llama-3.3-70b-versatile` (default), `llama-3.1-8b-instant`

### 3. Gemini (remote API)
- **Cost**: Free tier
- **Setup**: Get an API key from [aistudio.google.com](https://aistudio.google.com/)
- **Models**: `gemini-2.0-flash` (default)

### 4. Anthropic (remote API)
- **Setup**: Get an API key from [console.anthropic.com](https://console.anthropic.com/)
- **Models**: `claude-sonnet-4-6` (default); supports a custom `ANTHROPIC_BASE_URL`

### 5. Together AI (remote API)
- **Cost**: Free tier
- **Setup**: Get an API key from [api.together.xyz](https://api.together.xyz/)
- **Models**: `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` (default)

## Quick Setup

### Recommended: NVIDIA NIM

```bash
# Get a free key at https://build.nvidia.com (starts with nvapi-)
cat > .env << EOF
AI_PREFERRED_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-your_key_here
NVIDIA_MODEL=qwen/qwen3.5-122b-a10b
EOF

djangoprobe ~/path/to/your/project
```

### Other providers (optional fallbacks)

Add any of these keys; each provider only initializes when its key is present:

```bash
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
TOGETHER_API_KEY=your_key_here
```

## Configuration Options

### Environment Variables

```bash
# Provider selection (NVIDIA is always first regardless of this value;
# it only reorders the non-NVIDIA providers)
AI_PREFERRED_PROVIDER=auto        # auto, nvidia, anthropic, groq, gemini, together

# Models
NVIDIA_MODEL=qwen/qwen3.5-122b-a10b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1   # optional; any OpenAI-compatible endpoint
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_MODEL=gemini-2.0-flash
ANTHROPIC_MODEL=claude-sonnet-4-6
TOGETHER_MODEL=meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo

# Retry / fallback
AI_MAX_RETRIES=3
AI_RETRY_DELAY=60
```

### Priority Order

Providers are tried in this order (NVIDIA always first):

1. **NVIDIA** (first priority)
2. **Anthropic** (if `ANTHROPIC_API_KEY` set)
3. **Groq** (if `GROQ_API_KEY` set)
4. **Gemini** (if `GEMINI_API_KEY` set)
5. **Together** (if `TOGETHER_API_KEY` set)

`AI_PREFERRED_PROVIDER` can move one of the non-NVIDIA providers up to just after
NVIDIA, but NVIDIA always stays first. On any error or rate limit, the manager
rotates to the next available provider.

## Model Recommendations

For DjangoProbe's job (reading raw DRF source and writing a complete test file),
prefer strong coding/instruction-following models:

- **NVIDIA**: `qwen/qwen3.5-122b-a10b` (coding/reasoning) or `qwen/qwen3-next-80b-a3b-instruct`
- **Groq**: `llama-3.3-70b-versatile`
- **Gemini**: `gemini-2.0-flash`

## Troubleshooting

**No providers available**
- Set at least one API key in `.env` (NVIDIA recommended).

**NVIDIA returns 404 for the model**
- The model id is wrong. Copy the exact id from the model page on build.nvidia.com
  (the code snippet shows `model="..."`).

**Rate limit / quota exceeded**
- Configure additional providers for automatic fallback. Groq also supports
  numbered keys for rotation: `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, ...

**Invalid API key**
- NVIDIA keys start with `nvapi-`, Groq with `gsk_`, Gemini with `AIza`.

## Advanced Usage

### Custom Provider Configuration

```python
from ai_tester.providers.manager import ProviderManager

manager = ProviderManager(repo_path="/path/to/project")
response = manager.generate_text(
    messages=[{"role": "user", "content": "Generate test cases..."}],
    max_tokens=4096,
    temperature=0.7,
)
status = manager.get_provider_status()
print(f"Current provider: {status['current_provider']}")
```

### Adding Custom Providers

Extend `BaseProvider` (see `ai_tester/providers/nvidia_provider.py` for an
OpenAI-compatible example) and register it in `ProviderManager._initialize_providers`:

```python
from ai_tester.providers.base import BaseProvider

class CustomProvider(BaseProvider):
    def generate_text(self, messages, **kwargs): ...
    def get_model_info(self): return {"provider": "Custom", "current_model": "my-model"}
    def is_available(self): return True
```

## Summary

✅ **NVIDIA NIM** — recommended primary, free tier, OpenAI-compatible
✅ **Groq / Gemini / Anthropic / Together** — optional fallbacks, run only with a key
✅ **Automatic fallback** — rotates on error/rate-limit; NVIDIA always tried first
