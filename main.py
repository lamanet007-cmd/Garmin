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
        "sleep_score": 78,
        "sleep_hours": 7.5,
        "stress_avg": 25,
        "steps": 7500,
        "chronological_age": 44,
        "fitness_age": "39",
        "achievable_fitness_age": "37",
        "fitness_components": [],
        "activities_list": [],
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
                base = "https://personal.connectapi.garmin.com"

                # 2. Klidový tep (200 OK)
                try:
                    hr_url = f"{base}/wellness-service/wellness/dailyHeartRate?date={today_str}"
                    hr_res = requests.get(hr_url, headers=api_headers, timeout=10)
                    if hr_res.status_code == 200:
                        debug_log.append("Klidový tep stažen (200 OK)!")
                        rhr = hr_res.json().get("restingHeartRate")
                        if rhr is not None:
                            data_metrics["resting_heart_rate"] = int(rhr)
                except Exception as hr_err:
                    debug_log.append(f"Chyba tepu: {hr_err}")

                # 3. HRV (200 OK)
                try:
                    hrv_url = f"{base}/hrv-service/hrv/{today_str}"
                    hrv_res = requests.get(hrv_url, headers=api_headers, timeout=10)
                    if hrv_res.status_code == 200:
                        debug_log.append("HRV staženo (200 OK)!")
                        hrv_json = hrv_res.json()
                        val = hrv_json.get("hrvSummary", {}).get("lastNightAvg")
                        if isinstance(val, (int, float)):
                            data_metrics["hrv_ms"] = int(val)
                except Exception as h_err:
                    debug_log.append(f"Chyba HRV: {h_err}")

                # 4. Body Battery (200 OK)
                try:
                    bb_url = f"{base}/wellness-service/wellness/bodyBattery/reports/daily?startDate={today_str}&endDate={today_str}"
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

                # 5. Spánek & Skóre (200 OK)
                try:
                    sleep_url = f"{base}/sleep-service/sleep/dailySleep?date={today_str}"
                    sleep_res = requests.get(sleep_url, headers=api_headers, timeout=10)
                    if sleep_res.status_code == 200:
                        debug_log.append("Spánek stažen (200 OK)!")
                        sleep_json = sleep_res.json()
                        items = sleep_json if isinstance(sleep_json, list) else [sleep_json]
                        for item in items:
                            if isinstance(item, dict):
                                score_val = item.get("sleepScores", {}).get("overall", {}).get("value")
                                if score_val is not None:
                                    data_metrics["sleep_score"] = int(score_val)
                                seconds = item.get("sleepTimeSeconds") or item.get("durationInSeconds")
                                if seconds:
                                    data_metrics["sleep_hours"] = round(float(seconds) / 3600, 1)
                except Exception as s_err:
                    debug_log.append(f"Chyba spánku: {s_err}")

                # 6. Kroky přes ověřený stats endpoint
                try:
                    steps_url = f"{base}/usersummary-service/stats/steps/daily/{today_str}/{today_str}"
                    steps_res = requests.get(steps_url, headers=api_headers, timeout=10)
                    if steps_res.status_code == 200:
                        steps_json = steps_res.json()
                        items = steps_json if isinstance(steps_json, list) else [steps_json]
                        for item in items:
                            if isinstance(item, dict):
                                s_val = item.get("totalSteps") or item.get("steps") or item.get("value")
                                if s_val is not None:
                                    data_metrics["steps"] = int(s_val)
                except Exception as st_err:
                    debug_log.append(f"Chyba kroků: {st_err}")

                # 7. Stres přes ověřený stats endpoint
                try:
                    stress_url = f"{base}/usersummary-service/stats/stress/daily/{today_str}/{today_str}"
                    stress_res = requests.get(stress_url, headers=api_headers, timeout=10)
                    if stress_res.status_code == 200:
                        stress_json = stress_res.json()
                        items = stress_json if isinstance(stress_json, list) else [stress_json]
                        for item in items:
                            if isinstance(item, dict):
                                st_val = item.get("averageStressLevel") or item.get("stressScore") or item.get("value")
                                if st_val is not None:
                                    data_metrics["stress_avg"] = int(st_val)
                except Exception as str_err:
                    debug_log.append(f"Chyba stresu: {str_err}")

                # 8. Fitness věk, cíle a komponenty (vylepšené parsování)
                try:
                    fa_url = f"{base}/fitnessage-service/fitnessage/v2/{today_str}"
                    fa_res = requests.get(fa_url, headers=api_headers, timeout=10)
                    debug_log.append(f"Fitness Age API Status: {fa_res.status_code}")
                    if fa_res.status_code == 200:
                        fa_json = fa_res.json()
                        if fa_json.get("chronologicalAge") is not None:
                            data_metrics["chronological_age"] = int(round(float(fa_json.get("chronologicalAge"))))
                        if fa_json.get("fitnessAge") is not None:
                            data_metrics["fitness_age"] = str(int(round(float(fa_json.get("fitnessAge")))))
                        if fa_json.get("achievableFitnessAge") is not None:
                            data_metrics["achievable_fitness_age"] = str(int(round(float(fa_json.get("achievableFitnessAge")))))
                        
                        # Hledáme komponenty v různých možných polích
                        comps = fa_json.get("components") or fa_json.get("fitnessAgeComponents") or fa_json.get("factors") or []
                        if isinstance(comps, list) and len(comps) > 0:
                            parsed_comps = []
                            for c in comps:
                                name = c.get("title") or c.get("name") or c.get("componentType") or "Faktor"
                                desc = c.get("feedback") or c.get("description") or c.get("status") or c.get("recommendation") or "Upravit trénink nebo tělesný tuk."
                                parsed_comps.append({"name": str(name), "desc": str(desc)})
                            data_metrics["fitness_components"] = parsed_comps
                        else:
                            # Pokud jsou data v jiném formátu, zkusíme vytáhnout alespoň textové klíče
                            debug_log.append(f"FitnessAge surová struktura: {str(fa_json)[:150]}")
                except Exception as fa_err:
                    debug_log.append(f"Chyba fitness věku: {fa_err}")

                # 9. Historie aktivit přes ověřený search endpoint
                try:
                    act_url = f"{base}/activitylist-service/activities/search/activities?start=0&limit=30"
                    act_res = requests.get(act_url, headers=api_headers, timeout=10)
                    if act_res.status_code == 200:
                        acts = act_res.json()
                        if isinstance(acts, list):
                            parsed_acts = []
                            for a in acts:
                                name = a.get("activityName") or a.get("activityType", {}).get("typeKey", "Aktivita")
                                date_time = str(a.get("startTimeLocal", "")).split("T")[0]
                                duration = round(float(a.get("duration", 0)) / 60, 1)
                                distance_km = round(float(a.get("distance", 0)) / 1000, 2)
                                parsed_acts.append({"name": name, "date": date_time, "duration": duration, "distance": distance_km})
                            data_metrics["activities_list"] = parsed_acts
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
    
    debug_html = "".join([f"<div class='text-xs text-emerald-400 font-mono'>[API LOG] {item}</div>" for item in debug_log])

    activities_html = ""
    if garmin["activities_list"]:
        for act in garmin["activities_list"]:
            activities_html += f"""
            <div class="flex items-center justify-between py-2.5 border-b border-slate-800/60 last:border-none text-xs">
                <div>
                    <div class="font-bold text-white">{act['name']}</div>
                    <div class="text-[10px] text-slate-400">{act['date']} • {act['duration']} min</div>
                </div>
                <div class="font-mono text-emerald-400 font-semibold">{act['distance']} km</div>
            </div>
            """
    else:
        activities_html = '<div class="text-xs text-slate-500 py-2">Žádné nedávné aktivity k zobrazení.</div>'

    comps_html = ""
    if garmin["fitness_components"]:
        for comp in garmin["fitness_components"]:
            comps_html += f"""
            <div class="bg-black/30 p-2.5 rounded-xl border border-slate-800/80 mb-2 last:mb-0 text-xs">
                <span class="font-bold text-cyan-400 block mb-0.5">{comp['name']}</span>
                <span class="text-slate-300 text-[11px]">{comp['desc']}</span>
            </div>
            """
    else:
        comps_html = '<div class="text-xs text-slate-500 py-1">Garmin vrací fitness věk bez dílčích doporučení (nebo vyžaduje zadání aktuálního % tělesného tuku v profilu).</div>'

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
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Spánek ({garmin['sleep_score']} skóre)</p>
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
                    
                    <!-- Fitness věk & Doporučení -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl col-span-2 md:col-span-3">
                        <div class="flex flex-col md:flex-row md:items-center justify-between mb-3 pb-3 border-b border-slate-800 gap-3">
                            <div class="flex items-center space-x-3">
                                <span class="text-2xl">🧬</span>
                                <div>
                                    <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Fitness věk (Reálný: {garmin['chronological_age']} let)</p>
                                    <div class="text-2xl font-black text-cyan-400 mt-0.5">
                                        {garmin['fitness_age']} <small class="text-xs text-slate-400 font-normal">let</small>
                                    </div>
                                </div>
                            </div>
                            <div class="bg-black/30 px-3 py-2 rounded-xl border border-slate-800/80 text-left md:text-right">
                                <p class="text-[10px] text-slate-400 uppercase font-bold">Dosažitelný cíl</p>
                                <div class="text-lg font-extrabold text-emerald-400">{garmin['achievable_fitness_age']} let</div>
                            </div>
                        </div>
                        <div>
                            <p class="text-[10px] font-bold uppercase text-slate-400 mb-2">Co je potřeba upravit (Garmin doporučení):</p>
                            {comps_html}
                        </div>
                    </div>
                </div>
            </section>

            <!-- Rozbalovací historie aktivit -->
            <details class="bg-slate-900 border border-slate-800 rounded-2xl mb-6 shadow-xl overflow-hidden group">
                <summary class="p-4 cursor-pointer flex items-center justify-between font-semibold text-xs uppercase tracking-wider text-slate-300 hover:text-white transition select-none">
                    <span>Historie aktivit</span>
                    <span class="text-emerald-400 text-sm transform group-open:rotate-180 transition">▼</span>
                </summary>
                <div class="px-4 pb-4 pt-1 border-t border-slate-800/80 bg-black/20 max-h-60 overflow-y-auto">
                    {activities_html}
                </div>
            </details>

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
