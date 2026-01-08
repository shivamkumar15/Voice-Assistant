import os
import subprocess
import psutil
import pygetwindow as gw
from pathlib import Path
from typing import List, Optional, Dict
import time

class DesktopController:
    """Complete desktop control for file management, apps, and windows"""
    
    def __init__(self):
        self.common_app_paths = self._get_common_app_paths()
        
    def _get_common_app_paths(self) -> Dict[str, str]:
        """Map common app names to their executable paths"""
        return {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "paint": "mspaint.exe",
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "vscode": r"C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\Code.exe".format(os.getenv("USERNAME")),
            "code": r"C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\Code.exe".format(os.getenv("USERNAME")),
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            "spotify": r"C:\Users\{}\AppData\Roaming\Spotify\Spotify.exe".format(os.getenv("USERNAME")),
        }
    
    def search_files(self, query: str, search_path: str = None, limit: int = 10) -> List[Dict]:
        """
        Search for files by name
        
        Args:
            query: Search term
            search_path: Path to search in (default: user's home directory)
            limit: Maximum number of results
            
        Returns:
            List of file info dictionaries
        """
        if not search_path:
            search_path = str(Path.home())
        
        results = []
        query_lower = query.lower()
        
        try:
            for root, dirs, files in os.walk(search_path):
                # Skip system and hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['AppData', 'System32', 'Windows']]
                
                for file in files:
                    if query_lower in file.lower():
                        full_path = os.path.join(root, file)
                        try:
                            stat = os.stat(full_path)
                            results.append({
                                'name': file,
                                'path': full_path,
                                'size': stat.st_size,
                                'modified': time.ctime(stat.st_mtime)
                            })
                            
                            if len(results) >= limit:
                                return results
                        except:
                            continue
                            
        except Exception as e:
            print(f"Error searching files: {e}")
        
        return results
    
    def open_file(self, file_path: str) -> bool:
        """Open a file with its default application"""
        try:
            os.startfile(file_path)
            return True
        except Exception as e:
            print(f"Error opening file: {e}")
            return False
    
    def launch_application(self, app_name: str) -> bool:
        """
        Launch an application by name
        
        Args:
            app_name: Name of the application (e.g., 'chrome', 'notepad')
            
        Returns:
            True if successful, False otherwise
        """
        app_name_lower = app_name.lower()
        
        # Check if it's a known app
        if app_name_lower in self.common_app_paths:
            app_path = self.common_app_paths[app_name_lower]
            try:
                subprocess.Popen(app_path)
                return True
            except Exception as e:
                print(f"Error launching {app_name}: {e}")
                return False
        
        # Try to launch directly
        try:
            subprocess.Popen(app_name)
            return True
        except:
            # Try with .exe extension
            try:
                subprocess.Popen(f"{app_name}.exe")
                return True
            except Exception as e:
                print(f"Could not launch {app_name}: {e}")
                return False
    
    def get_running_applications(self) -> List[str]:
        """Get list of currently running applications"""
        apps = []
        for proc in psutil.process_iter(['name']):
            try:
                apps.append(proc.info['name'])
            except:
                continue
        return list(set(apps))  # Remove duplicates
    
    def close_application(self, app_name: str) -> bool:
        """Close an application by name"""
        app_name_lower = app_name.lower()
        
        for proc in psutil.process_iter(['name']):
            try:
                if app_name_lower in proc.info['name'].lower():
                    proc.terminate()
                    return True
            except:
                continue
        
        return False
    
    def get_windows(self) -> List[str]:
        """Get list of all open windows"""
        try:
            windows = gw.getAllTitles()
            return [w for w in windows if w]  # Filter out empty titles
        except Exception as e:
            print(f"Error getting windows: {e}")
            return []
    
    def focus_window(self, window_title: str) -> bool:
        """Bring a window to focus by title (partial match)"""
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].activate()
                return True
            return False
        except Exception as e:
            print(f"Error focusing window: {e}")
            return False
    
    def minimize_window(self, window_title: str) -> bool:
        """Minimize a window by title"""
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].minimize()
                return True
            return False
        except Exception as e:
            print(f"Error minimizing window: {e}")
            return False
    
    def maximize_window(self, window_title: str) -> bool:
        """Maximize a window by title"""
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].maximize()
                return True
            return False
        except Exception as e:
            print(f"Error maximizing window: {e}")
            return False
    
    def close_window(self, window_title: str) -> bool:
        """Close a window by title"""
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].close()
                return True
            return False
        except Exception as e:
            print(f"Error closing window: {e}")
            return False
    
    def create_folder(self, path: str) -> bool:
        """Create a new folder"""
        try:
            os.makedirs(path, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating folder: {e}")
            return False
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file (use with caution!)"""
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    def get_system_info(self) -> Dict:
        """Get system information"""
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('/').percent,
                'battery': psutil.sensors_battery().percent if psutil.sensors_battery() else None
            }
        except Exception as e:
            print(f"Error getting system info: {e}")
            return {}
