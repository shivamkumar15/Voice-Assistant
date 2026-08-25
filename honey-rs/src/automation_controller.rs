use anyhow::{anyhow, Result};
use std::process::Command;
use std::thread;
use std::time::Duration;

pub struct KeyboardController {
    wayland: bool,
}

#[derive(Clone, Copy)]
pub struct MouseController {
    pub wayland: bool,
}

pub fn automation_backend() -> &'static str {
    if std::env::var("WAYLAND_DISPLAY").is_ok() {
        "ydotool (Wayland)"
    } else {
        "xdotool (X11)"
    }
}

impl Default for KeyboardController {
    fn default() -> Self {
        Self::new()
    }
}

impl KeyboardController {
    pub fn new() -> Self {
        Self {
            wayland: std::env::var("WAYLAND_DISPLAY").is_ok(),
        }
    }

    pub fn type_text(&self, text: &str) -> Result<()> {
        if self.wayland {
            run_ydotool(&["type", "--", text])
        } else {
            run_xdo(&["type", "--delay", "40", text])
        }
    }

    pub fn press_key(&self, key: &str) -> Result<()> {
        let norm = normalize_key(key);
        if self.wayland {
            let code = evdev_code(&norm)
                .ok_or_else(|| anyhow!("unknown key '{key}'"))?;
            run_ydotool(&["key", &format!("{code}:1"), &format!("{code}:0")])
        } else {
            run_xdo(&["key", &norm])
        }
    }

    pub fn combo(&self, keys: &[&str]) -> Result<()> {
        let mapped: Vec<String> = keys.iter().map(|k| normalize_key(k)).collect();
        if self.wayland {
            let mut codes = Vec::new();
            for k in &mapped {
                codes.push(
                    evdev_code(k)
                        .ok_or_else(|| anyhow!("unknown key '{k}'"))?,
                );
            }
            let mut args: Vec<String> = Vec::new();
            args.push("key".into());
            for c in &codes[..codes.len() - 1] {
                args.push(format!("{c}:1"));
            }
            let last = *codes.last().unwrap();
            args.push(format!("{last}:1"));
            args.push(format!("{last}:0"));
            for c in codes[..codes.len() - 1].iter().rev() {
                args.push(format!("{c}:0"));
            }
            let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
            run_ydotool(&arg_refs)
        } else {
            let combo_str = mapped.join("+");
            run_xdo(&["key", &combo_str])
        }
    }

    pub fn execute_shortcut(&self, name: &str) -> Result<()> {
        let keys: &[&str] = match name.to_lowercase().as_str() {
            "copy" => &["ctrl", "c"],
            "paste" => &["ctrl", "v"],
            "cut" => &["ctrl", "x"],
            "select all" => &["ctrl", "a"],
            "undo" => &["ctrl", "z"],
            "redo" => &["ctrl", "y"],
            "save" => &["ctrl", "s"],
            "find" => &["ctrl", "f"],
            "new tab" => &["ctrl", "t"],
            "close tab" => &["ctrl", "w"],
            "switch window" | "alt tab" => &["alt", "tab"],
            "minimize all" | "show desktop" => &["meta", "d"],
            "screenshot" => &["meta", "shift", "s"],
            "lock screen" => &["meta", "l"],
            "task manager" => &["ctrl", "shift", "escape"],
            _ => return Err(anyhow!("unknown shortcut '{name}'")),
        };
        self.combo(keys)
    }
}

impl MouseController {
    pub fn new() -> Self {
        Self {
            wayland: std::env::var("WAYLAND_DISPLAY").is_ok(),
        }
    }

    pub fn click(&self) -> Result<()> {
        if self.wayland {
            run_ydotool(&["click", "0xC0"])
        } else {
            run_xdo(&["click", "1"])
        }
    }

    pub fn double_click(&self) -> Result<()> {
        self.click()?;
        thread::sleep(Duration::from_millis(60));
        self.click()
    }

    pub fn right_click(&self) -> Result<()> {
        if self.wayland {
            run_ydotool(&["click", "0xC1"])
        } else {
            run_xdo(&["click", "3"])
        }
    }

    pub fn scroll_up(&self) -> Result<()> {
        if self.wayland {
            Err(anyhow!(
                "mouse wheel scrolling isn't supported by ydotool on Wayland yet"
            ))
        } else {
            run_xdo(&["click", "4"])
        }
    }

    pub fn scroll_down(&self) -> Result<()> {
        if self.wayland {
            Err(anyhow!(
                "mouse wheel scrolling isn't supported by ydotool on Wayland yet"
            ))
        } else {
            run_xdo(&["click", "5"])
        }
    }
}

fn normalize_key(key: &str) -> String {
    match key.trim().to_lowercase().as_str() {
        "enter" | "return" => "Return".into(),
        "space" | "spacebar" => "space".into(),
        "escape" | "esc" => "Escape".into(),
        "backspace" => "BackSpace".into(),
        "delete" | "del" => "Delete".into(),
        "up" | "arrow up" => "Up".into(),
        "down" | "arrow down" => "Down".into(),
        "left" | "arrow left" => "Left".into(),
        "right" | "arrow right" => "Right".into(),
        "control" | "ctl" => "ctrl".into(),
        "windows" | "super" | "cmd" | "command" => "meta".into(),
        other => other.trim().to_string(),
    }
}

fn evdev_code(key: &str) -> Option<u16> {
    let k = key.to_lowercase();
    let named: Option<u16> = match k.as_str() {
        "escape" | "esc" => Some(1),
        "tab" => Some(15),
        "ctrl" | "control" | "leftctrl" => Some(29),
        "shift" | "leftshift" => Some(42),
        "alt" | "leftalt" => Some(56),
        "space" => Some(57),
        "return" | "enter" => Some(28),
        "backspace" => Some(14),
        "capslock" => Some(58),
        "delete" => Some(111),
        "meta" | "super" => Some(125),
        "up" => Some(103),
        "left" => Some(105),
        "right" => Some(106),
        "down" => Some(108),
        _ => None,
    };
    if let Some(c) = named {
        return Some(c);
    }
    if k.len() == 1 {
        let c = k.chars().next().unwrap();
        if c.is_ascii_lowercase() {
            return Some(30 + (c as u16 - 'a' as u16));
        }
        if c.is_ascii_digit() {
            if c == '0' {
                return Some(11);
            }
            return Some(1 + (c as u16 - '0' as u16));
        }
    }
    None
}

fn run_ydotool(args: &[&str]) -> Result<()> {
    let out = Command::new("ydotool").args(args).output()?;
    if out.status.success() {
        Ok(())
    } else {
        let stderr = String::from_utf8_lossy(&out.stderr);
        Err(anyhow!(
            "ydotool failed: {}. Is ydotoold running? Try: sudo systemctl enable --now ydotoold",
            stderr.trim()
        ))
    }
}

fn run_xdo(args: &[&str]) -> Result<()> {
    let out = Command::new("xdotool").args(args).output()?;
    if out.status.success() {
        Ok(())
    } else {
        Err(anyhow!(
            "xdotool failed: {}",
            String::from_utf8_lossy(&out.stderr)
        ))
    }
}
