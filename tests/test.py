# test.py
from openai import OpenAI

client = OpenAI(
    api_key  = "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",
    base_url = "https://api.groq.com/openai/v1",
)

response = client.chat.completions.create(
    model    = "llama-3.3-70b-versatile",
    messages = [
        {"role": "system", "content": "Return only Python code."},
        {"role": "user",   "content": "Write a Django test that checks 1+1==2"},
    ],
    max_tokens = 100,
)
print(response.choices[0].message.content)