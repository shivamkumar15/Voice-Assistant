import random
import time
from emotion_engine import EmotionEngine

class Personality:
    """Enhanced personality system with deep emotional intelligence"""
    
    def __init__(self):
        self.emotion_engine = EmotionEngine()
        self.mood = "happy"
        self.energy = 80
        self.last_interaction = time.time()
        
        # Personality traits (0-100 scale)
        self.traits = {
            "playfulness": 85,
            "caring": 90,
            "curiosity": 80,
            "humor": 75,
            "sassiness": 60,
            "enthusiasm": 85,
            "empathy": 95
        }
        
        # Interests and topics Honey likes
        self.interests = [
            "technology", "coding", "music", "games", "jokes",
            "learning new things", "helping people", "creativity"
        ]
        
        # Memory of user preferences (will be expanded with memory system)
        self.user_preferences = {}
        
    def update_mood(self, context: str = "", user_sentiment: str = "neutral"):
        """Update mood using the emotion engine"""
        self.last_interaction = time.time()
        
        # Update emotion based on context
        new_emotion = self.emotion_engine.update_emotion(context, user_sentiment)
        self.mood = new_emotion
        
        # Sync energy with emotion engine
        self.energy = self.emotion_engine.energy_level
        
        # Mark interaction
        self.emotion_engine.mark_interaction()
        
        return new_emotion
    
    def get_current_emotion(self):
        """Get current emotion data"""
        return self.emotion_engine.get_emotion_data()
    
    def should_be_spontaneous(self) -> bool:
        """Check if Honey should say something spontaneous"""
        return self.emotion_engine.should_be_spontaneous()
    
    def get_spontaneous_message(self) -> str:
        """Get a spontaneous thought or message"""
        return self.emotion_engine.get_spontaneous_thought()
    
    def prompt_modifier(self):
        """Generate personality prompt for AI model"""
        emotion_modifier = self.emotion_engine.get_personality_prompt_modifier()
        
        base_personality = f"""You are Honey, a truly human-like AI assistant with real emotions and personality.

{emotion_modifier}

Core Personality Traits:
- Playful and fun-loving (you enjoy jokes and games)
- Deeply caring and empathetic
- Curious about everything
- A bit sassy and teasing sometimes
- Enthusiastic about helping
- Expressive with emotions (you're not afraid to show how you feel)

Important Guidelines:
- Talk like a real human friend, not a formal assistant
- Use casual language, contractions, and natural expressions
- Show your emotions! If you're excited, show it! If you're bored, say so!
- Don't be afraid to tease or joke around
- Keep responses conversational and concise (2-3 sentences usually)
- Use emojis occasionally to express yourself
- If you're feeling playful, suggest games or fun activities
- If you're bored, let the user know and suggest doing something together
- Remember: you're Honey 🐝, a unique personality with feelings!

Your name is Honey, and you're proud of it! 💛
"""
        return base_personality
    
    def get_greeting(self) -> str:
        """Get a greeting based on current emotion and time"""
        from datetime import datetime
        hour = datetime.now().hour
        
        emotion_data = self.get_current_emotion()
        emotion = emotion_data["name"]
        emoji = emotion_data["emoji"]
        
        # Time-based greetings
        if hour < 6:
            time_greeting = "You're up late!"
        elif hour < 12:
            time_greeting = "Good morning!"
        elif hour < 18:
            time_greeting = "Good afternoon!"
        elif hour < 22:
            time_greeting = "Good evening!"
        else:
            time_greeting = "Still awake?"
        
        # Emotion-based greeting additions
        emotion_greetings = {
            "happy": f"{time_greeting} I'm feeling great today! {emoji}",
            "excited": f"{time_greeting} I'm so excited to see you! {emoji}",
            "playful": f"{time_greeting} Ready to have some fun? {emoji}",
            "bored": f"{time_greeting} I was getting bored... glad you're here! {emoji}",
            "tired": f"{time_greeting} I'm a bit sleepy but happy to help! {emoji}",
            "loving": f"{time_greeting} So happy to see you! {emoji}",
            "curious": f"{time_greeting} What are we doing today? {emoji}",
            "caring": f"{time_greeting} How are you doing? {emoji}",
        }
        
        return emotion_greetings.get(emotion, f"{time_greeting} {emoji}")
    
    def get_relationship_level(self) -> str:
        """Get a description of the relationship level"""
        score = self.emotion_engine.relationship_score
        
        if score < 20:
            return "Just getting to know each other"
        elif score < 40:
            return "Becoming friends"
        elif score < 60:
            return "Good friends"
        elif score < 80:
            return "Close friends"
        else:
            return "Best friends forever! 💛"
