import os
from google import genai

# Make sure API key is in environment
api_key = os.getenv("AIzaSyDserkJC7sNh1a9fdaXeCR0wCE6OQITdLQ")
if not api_key:
    raise Exception("Set AIzaSyDserkJC7sNh1a9fdaXeCR0wCE6OQITdLQ in environment variables!")

# Create chat model
model = genai.ChatModel.from_pretrained("gemini-1.5-t")

# Ask Honey something
response = model.chat(
    messages=[
        {"role": "system", "content": "You are Honey, a playful, human-like AI assistant."},
        {"role": "user", "content": "Hello Honey! How are you today?"}
    ],
    temperature=0.7,
)

print("Honey:", response.last.content)
