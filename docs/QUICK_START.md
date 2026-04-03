# Quick Start Guide - Multi-Provider AI System

Get started with DjangoProbe's multi-provider AI system in minutes!

## Fastest Setup (Ollama - Completely Free)

```bash
# Step 1: Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Step 2: Start Ollama and download a model
ollama serve &
ollama pull llama3.2

# Step 3: Run DjangoProbe
djangoprobe ~/path/to/your/django/project
```

That's it! No API keys needed.

## Alternative: Groq API (Fast Remote)

```bash
# Step 1: Get API key
# Visit: https://console.groq.com/keys

# Step 2: Add to .env
echo "GROQ_API_KEY=gsk_your_key_here" > .env
echo "GROQ_MODEL=llama-3.1-8b-instant" >> .env

# Step 3: Run DjangoProbe
djangoprobe ~/path/to/your/django/project
```

## Best Setup: Multiple Providers

```bash
# Step 1: Install Ollama (optional but recommended)
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &
ollama pull llama3.2

# Step 2: Add API keys to .env
cat > .env << EOF
GROQ_API_KEY=gsk_your_groq_key
GROQ_MODEL=llama-3.1-8b-instant
TOGETHER_API_KEY=your_together_key
EOF

# Step 3: Run DjangoProbe
djangoprobe ~/path/to/your/django/project
```

## How It Works

DjangoProbe automatically:
1. Detects available providers (Ollama, Groq, Together)
2. Uses the best available provider
3. Automatically falls back to other providers if one fails
4. Handles rate limits and errors gracefully

## Common Commands

```bash
# Check Ollama status
ollama list

# Download a different Ollama model
ollama pull mistral

# Test Ollama
ollama run llama3.2 "Hello, how are you?"

# Check DjangoProbe status
djangoprobe --help
```

## Troubleshooting

**Ollama not working?**
```bash
# Make sure Ollama is running
pgrep ollama  # Should show process ID

# Start it if not running
ollama serve
```

**Groq rate limits?**
```bash
# Add multiple API keys
echo "GROQ_API_KEY_1=gsk_key1" >> .env
echo "GROQ_API_KEY_2=gsk_key2" >> .env
echo "GROQ_API_KEY_3=gsk_key3" >> .env
```

**Provider not detected?**
```bash
# Check environment variables
env | grep -E "GROQ|TOGETHER|OLLAMA"

# Test Ollama connection
curl http://localhost:11434/api/tags
```

## Next Steps

- Read the full setup guide: [MULTI_PROVIDER_SETUP.md](MULTI_PROVIDER_SETUP.md)
- Check the main README: [README.md](../README.md)
- Configure custom models and providers

## Tips

1. **Start with Ollama** - It's free and has no rate limits
2. **Add Groq as backup** - Fast when Ollama is slow
3. **Use smaller models** - Faster and higher rate limits
4. **Configure multiple providers** - Maximum reliability

## Support

- Documentation: [MULTI_PROVIDER_SETUP.md](MULTI_PROVIDER_SETUP.md)
- Issues: GitHub Issues
- Discussions: GitHub Discussions