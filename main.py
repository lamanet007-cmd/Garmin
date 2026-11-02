import os
import datetime
import time
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

# Jednoduchá mezipaměť (Cache) proti přetížení API (platnost 15 minut = 900 sekund)
api_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 900 
}

def fetch_garmin_data_safe():
    current_time = time.time()
    # Pokud máme platná data v cache, vrátíme je rovnou ven
    if api_cache["data"] and (current_time - api_cache["timestamp"] < api_cache["ttl"]):
        cached_data, cached_log = api_cache["data"]
        return cached_data, ["[API CACHE] Data načtena z mezipaměti (bez dotazu na Garmin API)"] + cached_log

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
        "achievable_fitness_age": "38",
        "respiration_avg": 14.5,
        "intensity_curr_week": 0,
        "intensity_week": 0,
        "intensity_month": 0,
        "intensity_90d": 0,
        "intensity_goal": 150,
        "monthly_avg_hr": 55,
        "hr_history": [],
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
                today_obj = datetime.date.today()
                today_str = today_obj.isoformat()
                base = "https://personal.connectapi.garmin.com"

                # 2. Dnešní klidový tep (200 OK)[span_0](start_span)[span_0](end_span)
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

                # 3. HRV (200 OK)[span_1](start_span)[span_1](end_span)
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

                # 4. Body Battery (200 OK)[span_2](start_span)[span_2](end_span)
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

                # 5. Spánek & Skóre (200 OK)[span_3](start_span)[span_3](end_span)
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

                # 6. Kroky přes ověřený stats endpoint[span_4](start_span)[span_4](end_span)
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

                # 7. Stres přes ověřený stats endpoint[span_5](start_span)[span_5](end_span)
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

                # 8. Denní souhrny za 90 dní (Respirace a Intenzivní minuty)[span_6](start_span)[span_6](end_span)
                try:
                    date_90_ago = (today_obj - datetime.timedelta(days=89)).isoformat()
                    date_30_ago = (today_obj - datetime.timedelta(days=29)).isoformat()
                    date_7_ago = (today_obj - datetime.timedelta(days=6)).isoformat()
                    
                    days_since_monday = today_obj.weekday()
                    current_week_start = (today_obj - datetime.timedelta(days=days_since_monday)).isoformat()

                    sum_url = f"{base}/usersummary-service/v2/dailysummaries?startDate={date_90_ago}&endDate={today_str}"
                    sum_res = requests.get(sum_url, headers=api_headers, timeout=10)
                    if sum_res.status_code == 200:
                        sum_json = sum_res.json()
                        rows = sum_json.get("data", []) if isinstance(sum_json, dict) else (sum_json if isinstance(sum_json, list) else [])
                        
                        int_curr_w = 0
                        int_roll_w = 0
                        int_m = 0
                        int_90 = 0

                        for row in rows:
                            if isinstance(row, dict):
                                c_date = str(row.get("calendarDate") or row.get("date") or "")[:10]
                                if not c_date:
                                    continue
                                
                                intensity = row.get("intensityMinutes") or row.get("intensityMinuteSummary")
                                if isinstance(intensity, dict):
                                    mod = float(intensity.get("moderate") or intensity.get("moderateMinutes") or 0)
                                    vig = float(intensity.get("vigorous") or intensity.get("vigorousMinutes") or 0)
                                    day_total = int(mod + (vig * 2))
                                    
                                    if c_date >= date_90_ago:
                                        int_90 += day_total
                                    if c_date >= date_30_ago:
                                        int_m += day_total
                                    if c_date >= date_7_ago:
                                        int_roll_w += day_total
                                    if c_date >= current_week_start:
                                        int_curr_w += day_total

                                if c_date == today_str:
                                    resp = row.get("respiration")
                                    if isinstance(resp, dict):
                                        avg_r = resp.get("avgValue")
                                        if avg_r is not None:
                                            data_metrics["respiration_avg"] = round(float(avg_r), 1)

                        data_metrics["intensity_curr_week"] = int_curr_w
                        data_metrics["intensity_week"] = int_roll_w
                        data_metrics["intensity_month"] = int_m
                        data_metrics["intensity_90d"] = int_90
                except Exception as sum_err:
                    debug_log.append(f"Chyba souhrnů: {sum_err}")

                # 9. Spolehlivé stahování 30denní historie klidového tepu pro graf
                try:
                    hr_history = []
                    for i in range(29, -1, -1):
                        d_str = (today_obj - datetime.timedelta(days=i)).isoformat()
                        h_url = f"{base}/wellness-service/wellness/dailyHeartRate?date={d_str}"
                        h_res = requests.get(h_url, headers=api_headers, timeout=5)
                        if h_res.status_code == 200:
                            rhr_val = h_res.json().get("restingHeartRate")
                            if rhr_val is not None:
                                hr_history.append({"date": d_str, "hr": int(rhr_val)})
                    
                    if hr_history:
                        data_metrics["hr_history"] = hr_history
                        data_metrics["monthly_avg_hr"] = round(sum(item["hr"] for item in hr_history) / len(hr_history))
                except Exception as h_hist_err:
                    debug_log.append(f"Chyba historie tepu: {h_hist_err}")

                # 10. Fitness věk a cíle[span_7](start_span)[span_7](end_span)
                try:
                    fa_url = f"{base}/fitnessage-service/fitnessage/v2/{today_str}"
                    fa_res = requests.get(fa_url, headers=api_headers, timeout=10)
                    if fa_res.status_code == 200:
                        fa_json = fa_res.json()
                        if fa_json.get("chronologicalAge") is not None:
                            data_metrics["chronological_age"] = int(round(float(fa_json.get("chronologicalAge"))))
                        if fa_json.get("fitnessAge") is not None:
                            data_metrics["fitness_age"] = str(int(round(float(fa_json.get("fitnessAge")))))
                        if fa_json.get("achievableFitnessAge") is not None:
                            data_metrics["achievable_fitness_age"] = str(int(round(float(fa_json.get("achievableFitnessAge")))))
                except Exception as fa_err:
                    debug_log.append(f"Chyba fitness věku: {fa_err}")

                # 11. Historie aktivit[span_8](start_span)[span_8](end_span)
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

    # Uložení do cache
    api_cache["data"] = (data_metrics, debug_log)
    api_cache["timestamp"] = current_time

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

    # Generování SVG grafu pro 30denní klidový tep
    svg_chart = ""
    if garmin["hr_history"]:
        hrs = [item["hr"] for item in garmin["hr_history"]]
        min_hr = min(hrs)
        max_hr = max(hrs)
        
        chart_min = min_hr - 3
        chart_max = max_hr + 3
        if chart_max == chart_min:
            chart_max += 5
        
        width = 500
        height = 110
        dx = width / max(len(hrs) - 1, 1)
        
        points = []
        for i, val in enumerate(hrs):
            x = i * dx
            y = height - ((val - chart_min) / (chart_max - chart_min)) * (height - 30) - 15
            points.append(f"{x},{y}")
        polyline_pts = " ".join(points)
        
        svg_chart = f"""
        <svg viewBox="0 0 {width} {height}" class="w-full h-28 overflow-visible font-mono text-[10px]">
            <line x1="0" y1="15" x2="{width}" y2="15" stroke="#1e293b" stroke-dasharray="4" />
            <text x="0" y="10" fill="#94a3b8">Max: {max_hr} bpm</text>
            
            <line x1="0" y1="{height - 15}" x2="{width}" y2="{height - 15}" stroke="#1e293b" stroke-dasharray="4" />
            <text x="0" y="{height - 3}" fill="#94a3b8">Min: {min_hr} bpm</text>

            <polyline fill="none" stroke="#f97316" stroke-width="2.5" points="{polyline_pts}" />
        """
        for i, val in enumerate(hrs):
            x = i * dx
            y = height - ((val - chart_min) / (chart_max - chart_min)) * (height - 30) - 15
            svg_chart += f'<circle cx="{x}" cy="{y}" r="3.5" fill="#fb923c" /><text x="{x - 6}" y="{y - 7}" fill="#fdba74" font-size="9">{val}</text>'
        svg_chart += "</svg>"
    else:
        svg_chart = '<div class="text-xs text-slate-500 text-center py-4">Graf se načítá nebo data historie tepu nejsou dostupná.</div>'

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

            function switchIntensity(type) {{
                ['curr', 'week', 'month', '90d'].forEach(t => {{
                    const el = document.getElementById('val-' + t);
                    const btn = document.getElementById('btn-' + t);
                    if (el) el.classList.add('hidden');
                    if (btn) btn.className = 'px-2 py-1 rounded-lg text-[10px] font-semibold text-slate-400 hover:text-white transition';
                }});
                const targetEl = document.getElementById('val-' + type);
                const targetBtn = document.getElementById('btn-' + type);
                if (targetEl) targetEl.classList.remove('hidden');
                if (targetBtn) targetBtn.className = 'px-2 py-1 rounded-lg text-[10px] font-bold bg-amber-600 text-white transition shadow';
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
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl">
                        <span class="text-xl">🫁</span>
                        <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold mt-2">Dech. frekvence</p>
                        <div class="text-xl font-black text-indigo-400 mt-1">{garmin['respiration_avg']} <small class="text-xs text-slate-500 font-normal">dechů/m</small></div>
                    </div>
                    
                    <!-- Intenzivní minuty s přepínačem -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl col-span-2">
                        <div class="flex items-center justify-between mb-2">
                            <div class="flex items-center space-x-2">
                                <span class="text-xl">🔥</span>
                                <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Intenzivní minuty</p>
                            </div>
                            <div class="flex bg-black/50 p-1 rounded-xl border border-slate-800 space-x-1">
                                <button onclick="switchIntensity('curr')" id="btn-curr" class="px-2 py-1 rounded-lg text-[10px] font-bold bg-amber-600 text-white transition shadow">Akt. týden</button>
                                <button onclick="switchIntensity('week')" id="btn-week" class="px-2 py-1 rounded-lg text-[10px] font-semibold text-slate-400 hover:text-white transition">7 dní</button>
                                <button onclick="switchIntensity('month')" id="btn-month" class="px-2 py-1 rounded-lg text-[10px] font-semibold text-slate-400 hover:text-white transition">Měsíc</button>
                                <button onclick="switchIntensity('90d')" id="btn-90d" class="px-2 py-1 rounded-lg text-[10px] font-semibold text-slate-400 hover:text-white transition">90 dní</button>
                            </div>
                        </div>
                        <div class="mt-3 text-center py-1">
                            <div id="val-curr" class="intensity-view text-2xl font-black text-amber-400">{garmin['intensity_curr_week']} <small class="text-xs text-slate-500 font-normal">min (od pondělí)</small></div>
                            <div id="val-week" class="intensity-view text-2xl font-black text-amber-400 hidden">{garmin['intensity_week']} <small class="text-xs text-slate-500 font-normal">min (posledních 7 dní)</small></div>
                            <div id="val-month" class="intensity-view text-2xl font-black text-amber-400 hidden">{garmin['intensity_month']} <small class="text-xs text-slate-500 font-normal">min (posledních 30 dní)</small></div>
                            <div id="val-90d" class="intensity-view text-2xl font-black text-amber-400 hidden">{garmin['intensity_90d']} <small class="text-xs text-slate-500 font-normal">min (posledních 90 dní)</small></div>
                        </div>
                    </div>
                    
                    <!-- Fitness věk -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800 shadow-xl col-span-2 md:col-span-3">
                        <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
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
                    </div>

                    <!-- Měsíční průměr klidového tepu & Skrytelný graf -->
                    <details class="bg-gradient-to-br from-slate-900 to-slate-900/40 rounded-2xl border border-slate-800 shadow-xl col-span-2 md:col-span-3 overflow-hidden group">
                        <summary class="p-4 cursor-pointer flex items-center justify-between select-none list-none">
                            <div class="flex items-center space-x-3">
                                <span class="text-xl">📈</span>
                                <div>
                                    <p class="text-slate-400 text-[10px] uppercase tracking-wider font-semibold">Měsíční průměr klidového tepu (30 dní)</p>
                                    <div class="text-xl font-black text-orange-400 mt-0.5">{garmin['monthly_avg_hr']} <small class="text-xs text-slate-500 font-normal">bpm</small></div>
                                </div>
                            </div>
                            <div class="flex items-center space-x-2">
                                <span class="text-[10px] bg-slate-800 text-orange-400 border border-slate-700 px-2.5 py-1 rounded-full font-bold">GRAF</span>
                                <span class="text-emerald-400 text-sm transform group-open:rotate-180 transition">▼</span>
                            </div>
                        </summary>
                        <div class="px-4 pb-4 pt-1 border-t border-slate-800/80 bg-black/20">
                            {svg_chart}
                        </div>
                    </details>
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
