pub const AI_NAME: &str = "Honey";
const DEFAULT_USER_NAME: &str = "Shivam";

pub fn user_name() -> String {
    std::env::var("HONEY_USER_NAME").unwrap_or_else(|_| DEFAULT_USER_NAME.to_string())
}

pub fn openrouter_api_key() -> Option<String> {
    std::env::var("OPENROUTER_API_KEY")
        .ok()
        .map(|k| k.trim().to_string())
        .filter(|k| !k.is_empty())
}

pub fn model_name() -> String {
    std::env::var("OPENROUTER_MODEL").unwrap_or_else(|_| "stealth/ox-alpha".to_string())
}

pub fn openweather_api_key() -> Option<String> {
    std::env::var("OWM_API_KEY")
        .ok()
        .map(|k| k.trim().to_string())
        .filter(|k| !k.is_empty())
}

pub fn default_city() -> String {
    std::env::var("OWM_CITY").unwrap_or_else(|_| "New York".to_string())
}

pub fn vad_threshold() -> f32 {
    std::env::var("HONEY_VAD_THRESHOLD")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(350.0)
}

pub fn whisper_model_path() -> Option<std::path::PathBuf> {
    std::env::var("HONEY_WHISPER_MODEL").ok().map(PathBuf::from)
}

use std::path::PathBuf;

pub fn model_cache_path() -> PathBuf {
    let base = dirs::cache_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("honey");
    let _ = std::fs::create_dir_all(&base);
    base.join("ggml-tiny.en.bin")
}

pub const WHISPER_MODEL_URL: &str =
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin";
