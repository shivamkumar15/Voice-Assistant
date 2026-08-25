use anyhow::{anyhow, Result};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::Duration;
use sysinfo::{Disks, ProcessesToUpdate, Signal, System};
use walkdir::WalkDir;

pub struct FileInfo {
    pub name: String,
    pub path: String,
}

pub struct DesktopController {
    hyprland: bool,
    apps: Vec<(&'static str, &'static [&'static str])>,
}

impl Default for DesktopController {
    fn default() -> Self {
        Self::new()
    }
}

impl DesktopController {
    pub fn new() -> Self {
        let hyprland = std::env::var("HYPRLAND_INSTANCE_SIGNATURE").is_ok();
        Self {
            hyprland,
            apps: vec![
                ("firefox", &["firefox"]),
                ("chrome", &["google-chrome-stable", "google-chrome", "chromium"]),
                ("chromium", &["chromium"]),
                ("edge", &["microsoft-edge", "microsoft-edge-stable"]),
                ("brave", &["brave", "brave-browser"]),
                ("code", &["code"]),
                ("vscode", &["code"]),
                ("spotify", &["spotify"]),
                ("discord", &["discord"]),
                ("telegram", &["telegram-desktop"]),
                ("vlc", &["vlc"]),
                ("mpv", &["mpv"]),
                ("gimp", &["gimp"]),
                ("obs", &["obs"]),
                ("steam", &["steam"]),
                ("files", &["nautilus", "thunar", "dolphin", "pcmanfm"]),
                ("file manager", &["nautilus", "thunar", "dolphin", "pcmanfm"]),
                ("calculator", &["gnome-calculator", "kcalc", "qalculate-gtk"]),
                ("terminal", &["kitty", "alacritty", "foot", "konsole", "gnome-terminal"]),
                ("settings", &["xfce4-settings-manager", "gnome-control-center", "kcmshell6"]),
            ],
        }
    }

    pub fn search_files(&self, query: &str, limit: usize) -> Vec<FileInfo> {
        let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("/"));
        let skip_dirs = [
            ".cache", ".cargo", ".rustup", ".git", ".local", ".config", ".steam",
            ".vscode", ".gradle", ".android", ".npm", ".bun", "node_modules",
            "target", "__pycache__", ".gnupg", ".ssh", ".pki", ".nv",
        ];
        let query_lower = query.to_lowercase();
        let mut results = Vec::new();
        for entry in WalkDir::new(&home)
            .max_depth(8)
            .follow_links(false)
            .into_iter()
            .filter_entry(|e| {
                if e.depth() == 0 {
                    return true;
                }
                let name = e.file_name().to_string_lossy();
                !name.starts_with('.') && !skip_dirs.contains(&name.as_ref())
            })
        {
            let Ok(entry) = entry else { continue };
            if !entry.file_type().is_file() {
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_lowercase();
            if name.contains(&query_lower) {
                results.push(FileInfo {
                    name: entry.file_name().to_string_lossy().into_owned(),
                    path: entry.path().display().to_string(),
                });
                if results.len() >= limit {
                    break;
                }
            }
        }
        results
    }

    pub fn open_file(&self, path: &str) -> Result<()> {
        let status = Command::new("xdg-open")
            .arg(path)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()?;
        if status.success() {
            Ok(())
        } else {
            Err(anyhow!("xdg-open exited with {}", status))
        }
    }

    pub fn launch_application(&self, app_name: &str) -> Result<String> {
        let lower = app_name.trim().to_lowercase();
        for (name, candidates) in &self.apps {
            if *name == lower || name.split(' ').any(|w| w == lower) {
                for bin in *candidates {
                    if which(bin).is_some() {
                        spawn_detached(bin)?;
                        return Ok(format!("Launched {name}!"));
                    }
                }
            }
        }
        if let Some(bin) = which(&lower) {
            spawn_detached(&bin)?;
            return Ok(format!("Launched {lower}!"));
        }
        let out = Command::new("gtk-launch")
            .arg(&lower)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        if matches!(out, Ok(s) if s.success()) {
            return Ok(format!("Launched {lower}!"));
        }
        Err(anyhow!("couldn't find an app called '{app_name}'"))
    }

    pub fn close_application(&self, app_name: &str) -> bool {
        let needle = app_name.to_lowercase();
        let mut sys = System::new_all();
        sys.refresh_processes(ProcessesToUpdate::All, true);
        for (_pid, proc) in sys.processes() {
            let name = proc.name().to_string_lossy().to_lowercase();
            if name.contains(&needle) && !name.contains("honey") {
                if proc.kill_with(Signal::Term).unwrap_or_else(|| proc.kill()) {
                    return true;
                }
            }
        }
        false
    }

    pub fn list_windows(&self) -> Vec<String> {
        if self.hyprland {
            self.hypr_list_windows()
        } else {
            self.x11_list_windows()
        }
    }

    pub fn focus_window(&self, title: &str) -> Result<()> {
        if self.hyprland {
            let addr = self.find_window_address(title)?;
            run_hyprctl(&format!(
                "dispatch focuswindow address:{addr}"
            ))?;
        } else {
            let id = self.x11_find_window(title)?;
            run_xdotool(&["windowactivate", "--sync", &id])?;
        }
        Ok(())
    }

    pub fn close_window(&self, title: &str) -> Result<()> {
        if self.hyprland {
            let addr = self.find_window_address(title)?;
            run_hyprctl(&format!("dispatch closewindow address:{addr}"))?;
        } else {
            let id = self.x11_find_window(title)?;
            run_xdotool(&["windowclose", &id])?;
        }
        Ok(())
    }

    pub fn maximize_window(&self, title: &str) -> Result<()> {
        self.focus_window(title)?;
        if self.hyprland {
            run_hyprctl("dispatch fullscreen 1")?;
        } else {
            run_xdotool(&["key", "super+Up"])?;
        }
        Ok(())
    }

    pub fn minimize_window(&self, title: &str) -> Result<()> {
        self.focus_window(title)?;
        if self.hyprland {
            run_hyprctl("dispatch movetoworkspacesilent special:minimized")?;
        } else {
            let id = self.x11_find_window(title)?;
            run_xdotool(&["windowminimize", &id])?;
        }
        Ok(())
    }

    fn find_window_address(&self, title: &str) -> Result<String> {
        let needle = title.to_lowercase();
        for win in self.hypr_windows()? {
            let t = win
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            let class = win
                .get("class")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            if (t.contains(&needle) || class.contains(&needle)) && !t.is_empty() {
                return win["address"]
                    .as_str()
                    .map(|s| s.to_string())
                    .ok_or_else(|| anyhow!("window has no address"));
            }
        }
        Err(anyhow!("no window matching '{title}'"))
    }

    fn hypr_windows(&self) -> Result<Vec<Value>> {
        let out = Command::new("hyprctl").args(["clients", "-j"]).output()?;
        let v: Value = serde_json::from_slice(&out.stdout)?;
        Ok(v.as_array().cloned().unwrap_or_default())
    }

    fn hypr_list_windows(&self) -> Vec<String> {
        match self.hypr_windows() {
            Ok(wins) => wins
                .iter()
                .filter_map(|w| {
                    let title = w.get("title")?.as_str()?.trim();
                    if title.is_empty() {
                        return None;
                    }
                    let class = w.get("class").and_then(|c| c.as_str()).unwrap_or("?");
                    Some(format!("{class}: {title}"))
                })
                .collect(),
            Err(_) => Vec::new(),
        }
    }

    fn x11_list_windows(&self) -> Vec<String> {
        Command::new("xdotool")
            .args(["search", "--onlyvisible", "--name", "", "getwindowname", "%@"])
            .output()
            .map(|o| {
                String::from_utf8_lossy(&o.stdout)
                    .lines()
                    .filter(|l| !l.trim().is_empty())
                    .map(|l| l.to_string())
                    .collect()
            })
            .unwrap_or_default()
    }

    fn x11_find_window(&self, title: &str) -> Result<String> {
        let out = Command::new("xdotool")
            .args(["search", "--name", title])
            .output()?;
        let first = String::from_utf8_lossy(&out.stdout)
            .lines()
            .next()
            .unwrap_or("")
            .trim()
            .to_string();
        if first.is_empty() {
            Err(anyhow!("no window matching '{title}'"))
        } else {
            Ok(first)
        }
    }

    pub fn create_folder(&self, name: &str) -> Result<PathBuf> {
        let desktop = dirs::home_dir()
            .ok_or_else(|| anyhow!("cannot find home dir"))?
            .join("Desktop")
            .join(name);
        std::fs::create_dir_all(&desktop)?;
        Ok(desktop)
    }

    pub fn delete_file(&self, path: &str) -> Result<()> {
        std::fs::remove_file(path)?;
        Ok(())
    }

    pub fn system_info(&self) -> String {
        let mut sys = System::new_all();
        sys.refresh_cpu_usage();
        thread::sleep(Duration::from_millis(400));
        sys.refresh_cpu_usage();
        sys.refresh_memory();

        let cpu = sys.global_cpu_usage();
        let mem_total = sys.total_memory();
        let mem_used = sys.used_memory();
        let mem_pct = if mem_total > 0 {
            mem_used as f32 / mem_total as f32 * 100.0
        } else {
            0.0
        };

        let disks = Disks::new_with_refreshed_list();
        let (disk_pct, disk_free) = disks
            .list()
            .iter()
            .find(|d| d.mount_point() == Path::new("/"))
            .map(|d| {
                let pct = if d.total_space() > 0 {
                    (d.total_space() - d.available_space()) as f32 / d.total_space() as f32 * 100.0
                } else {
                    0.0
                };
                (pct, d.available_space())
            })
            .unwrap_or((0.0, 0));

        let battery = battery_percent().map(|p| format!("{p:.0}%"));

        let mut out = format!(
            "System status:\nCPU: {cpu:.1}%\nMemory: {:.1}%\nDisk: {disk_pct:.1}% used ({:.1} GB free)",
            mem_pct,
            disk_free as f64 / 1e9
        );
        if let Some(b) = battery {
            out.push_str(&format!("\nBattery: {b}"));
        }
        out
    }
}

fn spawn_detached(bin: &str) -> Result<()> {
    Command::new(bin)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .stdin(std::process::Stdio::null())
        .spawn()?;
    Ok(())
}

fn battery_percent() -> Option<f64> {
    let base = std::path::Path::new("/sys/class/power_supply");
    let mut entries: Vec<_> = std::fs::read_dir(base)
        .ok()?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| {
            p.file_name()
                .map(|n| n.to_string_lossy().starts_with("BAT"))
                .unwrap_or(false)
        })
        .collect();
    entries.sort();
    let bat = entries.first()?;
    let cap = std::fs::read_to_string(bat.join("capacity")).ok()?;
    cap.trim().parse::<f64>().ok()
}

fn which(bin: &str) -> Option<String> {
    if bin.contains('/') {
        let p = PathBuf::from(bin);
        return p.exists().then(|| bin.to_string());
    }
    let path = std::env::var("PATH").ok()?;
    for dir in path.split(':') {
        let candidate = PathBuf::from(dir).join(bin);
        if candidate.is_file() {
            return Some(candidate.display().to_string());
        }
    }
    None
}

fn run_hyprctl(args: &str) -> Result<()> {
    let out = Command::new("hyprctl").arg(args).output()?;
    if out.status.success() {
        Ok(())
    } else {
        Err(anyhow!(
            "hyprctl failed: {}",
            String::from_utf8_lossy(&out.stderr)
        ))
    }
}

fn run_xdotool(args: &[&str]) -> Result<()> {
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
