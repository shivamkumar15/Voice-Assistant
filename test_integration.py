import sys
from unittest.mock import MagicMock

# Mock dependencies
sys.modules["speech_recognition"] = MagicMock()
sys.modules["pyaudio"] = MagicMock()
sys.modules["google"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()
sys.modules["pyttsx3"] = MagicMock()

# Mock voice_input module
voice_input_mock = MagicMock()
# First return "Hello", second "exit" to break loop
voice_input_mock.listen.side_effect = ["Hello", "exit"]
sys.modules["voice_input"] = voice_input_mock

# Mock other components that main imports
brain_mock = MagicMock()
brain_mock.think.return_value = "I am thinking."
sys.modules["brain"] = brain_mock

voice_output_mock = MagicMock()
sys.modules["voice_output"] = voice_output_mock

print("Starting integration test of main.py...")

# Import main to run it
import main

print("Integration test passed: main.py executed and exited cleanly.")
