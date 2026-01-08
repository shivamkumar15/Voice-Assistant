import os
import google.generativeai as genai
from personality import Personality
import config
import time

personality = Personality()

# Check API key
if not config.GENAI_API_KEY:
    raise Exception("Set GENAI_API_KEY in environment variables!")

# Configure the SDK
genai.configure(api_key=config.GENAI_API_KEY)

# Create chat model
model = genai.GenerativeModel("gemini-2.0-flash")
chat = model.start_chat(history=[])

def think(user_input):
    personality.last_interaction = time.time()
    personality.update_mood()

    system_prompt = f"""You are Honey, a human-like AI assistant.
Personality: caring, playful, emotional, slightly teasing.
Current mood: {personality.mood}
Talk naturally like a real human. Keep responses concise."""

    # Note: Gemini 1.5 Flash doesn't support system instructions in the same way as Pro 1.0 via this method cleanly in all versions like this, 
    # so we'll prepend the persona to the user message for simpler stateless or stateful interactions for now, 
    # or rely on the chat history. To keep it robust, we'll send it as context.
    
    try:
        response = chat.send_message(f"{system_prompt}\n\nUser: {user_input}")
        return response.text
    except Exception as e:
        return f"I'm having trouble thinking right now. ({e})"
