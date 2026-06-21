# Quick Start Guide - Multi-Provider AI System

Get started with DjangoProbe's multi-provider AI system in minutes!

At least one provider must be configured. **NVIDIA NIM is always tried first**;
the other providers are fallbacks and only run when their API key is set.

## Fastest Setup (NVIDIA NIM - Free Tier, Recommended)

```bash
# Step 1: Get a free API key (starts with nvapi-)
# Visit: https://build.nvidia.com

# Step 2: Add to .env in your working directory
cat > .env << EOF
AI_PREFERRED_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-your_key_here
NVIDIA_MODEL=qwen/qwen3.5-122b-a10b
EOF

# Step 3: Run DjangoProbe
djangoprobe ~/path/to/your/django/project
```

> Tip: copy the exact model id from the model's page on build.nvidia.com
> (the "Get API Key" code snippet shows `model="..."`). If the id is wrong the
> API returns a 404. `qwen/qwen3.5-122b-a10b` is a good coding/reasoning choice;
> `qwen/qwen3-next-80b-a3b-instruct` is a solid alternate.

## Alternative: Groq API (Fast Remote)

```bash
# Step 1: Get an API key at https://console.groq.com/keys

# Step 2: Add to .env
echo "GROQ_API_KEY=gsk_your_key_here" >> .env
echo "GROQ_MODEL=llama-3.3-70b-versatile" >> .env

# Step 3: Run DjangoProbe
djangoprobe ~/path/to/your/django/project
```

## Best Setup: Multiple Providers (Maximum Reliability)

```bash
cat > .env << EOF
AI_PREFERRED_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-your_key_here
NVIDIA_MODEL=qwen/qwen3.5-122b-a10b
GROQ_API_KEY=gsk_your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash
EOF

djangoprobe ~/path/to/your/django/project
```

## How It Works

DjangoProbe automatically:
1. Initializes only the providers whose API key is configured
2. Always uses NVIDIA first, then the rest (Anthropic → Groq → Gemini → Together)
3. Rotates to the next available provider on any error or rate limit
4. Handles rate limits and errors gracefully

## Common Commands

```bash
# Run against a local project
djangoprobe ~/path/to/your/django/project

# Run against a git URL
djangoprobe https://github.com/user/repo

# Check the provider system
python tests/test_providers.py

# Show help
djangoprobe --help
```

## Troubleshooting

**No providers available?**
```bash
# Make sure at least one key is set
env | grep -E "NVIDIA|GROQ|GEMINI|ANTHROPIC|TOGETHER"
```

**NVIDIA returns a 404 on the model?**
```bash
# The model id is wrong. Copy the exact id from the model page on
# build.nvidia.com (the code snippet shows model="...").
```

**Provider rate limited?**
```bash
# Configure additional providers so the manager can fall back.
# Groq also supports numbered keys for rotation:
echo "GROQ_API_KEY_1=gsk_key1" >> .env
echo "GROQ_API_KEY_2=gsk_key2" >> .env
```

## Next Steps

- Read the full setup guide: [MULTI_PROVIDER_SETUP.md](MULTI_PROVIDER_SETUP.md)
- Check the main README: [README.md](../README.md)

## Tips

1. **Start with NVIDIA NIM** - free tier, OpenAI-compatible, strong models
2. **Add Groq/Gemini as backups** - automatic fallback on rate limits
3. **Pin the exact NVIDIA model id** from the model page to avoid 404s
4. **Configure multiple providers** - maximum reliability
