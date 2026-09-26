//! Persistent memory vault for Honey.
//!
//! Stores facts the user asks Honey to remember in a small JSON file so the
//! assistant gets smarter over time (mirrors the Python original's
//! `assistant/memory.py` philosophy: tiny file, never raises on load/save).
//!
//! File: ~/.local/share/honey/memory_vault.json

use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

const MAX_MEMORIES: usize = 200;
const MAX_PROMPT_MEMORIES: usize = 8;
const MAX_CONTENT_LEN: usize = 500;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: u64,
    pub content: String,
    pub category: String,
    pub created_at: String,
}

pub struct MemoryVault {
    path: PathBuf,
    memories: Vec<Memory>,
    next_id: u64,
}

fn default_path() -> PathBuf {
    let base = dirs::data_dir()
        .or_else(dirs::home_dir)
        .unwrap_or_else(|| PathBuf::from("."));
    base.join("honey").join("memory_vault.json")
}

impl MemoryVault {
    pub fn open() -> Self {
        Self::open_at(&default_path())
    }

    pub fn open_at(path: &Path) -> Self {
        let mut vault = Self {
            path: path.to_path_buf(),
            memories: Vec::new(),
            next_id: 1,
        };
        vault.load();
        vault
    }

    fn load(&mut self) {
        let Ok(contents) = std::fs::read_to_string(&self.path) else {
            return;
        };
        let Ok(parsed) = serde_json::from_str::<Vec<Memory>>(&contents) else {
            eprintln!("\u{26A0}\u{FE0F} Memory vault file is corrupt, starting fresh.");
            return;
        };
        self.next_id = parsed.iter().map(|m| m.id).max().unwrap_or(0) + 1;
        self.memories = parsed;
    }

    fn save(&self) {
        let Ok(json) = serde_json::to_string_pretty(&self.memories) else {
            return;
        };
        if let Some(parent) = self.path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let tmp = self.path.with_extension("json.tmp");
        if std::fs::write(&tmp, json).is_ok() {
            let _ = std::fs::rename(&tmp, &self.path);
        } else {
            eprintln!("\u{26A0}\u{FE0F} Couldn't save the memory vault.");
        }
    }

    /// Store a new fact. Deduplicates (case-insensitive) and caps the vault.
    pub fn remember(&mut self, content: &str) -> Result<Memory> {
        let content = content
            .trim()
            .trim_end_matches(['.', '?', '!'])
            .to_string();
        if content.is_empty() {
            bail!("there's nothing in that to remember");
        }
        if content.len() > MAX_CONTENT_LEN {
            bail!("that memory is too long (max {MAX_CONTENT_LEN} characters)");
        }
        let lower = content.to_lowercase();
        if let Some(existing) = self
            .memories
            .iter()
            .find(|m| m.content.to_lowercase() == lower)
        {
            return Ok(existing.clone());
        }
        let memory = Memory {
            id: self.next_id,
            category: categorize(&content).to_string(),
            created_at: chrono::Local::now().format("%Y-%m-%d %H:%M").to_string(),
            content,
        };
        self.next_id += 1;
        self.memories.push(memory.clone());
        while self.memories.len() > MAX_MEMORIES {
            self.memories.remove(0);
        }
        self.save();
        Ok(memory)
    }

    /// Keyword-scored recall: memories matching any query token, best first.
    pub fn recall(&self, query: &str) -> Vec<Memory> {
        let tokens = tokenize(query);
        if tokens.is_empty() {
            return Vec::new();
        }
        let mut scored: Vec<(usize, &Memory)> = self
            .memories
            .iter()
            .map(|m| (score_memory(m, &tokens), m))
            .filter(|(s, _)| *s > 0)
            .collect();
        scored.sort_by(|a, b| b.0.cmp(&a.0).then(b.1.id.cmp(&a.1.id)));
        scored.into_iter().map(|(_, m)| m.clone()).collect()
    }

    pub fn all(&self) -> Vec<Memory> {
        self.memories.clone()
    }

    pub fn count(&self) -> usize {
        self.memories.len()
    }

    /// Remove the best match for `query`; returns the removed memory.
    pub fn forget(&mut self, query: &str) -> Option<Memory> {
        let lower = query.trim().to_lowercase();
        let exact = self
            .memories
            .iter()
            .position(|m| m.content.to_lowercase() == lower);
        let idx = exact.or_else(|| {
            let tokens = tokenize(&lower);
            if tokens.is_empty() {
                return None;
            }
            let mut best: Option<(usize, usize)> = None;
            for (idx, m) in self.memories.iter().enumerate() {
                let s = score_memory(m, &tokens);
                if s > 0 && best.map_or(true, |(bs, _)| s > bs) {
                    best = Some((s, idx));
                }
            }
            best.map(|(_, idx)| idx)
        })?;
        let removed = self.memories.remove(idx);
        self.save();
        Some(removed)
    }

    pub fn forget_all(&mut self) -> usize {
        let n = self.memories.len();
        self.memories.clear();
        if n > 0 {
            self.save();
        }
        n
    }

    /// Memories formatted for injection into the brain's system prompt.
    /// With a query, returns the most relevant memories; without, the most
    /// recent ones. Empty string when the vault has nothing useful.
    pub fn prompt_context(&self, query: Option<&str>) -> String {
        let picked: Vec<Memory> = match query {
            Some(q) => self.recall(q).into_iter().take(MAX_PROMPT_MEMORIES).collect(),
            None => self
                .memories
                .iter()
                .rev()
                .take(MAX_PROMPT_MEMORIES)
                .rev()
                .cloned()
                .collect(),
        };
        picked
            .iter()
            .map(|m| format!("- {} (saved {})", m.content, m.created_at))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Try to interpret `text` as a memory-vault command. Returns the spoken
    /// reply when handled, `None` when the text isn't a memory command.
    pub fn try_handle(&mut self, text: &str) -> Option<String> {
        let text = text.trim();
        let lower = text.to_lowercase();

        // Recall / list first so "what do you remember" isn't parsed as "remember".
        if let Some(rest) = strip_any_ci(
            text,
            &[
                "what do you remember about ",
                "what do you remember of ",
                "what do you know about ",
                "what do you remember",
                "do you remember about ",
                "do you remember ",
            ],
        ) {
            let query = rest.trim_end_matches(['?', '!', '.']).trim();
            return Some(self.reply_recall(query));
        }
        if [
            "show memories",
            "show your memories",
            "list memories",
            "list your memories",
            "what's in your memory",
            "whats in your memory",
            "read your memory",
        ]
        .contains(&lower.trim_end_matches(['?', '!', '.']))
        {
            return Some(self.reply_list_all());
        }

        // Wipe everything.
        if lower.contains("forget everything")
            || lower.contains("forget it all")
            || lower.contains("clear your memory")
            || lower.contains("clear memory")
            || lower.contains("wipe your memory")
        {
            let n = self.forget_all();
            return Some(if n == 0 {
                "My memory was already empty. Fresh start!".into()
            } else {
                format!("Done, I forgot all {n} memories. Clean slate!")
            });
        }

        // Store a new fact.
        if let Some(rest) = strip_any_ci(
            text,
            &[
                "remember that ",
                "remember this ",
                "note that ",
                "note this ",
                "remember ",
                "note ",
            ],
        ) {
            let fact = rest.trim_end_matches(['?', '!', '.']).trim();
            if fact.is_empty() {
                return Some(
                    "Tell me what to remember, like: remember that my sister's birthday is May 3rd."
                        .into(),
                );
            }
            // "remember how to open firefox" style requests go to the brain instead.
            if fact.to_lowercase().starts_with("how to")
                || fact.to_lowercase().starts_with("how i")
            {
                return None;
            }
            return Some(self.reply_remember(fact));
        }

        // Forget a specific thing.
        if let Some(rest) = strip_any_ci(
            text,
            &[
                "forget about ",
                "forget that ",
                "forget this ",
                "forget the ",
                "forget ",
            ],
        ) {
            let query = rest.trim_end_matches(['?', '!', '.']).trim();
            if query.is_empty() {
                return Some(
                    "What should I forget? Name it, or say forget everything to wipe the vault."
                        .into(),
                );
            }
            return Some(self.reply_forget(query));
        }

        None
    }

    fn reply_remember(&mut self, fact: &str) -> String {
        match self.remember(fact) {
            Ok(memory) => {
                format!(
                    "Got it, locked into my memory vault: \"{}\". That's memory number {}!",
                    memory.content,
                    self.count()
                )
            }
            Err(e) => format!("I couldn't remember that: {e}"),
        }
    }

    fn reply_recall(&self, query: &str) -> String {
        if query.is_empty() {
            return self.reply_list_all();
        }
        let hits = self.recall(query);
        if hits.is_empty() {
            format!(
                "That's a blank spot in my memory vault — I don't remember anything about {query} yet."
            )
        } else {
            let mut reply = format!(
                "Here's what I remember about {query} ({} thing{}):",
                hits.len(),
                if hits.len() == 1 { "" } else { "s" }
            );
            for m in hits.iter().take(5) {
                reply.push_str(&format!("\n- {}", m.content));
            }
            reply
        }
    }

    fn reply_list_all(&self) -> String {
        let all = self.all();
        if all.is_empty() {
            "My memory vault is empty. Teach me something with: remember that ...".into()
        } else {
            let mut reply = format!(
                "I'm holding {} memor{} in my vault:",
                all.len(),
                if all.len() == 1 { "y" } else { "ies" }
            );
            for m in all.iter().rev().take(10) {
                reply.push_str(&format!("\n- {}", m.content));
            }
            if all.len() > 10 {
                reply.push_str(&format!("\n...and {} older ones.", all.len() - 10));
            }
            reply
        }
    }

    fn reply_forget(&mut self, query: &str) -> String {
        match self.forget(query) {
            Some(m) => format!("Poof! Forgot: \"{}\".", m.content),
            None => format!(
                "I couldn't find a memory matching '{query}'. Say 'what do you remember' to hear the list."
            ),
        }
    }
}

/// Case-insensitive prefix stripper that preserves the original text case.
/// Picks the longest matching prefix and returns the remainder of `s`.
fn strip_any_ci<'a>(s: &'a str, prefixes: &[&str]) -> Option<&'a str> {
    let mut best: Option<(&'a str, usize)> = None;
    for p in prefixes {
        if let Some(rest) = strip_prefix_ci(s, p) {
            if best.map_or(true, |(_, len)| p.len() > len) {
                best = Some((rest, p.len()));
            }
        }
    }
    best.map(|(rest, _)| rest)
}

fn strip_prefix_ci<'a>(s: &'a str, prefix: &str) -> Option<&'a str> {
    let head = s.get(..prefix.len())?;
    if head.eq_ignore_ascii_case(prefix) {
        Some(&s[prefix.len()..])
    } else {
        None
    }
}

fn tokenize(s: &str) -> Vec<String> {
    s.split(|c: char| !c.is_alphanumeric())
        .filter(|t| t.len() > 1)
        .map(|t| t.to_lowercase())
        .collect()
}

fn score_memory(memory: &Memory, tokens: &[String]) -> usize {
    let hay = format!("{} {}", memory.content, memory.category).to_lowercase();
    tokens
        .iter()
        .filter(|t| hay.split(|c: char| !c.is_alphanumeric()).any(|w| w == *t))
        .count()
}

fn categorize(content: &str) -> &'static str {
    let lower = content.to_lowercase();
    if lower.contains("my name") || lower.contains("i am called") || lower.contains("call me") {
        "identity"
    } else if lower.contains("birthday") || lower.contains("anniversary") {
        "date"
    } else if ["like", "love", "favorite", "favourite", "prefer", "hate", "dislike"]
        .iter()
        .any(|k| lower.contains(k))
    {
        "preference"
    } else if lower.contains("work") || lower.contains("job") || lower.contains("office") {
        "work"
    } else {
        "general"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    static FILE_LOCK: Mutex<()> = Mutex::new(());

    fn temp_vault(name: &str) -> (MemoryVault, PathBuf) {
        let path = std::env::temp_dir().join(format!(
            "honey-mv-test-{}-{name}.json",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        (MemoryVault::open_at(&path), path)
    }

    #[test]
    fn remembers_and_persists_across_reopen() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("persist");
        vault.remember("my sister's birthday is May 3rd").unwrap();
        vault.remember("I love spicy ramen").unwrap();
        drop(vault);

        let reopened = MemoryVault::open_at(&path);
        assert_eq!(reopened.count(), 2);
        assert_eq!(reopened.all()[0].content, "my sister's birthday is May 3rd");
        assert_eq!(reopened.all()[0].category, "date");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn recall_scores_matching_memories_first() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("recall");
        vault.remember("I love spicy ramen").unwrap();
        vault.remember("The wifi password is honeybee42").unwrap();
        vault.remember("My project deadline is Friday").unwrap();

        let hits = vault.recall("wifi password");
        assert_eq!(hits.len(), 1);
        assert!(hits[0].content.contains("wifi password"));
        assert!(vault.recall("gardening").is_empty());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn forget_removes_best_match() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("forget");
        vault.remember("I love spicy ramen").unwrap();
        vault.remember("The wifi password is honeybee42").unwrap();

        let removed = vault.forget("wifi password").unwrap();
        assert!(removed.content.contains("wifi"));
        assert_eq!(vault.count(), 1);
        assert!(vault.forget("nonexistent thing").is_none());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn deduplicates_case_insensitively() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("dedup");
        vault.remember("I Love Spicy Ramen").unwrap();
        vault.remember("i love spicy ramen").unwrap();
        assert_eq!(vault.count(), 1);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn handles_natural_commands() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("commands");

        let reply = vault
            .try_handle("remember that my sister's birthday is May 3rd")
            .unwrap();
        assert!(reply.contains("Got it"), "reply was: {reply}");
        assert_eq!(vault.count(), 1);

        let reply = vault
            .try_handle("what do you remember about birthday")
            .unwrap();
        assert!(reply.contains("May 3rd"), "reply was: {reply}");

        let reply = vault
            .try_handle("forget about my sister's birthday")
            .unwrap();
        assert!(reply.contains("Forgot"), "reply was: {reply}");
        assert_eq!(vault.count(), 0);

        // Non-memory text passes through untouched.
        assert!(vault.try_handle("what time is it").is_none());
        assert!(vault.try_handle("open firefox").is_none());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn wipes_everything_on_command() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("wipe");
        vault.remember("fact one").unwrap();
        vault.remember("fact two").unwrap();
        let reply = vault.try_handle("forget everything").unwrap();
        assert!(reply.contains('2'), "reply was: {reply}");
        assert_eq!(vault.count(), 0);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn prompt_context_lists_recent_memories() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("prompt");
        assert_eq!(vault.prompt_context(None), "");
        vault.remember("I love spicy ramen").unwrap();
        let ctx = vault.prompt_context(None);
        assert!(ctx.contains("spicy ramen"), "ctx was: {ctx}");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn list_all_when_bare_remember_question() {
        let _guard = FILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let (mut vault, path) = temp_vault("bare");
        let reply = vault.try_handle("what do you remember").unwrap();
        assert!(reply.contains("empty"), "reply was: {reply}");
        let _ = std::fs::remove_file(&path);
    }
}