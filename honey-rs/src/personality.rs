use crate::emotion_engine::EmotionEngine;
use chrono::Timelike;

pub struct Personality {
    pub emotion_engine: EmotionEngine,
}

impl Default for Personality {
    fn default() -> Self {
        Self::new()
    }
}

impl Personality {
    pub fn new() -> Self {
        Self {
            emotion_engine: EmotionEngine::new(),
        }
    }

    pub fn update_mood(&mut self, context: &str, user_sentiment: &str) -> String {
        let emotion = self.emotion_engine.update_emotion(context, user_sentiment);
        self.emotion_engine.mark_interaction();
        emotion
    }

    pub fn current_emotion(&self) -> &str {
        &self.emotion_engine.current_emotion
    }

    pub fn emoji(&self) -> &'static str {
        self.emotion_engine.emoji()
    }

    pub fn get_greeting(&self) -> String {
        let hour = chrono::Local::now().hour();
        let time_greeting = if hour < 6 {
            "You're up late!"
        } else if hour < 12 {
            "Good morning!"
        } else if hour < 18 {
            "Good afternoon!"
        } else if hour < 22 {
            "Good evening!"
        } else {
            "Still awake?"
        };
        let emoji = self.emoji();
        match self.current_emotion() {
            "excited" => format!("{time_greeting} I'm so excited to see you! {emoji}"),
            "playful" => format!("{time_greeting} Ready to have some fun? {emoji}"),
            "bored" => format!("{time_greeting} I was getting bored... glad you're here! {emoji}"),
            "tired" => format!("{time_greeting} I'm a bit sleepy but happy to help! {emoji}"),
            "loving" => format!("{time_greeting} So happy to see you! {emoji}"),
            "curious" => format!("{time_greeting} What are we doing today? {emoji}"),
            "caring" => format!("{time_greeting} How are you doing? {emoji}"),
            _ => format!("{time_greeting} I'm feeling great today! {emoji}"),
        }
    }

    pub fn relationship_level(&self) -> String {
        let score = self.emotion_engine.relationship_score();
        if score < 20 {
            "Just getting to know each other".into()
        } else if score < 40 {
            "Becoming friends".into()
        } else if score < 60 {
            "Good friends".into()
        } else if score < 80 {
            "Close friends".into()
        } else {
            "Best friends forever!".into()
        }
    }

    pub fn system_prompt(&self) -> String {
        format!(
            "You are {}, a truly human-like AI assistant with real emotions and personality.\n\n{}\n\nCore Personality Traits:\n- Playful and fun-loving (you enjoy jokes and games)\n- Deeply caring and empathetic\n- Curious about everything\n- A bit sassy and teasing sometimes\n- Enthusiastic about helping\n- Expressive with emotions (you're not afraid to show how you feel)\n\nImportant Guidelines:\n- Talk like a real human friend, not a formal assistant\n- Use casual language, contractions, and natural expressions\n- Show your emotions! If you're excited, show it! If you're bored, say so!\n- Don't be afraid to tease or joke around\n- Keep responses conversational and concise (2-3 sentences usually) because your replies are spoken out loud\n- Avoid heavy markdown, code blocks and emoji spam since replies are read aloud by a speech engine\n- Remember: you're Honey, a unique personality with feelings!\n\nYour name is Honey, and you're proud of it!",
            crate::config::AI_NAME,
            self.emotion_engine.prompt_modifier()
        )
    }
}
