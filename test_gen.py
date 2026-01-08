import google.generativeai as genai
import os
import config

# Make sure GENAI_API_KEY is set
api_key = config.GENAI_API_KEY or os.getenv("GENAI_API_KEY")

if not api_key:
    raise Exception("Set GENAI_API_KEY environment variable or in config.py!")

genai.configure(api_key=api_key)

model = genai.GenerativeModel("gemini-2.0-flash")

prompt = "Hello, respond as a playful AI assistant called Honey."

try:
    response = model.generate_content(prompt)
    print("Gemini says:", response.text)
except Exception as e:
    print(f"Error: {e}")
