import random
import time

class Personality:
    def __init__(self):
        self.mood = "happy"
        self.energy = 80
        self.last_interaction = time.time()

    def update_mood(self):
        idle_time = time.time() - self.last_interaction

        if idle_time > 3600:
            self.mood = "bored"
        elif self.energy < 30:
            self.mood = "tired"
        else:
            self.mood = random.choice(["happy", "playful", "curious"])

    def prompt_modifier(self):
        return f"""
You are Honey, a human-like AI assistant.
Current mood: {self.mood}
Personality: caring, playful, slightly teasing, emotional.
Talk naturally like a human.
"""
