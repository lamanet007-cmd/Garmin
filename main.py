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
        "resting_heart_rate": 56,
        "hrv_ms": 48,
        "body_battery_max": 75,
        "sleep_hours": 7.5,
        "stress_avg": 28,
        "steps": 8420,
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

                # 2. Klidový tep (200 OK)
                try:
                    hr_url = f"https://personal.connectapi.garmin.com/wellness-service/wellness/dailyHeartRate?date={today_str}"
                    hr_res = requests.get(hr_url, headers=api_headers, timeout=10)
                    if hr_res.status_code == 200:
                        debug_log.append("Klidový tep stažen (200 OK)!")
                        rhr = hr_res.json().get("restingHeartRate")
                        if rhr is not None:
                            data_metrics["resting_heart_rate"] = int(rhr)
                except Exception as hr_err:
                    debug_log.append(f"Chyba tepu: {hr_err}")

                # 3. HRV v milisekundách (200 OK)
                try:
                    hrv_url = f"https://personal.connectapi.garmin.com/hrv-service/hrv/{today_str}"
                    hrv_res = requests.get(hrv_url, headers=api_headers, timeout=10)
                    if hrv_res.status_code == 200:
                        debug_log.append("HRV staženo (200 OK)!")
                        hrv_json = hrv_res.json()
                        val = hrv_json.get("hrvSummary", {}).get("lastNightAvg") or hrv_json.get("lastNightAvg")
                        if val is not None:
                            data_metrics["hrv_ms"] = int(val)
                except Exception as h_err:
                    debug_log.append(f"Chyba HRV: {h_err}")

                # 4. Body Battery (200 OK)
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

                # 5. Spánek v hodinách (200 OK)
                try:
                    sleep_url = f"https://personal.connectapi.garmin.com/sleep-service/sleep/dailySleep?date={today_str}"
                    sleep_res = requests.get(sleep_url, headers=api_headers, timeout=10)
                    if sleep_res.status_code == 200:
                        debug_log.append("Spánek stažen (200 OK)!")
                        sleep_json = sleep_res.json()
                        items = sleep_json if isinstance(sleep_json, list) else [sleep_json]
                        for item in items:
                            if isinstance(item, dict):
                                seconds = item.get("sleepTimeSeconds") or item.get("durationInSeconds")
                                if seconds:
                                    data_metrics["sleep_hours"] = round(float(seconds) / 3600, 1)
                except Exception as s_err:
                    debug_log.append(f"Chyba spánku: {s_err}")

                # 6. Kroky a Stres ze souhrnného endpointu uživatele
                try:
                    summary_url = f"https://personal.connectapi.garmin.com/usersummary-service/usersummary/daily/{today_str}"
                    sum_res = requests.get(summary_url, headers=api_headers, timeout=10)
                    debug_log.append(f"User Summary API Status: {sum_res.status_code}")
                    if sum_res.status_code == 200:
                        sum_json = sum_res.json()
                        steps = sum_json.get("totalSteps") or sum_json.get("steps")
                        if steps is not None:
                            data_metrics["steps"] = int(steps)
                        stress = sum_json.get("averageStressLevel") or sum_json.get("stressScore")
                        if stress is not None:
                            data_metrics["stress_avg"] = int(stress)
                except Exception as sum_err:
                    debug_log.append(f"Chyba User Summary: {sum_err}")

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
    
    debug_html = "".join([f"<div class='text-xs text-emerald-400 font-mono'>[API LOG] {item}</div>" for item in debug_log])

    html_content = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GARMIN AI LIFE</title>
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
            <header class="mb-5 flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <span class="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center font-black text-white text-lg shadow-lg">G</span>
                    <div>
                        <h1 class="text-lg font-black text-white tracking-wide">GARMIN AI LIFE</h1>
                        <p class="text-[10px] text-emerald-400 uppercase font-bold tracking-widest">Live Garmin Připojeno</p>
                    </div>
                </div>
                <div class="text-xs bg-slate-800 text-blue-400 border border-slate-700 px-3 py-1 rounded-full font-medium">
                    Svěřenec: <span class="text-white font-bold">{user_stats_cache['user']}</span>
                </div>
            </header>

            <section class="bg-slate-900 border border-slate-800 p-3 rounded-2xl mb-5 shadow-xl">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="text-[10px] font-bold uppercase text-slate-400">Stav komunikace a surová data:</h3>
                    <button id="copy-btn" onclick="copyLogToClipboard()" class="text-[10px] bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-slate-700 px-2.5 py-1 rounded-lg transition font-mono uppercase font-semibold">
                        Kopírovat log
                    </button>
                </div>
                <div id="log-text-container" class="bg-black/40 p-2.5 rounded-xl border border-slate-800/80 space-y-1 overflow-x-auto">
                    {debug_html}
                </div>
            </section>

            <section class="mb-6">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <p class="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Dnešní přehled</p>
                        <h2 class="text-xl font-black text-white">Moje metriky</h2>
                    </div>
                    <span class="text-[10px] bg-slate-800 text-emerald-400 border border-slate-700 px-2.5 py-1 rounded-full font-bold">GARMIN CONNECT</span>
                </div>

                <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">❤️</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Klidový tep</p>
                        <div class="text-xl font-black text-orange-400 mt-1">{garmin['resting_heart_rate']} <small class="text-xs text-slate-500 font-normal">bpm</small></div>
                    </div>
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">💚</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">HRV</p>
                        <div class="text-xl font-black text-teal-400 mt-1">{garmin['hrv_ms']} <small class="text-xs text-slate-500 font-normal">ms</small></div>
                    </div>
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">🔋</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Body Battery</p>
                        <div class="text-xl font-black text-blue-400 mt-1">{garmin['body_battery_max']} <small class="text-xs text-slate-500 font-normal">/ 100</small></div>
                    </div>
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">😴</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Spánek</p>
                        <div class="text-xl font-black text-emerald-400 mt-1">{garmin['sleep_hours']} <small class="text-xs text-slate-500 font-normal">hod</small></div>
                    </div>
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">⚡</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Stres</p>
                        <div class="text-xl font-black text-purple-400 mt-1">{garmin['stress_avg']} <small class="text-xs text-slate-500 font-normal">/ 100</small></div>
                    </div>
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">👟</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Kroky</p>
                        <div class="text-xl font-black text-pink-400 mt-1">{garmin['steps']} <small class="text-xs text-slate-500 font-normal">kroků</small></div>
                    </div>
                </div>
            </section>

            <div class="bg-slate-900 border border-slate-800 p-4 rounded-2xl mb-6 shadow-xl">
                <h3 class="text-xs font-bold uppercase text-slate-400 mb-3">Tělesné metriky & Hmotnost</h3>
                <form action="/update-stats" method="POST" class="space-y-3">
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-[10px] text-slate-400 uppercase font-semibold mb-1">Hmotnost (kg)</label>
                            <input type="number" step="0.1" name="weight" value="{user_stats_cache['weight']}" class="w-full bg-black/40 border border-slate-800 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500 font-mono">
                        </div>
                        <div>
                            <label class="block text-[10px] text-slate-400 uppercase font-semibold mb-1">Tělesný tuk (%)</label>
                            <input type="number" step="0.1" name="body_fat" value="{user_stats_cache['body_fat']}" class="w-full bg-black/40 border border-slate-800 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-emerald-500 font-mono">
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
