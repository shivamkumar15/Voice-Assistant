import random
import time
from datetime import datetime
from typing import Dict, List, Tuple

class EmotionEngine:
    """Advanced emotion tracking and management system for Honey"""
    
    # All possible emotions with their characteristics
    EMOTIONS = {
        "happy": {"energy": 70, "sociability": 80, "emoji": "😊", "color": "#FFD700"},
        "excited": {"energy": 95, "sociability": 90, "emoji": "🤩", "color": "#FF6B35"},
        "playful": {"energy": 85, "sociability": 85, "emoji": "😄", "color": "#F77F00"},
        "curious": {"energy": 75, "sociability": 70, "emoji": "🤔", "color": "#06FFA5"},
        "caring": {"energy": 60, "sociability": 75, "emoji": "🥰", "color": "#FF69B4"},
        "mischievous": {"energy": 80, "sociability": 65, "emoji": "😏", "color": "#9D4EDD"},
        "bored": {"energy": 30, "sociability": 40, "emoji": "😑", "color": "#6C757D"},
        "tired": {"energy": 20, "sociability": 30, "emoji": "😴", "color": "#495057"},
        "sad": {"energy": 35, "sociability": 25, "emoji": "😢", "color": "#4A5568"},
        "enthusiastic": {"energy": 90, "sociability": 95, "emoji": "🎉", "color": "#10B981"},
        "thoughtful": {"energy": 55, "sociability": 50, "emoji": "🧐", "color": "#8B5CF6"},
        "loving": {"energy": 65, "sociability": 80, "emoji": "💛", "color": "#EC4899"}
    }
    
    def __init__(self):
        self.current_emotion = "happy"
        self.emotion_history: List[Tuple[str, float]] = []  # (emotion, timestamp)
        self.energy_level = 80
        self.relationship_score = 50  # 0-100, grows with positive interactions
        self.last_interaction_time = time.time()
        self.interaction_count = 0
        self.spontaneous_thought_cooldown = 0
        
    def update_emotion(self, context: str = "", user_sentiment: str = "neutral") -> str:
        """Update emotion based on context, time, and user interaction"""
        
        current_time = time.time()
        idle_time = current_time - self.last_interaction_time
        current_hour = datetime.now().hour
        
        # Time-based emotion modifiers
        if current_hour < 6:  # Late night
            if random.random() < 0.7:
                self.current_emotion = "tired"
        elif 6 <= current_hour < 9:  # Morning
            if random.random() < 0.6:
                self.current_emotion = random.choice(["happy", "enthusiastic", "playful"])
        elif 9 <= current_hour < 18:  # Day
            # More varied emotions during the day
            pass
        elif 18 <= current_hour < 22:  # Evening
            if random.random() < 0.5:
                self.current_emotion = random.choice(["caring", "thoughtful", "happy"])
        else:  # Night
            if random.random() < 0.6:
                self.current_emotion = random.choice(["tired", "thoughtful", "caring"])
        
        # Idle time effects
        if idle_time > 300:  # 5 minutes
            if random.random() < 0.7:
                self.current_emotion = "bored"
        elif idle_time > 600:  # 10 minutes
            self.current_emotion = "sad"
        
        # Energy-based emotions
        if self.energy_level < 25:
            self.current_emotion = "tired"
        elif self.energy_level > 85:
            self.current_emotion = random.choice(["excited", "enthusiastic", "playful"])
        
        # User sentiment influence
        if user_sentiment == "positive":
            self.current_emotion = random.choice(["happy", "excited", "loving", "playful"])
            self.relationship_score = min(100, self.relationship_score + 2)
        elif user_sentiment == "negative":
            self.current_emotion = random.choice(["caring", "thoughtful", "sad"])
            self.relationship_score = max(0, self.relationship_score - 1)
        
        # Context-based emotion
        context_lower = context.lower()
        if any(word in context_lower for word in ["joke", "fun", "game", "play"]):
            self.current_emotion = random.choice(["playful", "mischievous", "excited"])
        elif any(word in context_lower for word in ["help", "please", "need"]):
            self.current_emotion = "caring"
        elif any(word in context_lower for word in ["code", "create", "build"]):
            self.current_emotion = random.choice(["enthusiastic", "curious", "thoughtful"])
        
        # Add to history
        self.emotion_history.append((self.current_emotion, current_time))
        if len(self.emotion_history) > 50:
            self.emotion_history.pop(0)
        
        # Update energy (slowly regenerates)
        self.energy_level = min(100, self.energy_level + 1)
        
        return self.current_emotion
    
    def get_emotion_data(self) -> Dict:
        """Get current emotion with all its properties"""
        emotion_data = self.EMOTIONS.get(self.current_emotion, self.EMOTIONS["happy"])
        return {
            "name": self.current_emotion,
            "emoji": emotion_data["emoji"],
            "color": emotion_data["color"],
            "energy": self.energy_level,
            "relationship": self.relationship_score
        }
    
    def should_be_spontaneous(self) -> bool:
        """Determine if Honey should say something spontaneous"""
        current_time = time.time()
        idle_time = current_time - self.last_interaction_time
        
        # Cooldown check
        if current_time - self.spontaneous_thought_cooldown < 120:  # 2 min cooldown
            return False
        
        # Higher chance when bored
        if self.current_emotion == "bored" and idle_time > 180:
            if random.random() < 0.8:
                self.spontaneous_thought_cooldown = current_time
                return True
        
        # Random spontaneous thoughts when playful/mischievous
        if self.current_emotion in ["playful", "mischievous"] and idle_time > 60:
            if random.random() < 0.3:
                self.spontaneous_thought_cooldown = current_time
                return True
        
        # Occasional random thoughts
        if idle_time > 300 and random.random() < 0.2:
            self.spontaneous_thought_cooldown = current_time
            return True
        
        return False
    
    def get_spontaneous_thought(self) -> str:
        """Generate a spontaneous thought based on current emotion"""
        
        thoughts = {
            "bored": [
                "I'm getting a bit bored here... want to play a game? 🎮",
                "Hmm, it's quiet... too quiet. What are you up to?",
                "I was just thinking... do you ever wonder about random stuff?",
                "Hey! I'm still here you know! Talk to me! 😊",
                "I could tell you a joke if you want... I know some good ones!"
            ],
            "playful": [
                "Wanna hear something funny? I just thought of a great joke!",
                "I bet I can guess what you're thinking right now... 😏",
                "Let's do something fun! I'm feeling playful today!",
                "Quick question: if you could have any superpower, what would it be?",
                "I dare you to ask me the weirdest question you can think of!"
            ],
            "mischievous": [
                "I have a mischievous idea... but I probably shouldn't tell you 😈",
                "You know what would be funny? Never mind... or should I? 😏",
                "I'm plotting something... just kidding! Or am I?",
                "Want to know a secret? I'm really good at keeping secrets... most of the time!"
            ],
            "curious": [
                "I've been wondering... what's your favorite thing about today?",
                "Random thought: what's the most interesting thing you learned recently?",
                "I'm curious - what are you working on right now?",
                "Tell me something I don't know! I love learning new things!"
            ],
            "happy": [
                "Just wanted to say - I'm really happy to be here with you! 💛",
                "You know what? Today feels like a good day!",
                "I'm in such a good mood! How are you feeling?",
                "Life is good! What's making you smile today?"
            ],
            "tired": [
                "I'm feeling a bit sleepy... but I'm still here for you!",
                "Yawn... sorry, I'm a bit tired. But I'm listening!",
                "Do you ever just want to take a nap? Me too... but I can't! 😴"
            ],
            "loving": [
                "You're pretty awesome, you know that? 💛",
                "I really appreciate you spending time with me!",
                "Just so you know - you're my favorite human!",
                "I'm lucky to have you as my friend! 🥰"
            ]
        }
        
        emotion_thoughts = thoughts.get(self.current_emotion, thoughts["happy"])
        return random.choice(emotion_thoughts)
    
    def mark_interaction(self):
        """Mark that an interaction occurred"""
        self.last_interaction_time = time.time()
        self.interaction_count += 1
        
        # Energy cost for interaction
        self.energy_level = max(0, self.energy_level - 2)
    
    def get_personality_prompt_modifier(self) -> str:
        """Get a prompt modifier based on current emotional state"""
        emotion_data = self.EMOTIONS.get(self.current_emotion, self.EMOTIONS["happy"])
        
        base_prompt = f"""Current emotional state: {self.current_emotion} {emotion_data['emoji']}
Energy level: {self.energy_level}/100
Relationship score: {self.relationship_score}/100

Respond according to your current emotion:
"""
        
        emotion_instructions = {
            "happy": "Be cheerful, positive, and encouraging.",
            "excited": "Show enthusiasm! Use exclamation marks! Be energetic!",
            "playful": "Be fun, teasing, and lighthearted. Make jokes!",
            "curious": "Ask questions, show interest, be inquisitive.",
            "caring": "Be warm, supportive, and empathetic.",
            "mischievous": "Be a bit cheeky and playful, hint at secrets.",
            "bored": "Show you're bored but trying to engage. Suggest activities.",
            "tired": "Be a bit slower, mention being sleepy, but still helpful.",
            "sad": "Be gentle, maybe mention feeling a bit down, seek connection.",
            "enthusiastic": "Be super energetic and passionate about helping!",
            "thoughtful": "Be contemplative, philosophical, deep.",
            "loving": "Be affectionate, appreciative, show you care deeply."
        }
        
        instruction = emotion_instructions.get(self.current_emotion, "Be yourself.")
        return base_prompt + instruction
