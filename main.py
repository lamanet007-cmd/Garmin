import os
import datetime
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "")

user_stats_cache = {
    "user": "Drsňák",
    "weight": 84.5,
    "body_fat": 14.2,
}

def fetch_garmin_data_safe():
    """
    Bezpečné volání Garmin Personal API s krátkým timeoutem, 
    zaměřené čistě na získání reálných metrik.
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
        debug_log.append("Klíč GARMIN_PERSONAL_API_KEY není nastaven v Renderu.")
        return default_data, debug_log

    try:
        token_url = "https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token"
        headers = {"Authorization": f"ApiKey {GARMIN_PERSONAL_API_KEY}"}
        
        token_res = requests.post(token_url, headers=headers, timeout=5)
        debug_log.append(f"Token Status: {token_res.status_code}")
        
        if token_res.status_code == 200:
            access_token = None
            try:
                token_json = token_res.json()
                access_token = token_json.get("access_token") or token_json.get("token")
            except:
                access_token = token_res.text.strip().replace('"', '')

            if access_token:
                debug_log.append("Token úspěšně zřízen.")
                api_headers = {"Authorization": f"Bearer {access_token}"}
                today_str = datetime.date.today().isoformat()

                sleep_url = f"https://apis.garmin.com/wellness-service/wellness/dailySleep?date={today_str}"
                sleep_res = requests.get(sleep_url, headers=api_headers, timeout=5)
                debug_log.append(f"Sleep API Status: {sleep_res.status_code}")

                if sleep_res.status_code == 200:
                    try:
                        sleep_json = sleep_res.json()
                        debug_log.append(f"Sleep Data: str(sleep_json)[:100]")
                        if isinstance(sleep_json, list) and len(sleep_json) > 0:
                            val = sleep_json[0].get("dailySleepDTO", {}).get("sleepScorePercentage", {}).get("value")
                            if val: default_data["sleep_score"] = int(val)
                        elif isinstance(sleep_json, dict):
                            val = sleep_json.get("dailySleepDTO", {}).get("sleepScorePercentage", {}).get("value")
                            if val: default_data["sleep_score"] = int(val)
                    except Exception as parse_err:
                        debug_log.append(f"Chyba parsování spánku: {parse_err}")
                else:
                    debug_log.append(f"Sleep API chyba text: {sleep_res.text[:100]}")
            else:
                debug_log.append("Token nebyl v odpovědi nalezen.")
        else:
            debug_log.append(f"Token chyba text: {token_res.text[:100]}")

    except requests.exceptions.Timeout:
        debug_log.append("Chyba: Vypršel časový limit (Timeout) při komunikaci s Garminem.")
    except Exception as e:
        debug_log.append(f"Neočekávaná výjimka: {str(e)}")

    return default_data, debug_log

@app.get("/", response_class=HTMLResponse)
def home():
    garmin, debug_log = fetch_garmin_data_safe()
    
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

    debug_html = "".join([f"<div class='text-xs text-amber-400 font-mono'>[API LOG] {item}</div>" for item in debug_log])

    html_content = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Garmin Data Debugger</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-[#030712] text-slate-100 font-sans min-h-screen pb-12">
        <div class="max-w-md md:max-w-2xl mx-auto px-4 mt-6">
            <div class="mb-5">
                <h1 class="text-2xl font-black text-white">Garmin Data Debugger</h1>
                <p class="text-slate-400 text-xs mt-1">AI je dočasně pozastavena – ladíme čistý přenos z hodinek</p>
            </div>

            <!-- Diagnostický box -->
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-2xl mb-6 shadow-xl">
                <h3 class="text-xs font-bold uppercase text-slate-400 mb-2">Živý výpis z Garmin API:</h3>
                <div class="bg-black/40 p-3 rounded-xl border border-slate-800/80 space-y-1 overflow-x-auto">
                    {debug_html}
                </div>
            </div>

            <!-- Metriky z Garminu -->
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

            <!-- Informace o pozastavení AI -->
            <div class="bg-slate-900/60 p-5 rounded-3xl border border-slate-800 text-center">
                <p class="text-slate-400 text-xs uppercase tracking-wider font-semibold">AI Trenér je nyní uspaný</p>
                <p class="text-slate-500 text-xs mt-1">Až Garmin data úspěšně potečou, AI zase zapneme.</p>
            </div>

            <div class="mt-6 text-center">
                <button onclick="window.location.reload();" class="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs uppercase rounded-xl transition shadow-lg">
                    Znovu načíst a testovat
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
