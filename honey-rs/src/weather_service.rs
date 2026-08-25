use anyhow::Result;
use serde_json::Value;
use std::time::Duration;

pub struct WeatherService {
    api_key: Option<String>,
    default_city: String,
    http: reqwest::blocking::Client,
}

pub struct WeatherData {
    pub city: String,
    pub temperature: f64,
    pub feels_like: f64,
    pub humidity: i64,
    pub description: String,
    pub wind_speed: f64,
}

impl WeatherService {
    pub fn new(api_key: Option<String>) -> Self {
        Self {
            api_key,
            default_city: crate::config::default_city(),
            http: reqwest::blocking::Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .expect("http client"),
        }
    }

    pub fn get_weather(&self, city: Option<&str>) -> Result<WeatherData> {
        let Some(key) = &self.api_key else {
            anyhow::bail!("no weather API key configured");
        };
        let city = city.unwrap_or(&self.default_city);
        let resp = self
            .http
            .get("https://api.openweathermap.org/data/2.5/weather")
            .query(&[
                ("q", city),
                ("appid", key.as_str()),
                ("units", "metric"),
            ])
            .send()?;
        if !resp.status().is_success() {
            anyhow::bail!("weather service returned HTTP {}", resp.status());
        }
        let v: Value = resp.json()?;
        Ok(WeatherData {
            city: v["name"].as_str().unwrap_or(city).to_string(),
            temperature: v["main"]["temp"].as_f64().unwrap_or(0.0),
            feels_like: v["main"]["feels_like"].as_f64().unwrap_or(0.0),
            humidity: v["main"]["humidity"].as_i64().unwrap_or(0),
            description: v["weather"][0]["description"]
                .as_str()
                .unwrap_or("unknown")
                .to_string(),
            wind_speed: v["wind"]["speed"].as_f64().unwrap_or(0.0),
        })
    }

    pub fn smart_response(&self, city: Option<&str>) -> String {
        match self.get_weather(city) {
            Ok(w) => {
                let emoji = emoji_for(&w.description);
                let outfit = outfit_suggestion(w.temperature);
                let activity = activity_suggestion(&w.description, w.temperature);
                format!(
                    "Weather in {} {}: {:.1} degrees (feels like {:.1}), humidity {} percent, wind {:.1} meters per second, {}. {}. {}",
                    w.city, emoji, w.temperature, w.feels_like, w.humidity,
                    w.wind_speed, title_case(&w.description), outfit, activity
                )
            }
            Err(e) => {
                if self.api_key.is_none() {
                    "I don't have a weather API key configured yet. Set OWM_API_KEY and I'll check the sky for you!".into()
                } else {
                    format!("Sorry, I couldn't fetch the weather for {}. ({e})", city.unwrap_or(&self.default_city))
                }
            }
        }
    }
}

fn emoji_for(description: &str) -> &'static str {
    let d = description.to_lowercase();
    if d.contains("clear") {
        "\u{2600}\u{FE0F}"
    } else if d.contains("thunder") || d.contains("storm") {
        "\u{26A8}\u{FE0F}"
    } else if d.contains("snow") {
        "\u{2744}\u{FE0F}"
    } else if d.contains("rain") || d.contains("drizzle") {
        "\u{1F327}\u{FE0F}"
    } else if d.contains("cloud") {
        "\u{2601}\u{FE0F}"
    } else if d.contains("mist") || d.contains("fog") {
        "\u{1F32B}\u{FE0F}"
    } else {
        "\u{1F324}\u{FE0F}"
    }
}

fn outfit_suggestion(temp: f64) -> &'static str {
    if temp < 0.0 {
        "Bundle up! Heavy coat, scarf and gloves."
    } else if temp < 10.0 {
        "Wear a warm jacket and layers."
    } else if temp < 20.0 {
        "A light jacket or sweater should be good."
    } else if temp < 25.0 {
        "T-shirt and jeans weather!"
    } else if temp < 30.0 {
        "Light clothes recommended, stay cool."
    } else {
        "It's hot! Wear light breathable clothes and stay hydrated."
    }
}

fn activity_suggestion(description: &str, temp: f64) -> &'static str {
    let d = description.to_lowercase();
    if d.contains("rain") || d.contains("storm") {
        "Indoor day! Perfect for movies, reading or coding."
    } else if d.contains("clear") && (15.0..25.0).contains(&temp) {
        "Beautiful day! Great for a walk or a picnic."
    } else if temp > 30.0 {
        "Hot day! Swimming or staying in the AC sounds good."
    } else if temp < 5.0 {
        "Cold! Hot chocolate and indoor activities recommended."
    } else {
        "Decent weather for outdoor activities if you dress appropriately."
    }
}

fn title_case(s: &str) -> String {
    s.split_whitespace()
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}
