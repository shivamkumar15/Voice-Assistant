import re
from typing import Dict, Optional, List, Tuple
from desktop_controller import DesktopController
from automation_controller import KeyboardController, MouseController
from time_service import TimeService, ReminderManager
from weather_service import WeatherService

class CommandParser:
    """Parse natural language commands and execute desktop actions"""
    
    def __init__(self, weather_api_key: str = None):
        self.desktop = DesktopController()
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.time_service = TimeService()
        self.weather_service = WeatherService(api_key=weather_api_key)
        self.reminder_manager = ReminderManager()
        
        # Command patterns
        self.patterns = {
            # File operations
            'search_file': r'(?:search|find|look for|locate)\s+(?:file|files?)?\s*(?:named|called)?\s+(.+)',
            'open_file': r'open\s+(?:file\s+)?(.+)',
            'create_folder': r'create\s+(?:folder|directory)\s+(?:named|called)?\s+(.+)',
            
            # Application control
            'launch_app': r'(?:open|launch|start|run)\s+(.+?)(?:\s+app(?:lication)?)?$',
            'close_app': r'close\s+(.+?)(?:\s+app(?:lication)?)?$',
            
            # Window management
            'minimize_window': r'minimize\s+(.+?)(?:\s+window)?$',
            'maximize_window': r'maximize\s+(.+?)(?:\s+window)?$',
            'close_window': r'close\s+(?:window\s+)?(.+)',
            'focus_window': r'(?:focus|switch to|go to)\s+(.+?)(?:\s+window)?$',
            'list_windows': r'(?:list|show|what)\s+(?:windows|apps)\s+(?:are\s+)?(?:open|running)',
            
            # Keyboard actions
            'type_text': r'type\s+(.+)',
            'press_key': r'press\s+(.+?)(?:\s+key)?$',
            'execute_shortcut': r'(?:execute|do|press)\s+(.+?)\s+(?:shortcut|command)',
            
            # Common shortcuts
            'copy': r'copy(?:\s+(?:this|that|text))?$',
            'paste': r'paste(?:\s+(?:this|that|text))?$',
            'save': r'save(?:\s+(?:this|file))?$',
            'undo': r'undo(?:\s+(?:that|last))?$',
            
            # Mouse actions
            'click': r'click(?:\s+(?:here|there|mouse))?$',
            'double_click': r'double\s*click$',
            'right_click': r'right\s*click$',
            'scroll_up': r'scroll\s+up',
            'scroll_down': r'scroll\s+down',
            
            # System info
            'system_info': r'(?:system|computer)\s+(?:info|status|stats)',
            
            # Time queries
            'what_time': r'(?:what|current)\s+time',
            'what_date': r'(?:what|today\'s?)\s+(?:date|day)',
            'is_weekend': r'(?:is it|it\'s)\s+(?:the\s+)?weekend',
            
            # Weather queries
            'weather': r'(?:what\'s|what is|how\'s|how is|check|get)\s+(?:the\s+)?weather',
            'weather_in': r'weather\s+in\s+(.+)',
        }
    
    def parse_and_execute(self, command: str) -> Tuple[bool, str]:
        """
        Parse a natural language command and execute it
        
        Args:
            command: Natural language command string
            
        Returns:
            Tuple of (success, response_message)
        """
        command = command.strip().lower()
        
        # Try to match command patterns
        for action, pattern in self.patterns.items():
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                return self._execute_action(action, match)
        
        return False, "I didn't understand that command. Try something like 'open chrome' or 'search file report.pdf'"
    
    def _execute_action(self, action: str, match: re.Match) -> Tuple[bool, str]:
        """Execute a matched action"""
        
        try:
            # File operations
            if action == 'search_file':
                filename = match.group(1).strip()
                results = self.desktop.search_files(filename, limit=5)
                if results:
                    response = f"Found {len(results)} file(s):\n"
                    for r in results[:3]:
                        response += f"- {r['name']} at {r['path']}\n"
                    return True, response
                return False, f"No files found matching '{filename}'"
            
            elif action == 'open_file':
                filename = match.group(1).strip()
                # First try to search for the file
                results = self.desktop.search_files(filename, limit=1)
                if results:
                    success = self.desktop.open_file(results[0]['path'])
                    if success:
                        return True, f"Opened {results[0]['name']}!"
                return False, f"Couldn't find or open '{filename}'"
            
            elif action == 'create_folder':
                folder_name = match.group(1).strip()
                # Create in user's home directory by default
                import os
                path = os.path.join(os.path.expanduser('~'), 'Desktop', folder_name)
                success = self.desktop.create_folder(path)
                if success:
                    return True, f"Created folder '{folder_name}' on Desktop!"
                return False, f"Couldn't create folder '{folder_name}'"
            
            # Application control
            elif action == 'launch_app':
                app_name = match.group(1).strip()
                success = self.desktop.launch_application(app_name)
                if success:
                    return True, f"Launched {app_name}!"
                return False, f"Couldn't launch {app_name}"
            
            elif action == 'close_app':
                app_name = match.group(1).strip()
                success = self.desktop.close_application(app_name)
                if success:
                    return True, f"Closed {app_name}!"
                return False, f"Couldn't find or close {app_name}"
            
            # Window management
            elif action == 'minimize_window':
                window_title = match.group(1).strip()
                success = self.desktop.minimize_window(window_title)
                if success:
                    return True, f"Minimized {window_title}!"
                return False, f"Couldn't find window '{window_title}'"
            
            elif action == 'maximize_window':
                window_title = match.group(1).strip()
                success = self.desktop.maximize_window(window_title)
                if success:
                    return True, f"Maximized {window_title}!"
                return False, f"Couldn't find window '{window_title}'"
            
            elif action == 'close_window':
                window_title = match.group(1).strip()
                success = self.desktop.close_window(window_title)
                if success:
                    return True, f"Closed {window_title}!"
                return False, f"Couldn't find window '{window_title}'"
            
            elif action == 'focus_window':
                window_title = match.group(1).strip()
                success = self.desktop.focus_window(window_title)
                if success:
                    return True, f"Switched to {window_title}!"
                return False, f"Couldn't find window '{window_title}'"
            
            elif action == 'list_windows':
                windows = self.desktop.get_windows()
                if windows:
                    response = f"Open windows ({len(windows)}):\n"
                    for w in windows[:10]:  # Show first 10
                        response += f"- {w}\n"
                    return True, response
                return False, "No windows open"
            
            # Keyboard actions
            elif action == 'type_text':
                text = match.group(1).strip()
                success = self.keyboard.type_text(text)
                if success:
                    return True, f"Typed: {text}"
                return False, "Couldn't type text"
            
            elif action == 'press_key':
                key = match.group(1).strip()
                success = self.keyboard.press_key(key)
                if success:
                    return True, f"Pressed {key} key"
                return False, f"Couldn't press {key}"
            
            elif action == 'execute_shortcut':
                shortcut = match.group(1).strip()
                success = self.keyboard.execute_shortcut(shortcut)
                if success:
                    return True, f"Executed {shortcut} shortcut"
                return False, f"Unknown shortcut: {shortcut}"
            
            # Common shortcuts
            elif action == 'copy':
                success = self.keyboard.copy_text()
                return True, "Copied!" if success else False, "Couldn't copy"
            
            elif action == 'paste':
                success = self.keyboard.paste_text()
                return True, "Pasted!" if success else False, "Couldn't paste"
            
            elif action == 'save':
                success = self.keyboard.save()
                return True, "Saved!" if success else False, "Couldn't save"
            
            elif action == 'undo':
                success = self.keyboard.undo()
                return True, "Undone!" if success else False, "Couldn't undo"
            
            # Mouse actions
            elif action == 'click':
                success = self.mouse.click()
                return True, "Clicked!" if success else False, "Couldn't click"
            
            elif action == 'double_click':
                success = self.mouse.double_click()
                return True, "Double-clicked!" if success else False, "Couldn't double-click"
            
            elif action == 'right_click':
                success = self.mouse.right_click()
                return True, "Right-clicked!" if success else False, "Couldn't right-click"
            
            elif action == 'scroll_up':
                success = self.mouse.scroll_up()
                return True, "Scrolled up!" if success else False, "Couldn't scroll"
            
            elif action == 'scroll_down':
                success = self.mouse.scroll_down()
                return True, "Scrolled down!" if success else False, "Couldn't scroll"
            
            # System info
            elif action == 'system_info':
                info = self.desktop.get_system_info()
                response = "System Status:\n"
                response += f"CPU: {info.get('cpu_percent', 'N/A')}%\n"
                response += f"Memory: {info.get('memory_percent', 'N/A')}%\n"
                response += f"Disk: {info.get('disk_usage', 'N/A')}%\n"
                if info.get('battery'):
                    response += f"Battery: {info['battery']}%"
                return True, response
            
            # Time queries
            elif action == 'what_time':
                return True, self.time_service.get_smart_time_response("what time")
            
            elif action == 'what_date':
                return True, self.time_service.get_smart_time_response("what date")
            
            elif action == 'is_weekend':
                return True, self.time_service.get_smart_time_response("weekend")
            
            # Weather queries
            elif action == 'weather':
                return True, self.weather_service.get_smart_weather_response()
            
            elif action == 'weather_in':
                city = match.group(1).strip()
                return True, self.weather_service.get_smart_weather_response(city)
        
        except Exception as e:
            return False, f"Error executing command: {e}"
        
        return False, "Command not implemented yet"
    
    def is_desktop_command(self, text: str) -> bool:
        """Check if text contains a desktop control command"""
        text_lower = text.lower()
        
        command_keywords = [
            'open', 'close', 'launch', 'start', 'run',
            'search', 'find', 'look for',
            'minimize', 'maximize', 'focus', 'switch to',
            'type', 'press', 'click', 'scroll',
            'copy', 'paste', 'save', 'undo',
            'create folder', 'delete', 'move',
            'system info', 'system status',
            'what time', 'what date', 'weekend',
            'weather', 'temperature'
        ]
        
        return any(keyword in text_lower for keyword in command_keywords)
