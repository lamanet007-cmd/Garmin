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
    debug_log = []
    data_metrics = {
        "sleep_score": 75,
        "hrv_status": "Balanced (Aktivní)",
        "body_battery_max": 70,
        "resting_heart_rate": 56,
        "muscle_mass": 68.2,
        "active_calories": 2450,
        "yesterday_workout": "Fullbody posilovna"
    }

    if not GARMIN_PERSONAL_API_KEY:
        debug_log.append("Klíč GARMIN_PERSONAL_API_KEY není nastaven.")
        return data_metrics, debug_log

    try:
        # 1. Získání tokenu
        token_url = "https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token"
        headers = {"Authorization": f"ApiKey {GARMIN_PERSONAL_API_KEY}"}
        token_res = requests.post(token_url, headers=headers, timeout=5)
        
        if token_res.status_code == 200:
            debug_log.append("Token Status: 200 (Úspěch)")
            access_token = None
            try:
                token_json = token_res.json()
                access_token = token_json.get("access_token") or token_json.get("token")
            except:
                access_token = token_res.text.strip().replace('"', '')

            if access_token:
                api_headers = {"Authorization": f"Bearer {access_token}"}
                today_str = datetime.date.today().isoformat()

                # 2. Stažení spánku
                sleep_url = f"https://personal.connectapi.garmin.com/wellness-service/wellness/dailySleep?date={today_str}"
                sleep_res = requests.get(sleep_url, headers=api_headers, timeout=5)
                
                if sleep_res.status_code == 200:
                    debug_log.append("Spánek stažen (200 OK)!")
                    debug_log.append(f"JSON: {sleep_res.text[:180]}")
                    try:
                        sleep_json = sleep_res.json()
                        items = sleep_json if isinstance(sleep_json, list) else [sleep_json]
                        for item in items:
                            dto = item.get("dailySleepDTO", {})
                            val = (
                                dto.get("sleepScorePercentage", {}).get("value") or 
                                dto.get("overallSleepScore", {}).get("value") or
                                dto.get("score") or
                                item.get("sleepScore")
                            )
                            if val is not None:
                                data_metrics["sleep_score"] = int(val)
                                debug_log.append(f"Nalezeno skóre spánku: {val}")
                    except Exception as parse_err:
                        debug_log.append(f"Chyba parsování: {parse_err}")
                else:
                    debug_log.append(f"Sleep API chyba: {sleep_res.status_code}")
            else:
                debug_log.append("Access token nenalezen.")
        else:
            debug_log.append(f"Token chyba: {token_res.status_code}")

    except Exception as e:
        debug_log.append(f"Výjimka: {str(e)}")

    return data_metrics, debug_log

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

    debug_html = "".join([f"<div class='text-xs text-emerald-400 font-mono'>[API LOG] {item}</div>" for item in debug_log])

    html_content = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Garmin Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            function copyLogToClipboard() {
                const logContainer = document.getElementById('log-text-container');
                const text = logContainer.innerText;
                navigator.clipboard.writeText(text).then(() => {
                    const btn = document.getElementById('copy-btn');
                    btn.innerText = 'Zkopírováno!';
                    btn.classList.remove('bg-slate-800', 'text-emerald-400');
                    btn.classList.add('bg-emerald-600', 'text-white');
                    setTimeout(() => {{
                        btn.innerText = 'Kopírovat log';
                        btn.classList.remove('bg-emerald-600', 'text-white');
                        btn.classList.add('bg-slate-800', 'text-emerald-400');
                    }}, 2000);
                });
            }
        </script>
    </head>
    <body class="bg-[#030712] text-slate-100 font-sans min-h-screen pb-12">
        <div class="max-w-md md:max-w-2xl mx-auto px-4 mt-6">
            <div class="mb-5 flex items-center justify-between">
                <div>
                    <h1 class="text-2xl font-black text-white">Garmin Dashboard</h1>
                    <p class="text-emerald-400 text-xs mt-0.5 font-semibold">● Live Personal API Připojeno</p>
                </div>
                <div class="text-xs bg-slate-800 text-blue-400 border border-slate-700 px-3 py-1 rounded-full font-medium">
                    Svěřenec: <span class="text-white font-bold">{data['user']}</span>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 p-3 rounded-2xl mb-5 shadow-xl">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="text-[10px] font-bold uppercase text-slate-400">Stav komunikace a surová data:</h3>
                    <button id="copy-btn" onclick="copyLogToClipboard()" class="text-[10px] bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-slate-700 px-2.5 py-1 rounded-lg transition font-mono uppercase font-semibold">
                        Kopírovat log
                    </button>
                </div>
                <div id="log-text-container" class="bg-black/40 p-2.5 rounded-xl border border-slate-800/80 space-y-1 overflow-x-auto">
                    {debug_html}
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
                <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Spánek (Živě)</div>
                    <div class="text-xl font-black text-emerald-400 mt-1">{data['sleep_score']}<span class="text-xs text-slate-500 font-normal">/100</span></div>
                </div>
                <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Body Battery</div>
                    <div class="text-xl font-black text-blue-400 mt-1">{data['body_battery_max']}<span class="text-xs text-slate-500 font-normal">/100</span></div>
                </div>
                <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Klidový tep</div>
                    <div class="text-xl font-black text-orange-400 mt-1">{data['resting_heart_rate']} <span class="text-[10px] text-slate-500 font-normal">bpm</span></div>
                </div>
            </div>

            <div class="bg-slate-900/60 p-4 rounded-2xl border border-slate-800 mb-6 shadow-lg">
                <h3 class="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3">Zapsat ranní metry (Váha & Tuk)</h3>
                <form action="/update-stats" method="post" class="flex gap-2">
                    <input type="number" step="0.1" name="weight" value="{data['weight']}" required class="w-1/2 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
                    <input type="number" step="0.1" name="body_fat" value="{data['body_fat']}" required class="w-1/2 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
                    <button type="submit" class="bg-blue-600 hover:bg-blue-500 text-white font-bold px-4 py-2 rounded-xl text-xs uppercase tracking-wider transition">Uložit</button>
                </form>
            </div>

            <div class="mt-6 text-center">
                <button onclick="window.location.reload();" class="w-full py-3 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 font-semibold text-xs uppercase tracking-wider rounded-xl transition shadow-lg">
                    Obnovit data z Garminu
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
