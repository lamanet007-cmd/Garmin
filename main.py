import os
import requests
from fastapi import FastAPI
from google import genai

app = FastAPI()

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

@app.get("/")
def home():
    return {"status": "running", "message": "Garmin AI Trainer běží, Drsňáku!"}

@app.get("/analyza")
def spustit_analyzu():
    try:
        # Kontrola klíčů
        if not GEMINI_API_KEY:
            return {"chyba": "Chybí GEMINI_API_KEY v proměnných prostředí na Renderu!"}
        
        # Testovací data (později napojíme na reálné Garmin API)
        data = {
            "user": "Drsňák",
            "sleep_score": 75,
            "hrv_status": "Balanced (42 ms)",
            "body_battery_max": 70,
            "resting_heart_rate": 56,
            "yesterday_workout": "Klidný výklus 8 km v zóně 2"
        }

        # Gemini AI analýza
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Jsi špičkový sportovní trenér. Tvým svěřencem je "Drsňák".
        Data z Garminu: {data}
        Napiš mu ostré, motivující slovní zhodnocení formy a doporuč dnešní trénink.
        """
        
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )
        
        return {
            "stav": "Úspěch",
            "ai_trenar_hodnoceni": response.text
        }
        
    except Exception as e:
        return {"chyba_serveru": str(e)}
