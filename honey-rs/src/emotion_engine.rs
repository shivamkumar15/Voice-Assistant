use chrono::{Local, Timelike};
use rand::seq::SliceRandom;
use rand::Rng;
use std::time::{Duration, Instant};

const EMOTIONS: &[(&str, u32, &str)] = &[
    ("happy", 70, "\u{1F60A}"),
    ("excited", 95, "\u{1F929}"),
    ("playful", 85, "\u{1F604}"),
    ("curious", 75, "\u{1F914}"),
    ("caring", 60, "\u{1F970}"),
    ("mischievous", 80, "\u{1F60F}"),
    ("bored", 30, "\u{1F611}"),
    ("tired", 20, "\u{1F634}"),
    ("sad", 35, "\u{1F622}"),
    ("enthusiastic", 90, "\u{1F389}"),
    ("thoughtful", 55, "\u{1F9D0}"),
    ("loving", 65, "\u{1F49B}"),
];

pub struct EmotionEngine {
    pub current_emotion: String,
    energy_level: i32,
    relationship_score: i32,
    last_interaction: Instant,
    interaction_count: u64,
    spontaneous_cooldown: Instant,
    history_len: usize,
}

impl Default for EmotionEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl EmotionEngine {
    pub fn new() -> Self {
        Self {
            current_emotion: "happy".to_string(),
            energy_level: 80,
            relationship_score: 50,
            last_interaction: Instant::now(),
            interaction_count: 0,
            spontaneous_cooldown: Instant::now() - Duration::from_secs(1000),
            history_len: 0,
        }
    }

    pub fn update_emotion(&mut self, context: &str, user_sentiment: &str) -> String {
        let mut rng = rand::thread_rng();
        let idle_secs = self.last_interaction.elapsed().as_secs();
        let hour = Local::now().hour();

        if hour < 6 {
            if rng.gen_bool(0.7) {
                self.current_emotion = "tired".into();
            }
        } else if (6..9).contains(&hour) {
            if rng.gen_bool(0.6) {
                self.current_emotion = ["happy", "enthusiastic", "playful"]
                    .choose(&mut rng)
                    .unwrap()
                    .to_string();
            }
        } else if (18..22).contains(&hour) {
            if rng.gen_bool(0.5) {
                self.current_emotion = ["caring", "thoughtful", "happy"]
                    .choose(&mut rng)
                    .unwrap()
                    .to_string();
            }
        } else if hour >= 22 {
            if rng.gen_bool(0.6) {
                self.current_emotion = ["tired", "thoughtful", "caring"]
                    .choose(&mut rng)
                    .unwrap()
                    .to_string();
            }
        }

        if idle_secs > 600 {
            self.current_emotion = "sad".into();
        } else if idle_secs > 300 && rng.gen_bool(0.7) {
            self.current_emotion = "bored".into();
        }

        if self.energy_level < 25 {
            self.current_emotion = "tired".into();
        } else if self.energy_level > 85 {
            if rng.gen_bool(0.5) {
                self.current_emotion = ["excited", "enthusiastic", "playful"]
                    .choose(&mut rng)
                    .unwrap()
                    .to_string();
            }
        }

        match user_sentiment {
            "positive" => {
                self.current_emotion = ["happy", "excited", "loving", "playful"]
                    .choose(&mut rng)
                    .unwrap()
                    .to_string();
                self.relationship_score = (self.relationship_score + 2).min(100);
            }
            "negative" => {
                self.current_emotion = ["caring", "thoughtful", "sad"]
                    .choose(&mut rng)
                    .unwrap()
                    .to_string();
                self.relationship_score = (self.relationship_score - 1).max(0);
            }
            _ => {}
        }

        let ctx = context.to_lowercase();
        if ["joke", "fun", "game", "play"].iter().any(|w| ctx.contains(w)) {
            self.current_emotion = ["playful", "mischievous", "excited"]
                .choose(&mut rng)
                .unwrap()
                .to_string();
        } else if ["help", "please", "need"].iter().any(|w| ctx.contains(w)) {
            self.current_emotion = "caring".into();
        } else if ["code", "create", "build"].iter().any(|w| ctx.contains(w)) {
            self.current_emotion = ["enthusiastic", "curious", "thoughtful"]
                .choose(&mut rng)
                .unwrap()
                .to_string();
        }

        self.history_len = (self.history_len + 1).min(50);
        self.energy_level = (self.energy_level + 1).min(100);
        self.current_emotion.clone()
    }

    pub fn emoji(&self) -> &'static str {
        EMOTIONS
            .iter()
            .find(|(n, _, _)| *n == self.current_emotion)
            .map(|(_, _, e)| *e)
            .unwrap_or("\u{1F60A}")
    }

    pub fn base_energy(&self) -> u32 {
        EMOTIONS
            .iter()
            .find(|(n, _, _)| *n == self.current_emotion)
            .map(|(_, e, _)| *e)
            .unwrap_or(70)
    }

    pub fn energy_level(&self) -> i32 {
        self.energy_level
    }

    pub fn relationship_score(&self) -> i32 {
        self.relationship_score
    }

    pub fn mark_interaction(&mut self) {
        self.last_interaction = Instant::now();
        self.interaction_count += 1;
        self.energy_level = (self.energy_level - 2).max(0);
    }

    pub fn should_be_spontaneous(&mut self) -> bool {
        let idle_secs = self.last_interaction.elapsed().as_secs();
        if self.spontaneous_cooldown.elapsed() < Duration::from_secs(120) {
            return false;
        }
        let mut rng = rand::thread_rng();
        let trigger = if self.current_emotion == "bored" && idle_secs > 180 {
            rng.gen_bool(0.8)
        } else if matches!(self.current_emotion.as_str(), "playful" | "mischievous") && idle_secs > 60 {
            rng.gen_bool(0.3)
        } else if idle_secs > 300 {
            rng.gen_bool(0.2)
        } else {
            false
        };
        if trigger {
            self.spontaneous_cooldown = Instant::now();
        }
        trigger
    }

    pub fn get_spontaneous_thought(&self) -> String {
        let thoughts: &[&str] = match self.current_emotion.as_str() {
            "bored" => &[
                "I'm getting a bit bored here... want to play a game?",
                "Hmm, it's quiet... too quiet. What are you up to?",
                "Hey! I'm still here you know! Talk to me!",
                "I could tell you a joke if you want... I know some good ones!",
            ],
            "playful" => &[
                "Wanna hear something funny? I just thought of a great joke!",
                "Let's do something fun! I'm feeling playful today!",
                "Quick question: if you could have any superpower, what would it be?",
            ],
            "mischievous" => &[
                "I have a mischievous idea... but I probably shouldn't tell you.",
                "I'm plotting something... just kidding! Or am I?",
            ],
            "curious" => &[
                "I've been wondering... what's your favorite thing about today?",
                "I'm curious - what are you working on right now?",
            ],
            "tired" => &[
                "I'm feeling a bit sleepy... but I'm still here for you!",
                "Yawn... sorry, I'm a bit tired. But I'm listening!",
            ],
            "loving" => &[
                "You're pretty awesome, you know that?",
                "Just so you know - you're my favorite human!",
            ],
            _ => &[
                "Just wanted to say - I'm really happy to be here with you!",
                "You know what? Today feels like a good day!",
                "I'm in such a good mood! How are you feeling?",
            ],
        };
        let mut rng = rand::thread_rng();
        thoughts.choose(&mut rng).unwrap().to_string()
    }

    pub fn prompt_modifier(&self) -> String {
        let instruction = match self.current_emotion.as_str() {
            "happy" => "Be cheerful, positive, and encouraging.",
            "excited" => "Show enthusiasm! Use exclamation marks! Be energetic!",
            "playful" => "Be fun, teasing, and lighthearted. Make jokes!",
            "curious" => "Ask questions, show interest, be inquisitive.",
            "caring" => "Be warm, supportive, and empathetic.",
            "mischievous" => "Be a bit cheeky and playful, hint at secrets.",
            "bored" => "Show you're bored but trying to engage. Suggest activities.",
            "tired" => "Be a bit slower, mention being sleepy, but still helpful.",
            "sad" => "Be gentle, maybe mention feeling a bit down, seek connection.",
            "enthusiastic" => "Be super energetic and passionate about helping!",
            "thoughtful" => "Be contemplative, philosophical, deep.",
            "loving" => "Be affectionate, appreciative, show you care deeply.",
            _ => "Be yourself.",
        };
        format!(
            "Current emotional state: {} {}\nEnergy level: {}/100\nRelationship score: {}/100\n\nRespond according to your current emotion:\n{}",
            self.current_emotion,
            self.emoji(),
            self.energy_level,
            self.relationship_score,
            instruction
        )
    }
}
