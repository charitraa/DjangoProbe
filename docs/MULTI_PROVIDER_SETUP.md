# Multi-Provider AI System Setup Guide

DjangoProbe now supports multiple AI providers with automatic fallback, giving you free and reliable options for test generation.

## Supported Providers

### 1. Groq (Remote API)
- **Cost**: Free tier available
- **Speed**: Very fast
- **Setup**: Get API key from [console.groq.com](https://console.groq.com/)
- **Models**: Llama 3.3 70B, Llama 3.1 8B, Gemma 2 9B
- **Rate Limits**: 14,400 requests/day, 30 requests/minute

### 2. Ollama (Local - Recommended)
- **Cost**: Completely free
- **Speed**: Fast (depends on your hardware)
- **Setup**: Install Ollama locally
- **Models**: Llama 3.2, Mistral, Qwen 2.5, CodeLlama
- **Rate Limits**: None (runs locally)

### 3. Together AI (Remote API)
- **Cost**: Free tier available
- **Speed**: Fast
- **Setup**: Get API key from [api.together.xyz](https://api.together.xyz/)
- **Models**: Llama 3.2 90B, Llama 3.1 70B, Qwen 2.5 72B
- **Rate Limits**: ~10,000-50,000 tokens/month on free tier

## Quick Setup

### Option 1: Ollama (Recommended - Completely Free)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama server (in one terminal)
ollama serve

# Download a model (in another terminal)
ollama pull llama3.2

# Run DjangoProbe - it will automatically use Ollama
djangoprobe ~/path/to/your/project
```

### Option 2: Groq (Fast Remote API)

```bash
# Get API key from https://console.groq.com/keys

# Add to your .env file
echo "GROQ_API_KEY=gsk_your_key_here" >> .env

# Run DjangoProbe
djangoprobe ~/path/to/your/project
```

### Option 3: Together AI (Good Free Tier)

```bash
# Get API key from https://api.together.xyz/

# Add to your .env file
echo "TOGETHER_API_KEY=your_key_here" >> .env

# Run DjangoProbe
djangoprobe ~/path/to/your/project
```

## Multiple Providers (Best Reliability)

Configure multiple providers for automatic fallback:

```bash
# .env file
GROQ_API_KEY=gsk_your_groq_key
TOGETHER_API_KEY=your_together_key

# Ollama will be auto-detected if running
```

## Configuration Options

### Environment Variables

```bash
# Provider Selection
AI_PREFERRED_PROVIDER=auto        # auto, groq, ollama, together

# Model Selection
GROQ_MODEL=llama-3.1-8b-instant
OLLAMA_MODEL=llama3.2
TOGETHER_MODEL=meta-llama/Llama-3.1-8b-chat-Instruct-Turbo

# Retry Configuration
AI_MAX_RETRIES=3
AI_RETRY_DELAY=60
```

### Priority Order

By default, providers are tried in this order:
1. **Ollama** (if available) - Free, local
2. **Groq** (if configured) - Fast, good rate limits
3. **Together AI** (if configured) - Good free tier

You can customize this with `AI_PREFERRED_PROVIDER`:

```bash
# Prefer Groq first
AI_PREFERRED_PROVIDER=groq

# Prefer Together AI first
AI_PREFERRED_PROVIDER=together

# Let system decide (default)
AI_PREFERRED_PROVIDER=auto
```

## Model Recommendations

### For Best Quality
- **Groq**: `llama-3.3-70b-versatile`
- **Ollama**: `llama3.2:70b` (requires good hardware)
- **Together**: `meta-llama/Llama-3.2-90b-chat-preview`

### For Best Speed
- **Groq**: `llama-3.1-8b-instant`
- **Ollama**: `llama3.2:3b` (fastest)
- **Together**: `meta-llama/Llama-3.1-8b-chat-Instruct-Turbo`

### For Best Rate Limits
- **Groq**: `llama-3.1-8b-instant` (highest rate limits)
- **Ollama**: Any model (unlimited)
- **Together**: `meta-llama/Llama-3.1-8b-chat-Instruct-Turbo`

## Troubleshooting

### Ollama Issues

**Ollama not found:**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh
```

**Model not available:**
```bash
# Download the model
ollama pull llama3.2

# List available models
ollama list
```

**Server not running:**
```bash
# Start Ollama server
ollama serve
```

### Groq Issues

**Rate limit errors:**
- Switch to smaller model: `GROQ_MODEL=llama-3.1-8b-instant`
- Add multiple API keys: `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`

**Invalid API key:**
- Get a new key from [console.groq.com](https://console.groq.com/keys)
- Ensure key starts with `gsk_`

### Together AI Issues

**Quota exceeded:**
- Check your usage at [api.together.xyz](https://api.together.xyz/)
- Consider upgrading to paid tier or switching providers

**Invalid API key:**
- Get a new key from [api.together.xyz/keys](https://api.together.xyz/keys)

## Performance Comparison

| Provider | Speed | Quality | Cost | Rate Limits |
|----------|-------|---------|------|-------------|
| Ollama   | Medium (depends on hardware) | High | Free | Unlimited |
| Groq     | Very Fast | High | Free | 14.4K/day |
| Together | Fast | Excellent | Free tier | ~10-50K tokens/month |

## Advanced Usage

### Custom Provider Configuration

You can customize provider behavior programmatically:

```python
from ai_tester.providers.manager import ProviderManager

# Initialize with custom settings
manager = ProviderManager(repo_path="/path/to/project")

# Generate text with specific parameters
response = manager.generate_text(
    messages=[
        {"role": "user", "content": "Generate test cases..."}
    ],
    max_tokens=4096,
    temperature=0.7
)

# Check provider status
status = manager.get_provider_status()
print(f"Current provider: {status['current_provider']}")
```

### Adding Custom Providers

You can add custom providers by extending `BaseProvider`:

```python
from ai_tester.providers.base import BaseProvider

class CustomProvider(BaseProvider):
    def generate_text(self, messages, **kwargs):
        # Your implementation
        pass

    def get_model_info(self):
        return {"provider": "Custom", "model": "my-model"}

    def is_available(self):
        return True
```

## Migration from Single Provider

If you were using the old Groq-only setup:

1. **No changes needed** - The system is backward compatible
2. **Optional**: Add more providers for reliability
3. **Recommended**: Set `GROQ_MODEL=llama-3.1-8b-instant` for better rate limits

```bash
# Old .env (still works)
GROQ_API_KEY=gsk_...

# New .env (better)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant
TOGETHER_API_KEY=...
# Ollama will be auto-detected
```

## Getting Help

- **Documentation**: Check this guide and the main README
- **Issues**: Report bugs on GitHub
- **Discussions**: Ask questions in GitHub Discussions

## Summary

✅ **Ollama** - Best for completely free, local usage
✅ **Groq** - Best for fast remote API with good free tier
✅ **Together AI** - Good alternative with excellent models
✅ **Multiple Providers** - Best reliability with automatic fallback

Start with Ollama for free local testing, then add Groq/Together for cloud backup!