use anyhow::{anyhow, bail, Result};
use reqwest::blocking::{Client, Response};
use serde_json::{json, Value};
use std::time::Duration;

const DEFAULT_MODEL: &str = "stealth/ox-alpha";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const MAX_ATTEMPTS: u32 = 4;
const INITIAL_BACKOFF: Duration = Duration::from_secs(2);

fn base_url() -> String {
    std::env::var("HONEY_BASE_URL").unwrap_or_else(|_| DEFAULT_BASE_URL.to_string())
}

fn is_retryable(status: reqwest::StatusCode) -> bool {
    status == reqwest::StatusCode::TOO_MANY_REQUESTS || status.is_server_error()
}

fn retry_after(resp: &Response) -> Option<Duration> {
    let secs = resp
        .headers()
        .get(reqwest::header::RETRY_AFTER)?
        .to_str()
        .ok()?
        .trim()
        .parse::<u64>()
        .ok()?;
    Some(Duration::from_secs(secs))
}

pub struct Brain {
    api_key: String,
    pub model: String,
    http: Client,
    history: Vec<(String, String)>,
}

impl Brain {
    pub fn from_env() -> Result<Self> {
        let api_key = crate::config::openrouter_api_key()
            .ok_or_else(|| anyhow!("OPENROUTER_API_KEY not set"))?;
        let http = Client::builder()
            .timeout(Duration::from_secs(120))
            .build()?;
        let mut brain = Self {
            api_key,
            model: crate::config::model_name(),
            http,
            history: Vec::new(),
        };
        brain.resolve_model()?;
        Ok(brain)
    }

    fn resolve_model(&mut self) -> Result<()> {
        let resp = self
            .http
            .get(format!("{}/models", base_url()))
            .send()?;
        if !resp.status().is_success() {
            println!(
                "\u{26A0}\u{FE0F} Couldn't verify model '{}' (catalog HTTP {}), using it anyway.",
                self.model,
                resp.status()
            );
            return Ok(());
        }
        let v: Value = resp.json()?;
        let known = v["data"]
            .as_array()
            .map(|models| models.iter().any(|m| m["id"].as_str() == Some(self.model.as_str())))
            .unwrap_or(false);
        if known {
            println!("Using model: {}", self.model);
            Ok(())
        } else {
            bail!(
                "model '{}' isn't available on your OpenRouter account — check OPENROUTER_MODEL",
                self.model
            )
        }
    }

    fn parse_body(&self, resp: Response) -> Value {
        resp.json().unwrap_or(Value::Null)
    }

    pub fn think(&mut self, system: &str, user_text: &str) -> Result<String> {
        let mut messages = vec![json!({"role": "system", "content": system})];
        for (role, text) in &self.history {
            messages.push(json!({"role": role, "content": text}));
        }
        messages.push(json!({"role": "user", "content": user_text}));

        let body = json!({
            "model": self.model,
            "messages": messages,
        });

        let mut backoff = INITIAL_BACKOFF;
        let mut result: Option<(reqwest::StatusCode, Value)> = None;
        for attempt in 1..=MAX_ATTEMPTS {
            let resp = self
                .http
                .post(format!("{}/chat/completions", base_url()))
                .header("Authorization", format!("Bearer {}", self.api_key))
                .header("X-Title", "Honey")
                .json(&body)
                .send()?;
            let status = resp.status();
            let wait_hint = retry_after(&resp);
            let parsed = self.parse_body(resp);
            if !is_retryable(status) || attempt == MAX_ATTEMPTS {
                result = Some((status, parsed));
                break;
            }
            let wait = wait_hint.unwrap_or(backoff);
            println!(
                "\u{26A0}\u{FE0F} {status} from model, retrying in {}s (attempt {}/{})...",
                wait.as_secs(),
                attempt + 1,
                MAX_ATTEMPTS
            );
            std::thread::sleep(wait);
            backoff = Duration::from_secs((backoff.as_secs() * 2).min(30));
        }
        let Some((status, v)) = result else {
            bail!("no response from model");
        };
        if !status.is_success() {
            let msg = v["error"]["message"]
                .as_str()
                .unwrap_or("unknown error");
            bail!("HTTP {status}: {msg}");
        }
        let text = v["choices"][0]["message"]["content"]
            .as_str()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .ok_or_else(|| anyhow!("empty response from model"))?;

        self.history.push(("user".into(), user_text.into()));
        self.history.push(("assistant".into(), text.clone()));
        while self.history.len() > 40 {
            self.history.remove(0);
            self.history.remove(0);
        }
        Ok(text)
    }

    pub fn think_about_failure(
        &mut self,
        system: &str,
        command: &str,
        failure: &str,
    ) -> Result<String> {
        let enhanced = format!(
            "[A desktop command was attempted but failed: {failure}]\n\nUser said: \"{command}\"\nRespond briefly as Honey."
        );
        self.think(system, &enhanced)
    }

    pub fn reset_history(&mut self) {
        self.history.clear();
    }
}

pub fn detect_sentiment(text: &str) -> &'static str {
    let lower = text.to_lowercase();
    let positive = [
        "thanks", "thank you", "great", "awesome", "love", "good", "excellent",
        "wonderful", "amazing", "perfect", "yes", "yay",
    ];
    let negative = [
        "bad", "hate", "terrible", "awful", "no", "stop", "wrong", "error",
        "problem", "issue", "sad", "angry",
    ];
    let p = positive.iter().filter(|w| lower.contains(*w)).count();
    let n = negative.iter().filter(|w| lower.contains(*w)).count();
    if p > n {
        "positive"
    } else if n > p {
        "negative"
    } else {
        "neutral"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::{Mutex, MutexGuard, OnceLock};

    fn env_lock() -> MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .unwrap_or_else(|e| e.into_inner())
    }

    #[test]
    fn retries_on_429_then_succeeds() {
        let _env = env_lock();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        std::env::set_var("HONEY_BASE_URL", format!("http://{addr}"));
        std::thread::spawn(move || {
            let mut hits = 0;
            for stream in listener.incoming() {
                let mut stream = stream.unwrap();
                let mut buf = [0u8; 4096];
                let _ = stream.read(&mut buf);
                hits += 1;
                if hits <= 2 {
                    stream
                        .write_all(
                            b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                        )
                        .unwrap();
                } else {
                    let body = serde_json::json!({
                        "choices": [{"message": {"content": " recovered "}}]
                    })
                    .to_string();
                    stream
                        .write_all(
                            format!(
                                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                                body.len(),
                                body
                            )
                            .as_bytes(),
                        )
                        .unwrap();
                }
                if hits >= 3 {
                    break;
                }
            }
        });

        let mut brain = Brain {
            api_key: "test".into(),
            model: "test-model".into(),
            http: Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .unwrap(),
            history: Vec::new(),
        };
        let reply = brain.think("be brief", "hi").unwrap();
        assert_eq!(reply, "recovered");
        assert_eq!(brain.history.len(), 2);
    }

    #[test]
    fn gives_up_after_max_attempts_on_429() {
        let _env = env_lock();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        std::env::set_var("HONEY_BASE_URL", format!("http://{addr}"));
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let mut stream = stream.unwrap();
                let mut buf = [0u8; 4096];
                let _ = stream.read(&mut buf);
                stream
                    .write_all(
                        b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 0\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"error\":{\"message\":\"limited\"}}",
                    )
                    .unwrap();
            }
        });

        let mut brain = Brain {
            api_key: "test".into(),
            model: "test-model".into(),
            http: Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .unwrap(),
            history: Vec::new(),
        };
        let err = brain.think("sys", "hi").unwrap_err().to_string();
        assert!(err.contains("429"), "unexpected error: {err}");
    }
}
