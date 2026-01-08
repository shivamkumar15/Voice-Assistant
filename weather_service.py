import requests
from typing import Dict, Optional
from datetime import datetime

class WeatherService:
    """Weather information and intelligent analysis"""
    
    def __init__(self, api_key: str = None):
        """
        Initialize weather service
        
        Args:
            api_key: OpenWeatherMap API key (get free at openweathermap.org)
        """
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5"
        self.default_city = "New York"  # Can be customized
    
    def get_weather(self, city: str = None) -> Optional[Dict]:
        """
        Get current weather for a city
        
        Args:
            city: City name (uses default if not provided)
            
        Returns:
            Weather data dictionary or None if failed
        """
        if not self.api_key:
            return None
        
        if not city:
            city = self.default_city
        
        try:
            url = f"{self.base_url}/weather"
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric'  # Celsius
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'city': data['name'],
                    'temperature': data['main']['temp'],
                    'feels_like': data['main']['feels_like'],
                    'humidity': data['main']['humidity'],
                    'description': data['weather'][0]['description'],
                    'wind_speed': data['wind']['speed'],
                    'icon': data['weather'][0]['icon']
                }
            return None
        except Exception as e:
            print(f"Error fetching weather: {e}")
            return None
    
    def get_forecast(self, city: str = None, days: int = 3) -> Optional[list]:
        """Get weather forecast for upcoming days"""
        if not self.api_key:
            return None
        
        if not city:
            city = self.default_city
        
        try:
            url = f"{self.base_url}/forecast"
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric',
                'cnt': days * 8  # 8 forecasts per day (3-hour intervals)
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                forecasts = []
                
                for item in data['list']:
                    forecasts.append({
                        'time': datetime.fromtimestamp(item['dt']),
                        'temperature': item['main']['temp'],
                        'description': item['weather'][0]['description'],
                        'humidity': item['main']['humidity']
                    })
                
                return forecasts
            return None
        except Exception as e:
            print(f"Error fetching forecast: {e}")
            return None
    
    def get_weather_emoji(self, description: str) -> str:
        """Get emoji for weather condition"""
        description_lower = description.lower()
        
        if 'clear' in description_lower:
            return '☀️'
        elif 'cloud' in description_lower:
            return '☁️'
        elif 'rain' in description_lower:
            return '🌧️'
        elif 'thunder' in description_lower or 'storm' in description_lower:
            return '⛈️'
        elif 'snow' in description_lower:
            return '❄️'
        elif 'mist' in description_lower or 'fog' in description_lower:
            return '🌫️'
        else:
            return '🌤️'
    
    def get_outfit_suggestion(self, temperature: float) -> str:
        """Suggest outfit based on temperature"""
        if temperature < 0:
            return "Bundle up! Heavy coat, scarf, and gloves recommended. 🧥🧣"
        elif temperature < 10:
            return "Wear a warm jacket and layers. 🧥"
        elif temperature < 20:
            return "A light jacket or sweater should be good. 👔"
        elif temperature < 25:
            return "T-shirt and jeans weather! Perfect! 👕"
        elif temperature < 30:
            return "Light clothes recommended. Stay cool! 👕🩳"
        else:
            return "It's hot! Wear light, breathable clothes and stay hydrated! 🌡️💧"
    
    def get_activity_suggestion(self, weather_data: Dict) -> str:
        """Suggest activities based on weather"""
        description = weather_data['description'].lower()
        temp = weather_data['temperature']
        
        if 'rain' in description or 'storm' in description:
            return "Indoor day! Perfect for movies, reading, or coding. 🏠📚"
        elif 'clear' in description and 15 < temp < 25:
            return "Beautiful day! Great for a walk, picnic, or outdoor activities! 🌳🚶"
        elif temp > 30:
            return "Hot day! Swimming, air-conditioned mall, or stay indoors. 🏊"
        elif temp < 5:
            return "Cold! Hot chocolate and indoor activities recommended. ☕"
        else:
            return "Decent weather for outdoor activities if you dress appropriately! 🌤️"
    
    def get_smart_weather_response(self, city: str = None) -> str:
        """Generate intelligent weather response"""
        weather = self.get_weather(city)
        
        if not weather:
            if not self.api_key:
                return "I don't have a weather API key configured yet. You can get a free one from openweathermap.org!"
            return f"Sorry, I couldn't fetch the weather for {city or self.default_city} right now."
        
        emoji = self.get_weather_emoji(weather['description'])
        outfit = self.get_outfit_suggestion(weather['temperature'])
        activity = self.get_activity_suggestion(weather)
        
        response = f"""Weather in {weather['city']} {emoji}:
        
🌡️ Temperature: {weather['temperature']:.1f}°C (feels like {weather['feels_like']:.1f}°C)
💧 Humidity: {weather['humidity']}%
🌬️ Wind: {weather['wind_speed']} m/s
☁️ Conditions: {weather['description'].title()}

{outfit}

{activity}"""
        
        return response
    
    def is_good_weather(self, weather_data: Dict) -> bool:
        """Determine if weather is generally pleasant"""
        if not weather_data:
            return False
        
        description = weather_data['description'].lower()
        temp = weather_data['temperature']
        
        bad_conditions = ['rain', 'storm', 'snow', 'extreme']
        if any(cond in description for cond in bad_conditions):
            return False
        
        if 15 <= temp <= 25:
            return True
        
        return False
