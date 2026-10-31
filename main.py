import os
import requests
from fastapi import FastAPI
from google import genai

app = FastAPI()

# Načtení klíčů z proměnných prostředí na Renderu (nebo fallback pro test)
GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "TVUJ_GARMIN_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "TVUJ_GEMINI_KEY")

def get_garmin_token(api_key):
    url = "https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token"
    headers = {"Authorization": f"ApiKey {api_key}"}
    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("access_token")
    except Exception:
        pass
    return None

@app.get("/")
def home():
    return {"status": "running", "message": "Garmin AI Trainer běží, Drsňáku!"}

@app.get("/analyza")
def spustit_analyzu():
    # 1. Token z Garminu
    token = get_garmin_token(GARMIN_PERSONAL_API_KEY)
    
    # 2. Data (fallback nebo reálná data)
    data = {
        "user": "Drsňák",
        "sleep_score": 75,
        "hrv_status": "Balanced (42 ms)",
        "body_battery_max": 70,
        "resting_heart_rate": 56,
        "yesterday_workout": "Klidný výklus 8 km v zóně 2"
    }
    
    # Pokud máme token, zkusíme stáhnout reálná data
    if token:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            res = requests.get("https://personal.connectapi.garmin.com/user-summary-service/stats/daily", headers=headers)
            if res.status_code == 200:
                data = res.json()
        except Exception:
            pass

    # 3. Gemini AI analýza
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Jsi špičkový sportovní trenér. Tvým svěřencem je "Drsňák".
    Data z Garminu: {data}
    Napiš mu ostré, motivující slovní zhodnocení formy a doporuč dnešní trénink.
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    return {
        "garmin_data": data,
        "ai_trenar_hodnoceni": response.text
    }
