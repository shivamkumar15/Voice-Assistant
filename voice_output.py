import pyttsx3

engine = pyttsx3.init()
engine.setProperty("rate", 165)

voices = engine.getProperty("voices")
for v in voices:
    if "female" in v.name.lower() or "zira" in v.name.lower():
        engine.setProperty("voice", v.id)
        break

def speak(text):
    engine.say(text)
    engine.runAndWait()
