import whisper
import speech_recognition as sr
import os

model = whisper.load_model("base")

def record_audio(filename="input.wav"):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Adjusting for ambient noise...")
        r.adjust_for_ambient_noise(source)
        print("🎤 Honey is listening...")
        audio = r.listen(source)
        
    with open(filename, "wb") as f:
        f.write(audio.get_wav_data())
    return filename

def listen():
    try:
        filename = record_audio()
        result = model.transcribe(filename)
        return result["text"]
    except Exception as e:
        print(f"Error listening: {e}")
        return ""
