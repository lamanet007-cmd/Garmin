import os
import datetime
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "")

user_stats_cache = {
    "user": "Drsňák",
    "weight": 84.5,
    "body_fat": 14.2,
}

# 1. Oddělená cache pro historii (platí 24 hodin, protože minulost se nemění)
history_cache = {
    "hr_history": [],
    "hrv_history": [],
    "steps_month": 0,
    "monthly_avg_hr": 55,
    "monthly_avg_hrv": 48,
    "timestamp": 0,
    "ttl": 86400  # 24 hodin
}

# 2. Cache pro dnešní živá data (platí 15 minut)
live_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 900
}

ai_cache = {
    "title": "",
    "summary": "",
    "training_advice": "",
    "nutrition_advice": "",
    "longevity_deep_dive": "",
    "daily_menu": "",
    "timestamp": 0,
    "ttl": 900
}

def generate_ai_longevity_advice(garmin, force_ai: bool = False):
    """Generuje hloubkovou AI analýzu, tréninkový manuál a denní jídelníček pro longevity a fullbody."""
    global ai_cache
    current_time = time.time()
    
    if not force_ai and ai_cache["title"] and (current_time - ai_cache["timestamp"] < ai_cache["ttl"]):
        return ai_cache["title"], ai_cache["summary"], ai_cache["training_advice"], ai_cache["nutrition_advice"], ai_cache["longevity_deep_dive"], ai_cache["daily_menu"]

    hrv = garmin.get("hrv_ms", 48)
    monthly_hrv = garmin.get("monthly_avg_hrv", 48)
    bb = garmin.get("body_battery_max", 75)
    sleep = garmin.get("sleep_score", 78)
    sleep_h = garmin.get("sleep_hours", 7.5)
    stress = garmin.get("stress_avg", 25)
    rhr = garmin.get("resting_heart_rate", 56)
    weight = user_stats_cache.get("weight", 84.5)

    if bb >= 70 and hrv >= 45 and stress < 35:
        title = "MAXIMÁLNÍ ANABOLICKÁ PŘIPRAVENOST & ŠPIČKOVÁ VAGÁLNÍ AKTIVITA"
        summary = (
            f"Dnešní biometrický obraz jednoznačně potvrzuje ideální stav organismu. S hodnotou HRV na {hrv} ms (porovnej s tvým 30denním průměrem {monthly_hrv} ms) "
            f"a maximální energetickou rezervou Body Battery na {bb}/100 disponuješ vynikající tonizací vagového nervu. "
            f"Centrální nervová soustava (CNS) nevykazuje žádné známky kumulované únavy, sympatikus je v klidu a parasympatikus během noci dominoval. "
            f"Klidový tep {rhr} BPM a spánkové skóre {sleep}/100 ({sleep_h} hodin) svědčí o tom, že regenerace proběhla na 100 %. "
            f"Tělo se nachází v silném anabolickém okně s vysokou inzulínovou citlivostí a připraveností na maximální neuromuskulární výkon."
        )
        training_advice = (
            f"Využij tohoto vzácného okna pro **těžký, progresivní fullbody trénink (Heavy Day)**. "
            f"Tvá nervová soustava dokáže efektivně rekrutovat vysokoprahové motorické jednotky typu II (rychlá svalová vlákna). "
            f"Zavěs do tréninkového plánu 4–5 těžkých složených cviků: hluboké dřepy nebo trap-bar mrtvé tahy, shyby na hrazdě se závažím, "
            f"tlaky na lavičce (bench press) a vojenské tlaky nad hlavu (overhead press). "
            f"Pracuj v intenzitě 80–87 % 1RM, proveď 4–5 pracovních sérií po 5–6 opakování s delšími pauzami (2,5 až 3 minuty) pro úplné obnovení ATP-CP systému."
        )
    elif bb >= 50 and stress < 50:
        title = "STABILNÍ ADAPTACE / STŘEDNÍ INTENZITA A OPTIMALIZACE R.O.M."
        summary = (
            f"Biometrická data ukazují standardní, vyrovnaný stav (Body Battery {bb}/100, HRV {hrv} ms, průměrný stres {stress}/100). "
            f"Organismus úspěšně zvládl noční zotavení, ale vnitřní prostředí naráží na běžné denní stresory a mírnou únavu z minulých dní. "
            f"Nejedná se o deficit, který by vyžadoval úplné volno, ale centrální nervová soustava vyžaduje citlivější přístup."
        )
        training_advice = (
            f"Naplánuj si **fullbody trénink zaměřený na hypertrofii, svalové procítění a plný rozsah pohybu (R.O.M.)**. "
            f"Drž se v intenzitě RPE 7–8 (v rezervě 2–3 opakování do technického selhání). Zvol 3–4 série o 8–12 opakování. "
            f"Vyhni se maximálním vahám, které drancují CNS. Zařaď jednoručky, kladky a unilaterální cviky."
        )
    else:
        title = "AKUTNÍ SIGNÁL K REGENERACI – OCHRANA LONGEVITY & CNS"
        summary = (
            f"Varování: Tvoje tělo vysílá jasné signály o vyčerpání. HRV pokleslo na {hrv} ms, Body Battery stagnuje na nízké hodnotě ({bb}/100) "
            f"a průměrný denní stres {stress}/100 ukazuje, že organismus bojuje s vnitřním deficitem. "
            f"Pokus o těžký silový trénink v tomto stavu by vedl k masivnímu vyplavení kortizolu a katabolismu svalové hmoty."
        )
        training_advice = (
            f"Dnešní den **kategoricky vynechej veškeré těžké železo a silové cviky**. Přepni do režimu active recovery. "
            f"Absolvuj 45–60 minut vědomé chůze v Zóně 1 (tepová frekvence striktně pod 110 BPM) a 30 minut hlubokého strečinku či mobilizace."
        )

    protein_min = round(weight * 1.8, 1)
    protein_max = round(weight * 2.2, 1)
    nutrition_advice = (
        f"Jako cvičenec na fullbody režimu stimuluješ celé tělo najednou, což znamená, že svalová bílkovinná syntéza (MPS) "
        f"zůstává výrazně zvýšená přibližně 48 hodin po tréninku. Cílíš na **{protein_min} až {protein_max} gramů bílkovin denně** "
        f"(cca 1.8–2.2 g na kg tělesné hmotnosti), rozložených do 4 jídel. Nezapomeň na komplexní sacharidy, zdravé tuky a hořčík (glycinát před spaním)."
    )

    longevity_deep_dive = (
        f"Pro maximální prodloužení zdravého věku (healthspan) kombinuj fullbody trénink, mitochondriální kardio v Zóně 2 "
        f"a spánek (skóre {sleep}/100), během kterého se aktivuje glymfatický systém mozku pro odplavení metabolického odpadu."
    )

    day_of_week = datetime.date.today().weekday()
    menus = [
        ("Pondělní High-Protein & Anabolický Jídelníček", 
         "• **Snídaně:** Míchaná vajíčka (4 ks) na másle, žitný chléb, avokádo a zelenina.<br>• **Svačina:** Řecký jogurt s proteinem a lesním ovocem.<br>• **Oběd:** Hovězí steak (200g), batátové pyré, brokolice.<br>• **Večeře:** Pečený losos (180g), quinoa, listový salát."),
        ("Úterní Fullbody Regenerační Jídelníček", 
         "• **Snídaně:** Ovesná kaše s proteinem, arašídovým máslem a banánem.<br>• **Svačina:** Tvaroh (250g) s jablkem a skořicí.<br>• **Oběd:** Kuřecí prsa (200g), jasmínová rýže, dušená mrkev a hrášek.<br>• **Večeře:** Omeleta ze 4 vajec se špenátem a fetou."),
        ("Středomořský Longevity Jídelníček", 
         "• **Snídaně:** Vaječná omeleta (3 ks) s rajčaty a prosciuttem.<br>• **Svačina:** Cottage sýr s okurkou.<br>• **Oběd:** Krůtí medailonky, pečené brambory, fazolové lusky.<br>• **Večeře:** Treska na másle, rajčatový salát s olivovým olejem."),
        ("Čtvrteční Síla & Svalový Růst Jídelníček", 
         "• **Snídaně:** Proteinové palačinky s tvarohem.<br>• **Svačina:** Skyr (400ml) s mandlemi.<br>• **Oběd:** Vepřová panenka (200g), basmati rýže, okurkový salát.<br>• **Večeře:** Kuřecí čtvrtka, batátové hranolky, jogurtový dip."),
        ("Páteční Anabolický Jídelníček", 
         "• **Snídaně:** Vaječina (3 vejce + 2 bílky), kvalitní šunka, žitný chléb.<br>• **Svačina:** Proteinový shake s ovesným nápojem.<br>• **Oběd:** Hovězí guláš s rýží.<br>• **Večeře:** Mozzarella light, rajčata, bazalkové pesto, tuňák."),
        ("Víkendový Fitness Jídelníček", 
         "• **Snídaně:** Domácí vafle z vloček a vajec, tvaroh, jahody.<br>• **Svačina:** Hrst vlašských ořechů a proteinová tyčinka.<br>• **Oběd:** Pečené krůtí stehno, šťouchané brambory.<br>• **Večeře:** Pstruh na bylinkách, pečená kořenová zelenina."),
        ("Nedělní Longevity & Odpočinkový Jídelníček", 
         "• **Snídaně:** Zapečený sýrový toast s avokádem.<br>• **Svačina:** Tučný tvaroh s borůvkami.<br>• **Oběd:** Pomalu pečená hovězí pečeně, silný vývar.<br>• **Večeře:** Zeleninový salát s grilovaným kuřecím masem.")
    ]

    menu_title, menu_content = menus[day_of_week % len(menus)]

    ai_cache["title"] = title
    ai_cache["summary"] = summary
    ai_cache["training_advice"] = training_advice
    ai_cache["nutrition_advice"] = nutrition_advice
    ai_cache["longevity_deep_dive"] = longevity_deep_dive
    ai_cache["daily_menu"] = f"<strong>{menu_title}:</strong><br><br>{menu_content}"
    ai_cache["timestamp"] = current_time

    return title, summary, training_advice, nutrition_advice, longevity_deep_dive, ai_cache["daily_menu"]

def fetch_day_hrv(base, api_headers, d_str):
    try:
        res = requests.get(f"{base}/hrv-service/hrv/{d_str}", headers=api_headers, timeout=5)
        if res.status_code == 200:
            val = res.json().get("hrvSummary", {}).get("lastNightAvg")
            if isinstance(val, (int, float)):
                return {"date": d_str, "hrv": int(val)}
    except:
        pass
    return None

def fetch_day_steps(base, api_headers, d_str):
    try:
        res = requests.get(f"{base}/usersummary-service/stats/steps/daily/{d_str}/{d_str}", headers=api_headers, timeout=5)
        if res.status_code == 200:
            items = res.json()
            items = items if isinstance(items, list) else [items]
            for item in items:
                if isinstance(item, dict):
                    s_val = item.get("totalSteps") or item.get("steps") or item.get("value") or item.get("stepCount")
                    if s_val is not None:
                        return {"date": d_str, "steps": int(s_val)}
    except:
        pass
    return None

def fetch_day_hr(base, api_headers, d_str):
    try:
        res = requests.get(f"{base}/wellness-service/wellness/dailyHeartRate?date={d_str}", headers=api_headers, timeout=5)
        if res.status_code == 200:
            rhr_val = res.json().get("restingHeartRate")
            if rhr_val is not None:
                return {"date": d_str, "hr": int(rhr_val)}
    except:
        pass
    return None

def fetch_garmin_data_safe(force_refresh: bool = False):
    global history_cache
    current_time = time.time()
    
    # 1. Pokud máme platná živá data (v rámci 15 minut) a nenutili jsme explicitní refresh, vrátíme je
    if not force_refresh and live_cache["data"] and (current_time - live_cache["timestamp"] < live_cache["ttl"]):
        cached_data, cached_log = live_cache["data"]
        return cached_data, ["[API CACHE] Živá i historická data načtena z mezipaměti (okamžitě)"] + cached_log

    debug_log = []
    if force_refresh:
        debug_log.append("[API REFRESH] Vynucena obnova dat z Garmin API.")

    data_metrics = {
        "resting_heart_rate": 56,
        "hrv_ms": 48,
        "monthly_avg_hrv": 48,
        "hrv_history": [],
        "body_battery_max": 75,
        "sleep_score": 78,
        "sleep_hours": 7.5,
        "stress_avg": 25,
        "steps": 7500,
        "steps_month": 0,
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

    fetch_success = False

    try:
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
                fetch_success = True
                api_headers = {"Authorization": f"Bearer {access_token}"}
                today_obj = datetime.date.today()
                today_str = today_obj.isoformat()
                base = "https://personal.connectapi.garmin.com"

                # 2. INTELIGENTNÍ HISTORIE: Zkontrolujeme, zda máme starší historii v 24h cache.
                # Pokud vypršela nebo je prázdná, stáhneme ji paralelně. Minulost se přece nemění!
                is_history_expired = force_refresh or not history_cache["hr_history"] or (current_time - history_cache["timestamp"] > history_cache["ttl"])

                if is_history_expired:
                    debug_log.append("[HISTORY REFRESH] Minulost vypršela nebo je vynucena – stahuji 30denní historii paralelně.")
                    past_dates = [(today_obj - datetime.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]

                    with ThreadPoolExecutor(max_workers=10) as executor:
                        hrv_futures = {executor.submit(fetch_day_hrv, base, api_headers, d): d for d in past_dates}
                        steps_futures = {executor.submit(fetch_day_steps, base, api_headers, d): d for d in past_dates}
                        hr_futures = {executor.submit(fetch_day_hr, base, api_headers, d): d for d in past_dates}

                        hrv_list = []
                        for future in as_completed(hrv_futures):
                            res = future.result()
                            if res:
                                hrv_list.append(res)
                        hrv_list.sort(key=lambda x: x["date"])

                        total_month_steps = 0
                        steps_dict = {}
                        for future in as_completed(steps_futures):
                            res = future.result()
                            if res:
                                steps_dict[res["date"]] = res["steps"]
                                total_month_steps += res["steps"]

                        hr_list = []
                        for future in as_completed(hr_futures):
                            res = future.result()
                            if res:
                                hr_list.append(res)
                        hr_list.sort(key=lambda x: x["date"])

                    # Uložíme do 24hodinové historické cache
                    history_cache["hr_history"] = hr_list
                    history_cache["hrv_history"] = hrv_list
                    history_cache["steps_dict"] = steps_dict
                    history_cache["steps_month"] = total_month_steps
                    history_cache["monthly_avg_hr"] = round(sum(item["hr"] for item in hr_list) / len(hr_list)) if hr_list else 55
                    history_cache["monthly_avg_hrv"] = round(sum(item["hrv"] for item in hrv_list) / len(hrv_list)) if hrv_list else 48
                    history_cache["timestamp"] = current_time
                else:
                    debug_log.append("[HISTORY CACHE] Využívám uloženou 24h historii (minulost se nemění, šetříme API requesty).")

                # Naplníme metriky z historické cache
                data_metrics["hr_history"] = history_cache["hr_history"]
                data_metrics["hrv_history"] = history_cache["hrv_history"]
                data_metrics["steps_month"] = history_cache["steps_month"]
                data_metrics["monthly_avg_hr"] = history_cache["monthly_avg_hr"]
                data_metrics["monthly_avg_hrv"] = history_cache["monthly_avg_hrv"]
                if data_metrics["hr_history"]:
                    data_metrics["resting_heart_rate"] = data_metrics["hr_history"][-1]["hr"]

                # 3. Dnešní živá data (stahujeme vždy, protože dnešek se vyvíjí)
                try:
                    hrv_res = requests.get(f"{base}/hrv-service/hrv/{today_str}", headers=api_headers, timeout=5)
                    if hrv_res.status_code == 200:
                        val = hrv_res.json().get("hrvSummary", {}).get("lastNightAvg")
                        if isinstance(val, (int, float)):
                            data_metrics["hrv_ms"] = int(val)
                except:
                    pass

                try:
                    bb_res = requests.get(f"{base}/wellness-service/wellness/bodyBattery/reports/daily?startDate={today_str}&endDate={today_str}", headers=api_headers, timeout=5)
                    if bb_res.status_code == 200:
                        items = bb_res.json()
                        items = items if isinstance(items, list) else [items]
                        for item in items:
                            if isinstance(item, dict):
                                arr = item.get("bodyBatteryValuesArray", [])
                                if arr:
                                    last = arr[-1]
                                    if isinstance(last, list) and len(last) > 1:
                                        data_metrics["body_battery_max"] = int(last[1])
                except:
                    pass

                try:
                    sleep_res = requests.get(f"{base}/sleep-service/sleep/dailySleep?date={today_str}", headers=api_headers, timeout=5)
                    if sleep_res.status_code == 200:
                        items = sleep_res.json()
                        items = items if isinstance(items, list) else [items]
                        for item in items:
                            if isinstance(item, dict):
                                s_val = item.get("sleepScores", {}).get("overall", {}).get("value")
                                if s_val is not None:
                                    data_metrics["sleep_score"] = int(s_val)
                                secs = item.get("sleepTimeSeconds") or item.get("durationInSeconds")
                                if secs:
                                    data_metrics["sleep_hours"] = round(float(secs) / 3600, 1)
                except:
                    pass

                try:
                    stress_res = requests.get(f"{base}/usersummary-service/stats/stress/daily/{today_str}/{today_str}", headers=api_headers, timeout=5)
                    if stress_res.status_code == 200:
                        items = stress_res.json()
                        items = items if isinstance(items, list) else [items]
                        for item in items:
                            if isinstance(item, dict):
                                st = item.get("averageStressLevel") or item.get("stressScore") or item.get("value")
                                if st is not None:
                                    data_metrics["stress_avg"] = int(st)
                except:
                    pass

                try:
                    date_90_ago = (today_obj - datetime.timedelta(days=89)).isoformat()
                    date_7_ago = (today_obj - datetime.timedelta(days=6)).isoformat()
                    days_since_monday = today_obj.weekday()
                    current_week_start = (today_obj - datetime.timedelta(days=days_since_monday)).isoformat()

                    sum_res = requests.get(f"{base}/usersummary-service/v2/dailysummaries?startDate={date_90_ago}&endDate={today_str}", headers=api_headers, timeout=5)
                    if sum_res.status_code == 200:
                        sum_json = sum_res.json()
                        rows = sum_json.get("data", []) if isinstance(sum_json, dict) else (sum_json if isinstance(sum_json, list) else [])
                        int_curr_w, int_roll_w, int_m, int_90 = 0, 0, 0, 0
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
                                    if c_date >= (today_obj - datetime.timedelta(days=29)).isoformat():
                                        int_m += day_total
                                    if c_date >= date_7_ago:
                                        int_roll_w += day_total
                                    if c_date >= current_week_start:
                                        int_curr_w += day_total
                        data_metrics["intensity_curr_week"] = int_curr_w
                        data_metrics["intensity_week"] = int_roll_w
                        data_metrics["intensity_month"] = int_m
                        data_metrics["intensity_90d"] = int_90
                except:
                    pass

                try:
                    fa_res = requests.get(f"{base}/fitnessage-service/fitnessage/v2/{today_str}", headers=api_headers, timeout=5)
                    if fa_res.status_code == 200:
                        fa = fa_res.json()
                        if fa.get("fitnessAge") is not None:
                            data_metrics["fitness_age"] = str(int(round(float(fa.get("fitnessAge")))))
                        if fa.get("achievableFitnessAge") is not None:
                            data_metrics["achievable_fitness_age"] = str(int(round(float(fa.get("achievableFitnessAge")))))
                except:
                    pass

                try:
                    act_res = requests.get(f"{base}/activitylist-service/activities/search/activities?start=0&limit=30", headers=api_headers, timeout=5)
                    if act_res.status_code == 200:
                        acts = act_res.json()
                        if isinstance(acts, list):
                            parsed = []
                            for a in acts:
                                name = a.get("activityName") or a.get("activityType", {}).get("typeKey", "Aktivita")
                                dt = str(a.get("startTimeLocal", "")).split("T")[0]
                                dur = round(float(a.get("duration", 0)) / 60, 1)
                                dist = round(float(a.get("distance", 0)) / 1000, 2)
                                parsed.append({"name": name, "date": dt, "duration": dur, "distance": dist})
                            data_metrics["activities_list"] = parsed
                except:
                    pass

            else:
                debug_log.append("Access token nenalezen.")
        else:
            debug_log.append(f"Token chyba: {token_res.status_code}")

    except Exception as e:
        debug_log.append(f"Výjimka: {str(e)}")

    if fetch_success:
        live_cache["data"] = (data_metrics, debug_log)
        live_cache["timestamp"] = current_time

    return data_metrics, debug_log

@app.get("/", response_class=HTMLResponse)
def home(refresh: bool = False, ai_refresh: bool = False):
    garmin, debug_log = fetch_garmin_data_safe(force_refresh=refresh)
    
    debug_html = "".join([f"<div class='text-xs text-emerald-400 font-mono'>[API LOG] {item}</div>" for item in debug_log])
    ai_title, ai_summary, ai_training, ai_nutrition, ai_longevity, ai_menu = generate_ai_longevity_advice(garmin, force_ai=ai_refresh)

    activities_html = ""
    if garmin["activities_list"]:
        for act in garmin["activities_list"]:
            activities_html += f"""
            <div class="flex items-center justify-between py-3 border-b border-[#2c2c2e] last:border-none text-xs">
                <div>
                    <div class="font-bold text-white text-sm">{act['name']}</div>
                    <div class="text-[11px] text-[#8e8e93] mt-0.5">{act['date']} • {act['duration']} min</div>
                </div>
                <div class="font-mono text-emerald-400 font-bold text-sm">{act['distance']} km</div>
            </div>
            """
    else:
        activities_html = '<div class="text-xs text-slate-500 py-3">Žádné nedávné aktivity.</div>'

    steps_month_formatted = f"{garmin['steps_month']:,}".replace(',', ' ')

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
            <line x1="0" y1="15" x2="{width}" y2="15" stroke="#2c2c2e" stroke-dasharray="4" />
            <text x="0" y="10" fill="#8e8e93">Max: {max_hr} bpm</text>
            <line x1="0" y1="{height - 15}" x2="{width}" y2="{height - 15}" stroke="#2c2c2e" stroke-dasharray="4" />
            <text x="0" y="{height - 3}" fill="#8e8e93">Min: {min_hr} bpm</text>
            <polyline fill="none" stroke="#ff9500" stroke-width="2.5" stroke-linecap="round" points="{polyline_pts}" />
        """
        for i, val in enumerate(hrs):
            x = i * dx
            y = height - ((val - chart_min) / (chart_max - chart_min)) * (height - 30) - 15
            svg_chart += f'<circle cx="{x}" cy="{y}" r="3.5" fill="#ff9500" /><text x="{x - 6}" y="{y - 7}" fill="#ffb340" font-size="9">{val}</text>'
        svg_chart += "</svg>"
    else:
        svg_chart = '<div class="text-xs text-slate-500 text-center py-4">Graf historie tepu se načítá.</div>'

    svg_hrv_chart = ""
    if garmin["hrv_history"]:
        hrvs = [item["hrv"] for item in garmin["hrv_history"]]
        min_hrv = min(hrvs)
        max_hrv = max(hrvs)
        chart_min = max(0, min_hrv - 5)
        chart_max = max_hrv + 5
        if chart_max == chart_min:
            chart_max += 10
        
        width = 500
        height = 110
        dx = width / max(len(hrvs) - 1, 1)
        
        points_hrv = []
        for i, val in enumerate(hrvs):
            x = i * dx
            y = height - ((val - chart_min) / (chart_max - chart_min)) * (height - 30) - 15
            points_hrv.append(f"{x},{y}")
        polyline_hrv_pts = " ".join(points_hrv)
        
        svg_hrv_chart = f"""
        <svg viewBox="0 0 {width} {height}" class="w-full h-28 overflow-visible font-mono text-[10px]">
            <line x1="0" y1="15" x2="{width}" y2="15" stroke="#2c2c2e" stroke-dasharray="4" />
            <text x="0" y="10" fill="#8e8e93">Max: {max_hrv} ms</text>
            <line x1="0" y1="{height - 15}" x2="{width}" y2="{height - 15}" stroke="#2c2c2e" stroke-dasharray="4" />
            <text x="0" y="{height - 3}" fill="#8e8e93">Min: {min_hrv} ms</text>
            <polyline fill="none" stroke="#30d158" stroke-width="2.5" stroke-linecap="round" points="{polyline_hrv_pts}" />
        """
        for i, val in enumerate(hrvs):
            x = i * dx
            y = height - ((val - chart_min) / (chart_max - chart_min)) * (height - 30) - 15
            svg_hrv_chart += f'<circle cx="{x}" cy="{y}" r="3.5" fill="#30d158" /><text x="{x - 6}" y="{y - 7}" fill="#60e188" font-size="9">{val}</text>'
        svg_hrv_chart += "</svg>"
    else:
        svg_hrv_chart = '<div class="text-xs text-slate-500 text-center py-4">Graf historie HRV se načítá.</div>'

    html_content = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Zdraví & AI Longevity</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            function copyLogToClipboard() {{
                const logContainer = document.getElementById('log-text-container');
                const text = logContainer.innerText;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('copy-btn');
                    btn.innerText = 'Zkopírováno!';
                    setTimeout(() => {{ btn.innerText = 'Kopírovat log'; }}, 2000);
                }});
            }}

            function switchIntensity(type) {{
                ['curr', 'week', 'month', '90d'].forEach(t => {{
                    const el = document.getElementById('val-' + t);
                    const btn = document.getElementById('btn-' + t);
                    if (el) el.classList.add('hidden');
                    if (btn) btn.className = 'px-2.5 py-1 rounded-full text-[11px] font-semibold text-[#8e8e93] hover:text-white transition';
                }});
                const targetEl = document.getElementById('val-' + type);
                const targetBtn = document.getElementById('btn-' + type);
                if (targetEl) targetEl.classList.remove('hidden');
                if (targetBtn) targetBtn.className = 'px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#ff9500] text-black transition shadow';
            }}
        </script>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
        </style>
    </head>
    <body class="bg-black text-white min-h-screen pb-16 antialiased">
        <div class="max-w-md md:max-w-xl mx-auto px-4 mt-6">
            
            <header class="mb-6 flex items-end justify-between border-b border-[#2c2c2e] pb-4">
                <div>
                    <p class="text-xs font-semibold text-[#8e8e93] uppercase tracking-wider">Garmin Live Dashboard</p>
                    <h1 class="text-3xl font-extrabold text-white tracking-tight mt-0.5">Zdraví & Výkon</h1>
                </div>
                <div class="flex items-center space-x-2 bg-[#1c1c1e] px-3 py-1.5 rounded-full border border-[#2c2c2e]">
                    <div class="w-6 h-6 rounded-full bg-[#0a84ff] text-white flex items-center justify-center font-bold text-xs">D</div>
                    <span class="text-xs font-semibold text-white">{user_stats_cache['user']}</span>
                </div>
            </header>

            <details class="bg-[#1c1c1e] border border-[#2c2c2e] rounded-2xl mb-6 overflow-hidden group">
                <summary class="p-3.5 cursor-pointer flex items-center justify-between font-semibold text-xs text-[#8e8e93] hover:text-white transition select-none">
                    <span class="flex items-center space-x-2">
                        <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        <span>Stav API & Diagnostika Logu</span>
                    </span>
                    <span class="text-[#8e8e93] text-sm transform group-open:rotate-180 transition">▼</span>
                </summary>
                <div class="p-3 border-t border-[#2c2c2e] bg-black/50">
                    <div class="flex justify-end mb-2">
                        <button id="copy-btn" onclick="copyLogToClipboard()" class="text-[10px] bg-[#2c2c2e] text-emerald-400 border border-slate-700 px-2.5 py-1 rounded-lg transition font-mono uppercase font-semibold">
                            Kopírovat log
                        </button>
                    </div>
                    <div id="log-text-container" class="space-y-1 overflow-x-auto font-mono text-[11px]">
                        {debug_html}
                    </div>
                </div>
            </details>

            <main class="space-y-6">
                
                <section>
                    <div class="flex items-center justify-between mb-3">
                        <h2 class="text-xl font-bold text-white tracking-tight">Klíčové metriky</h2>
                        <span class="text-xs text-[#0a84ff] font-semibold">Živá data</span>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex flex-col justify-between h-36">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#ff453a]/20 flex items-center justify-center text-[#ff453a] text-sm">❤️</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Klidový tep</span>
                            </div>
                            <div>
                                <div class="text-3xl font-extrabold text-white tracking-tight">{garmin['resting_heart_rate']} <span class="text-sm font-normal text-[#8e8e93]">BPM</span></div>
                                <p class="text-[10px] text-[#8e8e93] mt-1">Ukazatel kardiovaskulární zdatnosti.</p>
                            </div>
                        </div>

                        <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex flex-col justify-between h-36">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#30d158]/20 flex items-center justify-center text-[#30d158] text-sm">💚</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">HRV (Variabilita)</span>
                            </div>
                            <div>
                                <div class="text-3xl font-extrabold text-white tracking-tight">{garmin['hrv_ms']} <span class="text-sm font-normal text-[#8e8e93]">ms</span></div>
                                <p class="text-[10px] text-[#8e8e93] mt-1">Stav nervové soustavy a připravenost.</p>
                            </div>
                        </div>

                        <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex flex-col justify-between h-36">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#5e5ce6]/20 flex items-center justify-center text-[#5e5ce6] text-sm">😴</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Spánek</span>
                            </div>
                            <div>
                                <div class="text-3xl font-extrabold text-white tracking-tight">{garmin['sleep_hours']} <span class="text-sm font-normal text-[#8e8e93]">hod</span></div>
                                <div class="text-[11px] font-semibold text-[#5e5ce6] mt-0.5">Skóre: {garmin['sleep_score']}/100</div>
                            </div>
                        </div>

                        <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex flex-col justify-between h-36">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#0a84ff]/20 flex items-center justify-center text-[#0a84ff] text-sm">🔋</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Body Battery</span>
                            </div>
                            <div>
                                <div class="text-3xl font-extrabold text-white tracking-tight">{garmin['body_battery_max']} <span class="text-sm font-normal text-[#8e8e93]">/100</span></div>
                                <p class="text-[10px] text-[#8e8e93] mt-1">Celková energetická rezerva těla.</p>
                            </div>
                        </div>

                        <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex flex-col justify-between h-36">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#ff2d55]/20 flex items-center justify-center text-[#ff2d55] text-sm">👟</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Kroky</span>
                            </div>
                            <div>
                                <div class="text-3xl font-extrabold text-white tracking-tight">{garmin['steps']}</div>
                                <div class="text-[10px] text-[#8e8e93] mt-0.5">Za měsíc: <span class="text-white font-bold">{steps_month_formatted}</span></div>
                            </div>
                        </div>

                        <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex flex-col justify-between h-36">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#bf5af2]/20 flex items-center justify-center text-[#bf5af2] text-sm">⚡</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Úroveň stresu</span>
                            </div>
                            <div>
                                <div class="text-3xl font-extrabold text-white tracking-tight">{garmin['stress_avg']} <span class="text-sm font-normal text-[#8e8e93]">/100</span></div>
                                <p class="text-[10px] text-[#8e8e93] mt-1">Zátěž organismu během dne.</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section class="space-y-3">
                    <h2 class="text-xl font-bold text-white tracking-tight">Kondice a Fullbody Trénink</h2>

                    <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e]">
                        <div class="flex items-center justify-between mb-3">
                            <div class="flex items-center space-x-2">
                                <div class="w-7 h-7 rounded-lg bg-[#ff9500]/20 flex items-center justify-center text-[#ff9500] text-sm">🔥</div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Intenzivní minuty</span>
                            </div>
                            <div class="flex bg-black p-1 rounded-full border border-[#2c2c2e]">
                                <button onclick="switchIntensity('curr')" id="btn-curr" class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#ff9500] text-black transition shadow">Týden</button>
                                <button onclick="switchIntensity('week')" id="btn-week" class="px-2.5 py-1 rounded-full text-[11px] font-semibold text-[#8e8e93] hover:text-white transition">7 dní</button>
                                <button onclick="switchIntensity('month')" id="btn-month" class="px-2.5 py-1 rounded-full text-[11px] font-semibold text-[#8e8e93] hover:text-white transition">Měsíc</button>
                                <button onclick="switchIntensity('90d')" id="btn-90d" class="px-2.5 py-1 rounded-full text-[11px] font-semibold text-[#8e8e93] hover:text-white transition">90 dní</button>
                            </div>
                        </div>
                        <div class="py-2 text-center">
                            <div id="val-curr" class="intensity-view text-4xl font-extrabold text-[#ff9500] tracking-tight">{garmin['intensity_curr_week']} <span class="text-sm font-normal text-[#8e8e93]">min (od pondělí)</span></div>
                            <div id="val-week" class="intensity-view text-4xl font-extrabold text-[#ff9500] tracking-tight hidden">{garmin['intensity_week']} <span class="text-sm font-normal text-[#8e8e93]">min (7 dní)</span></div>
                            <div id="val-month" class="intensity-view text-4xl font-extrabold text-[#ff9500] tracking-tight hidden">{garmin['intensity_month']} <span class="text-sm font-normal text-[#8e8e93]">min (30 dní)</span></div>
                            <div id="val-90d" class="intensity-view text-4xl font-extrabold text-[#ff9500] tracking-tight hidden">{garmin['intensity_90d']} <span class="text-sm font-normal text-[#8e8e93]">min (90 dní)</span></div>
                        </div>
                    </div>

                    <div class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e] flex items-center justify-between">
                        <div class="flex items-center space-x-3">
                            <div class="w-10 h-10 rounded-xl bg-[#64d2ff]/20 flex items-center justify-center text-[#64d2ff] text-xl">🧬</div>
                            <div>
                                <span class="text-xs font-semibold text-[#8e8e93]">Fitness Věk</span>
                                <div class="text-2xl font-extrabold text-[#64d2ff] tracking-tight">{garmin['fitness_age']} <span class="text-sm font-normal text-[#8e8e93]">let</span></div>
                            </div>
                        </div>
                        <div class="text-right">
                            <span class="text-[10px] font-semibold text-[#8e8e93] uppercase">Dosažitelný cíl</span>
                            <div class="text-lg font-bold text-[#30d158]">{garmin['achievable_fitness_age']} let</div>
                        </div>
                    </div>
                </section>

                <section class="space-y-3">
                    <h2 class="text-xl font-bold text-white tracking-tight">Trendy a Historie</h2>

                    <details class="bg-[#1c1c1e] rounded-2xl border border-[#2c2c2e] overflow-hidden group">
                        <summary class="p-4 cursor-pointer flex items-center justify-between select-none list-none">
                            <div class="flex items-center space-x-3">
                                <div class="w-8 h-8 rounded-lg bg-[#ff9500]/20 flex items-center justify-center text-[#ff9500] text-base">📈</div>
                                <div>
                                    <span class="text-xs font-semibold text-[#8e8e93]">30denní klidový tep</span>
                                    <div class="text-lg font-bold text-white">{garmin['monthly_avg_hr']} <span class="text-xs font-normal text-[#8e8e93]">bpm (průměr)</span></div>
                                </div>
                            </div>
                            <span class="text-[#0a84ff] text-xs font-semibold group-open:rotate-180 transition">▼</span>
                        </summary>
                        <div class="p-4 border-t border-[#2c2c2e] bg-black/40">
                            {svg_chart}
                        </div>
                    </details>

                    <details class="bg-[#1c1c1e] rounded-2xl border border-[#2c2c2e] overflow-hidden group">
                        <summary class="p-4 cursor-pointer flex items-center justify-between select-none list-none">
                            <div class="flex items-center space-x-3">
                                <div class="w-8 h-8 rounded-lg bg-[#30d158]/20 flex items-center justify-center text-[#30d158] text-base">💚</div>
                                <div>
                                    <span class="text-xs font-semibold text-[#8e8e93]">30denní trend HRV (Variabilita)</span>
                                    <div class="text-lg font-bold text-white">{garmin['monthly_avg_hrv']} <span class="text-xs font-normal text-[#8e8e93]">ms (průměr)</span></div>
                                </div>
                            </div>
                            <span class="text-[#0a84ff] text-xs font-semibold group-open:rotate-180 transition">▼</span>
                        </summary>
                        <div class="p-4 border-t border-[#2c2c2e] bg-black/40">
                            {svg_hrv_chart}
                        </div>
                    </details>

                    <details class="bg-[#1c1c1e] rounded-2xl border border-[#2c2c2e] overflow-hidden group">
                        <summary class="p-4 cursor-pointer flex items-center justify-between select-none list-none">
                            <div class="flex items-center space-x-3">
                                <div class="w-8 h-8 rounded-lg bg-[#30d158]/20 flex items-center justify-center text-[#30d158] text-base">🏋️‍♂️</div>
                                <span class="text-sm font-bold text-white">Poslední fullbody / aktivity</span>
                            </div>
                            <span class="text-[#0a84ff] text-xs font-semibold group-open:rotate-180 transition">▼</span>
                        </summary>
                        <div class="px-4 pb-3 border-t border-[#2c2c2e] bg-black/40 max-h-64 overflow-y-auto">
                            {activities_html}
                        </div>
                    </details>
                </section>

                <section class="bg-[#1c1c1e] p-4 rounded-2xl border border-[#2c2c2e]">
                    <h3 class="text-xs font-bold text-[#8e8e93] uppercase tracking-wider mb-3">Tělesná hmotnost a složení</h3>
                    <form action="/update-stats" method="POST" class="space-y-3">
                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label class="block text-[11px] text-[#8e8e93] font-semibold mb-1">Váha (kg)</label>
                                <input type="number" step="0.1" name="weight" value="{user_stats_cache['weight']}" class="w-full bg-black border border-[#2c2c2e] rounded-xl px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-[#0a84ff]">
                            </div>
                            <div>
                                <label class="block text-[11px] text-[#8e8e93] font-semibold mb-1">Tuk (%)</label>
                                <input type="number" step="0.1" name="body_fat" value="{user_stats_cache['body_fat']}" class="w-full bg-black border border-[#2c2c2e] rounded-xl px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-[#0a84ff]">
                            </div>
                        </div>
                        <button type="submit" class="w-full py-2.5 bg-[#0a84ff] hover:bg-[#0071e3] text-white font-bold text-xs uppercase tracking-wider rounded-xl transition shadow">
                            Uložit změny
                        </button>
                    </form>
                </section>

                <section class="bg-gradient-to-br from-[#1c1c1e] to-[#2c2c2e]/70 border border-blue-500/30 p-6 rounded-3xl shadow-2xl relative overflow-hidden space-y-6">
                    <div class="absolute -right-6 -bottom-6 text-7xl opacity-10">🤖</div>
                    
                    <div class="flex items-center justify-between border-b border-white/10 pb-4">
                        <div class="flex items-center space-x-2">
                            <span class="px-2.5 py-1 rounded-full text-[10px] font-black bg-blue-500/20 text-blue-400 border border-blue-500/30 uppercase tracking-widest">AI Master Coach</span>
                            <span class="text-xs font-extrabold text-emerald-400 font-mono">{ai_title}</span>
                        </div>
                        <button onclick="window.location.href='/?ai_refresh=true';" class="text-[10px] bg-blue-600 hover:bg-blue-500 text-white font-bold px-3.5 py-1.5 rounded-xl transition shadow">
                            🔄 Generovat čerstvou AI analýzu
                        </button>
                    </div>

                    <div class="space-y-2">
                        <div class="text-xs font-bold text-blue-400 uppercase tracking-wider flex items-center space-x-2">
                            <span>📊</span>
                            <span>Hloubková analýza biometrik a CNS:</span>
                        </div>
                        <p class="text-xs text-slate-200 leading-relaxed font-medium">
                            {ai_summary}
                        </p>
                    </div>

                    <div class="bg-black/40 p-4 rounded-2xl border border-white/5 space-y-2">
                        <div class="flex items-center space-x-2 text-xs font-bold text-orange-400 uppercase tracking-wider">
                            <span>🏋️‍♂️</span>
                            <span>Detailní tréninkový manuál (Fullbody stratégia):</span>
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            {ai_training}
                        </p>
                    </div>

                    <div class="bg-black/40 p-4 rounded-2xl border border-white/5 space-y-2">
                        <div class="flex items-center space-x-2 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                            <span>🥩</span>
                            <span>Kompletní nutriční strategie & proteinové okno:</span>
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            {ai_nutrition}
                        </p>
                    </div>

                    <div class="bg-blue-950/30 p-4 rounded-2xl border border-blue-500/20 space-y-2">
                        <div class="flex items-center space-x-2 text-xs font-bold text-blue-300 uppercase tracking-wider">
                            <span>🧬</span>
                            <span>Longevity Deep Dive (Dlouhověkost, Healthspan & Biologie):</span>
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            {ai_longevity}
                        </p>
                    </div>

                    <div class="bg-emerald-950/20 p-4 rounded-2xl border border-emerald-500/20 space-y-2">
                        <div class="flex items-center space-x-2 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                            <span>🥗</span>
                            <span>Detailní doporučený jídelníček na dnešní den:</span>
                        </div>
                        <div class="text-xs text-slate-300 leading-relaxed space-y-1">
                            {ai_menu}
                        </div>
                    </div>
                </section>

                <div class="pt-2">
                    <button onclick="window.location.href='/?refresh=true';" class="w-full py-3 bg-[#1c1c1e] hover:bg-[#2c2c2e] border border-[#2c2c2e] text-[#0a84ff] font-bold text-xs uppercase tracking-wider rounded-xl transition">
                        Synchronizovat s Garmin Connect
                    </button>
                </div>

            </main>
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
