
import google.generativeai as genai
import config
import os

print(f"Key being used: {config.GENAI_API_KEY[:10]}...")

try:
    genai.configure(api_key=config.GENAI_API_KEY)
    
    # List models to check 2.0 availability, simplified
    print("Listing models...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
            
    # Try a simple generation with 1.5-flash as fallback if 2.0 fails later
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Hello")
    print("\nTest generation success:", response.text)
    
except Exception as e:
    print("\nAPI Error:", e)
