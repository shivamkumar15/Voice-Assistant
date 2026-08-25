use std::process::{Command, Stdio};

pub struct Speaker {
    enabled: bool,
}

impl Default for Speaker {
    fn default() -> Self {
        Self::new()
    }
}

impl Speaker {
    pub fn new() -> Self {
        let enabled = Command::new("espeak-ng")
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok();
        Self { enabled }
    }

    pub fn speak(&self, text: &str) {
        if !self.enabled {
            return;
        }
        let clean = clean_for_speech(text);
        if clean.is_empty() {
            return;
        }
        let _ = Command::new("espeak-ng")
            .args(["-v", "en+f3", "-s", "165", "-a", "180", &clean])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

fn clean_for_speech(text: &str) -> String {
    text.chars()
        .filter(|c| {
            let c = *c;
            c.is_ascii_graphic() || c == ' ' || c == '\n'
        })
        .collect::<String>()
        .replace(['*', '_', '`', '#', '>', '|'], " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
