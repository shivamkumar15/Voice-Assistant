from datetime import datetime, timedelta
import calendar
from typing import Dict, Optional

class TimeService:
    """Intelligent time and date analysis service"""
    
    def __init__(self):
        self.user_timezone = None  # Can be set based on user location
    
    def get_current_time(self, format_12hr: bool = True) -> str:
        """Get current time in readable format"""
        now = datetime.now()
        if format_12hr:
            return now.strftime("%I:%M %p")
        return now.strftime("%H:%M")
    
    def get_current_date(self, format_long: bool = True) -> str:
        """Get current date in readable format"""
        now = datetime.now()
        if format_long:
            return now.strftime("%A, %B %d, %Y")
        return now.strftime("%m/%d/%Y")
    
    def get_day_of_week(self) -> str:
        """Get current day of the week"""
        return datetime.now().strftime("%A")
    
    def get_time_of_day(self) -> str:
        """Get time of day description"""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"
    
    def get_greeting_time(self) -> str:
        """Get appropriate greeting based on time"""
        time_of_day = self.get_time_of_day()
        greetings = {
            "morning": "Good morning",
            "afternoon": "Good afternoon",
            "evening": "Good evening",
            "night": "Good night"
        }
        return greetings.get(time_of_day, "Hello")
    
    def time_until(self, target_hour: int, target_minute: int = 0) -> str:
        """Calculate time until a specific time today"""
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        
        if target < now:
            # Target time has passed today, calculate for tomorrow
            target += timedelta(days=1)
        
        diff = target - now
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
    
    def days_until(self, target_date: datetime) -> int:
        """Calculate days until a specific date"""
        now = datetime.now()
        diff = target_date - now
        return diff.days
    
    def is_weekend(self) -> bool:
        """Check if today is weekend"""
        return datetime.now().weekday() >= 5
    
    def is_holiday(self, date: datetime = None) -> bool:
        """Check if date is a major holiday (simplified)"""
        if date is None:
            date = datetime.now()
        
        # Major US holidays (simplified)
        holidays = [
            (1, 1),   # New Year's Day
            (7, 4),   # Independence Day
            (12, 25), # Christmas
        ]
        
        return (date.month, date.day) in holidays
    
    def get_calendar_month(self, month: int = None, year: int = None) -> str:
        """Get calendar for a specific month"""
        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year
        
        cal = calendar.month(year, month)
        return cal
    
    def parse_relative_time(self, text: str) -> Optional[datetime]:
        """Parse relative time expressions like 'tomorrow', 'next week'"""
        text_lower = text.lower()
        now = datetime.now()
        
        if 'tomorrow' in text_lower:
            return now + timedelta(days=1)
        elif 'yesterday' in text_lower:
            return now - timedelta(days=1)
        elif 'next week' in text_lower:
            return now + timedelta(weeks=1)
        elif 'next month' in text_lower:
            return now + timedelta(days=30)
        elif 'in an hour' in text_lower or 'in 1 hour' in text_lower:
            return now + timedelta(hours=1)
        
        return None
    
    def get_time_analysis(self) -> Dict[str, str]:
        """Get comprehensive time analysis"""
        now = datetime.now()
        
        return {
            'current_time': self.get_current_time(),
            'current_date': self.get_current_date(),
            'day_of_week': self.get_day_of_week(),
            'time_of_day': self.get_time_of_day(),
            'is_weekend': self.is_weekend(),
            'week_number': now.isocalendar()[1],
            'day_of_year': now.timetuple().tm_yday,
        }
    
    def get_smart_time_response(self, query: str) -> str:
        """Generate intelligent response to time-related queries"""
        query_lower = query.lower()
        
        if 'what time' in query_lower or 'current time' in query_lower:
            return f"It's {self.get_current_time()} right now."
        
        elif 'what day' in query_lower or 'what\'s today' in query_lower:
            return f"Today is {self.get_day_of_week()}, {self.get_current_date()}."
        
        elif 'date' in query_lower:
            return f"Today's date is {self.get_current_date()}."
        
        elif 'weekend' in query_lower:
            if self.is_weekend():
                return "Yes! It's the weekend! 🎉"
            else:
                days_until_weekend = 5 - datetime.now().weekday()
                return f"Not yet, but the weekend is in {days_until_weekend} day{'s' if days_until_weekend != 1 else ''}!"
        
        elif 'morning' in query_lower or 'afternoon' in query_lower or 'evening' in query_lower:
            time_of_day = self.get_time_of_day()
            return f"It's currently {time_of_day}."
        
        else:
            # Default response
            analysis = self.get_time_analysis()
            return f"It's {analysis['current_time']} on {analysis['day_of_week']}, {analysis['current_date']}."


class ReminderManager:
    """Simple reminder system"""
    
    def __init__(self):
        self.reminders = []
    
    def add_reminder(self, text: str, remind_at: datetime) -> bool:
        """Add a new reminder"""
        try:
            self.reminders.append({
                'text': text,
                'time': remind_at,
                'active': True
            })
            return True
        except:
            return False
    
    def get_active_reminders(self) -> list:
        """Get all active reminders"""
        now = datetime.now()
        return [r for r in self.reminders if r['active'] and r['time'] > now]
    
    def check_due_reminders(self) -> list:
        """Check for reminders that are due"""
        now = datetime.now()
        due = []
        for reminder in self.reminders:
            if reminder['active'] and reminder['time'] <= now:
                due.append(reminder)
                reminder['active'] = False
        return due
