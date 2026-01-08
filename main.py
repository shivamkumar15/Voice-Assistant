from brain import think
from voice_output import speak

print("🐝 Honey is awake...")

import voice_input

while True:
    # user_text = input("You: ")
    user_text = voice_input.listen()
    if not user_text:
        continue
    
    print(f"You: {user_text}")

    if user_text.lower() in ["exit", "bye", "quit"]:
        speak("Okay... I’ll miss you. Talk soon 💛")
        break

    reply = think(user_text)
    print("Honey:", reply)
    speak(reply)
