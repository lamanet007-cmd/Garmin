import os
import datetime
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from google import genai

app = FastAPI()

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

user_stats_cache = {
    "user": "Drsňák",
    "weight": 84.5,
    "body_fat": 14.2,
}

def fetch_garmin_data_via_personal_api():
    """
    Pokusí se stáhnout data a vrátí jak surovou odpověď pro diagnózu, tak parsovaná data.
    """
    debug_log = []
    
    default_data = {
        "sleep_score": 75,
        "hrv_status": "Balanced (42 ms)",
        "body_battery_max": 70,
        "resting_heart_rate": 56,
        "muscle_mass": 68.2,
        "active_calories": 2450,
        "yesterday_workout": "Fullbody posilovna"
    }

    if not GARMIN_PERSONAL_API_KEY:
        debug_log.append("Chyba: GARMIN_PERSONAL_API_KEY není nastaven v prostředí Renderu.")
        return default_data, debug_log

    try:
        # 1. Získání tokenu
        token_url = "https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token"
        headers = {"Authorization": f"ApiKey {GARMIN_PERSONAL_API_KEY}"}
        token_res = requests.post(token_url, headers=headers, timeout=10)
        
        debug_log.append(f"Token Endpoint Status: {token_res.status_code}")
        
        if token_res.status_code != 200:
            debug_log.append(f"Token Error Body: {token_res.text}")
            return default_data, debug_log
            
        token_json = token_res.json()
        access_token = token_json.get("access_token")
        
        if not access_token:
            debug_log.append("Chyba: Access token nebyl v odpovědi nalezen.")
            return default_data, debug_log

        debug_log.append("Token úspěšně získána.")
        api_headers = {"Authorization": f"Bearer {access_token}"}
        today_str = datetime.date.today().isoformat()

        # 2. Stažení spánku
        sleep_url = f"https://apis.garmin.com/wellness-service/wellness/dailySleep?date={today_str}"
        sleep_res = requests.get(sleep_url, headers=api_headers, timeout=10)
        
        debug_log.append(f"Sleep API Status: {sleep_res.status_code}")
        debug_log.append(f"Sleep API Response: {sleep_res.text[:200]}") # Ukázka prvních 200 znaků

        if sleep_res.status_code == 200:
            sleep_json = sleep_res.json()
            # Zde se pokusíme vytáhnout reálné číslo
            if isinstance(sleep_json, list) and len(sleep_json) > 0:
                val = sleep_json[0].get("dailySleepDTO", {}).get("sleepScorePercentage", {}).get("value")
                if val:
                    default_data["sleep_score"] = int(val)
            elif isinstance(sleep_json, dict):
                val = sleep_json.get("dailySleepDTO", {}).get("sleepScorePercentage", {}).get("value")
                if val:
                    default_data["sleep_score"] = int(val)

        return default_data, debug_log

    except Exception as e:
        debug_log.append(f"Výjimka: {str(e)}")
        return default_data, debug_log

@app.get("/", response_class=HTMLResponse)
def home():
    garmin, debug_log = fetch_garmin_data_via_personal_api()
    
    data = {
        "user": user_stats_cache["user"],
        "weight": user_stats_cache["weight"],
        "body_fat": user_stats_cache["body_fat"],
        "sleep_score": garmin["sleep_score"],
        "hrv_status": garmin["hrv_status"],
        "body_battery_max": garmin["body_battery_max"],
        "resting_heart_rate": garmin["resting_heart_rate"],
        "muscle_mass": garmin["muscle_mass"],
        "active_calories": garmin["active_calories"],
        "yesterday_workout": garmin["yesterday_workout"]
    }
    
    raw_text = ""
    api_limited = False
    retry_in = ""

    try:
        if not GEMINI_API_KEY:
            raise Exception("Chybí GEMINI_API_KEY.")
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Jsi zkušený osobní trenér. Tvým svěřencem je "Drsňák", který cvičí fullbody tréninky.
        Aktuální data:
        - Hmotnost: {data['weight']} kg | Tuk: {data['body_fat']}%
        - Spánek: {data['sleep_score']}/100
        - HRV: {data['hrv_status']}
        - Body Battery: {data['body_battery_max']}/100
        - Klidový tep: {data['resting_heart_rate']} bpm
        
        Napiš stručný, zcela srozumitelný trenérský rozbor bez cizích slov rozdělený na 5 bodů:
        1. Hlava a nervy (spánek/únavy)
        2. Váha a jídlo
        3. Ochrana kloubů
        4. Dlouhověkost a kondice
        5. Dnešní verdikt (cvičit / odpočívat)
        """
        
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )
        raw_text = response.text

    except Exception as e:
        api_limited = True
        retry_in = "Limit API"
        raw_text = "Záložní posudek aktivní."

    # Sestavení HTML s přehledným diagnostickým boxem nahoře
    debug_html = "".join([f"<div class='text-xs text-amber-400 font-mono'>[API LOG] {item}</div>" for item in debug_log])

    html_content = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Garmin AI Fitness Trenér</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-[#030712] text-slate-100 font-sans min-h-screen pb-12">
        
        <div class="max-w-md md:max-w-2xl mx-auto px-4 mt-6">
            
            <div class="mb-5">
                <h1 class="text-2xl font-black text-white">Garmin API Diagnostika</h1>
                <p class="text-slate-400 text-xs mt-1">Sleduje stav komunikace s Garmin Personal API</p>
            </div>

            <!-- Diagnostický box přímo na stránce -->
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-2xl mb-6 shadow-xl">
                <h3 class="text-xs font-bold uppercase text-slate-400 mb-2">Výpis z pokusu o připojení:</h3>
                <div class="bg-black/40 p-3 rounded-xl border border-slate-800/80 space-y-1">
                    {debug_html}
                </div>
            </div>

            <!-- Metriky -->
            <div class="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
                <div class="bg-slate-900 p-3.5 rounded-2xl border border-slate-800">
                    <div class="text-slate-400 text-[10px] uppercase font-semibold">Spánek</div>
                    <div class="text-xl font-black text-emerald-400 mt-1">{data['sleep_score']}<span class="text-xs text-slate-500">/100</span></div>
                </div>
                <div class="bg-slate-900 p-3.5 rounded-2xl border border-slate-800">
                    <div class="text-slate-400 text-[10px] uppercase font-semibold">Body Battery</div>
                    <div class="text-xl font-black text-blue-400 mt-1">{data['body_battery_max']}<span class="text-xs text-slate-500">/100</span></div>
                </div>
                <div class="bg-slate-900 p-3.5 rounded-2xl border border-slate-800">
                    <div class="text-slate-400 text-[10px] uppercase font-semibold">Klidový tep</div>
                    <div class="text-xl font-black text-orange-400 mt-1">{data['resting_heart_rate']} <span class="text-[10px] text-slate-500">bpm</span></div>
                </div>
            </div>

            <!-- AI Rozbor -->
            <div class="bg-slate-900 p-5 rounded-3xl border border-slate-800">
                <h2 class="text-sm font-bold uppercase text-slate-200 mb-3">Trenérský rozbor</h2>
                <div class="text-slate-300 text-sm space-y-2">
                    {raw_text.replace(chr(10), '<br>')}
                </div>
            </div>

            <div class="mt-6 text-center">
                <button onclick="window.location.reload();" class="w-full py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs uppercase rounded-xl transition">
                    Obnovit stránku
                </button>
            </div>

        </div>
    </body>
    </html>
    """
    return html_content

@app.post("/update-stats", response_class=HTMLResponse)
def update_stats(weight: float = Form(...), body_fat: float = Form(...)):
    user_stats_cache["weight"] = weight
    user_stats_cache["body_fat"] = body_fat
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=303)
