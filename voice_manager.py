import threading
import voice_input
import voice_output
import time

class VoiceManager:
    def __init__(self):
        self.is_listening = False
        self.on_text_received = None # Callback function

    def start_listening_loop(self, callback):
        self.on_text_received = callback
        self.is_listening = True
        thread = threading.Thread(target=self._listen_loop, daemon=True)
        thread.start()

    def _listen_loop(self):
        while self.is_listening:
            # We assume listen() blocks until audio is processed
            text = voice_input.listen()
            if text and self.on_text_received:
                self.on_text_received(text)
            time.sleep(0.1)

    def stop_listening(self):
        self.is_listening = False

    def speak(self, text, callback_done=None):
        thread = threading.Thread(target=self._speak_thread, args=(text, callback_done), daemon=True)
        thread.start()

    def _speak_thread(self, text, callback_done):
        try:
            voice_output.speak(text)
        except Exception as e:
            print(f"Speaking error: {e}")
        finally:
            if callback_done:
                callback_done()
