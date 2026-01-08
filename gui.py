import customtkinter as ctk
import threading
from PIL import Image
import os
from brain import think, get_current_emotion_data, get_spontaneous_thought, get_relationship_status
from voice_manager import VoiceManager
import time
import threading

# Set appearance mode and color theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

class ChatBubble(ctk.CTkFrame):
    def __init__(self, master, text, is_user=True, **kwargs):
        super().__init__(master, **kwargs)
        self.is_user = is_user

        # Colors
        bg_color = "#2b2b2b" if is_user else "#4a3c1b" # Grey for user, Gold-tint for Honey
        text_color = "#ffffff"
        align = "e" if is_user else "w"

        self.configure(fg_color="transparent")

        self.bubble = ctk.CTkLabel(
            self, 
            text=text, 
            fg_color=bg_color, 
            text_color=text_color, 
            corner_radius=15,
            wraplength=350,
            padx=10, 
            pady=8
        )
        self.bubble.pack(anchor=align, padx=10, pady=5)

class AssistantGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Honey - Voice Assistant")
        self.geometry("900x600")
        
        # Grid Configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Voice Manager
        self.voice_manager = VoiceManager()
        self.is_listening = False
        
        # Spontaneous thought system
        self.spontaneous_check_active = False
        self.start_spontaneous_checker()

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar, text="🐝 Honey", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Emotion Display
        emotion_data = get_current_emotion_data()
        self.emotion_label = ctk.CTkLabel(
            self.sidebar, 
            text=f"{emotion_data['emoji']} {emotion_data['name'].title()}",
            font=ctk.CTkFont(size=18),
            text_color=emotion_data['color']
        )
        self.emotion_label.grid(row=1, column=0, padx=20, pady=5)
        
        # Energy & Relationship bars
        self.energy_label = ctk.CTkLabel(self.sidebar, text=f"Energy: {emotion_data['energy']}%", text_color="#06FFA5")
        self.energy_label.grid(row=2, column=0, padx=20, pady=2)
        
        self.relationship_label = ctk.CTkLabel(self.sidebar, text=get_relationship_status(), text_color="#FFD700")
        self.relationship_label.grid(row=3, column=0, padx=20, pady=2)

        self.status_label = ctk.CTkLabel(self.sidebar, text="Status: Idle", text_color="gray")
        self.status_label.grid(row=4, column=0, padx=20, pady=10)

        # Clear Chat Button
        self.clear_btn = ctk.CTkButton(self.sidebar, text="Clear Chat", command=self.clear_chat, fg_color="#444", hover_color="#555")
        self.clear_btn.grid(row=5, column=0, padx=20, pady=10)
        
        # --- Main Chat Area ---
        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.chat_frame.grid(row=0, column=1, padx=20, pady=(20, 0), sticky="nsew")

        # --- Input Area ---
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.grid(row=1, column=1, padx=20, pady=20, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.input_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Type message...")
        self.input_entry.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="ew")
        self.input_entry.bind("<Return>", self.send_message_event)

        self.send_btn = ctk.CTkButton(self.input_frame, text="Send", width=60, command=self.send_message_event)
        self.send_btn.grid(row=0, column=1, padx=(0, 10))

        self.mic_btn = ctk.CTkButton(
            self.input_frame, 
            text="🎤", 
            width=40, 
            fg_color="#333", 
            hover_color="#444", 
            command=self.toggle_mic
        )
        self.mic_btn.grid(row=0, column=2)

        # Initial Welcome with emotion
        from personality import Personality
        temp_personality = Personality()
        greeting = temp_personality.get_greeting()
        self.add_message(greeting, is_user=False)

        # Start listening in background if you want auto-listen, or manual toggle
        # self.toggle_mic() 

    def toggle_mic(self):
        if self.is_listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self):
        self.is_listening = True
        self.mic_btn.configure(fg_color="#e63946", hover_color="#c1121f") # Red for recording
        self.status_label.configure(text="Status: Listening...", text_color="#e63946")
        self.voice_manager.start_listening_loop(self.on_voice_input)

    def stop_listening(self):
        self.is_listening = False
        self.mic_btn.configure(fg_color="#333", hover_color="#444")
        self.status_label.configure(text="Status: Idle", text_color="gray")
        self.voice_manager.stop_listening()

    def on_voice_input(self, text):
        # Called from background thread, need to schedule UI update
        self.after(0, lambda: self.process_input(text))

    def send_message_event(self, event=None):
        text = self.input_entry.get()
        if text.strip():
            self.process_input(text)
            self.input_entry.delete(0, "end")

    def process_input(self, text):
        self.add_message(text, is_user=True)
        self.status_label.configure(text="Status: Thinking...", text_color="#fca311")
        
        # Run brain in thread to not block UI
        threading.Thread(target=self.get_ai_response, args=(text,), daemon=True).start()

    def get_ai_response(self, text):
        response = think(text)
        self.after(0, lambda: self.display_response(response))
        # Update emotion display after thinking
        self.after(0, self.update_emotion_display)

    def display_response(self, text):
        self.add_message(text, is_user=False)
        self.status_label.configure(text="Status: Speaking...", text_color="#2a9d8f")
        self.voice_manager.speak(text, callback_done=self.finished_speaking)

    def finished_speaking(self):
         self.after(0, lambda: self.status_label.configure(text="Status: Idle", text_color="gray"))

    def add_message(self, text, is_user):
        bubble = ChatBubble(self.chat_frame, text=text, is_user=is_user)
        bubble.pack(fill="x", pady=5)
        # Scroll to bottom
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    def clear_chat(self):
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
    
    def update_emotion_display(self):
        """Update the emotion display in sidebar"""
        emotion_data = get_current_emotion_data()
        self.emotion_label.configure(
            text=f"{emotion_data['emoji']} {emotion_data['name'].title()}",
            text_color=emotion_data['color']
        )
        self.energy_label.configure(text=f"Energy: {emotion_data['energy']}%")
        self.relationship_label.configure(text=get_relationship_status())
    
    def start_spontaneous_checker(self):
        """Start background thread to check for spontaneous thoughts"""
        self.spontaneous_check_active = True
        thread = threading.Thread(target=self._spontaneous_checker_loop, daemon=True)
        thread.start()
    
    def _spontaneous_checker_loop(self):
        """Background loop to check if Honey wants to say something"""
        while self.spontaneous_check_active:
            time.sleep(30)  # Check every 30 seconds
            
            # Only if not currently listening or speaking
            if not self.is_listening:
                thought = get_spontaneous_thought()
                if thought:
                    self.after(0, lambda t=thought: self.show_spontaneous_thought(t))
    
    def show_spontaneous_thought(self, thought):
        """Display a spontaneous thought from Honey"""
        self.add_message(thought, is_user=False)
        self.update_emotion_display()
        # Optionally speak it
        if not self.is_listening:
            self.voice_manager.speak(thought)

if __name__ == "__main__":
    app = AssistantGUI()
    app.mainloop()
