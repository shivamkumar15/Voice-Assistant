mod automation_controller;
mod brain;
mod command_parser;
mod config;
mod desktop_controller;
mod emotion_engine;
mod personality;
mod time_service;
mod voice_input;
mod voice_output;
mod weather_service;

use anyhow::Result;
use brain::{detect_sentiment, Brain};
use command_parser::CommandParser;
use personality::Personality;
use voice_input::{Recorder, Transcriber};
use voice_output::Speaker;
use weather_service::WeatherService;

fn main() {
    load_dotenv();
    if let Err(e) = run() {
        eprintln!("\u{1F41D} Fatal error: {e:#}");
        std::process::exit(1);
    }
}

fn load_dotenv() {
    let candidates: Vec<std::path::PathBuf> = [
        std::env::current_dir().ok().map(|d| d.join(".env")),
        dirs::home_dir().map(|h| h.join("Voice-Assistant").join("honey-rs").join(".env")),
    ]
    .into_iter()
    .flatten()
    .collect();
    for path in candidates {
        let Ok(contents) = std::fs::read_to_string(&path) else { continue };
        for line in contents.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some((key, value)) = line.split_once('=') {
                let key = key.trim();
                let value = value.trim().trim_matches('"').trim_matches('\'');
                if !key.is_empty() && std::env::var_os(key).is_none() {
                    std::env::set_var(key, value);
                }
            }
        }
        break;
    }
}

fn run() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let text_mode = args.iter().any(|a| a == "--text");
    let no_tts = args.iter().any(|a| a == "--no-tts");

    println!("\u{1F41D} {} is awake...", config::AI_NAME);
    println!("   (Rust edition | backend: {}) ", automation_controller::automation_backend());

    let mut personality = Personality::new();
    let mut parser = CommandParser::new(WeatherService::new(config::openweather_api_key()));
    let speaker = Speaker::new();
    let speak = |s: &str| {
        if !no_tts {
            speaker.speak(s);
        }
    };

    let mut brain = match Brain::from_env() {
        Ok(b) => Some(b),
        Err(e) => {
            println!(
                "\u{26A0}\u{FE0F} Chat disabled: {e}. Desktop commands still work. Set OPENROUTER_API_KEY to enable chat."
            );
            None
        }
    };

    let transcriber = if text_mode {
        None
    } else {
        Some(Transcriber::load_default()?)
    };
    let recorder = Recorder::new();

    let greeting = personality.get_greeting();
    println!("{greeting}");
    speak(&greeting);

    loop {
        let heard: Option<String> = match &transcriber {
            Some(t) => match t.listen_and_transcribe(&recorder) {
                Ok(x) => x,
                Err(e) => {
                    eprintln!("\u{26A0}\u{FE0F} Mic error: {e:#}");
                    continue;
                }
            },
            None => {
                print!("You: ");
                use std::io::Write;
                let _ = std::io::stdout().flush();
                let mut line = String::new();
                if std::io::stdin().read_line(&mut line)? == 0 {
                    break;
                }
                let t = line.trim().to_string();
                if t.is_empty() {
                    continue;
                }
                Some(t)
            }
        };

        let Some(text) = heard else { continue };
        if !text_mode {
            println!("You: {text}");
        }

        let lower = text.to_lowercase();
        if ["exit", "quit", "bye", "good bye", "goodbye", "see you", "shut down"]
            .contains(&lower.as_str())
        {
            let farewell = format!(
                "Okay {}... I'll miss you. Talk soon!",
                config::user_name()
            );
            println!("\u{1F41D} {farewell}");
            speak(&farewell);
            break;
        }

        if CommandParser::is_desktop_command(&text) {
            let (success, result) = parser.parse_and_execute(&text);
            if success {
                personality.update_mood(&text, "positive");
                println!("\u{1F41D} {result}");
                speak(&result);
                continue;
            }
            match &mut brain {
                Some(b) => {
                    let sys_prompt = personality.system_prompt();
                    match b.think_about_failure(&sys_prompt, &text, &result) {
                        Ok(reply) => {
                            println!("\u{1F41D} {reply}");
                            speak(&reply);
                        }
                        Err(e) => {
                            println!("\u{1F41D} {result} (chat unavailable: {e})");
                            speak(&result);
                        }
                    }
                }
                None => {
                    println!("\u{1F41D} {result}");
                    speak(&result);
                }
            }
            continue;
        }

        let sentiment = detect_sentiment(&text);
        personality.update_mood(&text, sentiment);

        match &mut brain {
            Some(b) => {
                let emotion_ctx = format!(
                    "[You are currently feeling {} {}]",
                    personality.current_emotion(),
                    personality.emoji()
                );
                let enhanced = format!("{emotion_ctx}\n\nUser: {text}");
                let sys_prompt = personality.system_prompt();
                match b.think(&sys_prompt, &enhanced) {
                    Ok(reply) => {
                        println!("\u{1F41D} {reply}");
                        speak(&reply);
                    }
                    Err(e) => {
                        let msg = "I'm having trouble thinking right now.";
                        println!("\u{1F41D} {msg} ({e})");
                        speak(msg);
                    }
                }
            }
            None => {
                let msg =
                    "I'm sorry, my brain isn't connected. Please check my API key.";
                println!("\u{1F41D} {msg}");
                speak(msg);
            }
        }
    }

    Ok(())
}
