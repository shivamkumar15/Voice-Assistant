use crate::automation_controller::{automation_backend, KeyboardController, MouseController};
use crate::desktop_controller::DesktopController;
use crate::time_service;
use crate::weather_service::WeatherService;

pub struct CommandParser {
    desktop: DesktopController,
    keyboard: KeyboardController,
    mouse: MouseController,
    weather: WeatherService,
}

type Outcome = (bool, String);

impl CommandParser {
    pub fn new(weather: WeatherService) -> Self {
        Self {
            desktop: DesktopController::new(),
            keyboard: KeyboardController::new(),
            mouse: MouseController::new(),
            weather,
        }
    }

    pub fn is_desktop_command(text: &str) -> bool {
        let lower = text.to_lowercase();
        const KEYWORDS: &[&str] = &[
            "open", "close", "launch", "start", "run", "search", "find",
            "look for", "locate", "minimize", "maximize", "focus",
            "switch to", "go to", "type ", "press", "click", "scroll",
            "copy", "paste", "save", "undo", "redo", "cut", "select all",
            "create folder", "delete", "move", "system info", "system status",
            "what time", "what date", "today's date", "weekend", "weather",
            "temperature", "screenshot", "lock screen", "task manager",
            "windows",
        ];
        KEYWORDS.iter().any(|k| lower.contains(k))
    }

    pub fn parse_and_execute(&mut self, command: &str) -> Outcome {
        let cmd = command.trim().to_lowercase();

        let actions: &[(&str, &str)] = &[
            ("copy", r"^(?:please\s+)?copy(?:\s+(?:this|that|text))?$"),
            ("paste", r"^(?:please\s+)?paste(?:\s+(?:this|that|text))?$"),
            ("save", r"^(?:please\s+)?save(?:\s+(?:this|that|file))?$"),
            ("undo", r"^(?:please\s+)?undo(?:\s+(?:this|that|last))?$"),
            ("double_click", r"^double\s*click$"),
            ("right_click", r"^right\s*click$"),
            ("click", r"^(?:left\s+)?click(?:\s+(?:here|there|mouse))?$"),
            ("scroll_up", r"^scroll\s+up$"),
            ("scroll_down", r"^scroll\s+down$"),
            ("system_info", r"(?:system|computer)\s+(?:info|status|stats)"),
            ("what_time", r"(?:what(?:'s| is)?\s+)?(?:the\s+)?(?:current\s+)?time"),
            ("what_date", r"(?:what(?:'s| is)?\s+)?(?:today'?s?\s+)?date|(?:what\s+day\s+is\s+it)"),
            ("is_weekend", r"(?:is it|it's)\s+(?:the\s+)?weekend"),
            ("weather_in", r"weather\s+(?:in|for|at)\s+(.+)"),
            ("weather", r"(?:what(?:'s| is)|how(?:'s| is)|check|get)\s+(?:the\s+)?weather"),
            ("list_windows", r"(?:list|show)\s+(?:all\s+)?(?:the\s+)?(?:open\s+)?windows|what\s+windows\s+are\s+open"),
            ("minimize_window", r"^minimize\s+(?:the\s+)?window\s+(.+)$"),
            ("maximize_window", r"^maximize\s+(?:the\s+)?window\s+(.+)$|^maximize\s+(.+)$"),
            ("close_window", r"^close\s+(?:the\s+)?window\s+(.+)$|^close\s+window$"),
            ("focus_window", r"^(?:focus|switch to|go to)\s+(?:window\s+)?(.+)$"),
            ("execute_shortcut", r"^(?:execute|do|press)\s+(.+?)\s+(?:shortcut|command)$"),
            ("press_key", r"^press\s+(?:the\s+)?(.+?)(?:\s+key)?$"),
            ("create_folder", r"^create\s+(?:a\s+)?(?:folder|directory)\s+(?:named\s+|called\s+)?(.+)$"),
            ("search_file", r"^(?:search|find|look for|locate)\s+(?:for\s+)?(?:files?\s+)?(?:named\s+|called\s+)?(.+)$"),
            ("open_file_ext", r"^(?:open|show)\s+(?:the\s+)?(.+\.[a-z0-9]{1,5})$"),
            ("open_file", r"^(?:open|show)\s+(?:the\s+)?file\s+(.+)$"),
            ("close_app", r"^close\s+(.+?)(?:\s+app(?:lication)?)?$"),
            ("launch_app", r"^(?:open|launch|start|run)\s+(.+?)(?:\s+app(?:lication)?)?$"),
            ("type_text", r"^type\s+(.+)$"),
        ];

        for (action, pattern) in actions {
            let Ok(re) = regex::Regex::new(pattern) else { continue };
            if let Some(caps) = re.captures(&cmd) {
                return self.execute(action, &caps);
            }
        }

        (
            false,
            "I didn't understand that command. Try something like 'open firefox' or 'find report pdf'.".into(),
        )
    }

    fn execute(&self, action: &str, caps: &regex::Captures) -> Outcome {
        match action {
            "copy" => self.ok_or_err(
                self.keyboard.combo(&["ctrl", "c"]),
                "Copied!",
                "Couldn't copy",
            ),
            "paste" => self.ok_or_err(
                self.keyboard.combo(&["ctrl", "v"]),
                "Pasted!",
                "Couldn't paste",
            ),
            "save" => self.ok_or_err(
                self.keyboard.combo(&["ctrl", "s"]),
                "Saved!",
                "Couldn't save",
            ),
            "undo" => self.ok_or_err(
                self.keyboard.combo(&["ctrl", "z"]),
                "Undone!",
                "Couldn't undo",
            ),
            "click" => self.ok_or_err(self.mouse.click(), "Clicked!", "Couldn't click"),
            "double_click" => self.ok_or_err(self.mouse.double_click(), "Double-clicked!", "Couldn't double-click"),
            "right_click" => self.ok_or_err(self.mouse.right_click(), "Right-clicked!", "Couldn't right-click"),
            "scroll_up" => self.ok_or_err(self.mouse.scroll_up(), "Scrolled up!", "Couldn't scroll"),
            "scroll_down" => self.ok_or_err(self.mouse.scroll_down(), "Scrolled down!", "Couldn't scroll"),

            "system_info" => (true, self.desktop.system_info()),

            "what_time" => (true, time_service::smart_time_response("what time")),
            "what_date" => (true, time_service::smart_time_response("what day")),
            "is_weekend" => (true, time_service::smart_time_response("weekend")),

            "weather_in" => {
                let city = caps.get(1).map(|m| m.as_str().trim()).unwrap_or("");
                (true, self.weather.smart_response(Some(city)))
            }
            "weather" => (true, self.weather.smart_response(None)),

            "list_windows" => {
                let windows = self.desktop.list_windows();
                if windows.is_empty() {
                    (false, "No windows open".into())
                } else {
                    let mut resp = format!("Open windows ({}):\n", windows.len());
                    for w in windows.iter().take(10) {
                        resp.push_str(&format!("- {w}\n"));
                    }
                    (true, resp)
                }
            }

            "minimize_window" | "maximize_window" | "close_window" | "focus_window" => {
                // close_window with no capture means active window
                let title = caps
                    .get(1)
                    .map(|m| m.as_str().trim().to_string())
                    .unwrap_or_default();
                let result = match action {
                    "minimize_window" => self
                        .desktop
                        .minimize_window(&title)
                        .map(|_| format!("Minimized {}!", title)),
                    "maximize_window" => self
                        .desktop
                        .maximize_window(&title)
                        .map(|_| format!("Maximized {}!", title)),
                    "close_window" => {
                        if title.is_empty() {
                            Err(anyhow::anyhow!("no window name given"))
                        } else {
                            self.desktop
                                .close_window(&title)
                                .map(|_| format!("Closed {}!", title))
                        }
                    }
                    _ => self
                        .desktop
                        .focus_window(&title)
                        .map(|_| format!("Switched to {}!", title)),
                };
                match result {
                    Ok(msg) => (true, msg),
                    Err(e) => (false, format!("{e}")),
                }
            }

            "execute_shortcut" => {
                let name = caps.get(1).map(|m| m.as_str()).unwrap_or("").to_string();
                match self.keyboard.execute_shortcut(&name) {
                    Ok(()) => (true, format!("Executed {name} shortcut")),
                    Err(e) => (false, format!("{e}")),
                }
            }

            "press_key" => {
                let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim().to_string();
                match self.keyboard.press_key(&key) {
                    Ok(()) => (true, format!("Pressed {key} key")),
                    Err(e) => (false, format!("Couldn't press {key}: {e}")),
                }
            }

            "type_text" => {
                let text = caps.get(1).map(|m| m.as_str()).unwrap_or("").to_string();
                match self.keyboard.type_text(&text) {
                    Ok(()) => (true, format!("Typed: {text}")),
                    Err(e) => (false, format!("Couldn't type: {e}")),
                }
            }

            "create_folder" => {
                let name = caps.get(1).map(|m| m.as_str()).unwrap_or("").to_string();
                match self.desktop.create_folder(&name) {
                    Ok(p) => (true, format!("Created folder '{}' at {}", name, p.display())),
                    Err(e) => (false, format!("Couldn't create folder '{name}': {e}")),
                }
            }

            "search_file" => {
                let query = caps.get(1).map(|m| m.as_str().trim()).unwrap_or("");
                let results = self.desktop.search_files(query, 5);
                if results.is_empty() {
                    (false, format!("No files found matching '{query}'"))
                } else {
                    let mut resp = format!("Found {} file(s):\n", results.len());
                    for r in results.iter().take(3) {
                        resp.push_str(&format!("- {} at {}\n", r.name, r.path));
                    }
                    (true, resp)
                }
            }

            "open_file_ext" | "open_file" => {
                let filename = caps.get(1).map(|m| m.as_str()).unwrap_or("");
                let results = self.desktop.search_files(filename, 1);
                if results.is_empty() {
                    (false, format!("Couldn't find a file matching '{filename}'"))
                } else {
                    match self.desktop.open_file(&results[0].path) {
                        Ok(()) => (true, format!("Opened {}!", results[0].name)),
                        Err(e) => (false, format!("Couldn't open {}: {e}", results[0].name)),
                    }
                }
            }

            "close_app" => {
                let app = caps.get(1).map(|m| m.as_str().trim()).unwrap_or("").to_string();
                if app == "window" {
                    return (false, "Which window should I close?".into());
                }
                if self.desktop.close_application(&app) {
                    (true, format!("Closed {app}!"))
                } else {
                    (false, format!("Couldn't find or close {app}"))
                }
            }

            "launch_app" => {
                let app = caps.get(1).map(|m| m.as_str().trim()).unwrap_or("").to_string();
                match self.desktop.launch_application(&app) {
                    Ok(msg) => (true, msg),
                    Err(e) => (false, format!("{e}")),
                }
            }

            _ => (
                false,
                format!("Command not implemented yet (backend: {})", automation_backend()),
            ),
        }
    }

    fn ok_or_err(&self, result: anyhow::Result<()>, ok_msg: &str, err_prefix: &str) -> Outcome {
        match result {
            Ok(()) => (true, ok_msg.to_string()),
            Err(e) => (false, format!("{err_prefix}: {e}")),
        }
    }
}
