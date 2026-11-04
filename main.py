import os
import html
import time
import datetime
import logging
import requests

from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

# ---------------------------------------------------------
# ZÁKLADNÍ NASTAVENÍ
# ---------------------------------------------------------

app = FastAPI(title="Garmin Health Dashboard")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin-dashboard")

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "").strip()
GARMIN_BASE = "https://personal.connectapi.garmin.com"

user_stats_cache = {
    "user": "Drsňák",
    "weight": 84.5,
    "body_fat": 14.2,
}

live_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 900,
}

history_cache = {
    "hr_history": [],
    "hrv_history": [],
    "steps_dict": {},
    "steps_month": None,
    "monthly_avg_hr": None,
    "monthly_avg_hrv": None,
    "timestamp": 0,
    "ttl": 86400,
}

# ---------------------------------------------------------
# POMOCNÉ FUNKCE
# ---------------------------------------------------------

def safe_text(value):
    """Bezpečný text pro vložení do HTML."""
    if value is None:
        return "Nedostupné"
    return html.escape(str(value))


def fmt(value, suffix="", decimals=0):
    """Formátování čísel bez nahrazování chybějících dat."""
    if value is None:
        return "Nedostupné"
    try:
        number = float(value)
        if decimals:
            result = f"{number:.{decimals}f}"
        else:
            result = f"{int(round(number)):,}".replace(",", " ")
        return f"{result}{suffix}"
    except (TypeError, ValueError):
        return "Nedostupné"


def get_number(data, *keys):
    """Vrátí první nalezenou číselnou hodnotu v objektu."""
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def api_get(url, headers, params=None, timeout=10):
    """Bezpečné GET volání Garmin API."""
    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def api_log_error(log, label, error):
    message = f"{label}: {str(error)[:250]}"
    log.append(message)
    logger.warning(message)


def listify(value):
    return value if isinstance(value, list) else [value]


def average(values):
    valid = [float(v) for v in values if isinstance(v, (int, float))]
    if not valid:
        return None
    return round(sum(valid) / len(valid))


# ---------------------------------------------------------
# HISTORICKÁ DATA
# ---------------------------------------------------------

def fetch_day_hrv(base, headers, date_string):
    try:
        result = api_get(
            f"{base}/hrv-service/hrv/{date_string}",
            headers,
            timeout=8,
        )
        summary = result.get("hrvSummary", {}) if isinstance(result, dict) else {}
        value = get_number(summary, "lastNightAvg")
        if value is not None:
            return {"date": date_string, "hrv": int(value)}
    except Exception:
        return None
    return None


def fetch_day_steps(base, headers, date_string):
    try:
        result = api_get(
            f"{base}/usersummary-service/stats/steps/daily/"
            f"{date_string}/{date_string}",
            headers,
            timeout=8,
        )
        for item in listify(result):
            value = get_number(
                item,
                "totalSteps",
                "steps",
                "value",
                "stepCount",
            )
            if value is not None:
                return {"date": date_string, "steps": int(value)}
    except Exception:
        return None
    return None


def fetch_day_hr(base, headers, date_string):
    try:
        result = api_get(
            f"{base}/wellness-service/wellness/dailyHeartRate",
            headers,
            params={"date": date_string},
            timeout=8,
        )
        value = get_number(result, "restingHeartRate")
        if value is not None:
            return {"date": date_string, "hr": int(value)}
    except Exception:
        return None
    return None


def fetch_history(base, headers, today):
    """Stáhne až 30 dní historie."""
    dates = [
        (today - datetime.timedelta(days=i)).isoformat()
        for i in range(29, -1, -1)
    ]

    hr_values = []
    hrv_values = []
    steps_dict = {}

    with ThreadPoolExecutor(max_workers=9) as executor:
        futures = []

        for date_string in dates:
            futures.append(executor.submit(
                fetch_day_hrv, base, headers, date_string
            ))
            futures.append(executor.submit(
                fetch_day_steps, base, headers, date_string
            ))
            futures.append(executor.submit(
                fetch_day_hr, base, headers, date_string
            ))

        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:
                result = None

            if not result:
                continue

            if "hrv" in result:
                hrv_values.append(result)
            elif "hr" in result:
                hr_values.append(result)
            elif "steps" in result:
                steps_dict[result["date"]] = result["steps"]

    hr_values.sort(key=lambda item: item["date"])
    hrv_values.sort(key=lambda item: item["date"])

    history_cache["hr_history"] = hr_values
    history_cache["hrv_history"] = hrv_values
    history_cache["steps_dict"] = steps_dict
    history_cache["steps_month"] = sum(steps_dict.values())
    history_cache["monthly_avg_hr"] = average(
        [item["hr"] for item in hr_values]
    )
    history_cache["monthly_avg_hrv"] = average(
        [item["hrv"] for item in hrv_values]
    )
    history_cache["timestamp"] = time.time()


# ---------------------------------------------------------
# GARMIN DATA
# ---------------------------------------------------------

def empty_metrics():
    return {
        "resting_heart_rate": None,
        "hrv_ms": None,
        "monthly_avg_hrv": None,
        "hrv_history": [],
        "body_battery_max": None,
        "sleep_score": None,
        "sleep_hours": None,
        "stress_avg": None,
        "steps": None,
        "steps_month": None,
        "fitness_age": None,
        "achievable_fitness_age": None,
        "respiration_avg": None,
        "intensity_curr_week": None,
        "intensity_week": None,
        "intensity_month": None,
        "intensity_90d": None,
        "intensity_goal": 150,
        "monthly_avg_hr": None,
        "hr_history": [],
        "activities_list": [],
    }


def fetch_garmin_data_safe(force_refresh=False):
    now = time.time()

    if (
        not force_refresh
        and live_cache["data"] is not None
        and now - live_cache["timestamp"] < live_cache["ttl"]
    ):
        cached_data, cached_log = live_cache["data"]
        return cached_data, ["Data načtena z 15minutové mezipaměti."] + cached_log

    metrics = empty_metrics()
    log = []

    if not GARMIN_PERSONAL_API_KEY:
        log.append("Chybí proměnná GARMIN_PERSONAL_API_KEY v Render Environment.")
        return metrics, log

    try:
        token_url = (
            f"{GARMIN_BASE}/personalapitoken-service/"
            "personal-api/personal-api-key/token"
        )
        token_response = requests.post(
            token_url,
            headers={"Authorization": f"ApiKey {GARMIN_PERSONAL_API_KEY}"},
            timeout=15,
        )

        if token_response.status_code != 200:
            log.append(f"Chyba získání Garmin tokenu: HTTP {token_response.status_code}")
            return metrics, log

        try:
            token_json = token_response.json()
            access_token = (
                token_json.get("access_token")
                or token_json.get("token")
            )
        except ValueError:
            access_token = token_response.text.strip().replace('"', "")

        if not access_token:
            log.append("Garmin nevrátil přístupový token.")
            return metrics, log

        headers = {"Authorization": f"Bearer {access_token}"}
        today = datetime.date.today()
        today_string = today.isoformat()

        log.append("Garmin token získán úspěšně.")

        # Historie
        history_expired = (
            not history_cache["hr_history"]
            and not history_cache["hrv_history"]
        ) or now - history_cache["timestamp"] > history_cache["ttl"]

        if history_expired:
            log.append("Načítám 30denní historii.")
            try:
                fetch_history(GARMIN_BASE, headers, today)
            except Exception as error:
                api_log_error(log, "Historie", error)
        else:
            log.append("Používám uloženou historii.")

        metrics["hr_history"] = history_cache["hr_history"]
        metrics["hrv_history"] = history_cache["hrv_history"]
        metrics["steps_month"] = history_cache["steps_month"]
        metrics["monthly_avg_hr"] = history_cache["monthly_avg_hr"]
        metrics["monthly_avg_hrv"] = history_cache["monthly_avg_hrv"]

        if metrics["hr_history"]:
            metrics["resting_heart_rate"] = metrics["hr_history"][-1]["hr"]

        # Dnešní kroky
        try:
            result = api_get(
                f"{GARMIN_BASE}/usersummary-service/stats/steps/daily/"
                f"{today_string}/{today_string}",
                headers,
            )
            for item in listify(result):
                value = get_number(
                    item, "totalSteps", "steps", "value", "stepCount"
                )
                if value is not None:
                    metrics["steps"] = int(value)
                    break
        except Exception as error:
            api_log_error(log, "Dnešní kroky", error)

        if metrics["steps"] is None:
            metrics["steps"] = history_cache["steps_dict"].get(today_string)

        # HRV
        try:
            result = api_get(
                f"{GARMIN_BASE}/hrv-service/hrv/{today_string}",
                headers,
            )
            summary = result.get("hrvSummary", {}) if isinstance(result, dict) else {}
            value = get_number(summary, "lastNightAvg")
            if value is not None:
                metrics["hrv_ms"] = int(value)
        except Exception as error:
            api_log_error(log, "HRV", error)

        # Body Battery
        try:
            result = api_get(
                f"{GARMIN_BASE}/wellness-service/wellness/bodyBattery/reports/daily",
                headers,
                params={"startDate": today_string, "endDate": today_string},
            )
            for item in listify(result):
                if not isinstance(item, dict):
                    continue
                values = item.get("bodyBatteryValuesArray") or []
                numeric_values = [
                    entry[-1]
                    for entry in values
                    if isinstance(entry, list) and len(entry) > 1
                    and isinstance(entry[-1], (int, float))
                ]
                if numeric_values:
                    metrics["body_battery_max"] = max(numeric_values)
        except Exception as error:
            api_log_error(log, "Body Battery", error)

        # Spánek
        try:
            result = api_get(
                f"{GARMIN_BASE}/sleep-service/sleep/dailySleep",
                headers,
                params={"date": today_string},
            )
            for item in listify(result):
                if not isinstance(item, dict):
                    continue
                scores = item.get("sleepScores") or {}
                overall = scores.get("overall") or {}
                score = get_number(overall, "value")
                if score is not None:
                    metrics["sleep_score"] = int(score)

                seconds = get_number(
                    item, "sleepTimeSeconds", "durationInSeconds"
                )
                if seconds is not None and seconds > 0:
                    metrics["sleep_hours"] = round(seconds / 3600, 1)
        except Exception as error:
            api_log_error(log, "Spánek", error)

        # Stres
        try:
            result = api_get(
                f"{GARMIN_BASE}/usersummary-service/stats/stress/daily/"
                f"{today_string}/{today_string}",
                headers,
            )
            for item in listify(result):
                value = get_number(
                    item, "averageStressLevel", "stressScore", "value"
                )
                if value is not None:
                    metrics["stress_avg"] = int(value)
                    break
        except Exception as error:
            api_log_error(log, "Stres", error)

        # Intenzivní minuty
        try:
            start_90 = (today - datetime.timedelta(days=89)).isoformat()
            start_7 = (today - datetime.timedelta(days=6)).isoformat()
            start_month = (today - datetime.timedelta(days=29)).isoformat()
            start_week = (
                today - datetime.timedelta(days=today.weekday())
            ).isoformat()

            result = api_get(
                f"{GARMIN_BASE}/usersummary-service/v2/dailysummaries",
                headers,
                params={"startDate": start_90, "endDate": today_string},
            )

            rows = (
                result.get("data", [])
                if isinstance(result, dict)
                else result if isinstance(result, list) else []
            )

            totals = {"week": 0, "7d": 0, "month": 0, "90d": 0}

            for row in rows:
                if not isinstance(row, dict):
                    continue

                date_value = str(
                    row.get("calendarDate") or row.get("date") or ""
                )[:10]
                intensity = (
                    row.get("intensityMinutes")
                    or row.get("intensityMinuteSummary")
                )

                if not date_value or not isinstance(intensity, dict):
                    continue

                moderate = get_number(
                    intensity, "moderate", "moderateMinutes"
                ) or 0
                vigorous = get_number(
                    intensity, "vigorous", "vigorousMinutes"
                ) or 0

                # Garmin doporučuje započítávat intenzivní minuty dvojnásobně.
                day_total = int(moderate + vigorous * 2)

                if date_value >= start_90:
                    totals["90d"] += day_total
                if date_value >= start_month:
                    totals["month"] += day_total
                if date_value >= start_7:
                    totals["7d"] += day_total
                if date_value >= start_week:
                    totals["week"] += day_total

            metrics["intensity_curr_week"] = totals["week"]
            metrics["intensity_week"] = totals["7d"]
            metrics["intensity_month"] = totals["month"]
            metrics["intensity_90d"] = totals["90d"]

        except Exception as error:
            api_log_error(log, "Intenzivní minuty", error)

        # Fitness věk
        try:
            result = api_get(
                f"{GARMIN_BASE}/fitnessage-service/fitnessage/v2/{today_string}",
                headers,
            )
            value = get_number(result, "fitnessAge")
            achievable = get_number(result, "achievableFitnessAge")

            if value is not None:
                metrics["fitness_age"] = round(value)
            if achievable is not None:
                metrics["achievable_fitness_age"] = round(achievable)
        except Exception as error:
            api_log_error(log, "Fitness věk", error)

        # Aktivity
        try:
            result = api_get(
                f"{GARMIN_BASE}/activitylist-service/activities/search/activities",
                headers,
                params={"start": 0, "limit": 30},
            )

            if isinstance(result, list):
                parsed = []
                for activity in result:
                    if not isinstance(activity, dict):
                        continue

                    activity_type = activity.get("activityType") or {}
                    name = (
                        activity.get("activityName")
                        or activity_type.get("typeKey")
                        or "Aktivita"
                    )

                    duration = get_number(activity, "duration") or 0
                    distance = get_number(activity, "distance") or 0

                    parsed.append({
                        "name": str(name)[:100],
                        "date": str(activity.get("startTimeLocal") or "")[:10],
                        "duration": round(duration / 60, 1),
                        "distance": round(distance / 1000, 2),
                    })

                metrics["activities_list"] = parsed

        except Exception as error:
            api_log_error(log, "Aktivity", error)

        log.append("Načítání Garmin dat dokončeno.")
        live_cache["data"] = (metrics, log)
        live_cache["timestamp"] = now

        return metrics, log

    except Exception as error:
        api_log_error(log, "Hlavní Garmin připojení", error)
        return metrics, log


# ---------------------------------------------------------
# DOPORUČENÍ A JÍDELNÍČEK
# ---------------------------------------------------------

def generate_advice(metrics):
    weight = user_stats_cache["weight"]
    hrv = metrics["hrv_ms"]
    battery = metrics["body_battery_max"]
    stress = metrics["stress_avg"]
    sleep_score = metrics["sleep_score"]
    sleep_hours = metrics["sleep_hours"]
    rhr = metrics["resting_heart_rate"]
    monthly_hrv = metrics["monthly_avg_hrv"]

    available = [
        value for value in (hrv, battery, stress, sleep_score)
        if value is not None
    ]

    if not available:
        title = "Čekám na dostupná data"
        summary = (
            "Zatím nemám dostatek dnešních údajů z Garminu pro smysluplné "
            "zhodnocení. Zkontroluj připojení a synchronizaci hodinek."
        )
        training = (
            "Řiď se aktuálním pocitem, kvalitou spánku a obvyklým tréninkovým "
            "plánem. Pokud se necítíš dobře, zvol odpočinek."
        )
    else:
        low_signals = 0
        good_signals = 0

        if battery is not None:
            good_signals += battery >= 70
            low_signals += battery < 30

        if stress is not None:
            good_signals += stress < 35
            low_signals += stress >= 60

        if sleep_score is not None:
            good_signals += sleep_score >= 75
            low_signals += sleep_score < 55

        if hrv is not None and monthly_hrv is not None and monthly_hrv > 0:
            good_signals += hrv >= monthly_hrv
            low_signals += hrv < monthly_hrv * 0.85

        if low_signals >= 2:
            title = "Dnes dej přednost regeneraci"
            summary = (
                "Některé dostupné ukazatele jsou méně příznivé. "
                "Jednotlivá měření Garminu sama o sobě neurčují zdravotní stav. "
                "Všímej si také únavy, nálady a případných příznaků."
            )
            training = (
                "Zvaž lehkou procházku, mobilitu nebo volno. Vynech maximální "
                "intenzitu, pokud se cítíš unaveně. Při nemoci nebo bolesti "
                "netrénuj."
            )
        elif good_signals >= 2 and low_signals == 0:
            title = "Příznivé signály pro běžný trénink"
            summary = (
                "Dostupné metriky vypadají relativně příznivě. Porovnávej "
                "zejména HRV a klidový tep se svým dlouhodobým trendem, "
                "nikoliv pouze s univerzálními hodnotami."
            )
            training = (
                "Pokud se cítíš dobře, můžeš absolvovat plánovaný fullbody "
                "trénink. Zachovej správnou techniku, postupné zatěžování "
                "a přiměřenou rezervu opakování."
            )
        else:
            title = "Stabilní den – sleduj vlastní pocit"
            summary = (
                "Dostupná data neposkytují jednoznačný signál pro zvýšení "
                "ani snížení zátěže. Důležitý je trend za více dní a subjektivní "
                "pocit."
            )
            training = (
                "Vhodný může být běžný trénink se střední intenzitou. "
                "Při známkách únavy sniž objem nebo intenzitu."
            )

    protein_min = round(weight * 1.6, 1)
    protein_max = round(weight * 2.0, 1)

    nutrition = (
        f"Při hmotnosti {weight:.1f} kg může být pro aktivního silově "
        f"trénujícího člověka praktickým cílem přibližně "
        f"{protein_min}–{protein_max} g bílkovin denně. "
        "Rozlož je do několika jídel a doplň jídelníček o zeleninu, ovoce, "
        "celozrnné přílohy, kvalitní tuky a dostatek tekutin. "
        "Potřeby se liší podle zdravotního stavu a tréninkového cíle."
    )

    longevity = (
        "Pro dlouhodobé zdraví kombinuj pravidelný silový trénink, "
        "přiměřenou aerobní aktivitu, dostatek spánku, pestrou stravu "
        "a regeneraci. Fitness hodinky poskytují orientační ukazatele, "
        "nikoliv přímé měření hormonů, aktivity nervového systému "
        "nebo biologického věku."
    )

    day = datetime.date.today().weekday()

    menus = [
        ("Pondělí – vyvážený jídelníček",
         "Snídaně: ovesná kaše, jogurt a ovoce.<br>"
         "Svačina: tvaroh a ořechy.<br>"
         "Oběd: kuřecí maso, rýže a zelenina.<br>"
         "Večeře: losos, brambory a salát."),
        ("Úterý – proteinový jídelníček",
         "Snídaně: vejce, žitný chléb a zelenina.<br>"
         "Svačina: skyr a ovoce.<br>"
         "Oběd: krůtí maso, brambory a zelenina.<br>"
         "Večeře: čočkový salát s vejcem."),
        ("Středa – středomořský jídelníček",
         "Snídaně: řecký jogurt, vločky a ovoce.<br>"
         "Svačina: cottage a zelenina.<br>"
         "Oběd: ryba, kuskus a salát.<br>"
         "Večeře: kuřecí maso, zelenina a celozrnné pečivo."),
        ("Čtvrtek – silový den",
         "Snídaně: ovesná kaše s tvarohem.<br>"
         "Svačina: banán a jogurt.<br>"
         "Oběd: hovězí maso, rýže a brokolice.<br>"
         "Večeře: omeleta se zeleninou."),
        ("Pátek – pestrý jídelníček",
         "Snídaně: míchaná vejce a žitný chléb.<br>"
         "Svačina: skyr s ovocem.<br>"
         "Oběd: krůtí maso, batáty a zelenina.<br>"
         "Večeře: tuňákový salát s fazolemi."),
        ("Sobota – aktivní den",
         "Snídaně: proteinové palačinky s ovocem.<br>"
         "Svačina: ořechy a kefír.<br>"
         "Oběd: pečené kuře, brambory a salát.<br>"
         "Večeře: pstruh a pečená zelenina."),
        ("Neděle – odpočinkový den",
         "Snídaně: jogurt, vločky a borůvky.<br>"
         "Svačina: cottage a ovoce.<br>"
         "Oběd: hovězí vývar a maso se zeleninou.<br>"
         "Večeře: zeleninový salát s vejcem.")
    ]

    menu_title, menu_content = menus[day]

    return (
        title,
        summary,
        training,
        nutrition,
        longevity,
        f"<strong>{menu_title}</strong><br><br>{menu_content}",
    )


# ---------------------------------------------------------
# GRAFY
# ---------------------------------------------------------

def make_svg_chart(items, key, unit, stroke):
    if not items:
        return '<div class="muted">Pro graf zatím nejsou dostupná historická data.</div>'

    values = [item[key] for item in items if item.get(key) is not None]
    if not values:
        return '<div class="muted">Pro graf zatím nejsou dostupná historická data.</div>'

    minimum = min(values)
    maximum = max(values)
    low = minimum - 3
    high = maximum + 3

    if high <= low:
        high = low + 5

    width = 500
    height = 130
    usable_height = height - 35
    dx = width / max(len(values) - 1, 1)

    points = []
    labels = []

    for index, value in enumerate(values):
        x = index * dx
        y = height - 18 - ((value - low) / (high - low)) * usable_height
        points.append(f"{x:.1f},{y:.1f}")

        if index == 0 or index == len(values) - 1 or index % 5 == 0:
            labels.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{stroke}" />'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" '
        f'role="img" aria-label="Historický graf">'
        f'<line x1="0" y1="15" x2="{width}" y2="15" stroke="#38383a" '
        f'stroke-dasharray="4"/>'
        f'<text x="0" y="11" fill="#8e8e93" font-size="10">'
        f'Max: {maximum} {unit}</text>'
        f'<line x1="0" y1="{height-15}" x2="{width}" y2="{height-15}" '
        f'stroke="#38383a" stroke-dasharray="4"/>'
        f'<text x="0" y="{height-2}" fill="#8e8e93" font-size="10">'
        f'Min: {minimum} {unit}</text>'
        f'<polyline fill="none" stroke="{stroke}" stroke-width="2.5" '
        f'stroke-linecap="round" points="{" ".join(points)}"/>'
        f'{"".join(labels)}</svg>'
    )


# ---------------------------------------------------------
# HTML DASHBOARD
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(refresh: bool = False, ai_refresh: bool = False):
    metrics, debug_log = fetch_garmin_data_safe(force_refresh=refresh)

    title, summary, training, nutrition, longevity, menu = generate_advice(metrics)

    def card(label, value, suffix="", note=""):
        return f"""
        <div class="metric">
            <div class="muted">{safe_text(label)}</div>
            <div class="metric-value">{safe_text(fmt(value, suffix))}</div>
            <div class="note">{safe_text(note)}</div>
        </div>
        """

    debug_html = "".join(
        f'<div class="log-line">{safe_text(item)}</div>'
        for item in debug_log
    )

    activity_html = ""
    if metrics["activities_list"]:
        for activity in metrics["activities_list"]:
            activity_html += f"""
            <div class="activity">
                <div>
                    <strong>{safe_text(activity["name"])}</strong>
                    <div class="muted">
                        {safe_text(activity["date"])} ·
                        {safe_text(fmt(activity["duration"], " min", 1))}
                    </div>
                </div>
                <strong>{safe_text(fmt(activity["distance"], " km", 2))}</strong>
            </div>
            """
    else:
        activity_html = '<p class="muted">Žádné nedávné aktivity nebo data nejsou dostupná.</p>'

    hr_chart = make_svg_chart(
        metrics["hr_history"], "hr", "bpm", "#ff9500"
    )
    hrv_chart = make_svg_chart(
        metrics["hrv_history"], "hrv", "ms", "#30d158"
    )

    steps_month = fmt(metrics["steps_month"])
    weight = user_stats_cache["weight"]
    body_fat = user_stats_cache["body_fat"]

    intensity_values = {
        "curr": metrics["intensity_curr_week"],
        "week": metrics["intensity_week"],
        "month": metrics["intensity_month"],
        "90d": metrics["intensity_90d"],
    }

    intensity_html = ""
    for key, label in [
        ("curr", "Od pondělí"),
        ("week", "Posledních 7 dní"),
        ("month", "30 dní"),
        ("90d", "90 dní"),
    ]:
        intensity_html += f"""
        <div class="intensity-item">
            <span class="muted">{label}</span>
            <strong>{safe_text(fmt(intensity_values[key], " min"))}</strong>
        </div>
        """

    page = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="theme-color" content="#000000">
        <title>Garmin – Zdraví a výkon</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                background: #000;
                color: #fff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                             Roboto, Arial, sans-serif;
            }}
            .container {{
                max-width: 760px;
                margin: auto;
                padding: 22px 15px 55px;
            }}
            .muted {{ color: #999; font-size: 12px; }}
            .note {{ color: #888; font-size: 11px; margin-top: 5px; }}
            .panel {{
                background: #1c1c1e;
                border: 1px solid #333;
                border-radius: 18px;
                padding: 17px;
                margin: 14px 0;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 10px;
            }}
            .metric {{
                background: #1c1c1e;
                border: 1px solid #333;
                border-radius: 16px;
                padding: 14px;
                min-height: 112px;
            }}
            .metric-value {{
                font-size: 25px;
                font-weight: 800;
                margin-top: 12px;
                overflow-wrap: anywhere;
            }}
            h1 {{ font-size: 29px; font-weight: 850; margin: 4px 0; }}
            h2 {{ font-size: 19px; font-weight: 800; margin: 24px 0 12px; }}
            h3 {{ font-size: 14px; font-weight: 800; margin-bottom: 10px; }}
            .blue {{ color: #0a84ff; }}
            .green {{ color: #30d158; }}
            .orange {{ color: #ff9500; }}
            .chart {{ width: 100%; height: auto; overflow: visible; }}
            .activity {{
                display: flex; justify-content: space-between; gap: 12px;
                padding: 12px 0; border-bottom: 1px solid #333;
                font-size: 13px;
            }}
            .activity:last-child {{ border-bottom: 0; }}
            .intensity-item {{
                display: flex; justify-content: space-between;
                padding: 8px 0; border-bottom: 1px solid #333;
            }}
            .log-line {{
                color: #6ee7a0; font: 11px monospace;
                padding: 3px 0; overflow-wrap: anywhere;
            }}
            input {{
                width: 100%; background: #000; border: 1px solid #444;
                color: white; padding: 11px; border-radius: 10px;
                margin-top: 5px;
            }}
            button, .button {{
                display: block; width: 100%; border: 0; border-radius: 11px;
                padding: 13px; margin-top: 12px; background: #0a84ff;
                color: white; font-weight: 750; text-align: center;
                text-decoration: none; cursor: pointer;
            }}
            .button-secondary {{ background: #29292c; color: #65aaff; }}
            .advice {{ line-height: 1.65; font-size: 13px; color: #ddd; }}
            .small-title {{
                font-size: 11px; color: #999; text-transform: uppercase;
                letter-spacing: 1px;
            }}
            @media (max-width: 380px) {{
                .metric-value {{ font-size: 21px; }}
                .container {{ padding-left: 11px; padding-right: 11px; }}
            }}
        </style>
    </head>
    <body>
    <div class="container">

        <header class="panel">
            <div class="small-title">Garmin Connect · osobní přehled</div>
            <h1>Zdraví & výkon</h1>
            <div class="muted">Profil: {safe_text(user_stats_cache["user"])}</div>
            <div class="muted">Aktualizováno: {datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}</div>
        </header>

        <details class="panel">
            <summary style="cursor:pointer;font-weight:700">
                Stav Garmin API a diagnostika
            </summary>
            <div style="margin-top:12px">{debug_html}</div>
            <a class="button button-secondary" href="/?refresh=true">
                Obnovit data z Garminu
            </a>
        </details>

        <h2>Klíčové metriky</h2>
        <div class="grid">
            {card("Klidový tep", metrics["resting_heart_rate"], " bpm")}
            {card("HRV – noční průměr", metrics["hrv_ms"], " ms")}
            {card("Délka spánku", metrics["sleep_hours"], " hod", "Dnešní dostupný záznam")}
            {card("Skóre spánku", metrics["sleep_score"], " / 100")}
            {card("Body Battery", metrics["body_battery_max"], " / 100")}
            {card("Stres", metrics["stress_avg"], " / 100")}
            {card("Dnešní kroky", metrics["steps"])}
            {card("Kroky za 30 dní", metrics["steps_month"])}
        </div>

        <h2>Kondice a aktivita</h2>
        <div class="panel">
            <h3>Intenzivní minuty</h3>
            {intensity_html}
            <div class="muted" style="margin-top:10px">
                Orientační týdenní doporučení WHO pro dospělé je 150–300 minut
                středně intenzivní nebo 75–150 minut intenzivní aerobní aktivity.
            </div>
        </div>

        <div class="panel">
            <div class="grid">
                <div>
                    <div class="muted">Fitness věk Garmin</div>
                    <div class="metric-value blue">{safe_text(fmt(metrics["fitness_age"], " let"))}</div>
                </div>
                <div>
                    <div class="muted">Dosažitelný fitness věk</div>
                    <div class="metric-value green">{safe_text(fmt(metrics["achievable_fitness_age"], " let"))}</div>
                </div>
            </div>
        </div>

        <h2>Trendy a historie</h2>
        <div class="panel">
            <h3>30denní klidový tep</h3>
            <div class="metric-value orange">{safe_text(fmt(metrics["monthly_avg_hr"], " bpm"))}</div>
            <div class="muted">Průměr z dostupných denních záznamů</div>
            {hr_chart}
        </div>

        <div class="panel">
            <h3>30denní HRV</h3>
            <div class="metric-value green">{safe_text(fmt(metrics["monthly_avg_hrv"], " ms"))}</div>
            <div class="muted">Průměr z dostupných nočních záznamů</div>
            {hrv_chart}
        </div>

        <div class="panel">
            <h3>Poslední aktivity</h3>
            {activity_html}
        </div>

        <h2>Tělesná hmotnost a složení</h2>
        <div class="panel">
            <form action="/update-stats" method="post">
                <label class="muted" for="weight">Hmotnost (kg)</label>
                <input id="weight" name="weight" type="number"
                       min="30" max="300" step="0.1"
                       value="{weight:.1f}" required>

                <label class="muted" for="body_fat"
                       style="display:block;margin-top:12px">
                    Tělesný tuk (%)
                </label>
                <input id="body_fat" name="body_fat" type="number"
                       min="2" max="70" step="0.1"
                       value="{body_fat:.1f}" required>

                <button type="submit">Uložit hodnoty</button>
            </form>
        </div>

        <h2>Trénink a longevity průvodce</h2>
        <div class="panel">
            <div class="small-title">Denní vyhodnocení</div>
            <h3 class="blue" style="font-size:18px;margin-top:8px">
                {safe_text(title)}
            </h3>
            <p class="advice">{safe_text(summary)}</p>

            <h3 class="orange" style="margin-top:20px">Tréninkové doporučení</h3>
            <p class="advice">{safe_text(training)}</p>

            <h3 class="green" style="margin-top:20px">Výživa</h3>
            <p class="advice">{safe_text(nutrition)}</p>

            <h3 class="blue" style="margin-top:20px">Longevity</h3>
            <p class="advice">{safe_text(longevity)}</p>
        </div>

        <div class="panel">
            <div class="small-title">Jídelníček na dnešní den</div>
            <div class="advice" style="margin-top:12px">{menu}</div>
        </div>

        <a class="button" href="/?refresh=true">
            Synchronizovat s Garmin Connect
        </a>

        <div class="muted" style="text-align:center;margin-top:18px">
            Data z hodinek jsou orientační a nenahrazují lékařské vyšetření.
        </div>

    </div>
    </body>
    </html>
    """

    return HTMLResponse(content=page)


# ---------------------------------------------------------
# ULOŽENÍ HMOTNOSTI A TĚLESNÉHO TUKU
# ---------------------------------------------------------

@app.post("/update-stats")
def update_stats(
    weight: float = Form(...),
    body_fat: float = Form(...),
):
    if not 30 <= weight <= 300:
        return HTMLResponse(
            "Hmotnost musí být mezi 30 a 300 kg.",
            status_code=400,
        )

    if not 2 <= body_fat <= 70:
        return HTMLResponse(
            "Tělesný tuk musí být mezi 2 a 70 %.",
            status_code=400,
        )

    user_stats_cache["weight"] = round(weight, 1)
    user_stats_cache["body_fat"] = round(body_fat, 1)

    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------
# HEALTH CHECK – KONTROLA, ZDA APLIKACE BĚŽÍ
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "garmin_api_key_configured": bool(GARMIN_PERSONAL_API_KEY),
    }