import os
import google.generativeai as genai
from personality import Personality
import config
import time
from command_parser import CommandParser

personality = Personality()
command_parser = CommandParser()

# Check API key
if not config.GENAI_API_KEY:
    config.GENAI_API_KEY = os.getenv("GENAI_API_KEY")

chat = None
model = None
model_name = "gemini-1.5-flash" # Default

def init_brain():
    global chat, model, model_name
    try:
        if config.GENAI_API_KEY:
            genai.configure(api_key=config.GENAI_API_KEY)
            
            # Find the first available model that supports generateContent
            available_models = []
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
            except Exception as e:
                print(f"Error listing models: {e}")
            
            # Select model (prefer gemini-1.5-flash, then pro, then any)
            
            # Priority list
            priorities = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
            
            found_model = False
            for priority in priorities:
                # Check if this priority model exists in available_models (partial match)
                for avail in available_models:
                    if priority in avail:
                        model_name = avail
                        found_model = True
                        break
                if found_model:
                    break
            
            # If no priority model found, just take the first available one
            if not found_model and available_models:
                model_name = available_models[0]
                
            print(f"Using model: {model_name}")

            # We'll create the model without system instruction first
            # and update it dynamically based on emotion
            model = genai.GenerativeModel(model_name)
            
            # Start chat with initial personality
            initial_instruction = personality.prompt_modifier()
            model_with_instruction = genai.GenerativeModel(
                model_name, 
                system_instruction=initial_instruction
            )
            chat = model_with_instruction.start_chat(history=[])
            
            print("Brain initialized successfully.")
        else:
            print("Warning: GENAI_API_KEY not found.")
            chat = None
    except Exception as e:
        print(f"Error initializing brain: {e}")
        chat = None

# Initialize on load
init_brain()

def think(user_input: str, force_emotion: str = None) -> str:
    """
    Process user input and generate response with emotional awareness
    
    Args:
        user_input: The user's message
        force_emotion: Optional emotion to force (for testing)
    
    Returns:
        AI response as string
    """
    global chat, model, model_name
    
    if not chat:
        return "I'm sorry, my brain isn't connected. Please check my API key."

    try:
        # First, check if this is a desktop control command
        if command_parser.is_desktop_command(user_input):
            success, result = command_parser.parse_and_execute(user_input)
            if success:
                # Command executed successfully
                # Update emotion to enthusiastic since we did something!
                personality.update_mood(context=user_input, user_sentiment="positive")
                return result
            else:
                # Command failed, let AI handle it with context
                personality.update_mood(context=user_input, user_sentiment="neutral")
                # Tell AI about the failure so it can respond appropriately
                context_message = f"[Desktop command attempted but failed: {result}]\n\nUser: {user_input}"
                response = chat.send_message(context_message)
                return response.text
        
        # Not a desktop command, proceed with normal AI response
        # Detect user sentiment (simple keyword-based for now)
        user_sentiment = detect_sentiment(user_input)
        
        # Update personality/emotion based on context
        personality.update_mood(context=user_input, user_sentiment=user_sentiment)
        
        if force_emotion:
            personality.emotion_engine.current_emotion = force_emotion
        
        # Get current emotion data
        emotion_data = personality.get_current_emotion()
        
        # Recreate chat with updated personality prompt
        # This ensures the AI responds according to current emotion
        updated_instruction = personality.prompt_modifier()
        model_with_emotion = genai.GenerativeModel(
            model_name,
            system_instruction=updated_instruction
        )
        
        # We need to maintain chat history, so we'll use the existing chat
        # but inject emotion context into the message
        emotion_context = f"[You are currently feeling {emotion_data['name']} {emotion_data['emoji']}]"
        enhanced_input = f"{emotion_context}\n\nUser: {user_input}"
        
        response = chat.send_message(enhanced_input)
        return response.text
        
    except Exception as e:
        return f"I'm having trouble thinking right now. ({e})"

def detect_sentiment(text: str) -> str:
    """Simple sentiment detection based on keywords"""
    text_lower = text.lower()
    
    positive_words = ["thanks", "thank you", "great", "awesome", "love", "good", 
                     "excellent", "wonderful", "amazing", "perfect", "yes", "yay"]
    negative_words = ["bad", "hate", "terrible", "awful", "no", "stop", 
                     "wrong", "error", "problem", "issue", "sad", "angry"]
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    else:
        return "neutral"

def get_spontaneous_thought() -> str:
    """Check if Honey wants to say something spontaneous"""
    if personality.should_be_spontaneous():
        return personality.get_spontaneous_message()
    return None

def get_current_emotion_data():
    """Get current emotion information for GUI display"""
    return personality.get_current_emotion()

def get_relationship_status():
    """Get relationship level description"""
    return personality.get_relationship_level()

