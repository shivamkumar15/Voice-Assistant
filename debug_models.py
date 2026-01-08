import google.generativeai as genai
import os

# Use the specific API key
genai.configure(api_key='AIzaSyDserkJC7sNh1a9fdaXeCR0wCE6OQITdLQ')

print("\n🔍 Checking available models...\n")

try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ FOUND: {m.name}")
except Exception as e:
    print(f"❌ Error listing models: {e}")
