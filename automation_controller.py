import pyautogui
import time
from typing import Tuple, List

# Safety settings
pyautogui.FAILSAFE = True  # Move mouse to corner to abort
pyautogui.PAUSE = 0.1  # Small pause between actions

class KeyboardController:
    """Advanced keyboard automation and control"""
    
    def __init__(self):
        self.macro_recording = False
        self.recorded_macro = []
    
    def type_text(self, text: str, interval: float = 0.05) -> bool:
        """
        Type text as if using keyboard
        
        Args:
            text: Text to type
            interval: Delay between keystrokes
            
        Returns:
            True if successful
        """
        try:
            pyautogui.write(text, interval=interval)
            return True
        except Exception as e:
            print(f"Error typing text: {e}")
            return False
    
    def press_key(self, key: str, presses: int = 1) -> bool:
        """
        Press a specific key
        
        Args:
            key: Key name (e.g., 'enter', 'space', 'a')
            presses: Number of times to press
            
        Returns:
            True if successful
        """
        try:
            pyautogui.press(key, presses=presses)
            return True
        except Exception as e:
            print(f"Error pressing key: {e}")
            return False
    
    def hotkey(self, *keys) -> bool:
        """
        Press a combination of keys (hotkey)
        
        Args:
            *keys: Keys to press together (e.g., 'ctrl', 'c')
            
        Returns:
            True if successful
        """
        try:
            pyautogui.hotkey(*keys)
            return True
        except Exception as e:
            print(f"Error executing hotkey: {e}")
            return False
    
    def copy_text(self) -> bool:
        """Execute Ctrl+C"""
        return self.hotkey('ctrl', 'c')
    
    def paste_text(self) -> bool:
        """Execute Ctrl+V"""
        return self.hotkey('ctrl', 'v')
    
    def cut_text(self) -> bool:
        """Execute Ctrl+X"""
        return self.hotkey('ctrl', 'x')
    
    def select_all(self) -> bool:
        """Execute Ctrl+A"""
        return self.hotkey('ctrl', 'a')
    
    def undo(self) -> bool:
        """Execute Ctrl+Z"""
        return self.hotkey('ctrl', 'z')
    
    def redo(self) -> bool:
        """Execute Ctrl+Y"""
        return self.hotkey('ctrl', 'y')
    
    def save(self) -> bool:
        """Execute Ctrl+S"""
        return self.hotkey('ctrl', 's')
    
    def find(self) -> bool:
        """Execute Ctrl+F"""
        return self.hotkey('ctrl', 'f')
    
    def new_tab(self) -> bool:
        """Execute Ctrl+T (new tab in browser)"""
        return self.hotkey('ctrl', 't')
    
    def close_tab(self) -> bool:
        """Execute Ctrl+W (close tab)"""
        return self.hotkey('ctrl', 'w')
    
    def switch_window(self) -> bool:
        """Execute Alt+Tab"""
        return self.hotkey('alt', 'tab')
    
    def minimize_all(self) -> bool:
        """Execute Win+D (show desktop)"""
        return self.hotkey('win', 'd')
    
    def screenshot(self) -> bool:
        """Execute Win+Shift+S (screenshot tool)"""
        return self.hotkey('win', 'shift', 's')
    
    def lock_screen(self) -> bool:
        """Execute Win+L (lock screen)"""
        return self.hotkey('win', 'l')
    
    def open_task_manager(self) -> bool:
        """Execute Ctrl+Shift+Esc"""
        return self.hotkey('ctrl', 'shift', 'esc')
    
    def execute_shortcut(self, shortcut_name: str) -> bool:
        """
        Execute a named shortcut
        
        Args:
            shortcut_name: Name of shortcut (e.g., 'copy', 'paste', 'save')
            
        Returns:
            True if successful
        """
        shortcuts = {
            'copy': lambda: self.copy_text(),
            'paste': lambda: self.paste_text(),
            'cut': lambda: self.cut_text(),
            'select all': lambda: self.select_all(),
            'undo': lambda: self.undo(),
            'redo': lambda: self.redo(),
            'save': lambda: self.save(),
            'find': lambda: self.find(),
            'new tab': lambda: self.new_tab(),
            'close tab': lambda: self.close_tab(),
            'switch window': lambda: self.switch_window(),
            'minimize all': lambda: self.minimize_all(),
            'screenshot': lambda: self.screenshot(),
            'lock screen': lambda: self.lock_screen(),
            'task manager': lambda: self.open_task_manager(),
        }
        
        shortcut_func = shortcuts.get(shortcut_name.lower())
        if shortcut_func:
            return shortcut_func()
        return False
    
    def start_macro_recording(self):
        """Start recording keyboard macro"""
        self.macro_recording = True
        self.recorded_macro = []
    
    def stop_macro_recording(self):
        """Stop recording keyboard macro"""
        self.macro_recording = False
    
    def play_macro(self):
        """Play recorded macro"""
        for action in self.recorded_macro:
            action_type, data = action
            if action_type == 'type':
                self.type_text(data)
            elif action_type == 'press':
                self.press_key(data)
            elif action_type == 'hotkey':
                self.hotkey(*data)
            time.sleep(0.1)


class MouseController:
    """Advanced mouse automation and control"""
    
    def __init__(self):
        self.screen_width, self.screen_height = pyautogui.size()
    
    def get_position(self) -> Tuple[int, int]:
        """Get current mouse position"""
        return pyautogui.position()
    
    def move_to(self, x: int, y: int, duration: float = 0.5) -> bool:
        """
        Move mouse to specific coordinates
        
        Args:
            x: X coordinate
            y: Y coordinate
            duration: Time to take for movement
            
        Returns:
            True if successful
        """
        try:
            pyautogui.moveTo(x, y, duration=duration)
            return True
        except Exception as e:
            print(f"Error moving mouse: {e}")
            return False
    
    def move_relative(self, x_offset: int, y_offset: int, duration: float = 0.5) -> bool:
        """Move mouse relative to current position"""
        try:
            pyautogui.move(x_offset, y_offset, duration=duration)
            return True
        except Exception as e:
            print(f"Error moving mouse: {e}")
            return False
    
    def click(self, x: int = None, y: int = None, clicks: int = 1, button: str = 'left') -> bool:
        """
        Click at position or current location
        
        Args:
            x: X coordinate (None for current position)
            y: Y coordinate (None for current position)
            clicks: Number of clicks (2 for double-click)
            button: 'left', 'right', or 'middle'
            
        Returns:
            True if successful
        """
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y, clicks=clicks, button=button)
            else:
                pyautogui.click(clicks=clicks, button=button)
            return True
        except Exception as e:
            print(f"Error clicking: {e}")
            return False
    
    def double_click(self, x: int = None, y: int = None) -> bool:
        """Double-click at position"""
        return self.click(x, y, clicks=2)
    
    def right_click(self, x: int = None, y: int = None) -> bool:
        """Right-click at position"""
        return self.click(x, y, button='right')
    
    def drag_to(self, x: int, y: int, duration: float = 0.5, button: str = 'left') -> bool:
        """
        Drag mouse to position
        
        Args:
            x: Target X coordinate
            y: Target Y coordinate
            duration: Time for drag
            button: Mouse button to hold
            
        Returns:
            True if successful
        """
        try:
            pyautogui.drag(x, y, duration=duration, button=button)
            return True
        except Exception as e:
            print(f"Error dragging: {e}")
            return False
    
    def scroll(self, amount: int) -> bool:
        """
        Scroll mouse wheel
        
        Args:
            amount: Positive for up, negative for down
            
        Returns:
            True if successful
        """
        try:
            pyautogui.scroll(amount)
            return True
        except Exception as e:
            print(f"Error scrolling: {e}")
            return False
    
    def scroll_up(self, clicks: int = 3) -> bool:
        """Scroll up"""
        return self.scroll(clicks)
    
    def scroll_down(self, clicks: int = 3) -> bool:
        """Scroll down"""
        return self.scroll(-clicks)
