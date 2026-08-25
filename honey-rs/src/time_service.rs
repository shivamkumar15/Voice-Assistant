use chrono::{Datelike, Local, Timelike};

pub fn current_time_12hr() -> String {
    let now = Local::now();
    let (is_pm, hour12) = match now.hour12() {
        (true, h) => (true, h),
        (false, 0) => (false, 12),
        (false, h) => (false, h),
    };
    format!("{:02}:{:02} {}", hour12, now.minute(), if is_pm { "PM" } else { "AM" })
}

pub fn current_date_long() -> String {
    Local::now().format("%A, %B %d, %Y").to_string()
}

pub fn day_of_week() -> String {
    Local::now().weekday().to_string()
}

pub fn time_of_day() -> &'static str {
    let h = Local::now().hour();
    if (5..12).contains(&h) {
        "morning"
    } else if (12..17).contains(&h) {
        "afternoon"
    } else if (17..21).contains(&h) {
        "evening"
    } else {
        "night"
    }
}

pub fn greeting_word() -> &'static str {
    match time_of_day() {
        "morning" => "Good morning",
        "afternoon" => "Good afternoon",
        "evening" => "Good evening",
        _ => "Good night",
    }
}

pub fn is_weekend() -> bool {
    matches!(Local::now().weekday(), chrono::Weekday::Sat | chrono::Weekday::Sun)
}

fn days_until_saturday() -> u32 {
    let wd = Local::now().weekday().number_from_monday();
    (6 - wd) % 7
}

pub fn smart_time_response(query: &str) -> String {
    let q = query.to_lowercase();
    if q.contains("what time") || q.contains("current time") {
        format!("It's {} right now.", current_time_12hr())
    } else if q.contains("weekend") {
        if is_weekend() {
            "Yes! It's the weekend!".into()
        } else {
            let d = days_until_saturday();
            if d == 0 {
                "Tomorrow is Saturday, almost the weekend!".into()
            } else if d == 1 {
                "Not yet, but the weekend starts tomorrow!".into()
            } else {
                format!("Not yet, but the weekend is in {d} days!")
            }
        }
    } else if q.contains("what day") || q.contains("today's date") || q.contains("date") {
        format!("Today is {}, {}.", day_of_week(), current_date_long())
    } else if ["morning", "afternoon", "evening", "night"]
        .iter()
        .any(|w| q.contains(w))
    {
        format!("It's currently {}.", time_of_day())
    } else {
        format!(
            "It's {} on {}, {}.",
            current_time_12hr(),
            day_of_week(),
            current_date_long()
        )
    }
}
