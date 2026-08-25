use anyhow::{anyhow, bail, Context, Result};
use std::io::{BufReader, Read, Write};
use std::path::Path;
use std::process::{Command, Stdio};
use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters,
};

const SAMPLE_RATE: u32 = 16000;

pub struct Recorder;

impl Default for Recorder {
    fn default() -> Self {
        Self::new()
    }
}

impl Recorder {
    pub fn new() -> Self {
        Self
    }

    fn rms(samples: &[i16]) -> f32 {
        if samples.is_empty() {
            return 0.0;
        }
        let sum: f64 = samples.iter().map(|s| (*s as f64) * (*s as f64)).sum();
        (sum / samples.len() as f64).sqrt() as f32
    }

    pub fn record_utterance(
        &self,
        listen_timeout_secs: f32,
        max_utterance_secs: f32,
    ) -> Result<Option<Vec<i16>>> {
        let mut child = Command::new("arecord")
            .args([
                "-q",
                "-t",
                "raw",
                "-f",
                "S16_LE",
                "-r",
                &SAMPLE_RATE.to_string(),
                "-c",
                "1",
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .context("failed to start arecord (is alsa-utils installed?)")?;

        let stdout = child
            .stdout
            .take()
            .context("arecord produced no stdout")?;
        let mut reader = BufReader::new(stdout);

        let chunk_samples = (SAMPLE_RATE / 10) as usize;
        let mut buf = vec![0u8; chunk_samples * 2];
        let threshold = crate::config::vad_threshold();

        let start = std::time::Instant::now();
        let mut spoken: Vec<i16> = Vec::new();
        let mut preroll: Vec<i16> = Vec::new();
        let mut speech_started = false;
        let mut trailing_silence_chunks = 0usize;

        loop {
            match reader.read_exact(&mut buf) {
                Ok(()) => {}
                Err(_) => break,
            }
            let chunk: Vec<i16> = buf
                .chunks_exact(2)
                .map(|b| i16::from_le_bytes([b[0], b[1]]))
                .collect();
            let level = Self::rms(&chunk);

            if !speech_started {
                preroll.extend_from_slice(&chunk);
                let keep_from = preroll.len().saturating_sub(chunk_samples * 3);
                preroll.drain(..keep_from);
                if level > threshold {
                    speech_started = true;
                    spoken.extend_from_slice(&preroll);
                    spoken.extend_from_slice(&chunk);
                    println!("\u{1F3A4} Listening...");
                } else if start.elapsed().as_secs_f32() > listen_timeout_secs {
                    break;
                }
            } else {
                spoken.extend_from_slice(&chunk);
                if level < threshold {
                    trailing_silence_chunks += 1;
                    if trailing_silence_chunks >= 13 {
                        break;
                    }
                } else {
                    trailing_silence_chunks = 0;
                }
                if spoken.len() as f32 / SAMPLE_RATE as f32 >= max_utterance_secs {
                    break;
                }
            }
        }

        let _ = child.kill();
        let _ = child.wait();

        if speech_started {
            Ok(Some(spoken))
        } else {
            Ok(None)
        }
    }
}

pub struct Transcriber {
    ctx: WhisperContext,
}

impl Transcriber {
    pub fn load_default() -> Result<Self> {
        let model_path = match crate::config::whisper_model_path() {
            Some(p) => p,
            None => {
                let p = crate::config::model_cache_path();
                if !p.exists() {
                    download_model(&p)?;
                }
                p
            }
        };
        println!(
            "\u{1F9E0} Loading speech model from {}...",
            model_path.display()
        );
        let path_str = model_path
            .to_str()
            .ok_or_else(|| anyhow!("model path is not valid UTF-8"))?
            .to_string();
        let ctx = WhisperContext::new_with_params(&path_str, WhisperContextParameters::default())
            .map_err(|e| anyhow!("failed to load whisper model: {e:?}"))?;
        println!("\u{1F9E0} Speech model ready.");
        Ok(Self { ctx })
    }

    pub fn transcribe(&self, samples: &[i16]) -> Result<String> {
        if samples.len() < SAMPLE_RATE as usize / 2 {
            return Ok(String::new());
        }
        let float_samples: Vec<f32> = samples.iter().map(|s| *s as f32 / 32768.0).collect();

        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        params.set_language(Some("en"));
        params.set_translate(false);
        params.set_print_progress(false);
        params.set_print_special(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        params.set_no_context(true);

        let mut state = self
            .ctx
            .create_state()
            .map_err(|e| anyhow!("whisper state error: {e:?}"))?;
        state
            .full(params, &float_samples[..])
            .map_err(|e| anyhow!("whisper inference error: {e:?}"))?;

        let n_segments = state.full_n_segments();
        let mut text = String::new();
        for i in 0..n_segments {
            if let Some(seg) = state.get_segment(i) {
                if let Ok(s) = seg.to_str() {
                    text.push_str(s.trim_start());
                }
            }
        }
        Ok(text.trim().to_string())
    }

    pub fn listen_and_transcribe(&self, recorder: &Recorder) -> Result<Option<String>> {
        print!("\u{1F3A4} (speak when the dot appears) ");
        let _ = std::io::stdout().flush();
        let samples = recorder.record_utterance(7.0, 10.0)?;
        match samples {
            None => Ok(None),
            Some(samples) => {
                let text = self.transcribe(&samples)?;
                if text.trim().is_empty() {
                    Ok(None)
                } else {
                    Ok(Some(text))
                }
            }
        }
    }
}

fn download_model(dest: &Path) -> Result<()> {
    println!(
        "\u{2B07}\u{FE0F} Downloading Whisper model (~78 MB, one time)..."
    );
    let client = reqwest::blocking::Client::builder()
        .timeout(None)
        .build()?;
    let mut resp = client
        .get(crate::config::WHISPER_MODEL_URL)
        .send()
        .context("failed to download whisper model")?;
    if !resp.status().is_success() {
        bail!("model download failed with HTTP {}", resp.status());
    }
    let mut file = std::fs::File::create(dest)
        .with_context(|| format!("cannot create {}", dest.display()))?;
    let mut downloaded: u64 = 0;
    let mut buffer = [0u8; 65536];
    loop {
        let n = resp.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        file.write_all(&buffer[..n])?;
        downloaded += n as u64;
        if downloaded % (5 * 1024 * 1024) < buffer.len() as u64 {
            print!("\r\u{2B07}\u{FE0F} {:.1} MB...", downloaded as f64 / 1e6);
            let _ = std::io::stdout().flush();
        }
    }
    println!("\r\u{2705} Model downloaded ({:.1} MB).", downloaded as f64 / 1e6);
    Ok(())
}
