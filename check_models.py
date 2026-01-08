import google.generativeai as genai

genai.configure(api_key='AIzaSyDserkJC7sNh1a9fdaXeCR0wCE6OQITdLQ')

print("Available models with generateContent support:")
print("-" * 60)

for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"Model: {model.name}")
        print(f"  Display Name: {model.display_name}")
        print(f"  Methods: {model.supported_generation_methods}")
        print()
