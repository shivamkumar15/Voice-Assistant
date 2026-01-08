import os

AI_NAME = "Honey"
USER_NAME = "Shivam"

# Must match exactly what brain.py expects
# First try environment variable, then fallback to direct value if needed
GENAI_API_KEY = os.getenv("GENAI_API_KEY") or "AIzaSyDserkJC7sNh1a9fdaXeCR0wCE6OQITdLQ"
