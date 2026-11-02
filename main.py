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
        "hrv_status": "Neznámý",
        "body_battery_max": 70,
        "resting_heart_rate": 56,
        "stress_avg": 0,
        "last_activity": "Žádná aktivita",
        "muscle_mass": 68.2,
        "active_calories": 2450,
    }

    if not GARMIN_PERSONAL_API_KEY:
        debug_log.append("Klíč GARMIN_PERSONAL_API_KEY není nastaven.")
        return data_metrics, debug_log

    try:
        # 1. Získání tokenu
        token_url = "https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token"
        headers = {"Authorization": f"ApiKey {GARMIN_PERSONAL_API_KEY}"}
        token_res = requests.post(token_url, headers=headers, timeout=10)
        
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

                # 2. Stažení spánku (200 OK)
                try:
                    sleep_url = f"https://personal.connectapi.garmin.com/sleep-service/sleep/dailySleep?date={today_str}"
                    sleep_res = requests.get(sleep_url, headers=api_headers, timeout=10)
                    if sleep_res.status_code == 200:
                        debug_log.append("Spánek stažen (200 OK)!")
                        sleep_json = sleep_res.json()
                        items = sleep_json if isinstance(sleep_json, list) else [sleep_json]
                        for item in items:
                            if isinstance(item, dict):
                                val = item.get("sleepScores", {}).get("overall", {}).get("value")
                                if val is not None:
                                    data_metrics["sleep_score"] = int(val)
                except Exception as s_err:
                    debug_log.append(f"Chyba spánku: {s_err}")

                # 3. Stažení Body Battery (200 OK)
                try:
                    bb_url = f"https://personal.connectapi.garmin.com/wellness-service/wellness/bodyBattery/reports/daily?startDate={today_str}&endDate={today_str}"
                    bb_res = requests.get(bb_url, headers=api_headers, timeout=10)
                    if bb_res.status_code == 200:
                        debug_log.append("Body Battery staženo (200 OK)!")
                        bb_json = bb_res.json()
                        items = bb_json if isinstance(bb_json, list) else [bb_json]
                        for item in items:
                            if isinstance(item, dict):
                                values_array = item.get("bodyBatteryValuesArray", [])
                                if values_array and isinstance(values_array, list):
                                    last_val = values_array[-1]
                                    if isinstance(last_val, list) and len(last_val) > 1:
                                        data_metrics["body_battery_max"] = int(last_val[1])
                except Exception as bb_err:
                    debug_log.append(f"Chyba Body Battery: {bb_err}")

                # 4. Stažení klidového tepu (200 OK)
                try:
                    hr_url = f"https://personal.connectapi.garmin.com/wellness-service/wellness/dailyHeartRate?date={today_str}"
                    hr_res = requests.get(hr_url, headers=api_headers, timeout=10)
                    if hr_res.status_code == 200:
                        debug_log.append("Klidový tep stažen (200 OK)!")
                        hr_json = hr_res.json()
                        rhr = hr_json.get("restingHeartRate")
                        if rhr is not None:
                            data_metrics["resting_heart_rate"] = int(rhr)
                except Exception as hr_err:
                    debug_log.append(f"Chyba tepu: {hr_err}")

                # 5. Stažení HRV (200 OK)
                try:
                    hrv_url = f"https://personal.connectapi.garmin.com/hrv-service/hrv/{today_str}"
                    hrv_res = requests.get(hrv_url, headers=api_headers, timeout=10)
                    if hrv_res.status_code == 200:
                        debug_log.append("HRV staženo (200 OK)!")
                        hrv_json = hrv_res.json()
                        status = hrv_json.get("hrvSummary", {}).get("status") or hrv_json.get("hrvStatus")
                        if status:
                            data_metrics["hrv_status"] = str(status)
                except Exception as h_err:
                    debug_log.append(f"Chyba HRV: {h_err}")

                # 6. Stažení Stresu přes denní reporty (stejná struktura jako Body Battery)
                try:
                    stress_url = f"https://personal.connectapi.garmin.com/wellness-service/wellness/stress/reports/daily?startDate={today_str}&endDate={today_str}"
                    stress_res = requests.get(stress_url, headers=api_headers, timeout=10)
                    debug_log.append(f"Stress API Status: {stress_res.status_code}")
                    if stress_res.status_code == 200:
                        stress_json = stress_res.json()
                        items = stress_json if isinstance(stress_json, list) else [stress_json]
                        for item in items:
                            if isinstance(item, dict):
                                avg = item.get("overallStressLevel") or item.get("avgStressLevel")
                                if avg is not None:
                                    data_metrics["stress_avg"] = int(avg)
                                    debug_log.append(f"Stres nalezen: {avg}")
                except Exception as st_err:
                    debug_log.append(f"Chyba stresu: {st_err}")

                # 7. Stažení Aktivit s požadovaným parametrem limit
                try:
                    act_url = "https://personal.connectapi.garmin.com/activitylist-service/activities/search/dedup?start=0&limit=5"
                    act_res = requests.get(act_url, headers=api_headers, timeout=10)
                    debug_log.append(f"Activities API Status: {act_res.status_code}")
                    if act_res.status_code != 200:
                        act_url = "https://personal.connectapi.garmin.com/activity-service/activity/activities?limit=5"
                        act_res = requests.get(act_url, headers=api_headers, timeout=10)
                        debug_log.append(f"Activities Fallback Status: {act_res.status_code}")
                    
                    if act_res.status_code == 200:
                        acts = act_res.json()
                        if isinstance(acts, list) and len(acts) > 0:
                            last_act = acts[0].get("activityName") or acts[0].get("activityType", {}).get("typeKey")
                            if last_act:
                                data_metrics["last_activity"] = str(last_act)
                                debug_log.append(f"Poslední aktivita: {last_act}")
                except Exception as a_err:
                    debug_log.append(f"Chyba aktivit: {a_err}")

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
        "stress_avg": garmin["stress_avg"],
        "last_activity": garmin["last_activity"],
        "muscle_mass": garmin["muscle_mass"],
        "active_calories": garmin["active_calories"]
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
            function copyLogToClipboard() {{
                const logContainer = document.getElementById('log-text-container');
                const text = logContainer.innerText;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('copy-btn');
                    btn.innerText = 'Zkopírováno!';
                    btn.classList.remove('bg-slate-800', 'text-emerald-400');
                    btn.classList.add('bg-emerald-600', 'text-white');
                    setTimeout(() => {{
                        btn.innerText = 'Kopírovat log';
                        btn.classList.remove('bg-emerald-600', 'text-white');
                        btn.classList.add('bg-slate-800', 'text-emerald-400');
                    }}, 2000);
                }});
            }}
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
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Spánek</div>
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
                <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Průměrný stres</div>
                    <div class="text-xl font-black text-purple-400 mt-1">{data['stress_avg']}</div>
                </div>
                <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Stav HRV</div>
                    <div class="text-sm font-bold text-teal-400 mt-1 truncate">{data['hrv_status']}</div>
                </div>
                <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
                    <div class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Poslední aktivita</div>
                    <div class="text-sm font-bold text-pink-400 mt-1 truncate">{data['last_activity']}</div>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 p-4 rounded-2xl mb-6 shadow-xl">
                <h3 class="text-xs font-bold uppercase text-slate-400 mb-3">Tělesné metriky & Hmotnost</h3>
                <form action="/update-stats" method="POST" class="space-y-3">
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-[10px] text-slate-400 uppercase font-semibold mb-1">Hmotnost (kg)</label>
                            <input type="number" step="0.1" name="weight" value="{data['weight']}" class="w-full bg-black/40 border border-slate-800 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500 font-mono">
                        </div>
                        <div>
                            <label class="block text-[10px] text-slate-400 uppercase font-semibold mb-1">Tělesný tuk (%)</label>
                            <input type="number" step="0.1" name="body_fat" value="{data['body_fat']}" class="w-full bg-black/40 border border-slate-800 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500 font-mono">
                        </div>
                    </div>
                    <button type="submit" class="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs uppercase tracking-wider rounded-xl transition shadow-lg">
                        Uložit změny
                    </button>
                </form>
            </div>

            <div class="text-center">
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
