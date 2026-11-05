import os
import html
import time
import datetime
import logging
import threading
import email.utils
import requests

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Garmin Health Dashboard")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin-dashboard")

GARMIN_PERSONAL_API_KEY = os.environ.get(
    "GARMIN_PERSONAL_API_KEY", ""
).strip()

GARMIN_BASE = "https://personal.connectapi.garmin.com"

LIVE_TTL = 300
HISTORY_TTL = 6 * 60 * 60
REQUEST_TIMEOUT = 20

MIN_REQUEST_INTERVAL = 1.5
MAX_RETRIES_429 = 3
HRV_HISTORY_DAYS = 14

_request_lock = threading.Lock()
_last_request_at = 0.0
_refresh_lock = threading.Lock()

user_stats_cache = {
    "user": "Drsňák",
    "weight": 84.5,
    "body_fat": 14.2,
}

live_cache = {
    "data": None,
    "timestamp": 0,
}

history_cache = {
    "data": None,
    "timestamp": 0,
    "summaries_90d": [],
}


# ---------------------------------------------------------
# POMOCNÉ FUNKCE
# ---------------------------------------------------------

def safe_text(value):
    return html.escape(
        str(value)
    ) if value is not None else "Nedostupné"


def fmt(value, suffix="", decimals=0):
    if value is None:
        return "Nedostupné"

    try:
        number = float(value)

        result = (
            f"{number:.{decimals}f}"
            if decimals
            else f"{int(round(number)):,}".replace(",", " ")
        )

        return f"{result}{suffix}"

    except (TypeError, ValueError):
        return "Nedostupné"


def get_number(data, *keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = data.get(key)

        if value is None or isinstance(value, bool):
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            pass

    return None


def find_nested_number(data, keys, depth=0):
    """
    Hledá hodnotu i v zanořených objektech a seznamech.
    Garmin endpointy mohou vracet různé struktury odpovědí.
    """

    if depth > 6:
        return None

    if isinstance(data, dict):

        value = get_number(data, *keys)

        if value is not None:
            return value

        for child in data.values():

            if isinstance(child, (dict, list)):
                value = find_nested_number(
                    child,
                    keys,
                    depth + 1,
                )

                if value is not None:
                    return value

    elif isinstance(data, list):

        for child in data:
            value = find_nested_number(
                child,
                keys,
                depth + 1,
            )

            if value is not None:
                return value

    return None


def average(values, decimals=1):
    valid = []

    for value in values:
        try:
            if value is not None:
                valid.append(float(value))
        except (TypeError, ValueError):
            pass

    return (
        round(sum(valid) / len(valid), decimals)
        if valid else None
    )


def extract_rows(result):
    if isinstance(result, list):
        return result

    if isinstance(result, dict):
        for key in (
            "data",
            "dailySummaries",
            "summaries",
            "items",
        ):
            if isinstance(result.get(key), list):
                return result[key]

        return [result]

    return []


def date_range(days, today=None):
    today = today or datetime.date.today()

    return [
        (
            today - datetime.timedelta(days=i)
        ).isoformat()
        for i in range(days - 1, -1, -1)
    ]


def log_error(log, label, error):
    message = f"{label}: {str(error)[:220]}"

    log.append(message)
    logger.warning(message)


# ---------------------------------------------------------
# GARMIN API OMEZENÍ POŽADAVKŮ
# ---------------------------------------------------------

def wait_for_request_slot():
    global _last_request_at

    with _request_lock:
        now = time.monotonic()

        wait = MIN_REQUEST_INTERVAL - (
            now - _last_request_at
        )

        if wait > 0:
            time.sleep(wait)

        _last_request_at = time.monotonic()


def retry_delay(response, attempt):
    retry_after = response.headers.get("Retry-After")

    if retry_after:
        try:
            return min(max(float(retry_after), 2), 90)

        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(
                    retry_after
                )

                seconds = (
                    parsed -
                    datetime.datetime.now(parsed.tzinfo)
                ).total_seconds()

                return min(max(seconds, 2), 90)

            except Exception:
                pass

    return min(5 * (2 ** attempt), 60)


def api_get(url, headers, params=None, timeout=REQUEST_TIMEOUT):
    for attempt in range(MAX_RETRIES_429 + 1):

        wait_for_request_slot()

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=timeout,
        )

        if response.status_code == 429:

            if attempt >= MAX_RETRIES_429:
                response.raise_for_status()

            delay = retry_delay(response, attempt)

            logger.warning(
                "Garmin 429. Opakuji za %.1f sekund.",
                delay,
            )

            time.sleep(delay)
            continue

        response.raise_for_status()

        if not response.content:
            return {}

        return response.json()

    return {}


# ---------------------------------------------------------
# BODY BATTERY
# ---------------------------------------------------------

def parse_body_battery_values(item):
    raw = (
        item.get("bodyBatteryValuesArray")
        or item.get("bodyBatteryValues")
        or []
    )

    values = []

    for entry in raw:

        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            try:
                value = float(entry[-1])

                if 0 <= value <= 100:
                    values.append(value)

            except (TypeError, ValueError):
                pass

        elif isinstance(entry, dict):

            value = get_number(
                entry,
                "bodyBatteryLevel",
                "value",
                "level",
            )

            if value is not None and 0 <= value <= 100:
                values.append(value)

    return values


def find_latest_body_battery(result):
    candidates = []

    for item in extract_rows(result):

        if not isinstance(item, dict):
            continue

        entries = (
            item.get("bodyBatteryValuesArray")
            or item.get("bodyBatteryValues")
            or []
        )

        for entry in entries:

            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    candidates.append(
                        (float(entry[0]), float(entry[-1]))
                    )
                except (TypeError, ValueError):
                    pass

            elif isinstance(entry, dict):

                timestamp = get_number(
                    entry,
                    "timestamp",
                    "startTimestamp",
                )

                value = get_number(
                    entry,
                    "bodyBatteryLevel",
                    "value",
                    "level",
                )

                if timestamp is not None and value is not None:
                    candidates.append((timestamp, value))

    if candidates:
        return max(
            candidates,
            key=lambda x: x[0],
        )[1]

    return None


# ---------------------------------------------------------
# DENNÍ SOUHRNY
# ---------------------------------------------------------

def map_daily_summary(row):
    result = {}

    fields = (
        (
            ("totalSteps", "steps", "stepCount"),
            "steps",
        ),
        (
            ("restingHeartRate", "restingHr"),
            "hr",
        ),
        (
            (
                "averageStressLevel",
                "avgStressLevel",
                "averageStress",
                "stressScore",
            ),
            "stress",
        ),
        (
            (
                "averageRespirationRate",
                "avgWakingRespirationValue",
                "averageRespirationValue",
            ),
            "respiration",
        ),
        (
            ("activeKilocalories", "activeCalories"),
            "active_calories",
        ),
        (
            ("totalKilocalories", "totalCalories"),
            "total_calories",
        ),
    )

    for keys, target in fields:

        value = get_number(row, *keys)

        if value is not None:
            result[target] = round(value, 1)

    return result


def get_daily_intensity(row):
    intensity = (
        row.get("intensityMinutes")
        or row.get("intensityMinuteSummary")
        or {}
    )

    moderate = get_number(
        intensity,
        "moderate",
        "moderateMinutes",
    ) or 0

    vigorous = get_number(
        intensity,
        "vigorous",
        "vigorousMinutes",
    ) or 0

    return moderate + vigorous * 2


# ---------------------------------------------------------
# SAMOSTATNÉ NAČÍTÁNÍ KLIDOVÉHO TEPU
# ---------------------------------------------------------

def fetch_today_heart_rate_and_stress(
    headers,
    today_s,
    metrics,
    log,
):
    """
    Doplní pouze chybějící klidový tep.

    Denní stres se načítá výhradně z denních souhrnů
    přes map_daily_summary().

    Samostatný endpoint dailyStress se nepoužívá,
    protože může vracet HTTP 404.
    """

    if metrics.get("resting_heart_rate") is None:

        try:
            result = api_get(
                f"{GARMIN_BASE}/wellness-service/wellness/dailyHeartRate",
                headers,
                params={"date": today_s},
            )

            value = find_nested_number(
                result,
                (
                    "restingHeartRate",
                    "restingHr",
                    "restingHeartRateValue",
                ),
            )

            if value is not None:
                metrics["resting_heart_rate"] = round(value)

                log.append(
                    "Klidový tep doplněn ze samostatného Garmin endpointu: "
                    f"{round(value)} bpm."
                )

            else:
                log.append(
                    "Klidový tep: samostatný endpoint odpověděl, "
                    "ale hodnota nebyla nalezena."
                )

                logger.info(
                    "Garmin dailyHeartRate odpověď: %s",
                    str(result)[:500],
                )

        except Exception as error:
            log_error(
                log,
                "Samostatné načtení klidového tepu",
                error,
            )


# ---------------------------------------------------------
# HISTORIE
# ---------------------------------------------------------

def fetch_history(headers, today, log):

    start_90 = today - datetime.timedelta(days=89)

    try:

        data = api_get(
            f"{GARMIN_BASE}/usersummary-service/v2/dailysummaries",
            headers,
            params={
                "startDate": start_90.isoformat(),
                "endDate": today.isoformat(),
            },
        )

        summaries = extract_rows(data)

    except Exception as error:

        log_error(
            log,
            "Historické denní souhrny",
            error,
        )

        summaries = []

    by_date = {}

    for item in summaries:

        if not isinstance(item, dict):
            continue

        date_s = str(
            item.get("calendarDate")
            or item.get("date")
            or ""
        )[:10]

        try:
            datetime.date.fromisoformat(date_s)
        except ValueError:
            continue

        by_date[date_s] = item

    rows = []

    for day in date_range(30, today):

        row = {"date": day}

        source = by_date.get(day)

        if source:
            row.update(map_daily_summary(source))

        rows.append(row)

    # HRV pouze za posledních 14 dní.
    hrv_start = today - datetime.timedelta(
        days=HRV_HISTORY_DAYS - 1
    )

    rate_limited = False

    for row in rows:

        if rate_limited:
            break

        day = datetime.date.fromisoformat(row["date"])

        if day < hrv_start:
            continue

        try:

            data = api_get(
                f"{GARMIN_BASE}/hrv-service/hrv/{row['date']}",
                headers,
            )

            summary = (
                data.get("hrvSummary", {})
                if isinstance(data, dict)
                else {}
            )

            value = get_number(
                summary,
                "lastNightAvg",
            )

            if value is not None:
                row["hrv"] = round(value)

        except requests.HTTPError as error:

            if getattr(
                error.response,
                "status_code",
                None,
            ) == 429:

                rate_limited = True

                log_error(
                    log,
                    "HRV historie – další dny přeskočeny kvůli limitu",
                    error,
                )

            else:
                logger.warning(
                    "HRV %s: %s",
                    row["date"],
                    error,
                )

        except Exception as error:

            logger.warning(
                "HRV %s: %s",
                row["date"],
                error,
            )

    rows.sort(key=lambda x: x["date"])

    history_cache["data"] = rows
    history_cache["timestamp"] = time.time()
    history_cache["summaries_90d"] = summaries

    return rows


# ---------------------------------------------------------
# GARMIN DATA
# ---------------------------------------------------------

def empty_metrics():
    return {
        "resting_heart_rate": None,
        "hrv_ms": None,
        "body_battery": None,
        "body_battery_min": None,
        "body_battery_max": None,
        "sleep_score": None,
        "sleep_hours": None,
        "stress_avg": None,
        "steps": None,
        "steps_month": None,
        "fitness_age": None,
        "achievable_fitness_age": None,
        "respiration_avg": None,
        "active_calories": None,
        "total_calories": None,
        "intensity_curr_week": None,
        "intensity_week": None,
        "intensity_month": None,
        "intensity_90d": None,
        "monthly_avg_hr": None,
        "monthly_avg_hrv": None,
        "history": [],
        "activities_list": [],
        "last_sync": None,
        "body_battery_time": None,
    }


def get_garmin_token():

    url = (
        f"{GARMIN_BASE}/personalapitoken-service/"
        "personal-api/personal-api-key/token"
    )

    for attempt in range(MAX_RETRIES_429 + 1):

        wait_for_request_slot()

        response = requests.post(
            url,
            headers={
                "Authorization": (
                    f"ApiKey {GARMIN_PERSONAL_API_KEY}"
                )
            },
            timeout=20,
        )

        if response.status_code == 429:

            if attempt >= MAX_RETRIES_429:
                response.raise_for_status()

            delay = retry_delay(response, attempt)

            logger.warning(
                "Garmin token 429. Opakuji za %.1f sekund.",
                delay,
            )

            time.sleep(delay)
            continue

        response.raise_for_status()

        try:

            data = response.json()

            token = (
                data.get("access_token")
                or data.get("token")
            )

        except ValueError:

            token = response.text.strip().replace('"', "")

        if not token:
            raise RuntimeError(
                "Garmin nevrátil přístupový token."
            )

        return token

    raise RuntimeError(
        "Nepodařilo se získat Garmin token."
    )


def fetch_garmin_data_safe(force_refresh=False):

    now = time.time()

    if (
        not force_refresh
        and live_cache["data"] is not None
        and now - live_cache["timestamp"] < LIVE_TTL
    ):

        data, old_log = live_cache["data"]

        return data, [
            f"Data z cache ({int(now - live_cache['timestamp'])} s)."
        ] + old_log

    with _refresh_lock:

        now = time.time()

        if (
            not force_refresh
            and live_cache["data"] is not None
            and now - live_cache["timestamp"] < LIVE_TTL
        ):

            data, old_log = live_cache["data"]

            return data, [
                f"Data z cache ({int(now - live_cache['timestamp'])} s)."
            ] + old_log

        return _fetch_garmin_data(force_refresh)


def _fetch_garmin_data(force_refresh=False):

    now = time.time()

    metrics = empty_metrics()
    log = []

    if not GARMIN_PERSONAL_API_KEY:

        return metrics, [
            "Chybí GARMIN_PERSONAL_API_KEY v prostředí aplikace."
        ]

    try:

        token = get_garmin_token()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        today = datetime.date.today()
        today_s = today.isoformat()

        metrics["last_sync"] = (
            datetime.datetime.now()
            .astimezone()
            .isoformat(timespec="seconds")
        )

        log.append("Garmin token získán.")

        if (
            force_refresh
            or history_cache["data"] is None
            or now - history_cache["timestamp"] > HISTORY_TTL
        ):

            log.append(
                "Obnovuji historii postupně s omezením požadavků."
            )

            history = fetch_history(
                headers,
                today,
                log,
            )

        else:

            history = history_cache["data"]

            log.append("Historie načtena z cache.")

        metrics["history"] = history

        metrics["monthly_avg_hr"] = average(
            [r.get("hr") for r in history]
        )

        metrics["monthly_avg_hrv"] = average(
            [r.get("hrv") for r in history]
        )

        metrics["steps_month"] = sum(
            r.get("steps", 0) or 0
            for r in history
        )

        today_row = next(
            (
                r for r in reversed(history)
                if r["date"] == today_s
            ),
            {},
        )

        metrics["resting_heart_rate"] = today_row.get("hr")
        metrics["stress_avg"] = today_row.get("stress")
        metrics["respiration_avg"] = today_row.get("respiration")
        metrics["steps"] = today_row.get("steps")
        metrics["hrv_ms"] = today_row.get("hrv")

        metrics["active_calories"] = today_row.get(
            "active_calories"
        )

        metrics["total_calories"] = today_row.get(
            "total_calories"
        )

        # Samostatné načtení pouze chybějícího klidového tepu.
        # Denní stres pochází z denních souhrnů.
        fetch_today_heart_rate_and_stress(
            headers,
            today_s,
            metrics,
            log,
        )

        # Kroky – dodatečný dotaz jen pokud chybí v souhrnu.
        if metrics["steps"] is None:

            try:

                result = api_get(
                    f"{GARMIN_BASE}/usersummary-service/stats/"
                    f"steps/daily/{today_s}/{today_s}",
                    headers,
                )

                value = find_nested_number(
                    result,
                    (
                        "totalSteps",
                        "steps",
                        "value",
                        "stepCount",
                    ),
                )

                if value is not None:
                    metrics["steps"] = round(value)

            except Exception as error:

                log_error(
                    log,
                    "Kroky",
                    error,
                )

        # HRV – dodatečný dotaz pouze pokud chybí v historii.
        if metrics["hrv_ms"] is None:

            try:

                result = api_get(
                    f"{GARMIN_BASE}/hrv-service/hrv/{today_s}",
                    headers,
                )

                summary = (
                    result.get("hrvSummary", {})
                    if isinstance(result, dict)
                    else {}
                )

                value = get_number(
                    summary,
                    "lastNightAvg",
                )

                if value is not None:
                    metrics["hrv_ms"] = round(value)

            except Exception as error:

                log_error(
                    log,
                    "HRV dnes",
                    error,
                )

        # Body Battery.
        try:

            result = api_get(
                f"{GARMIN_BASE}/wellness-service/wellness/"
                "bodyBattery/reports/daily",
                headers,
                params={
                    "startDate": today_s,
                    "endDate": today_s,
                },
            )

            metrics["body_battery"] = (
                find_latest_body_battery(result)
            )

            all_values = []

            for row in extract_rows(result):

                if isinstance(row, dict):

                    all_values.extend(
                        parse_body_battery_values(row)
                    )

            if all_values:

                metrics["body_battery_min"] = min(all_values)
                metrics["body_battery_max"] = max(all_values)

            if metrics["body_battery"] is not None:

                metrics["body_battery_time"] = (
                    "Poslední dostupný vzorek dne"
                )

        except Exception as error:

            log_error(
                log,
                "Body Battery",
                error,
            )

        # Spánek.
        try:

            result = api_get(
                f"{GARMIN_BASE}/sleep-service/sleep/dailySleep",
                headers,
                params={
                    "date": today_s
                },
            )

            for row in extract_rows(result):

                if not isinstance(row, dict):
                    continue

                overall = (
                    row.get("sleepScores") or {}
                ).get("overall") or {}

                score = get_number(
                    overall,
                    "value",
                )

                if score is not None:
                    metrics["sleep_score"] = round(score)

                seconds = get_number(
                    row,
                    "sleepTimeSeconds",
                    "durationInSeconds",
                )

                if seconds and seconds > 0:

                    metrics["sleep_hours"] = round(
                        seconds / 3600,
                        1,
                    )

                if metrics["respiration_avg"] is None:

                    metrics["respiration_avg"] = get_number(
                        row,
                        "averageRespirationValue",
                        "avgRespirationValue",
                    )

        except Exception as error:

            log_error(
                log,
                "Spánek",
                error,
            )

        # Intenzivní minuty.
        summaries = (
            history_cache.get("summaries_90d") or []
        )

        start_90 = today - datetime.timedelta(days=89)
        start_30 = today - datetime.timedelta(days=29)
        start_7 = today - datetime.timedelta(days=6)
        start_week = today - datetime.timedelta(
            days=today.weekday()
        )

        totals = {
            "week": 0,
            "7d": 0,
            "month": 0,
            "90d": 0,
        }

        for row in summaries:

            if not isinstance(row, dict):
                continue

            date_s = str(
                row.get("calendarDate")
                or row.get("date")
                or ""
            )[:10]

            try:
                day = datetime.date.fromisoformat(date_s)
            except ValueError:
                continue

            total = get_daily_intensity(row)

            if day >= start_90:
                totals["90d"] += total

            if day >= start_30:
                totals["month"] += total

            if day >= start_7:
                totals["7d"] += total

            if day >= start_week:
                totals["week"] += total

        metrics["intensity_curr_week"] = round(
            totals["week"]
        )

        metrics["intensity_week"] = round(
            totals["7d"]
        )

        metrics["intensity_month"] = round(
            totals["month"]
        )

        metrics["intensity_90d"] = round(
            totals["90d"]
        )

        # Fitness věk.
        try:

            result = api_get(
                f"{GARMIN_BASE}/fitnessage-service/fitnessage/v2/"
                f"{today_s}",
                headers,
            )

            metrics["fitness_age"] = get_number(
                result,
                "fitnessAge",
            )

            metrics["achievable_fitness_age"] = get_number(
                result,
                "achievableFitnessAge",
            )

        except Exception as error:

            log_error(
                log,
                "Fitness věk",
                error,
            )

        # Aktivity.
        try:

            result = api_get(
                f"{GARMIN_BASE}/activitylist-service/"
                "activities/search/activities",
                headers,
                params={
                    "start": 0,
                    "limit": 30,
                },
            )

            if isinstance(result, list):

                for activity in result:

                    if not isinstance(activity, dict):
                        continue

                    kind = (
                        activity.get("activityType") or {}
                    )

                    duration = get_number(
                        activity,
                        "duration",
                    ) or 0

                    distance = get_number(
                        activity,
                        "distance",
                    ) or 0

                    metrics["activities_list"].append({
                        "name": str(
                            activity.get("activityName")
                            or kind.get("typeKey")
                            or "Aktivita"
                        )[:100],

                        "date": str(
                            activity.get("startTimeLocal") or ""
                        )[:16],

                        "duration": round(
                            duration / 60,
                            1,
                        ),

                        "distance": round(
                            distance / 1000,
                            2,
                        ),

                        "calories": get_number(
                            activity,
                            "calories",
                        ),

                        "avg_hr": get_number(
                            activity,
                            "averageHR",
                            "avgHR",
                        ),
                    })

        except Exception as error:

            log_error(
                log,
                "Aktivity",
                error,
            )

        log.append(
            "Načítání Garmin dat dokončeno."
        )

        live_cache["data"] = (
            metrics,
            log,
        )

        live_cache["timestamp"] = time.time()

        return metrics, log

    except Exception as error:

        log_error(
            log,
            "Hlavní Garmin připojení",
            error,
        )

        return metrics, log


# ---------------------------------------------------------
# VYHODNOCENÍ
# ---------------------------------------------------------

def generate_advice(metrics):

    hrv = metrics["hrv_ms"]
    battery = metrics["body_battery"]
    stress = metrics["stress_avg"]
    sleep_score = metrics["sleep_score"]
    monthly_hrv = metrics["monthly_avg_hrv"]

    low = 0
    good = 0

    if battery is not None:
        good += battery >= 70
        low += battery < 30

    if stress is not None:
        good += stress < 35
        low += stress >= 60

    if sleep_score is not None:
        good += sleep_score >= 75
        low += sleep_score < 55

    if hrv is not None and monthly_hrv:
        good += hrv >= monthly_hrv
        low += hrv < monthly_hrv * 0.85

    if good == 0 and low == 0:

        title = "Čekám na dostatek dat"

        summary = (
            "Pro smysluplné vyhodnocení zatím chybí některé "
            "klíčové metriky."
        )

        training = (
            "Rozhoduj se podle subjektivního pocitu, spánku "
            "a svého plánu."
        )

    elif low >= 2:

        title = "Dnes dej přednost regeneraci"

        summary = (
            "Více dostupných ukazatelů je mimo příznivou oblast. "
            "Sleduj také vlastní pocit a vývoj v dalších dnech."
        )

        training = (
            "Zvaž volno, procházku nebo lehkou mobilitu. "
            "Při nemoci či bolesti netrénuj."
        )

    elif good >= 2 and low == 0:

        title = "Příznivé signály pro běžný trénink"

        summary = (
            "Dostupné metriky vypadají příznivě. Nejde však "
            "o zdravotní diagnózu ani záruku připravenosti."
        )

        training = (
            "Pokud se cítíš dobře, můžeš absolvovat plánovaný "
            "trénink s obvyklou rezervou."
        )

    else:

        title = "Stabilní den – sleduj vlastní pocit"

        summary = (
            "Data nedávají jednoznačný signál. Důležitější je "
            "trend za více dní než jediná hodnota."
        )

        training = (
            "Vhodný může být běžný trénink se střední intenzitou; "
            "při únavě sniž objem."
        )

    weight = user_stats_cache["weight"]

    pmin = round(weight * 1.6)
    pmax = round(weight * 2.0)

    nutrition = (
        f"Při hmotnosti {weight:.1f} kg může být orientačním "
        f"cílem pro aktivního člověka {pmin}–{pmax} g "
        "bílkovin denně. Potřeby se liší podle cíle "
        "a zdravotního stavu; doplň pestrou stravu "
        "a dostatek tekutin."
    )

    longevity = (
        "Dlouhodobě kombinuj silový a aerobní pohyb, "
        "pravidelný spánek, pestrou stravu a přiměřenou "
        "regeneraci. Hodinky poskytují orientační ukazatele, "
        "nikoliv lékařské měření."
    )

    return (
        title,
        summary,
        training,
        nutrition,
        longevity,
    )


# ---------------------------------------------------------
# GRAFY
# ---------------------------------------------------------

def make_svg_chart(
    items,
    key,
    unit,
    stroke,
    title,
):

    valid = [
        (x.get("date", ""), x.get(key))
        for x in items
        if x.get(key) is not None
    ]

    if not valid:

        return (
            '<div class="muted">'
            'Pro graf zatím nejsou dostupná historická data.'
            '</div>'
        )

    values = [
        float(v)
        for _, v in valid
    ]

    minimum = min(values)
    maximum = max(values)

    span = maximum - minimum
    padding = max(span * 0.18, 2)

    low = minimum - padding
    high = maximum + padding

    width = 620
    height = 205

    left = 38
    right = 12
    top = 28
    bottom = 36

    plot_w = width - left - right
    plot_h = height - top - bottom

    coords = []

    for i, (day, value) in enumerate(valid):

        x = (
            left
            + plot_w * i / max(len(valid) - 1, 1)
        )

        y = (
            top
            + (high - float(value))
            / (high - low)
            * plot_h
        )

        coords.append(
            (x, y, day, float(value))
        )

    polyline = " ".join(
        f"{x:.1f},{y:.1f}"
        for x, y, _, _ in coords
    )

    circles = []

    for x, y, day, value in coords:

        label = f"{day}: {value:g} {unit}"

        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" '
            f'r="3.6" fill="{stroke}">'
            f'<title>{html.escape(label)}</title>'
            f'</circle>'
        )

    important = {
        0,
        len(coords) - 1,
        values.index(minimum),
        values.index(maximum),
    }

    value_labels = []

    for idx in sorted(important):

        x, y, day, value = coords[idx]

        anchor = (
            "start"
            if x < width * 0.75
            else "end"
        )

        dx = (
            5
            if anchor == "start"
            else -5
        )

        value_labels.append(
            f'<text x="{x+dx:.1f}" '
            f'y="{max(12,y-9):.1f}" '
            f'text-anchor="{anchor}" '
            f'fill="#fff" font-size="10" '
            f'font-weight="700">{value:g}</text>'
        )

    date_labels = []

    for idx in sorted({
        0,
        len(coords) // 2,
        len(coords) - 1,
    }):

        x, _, day, _ = coords[idx]

        date_labels.append(
            f'<text x="{x:.1f}" y="{height-10}" '
            f'text-anchor="middle" fill="#999" '
            f'font-size="10">{html.escape(day[5:])}</text>'
        )

    mid = (minimum + maximum) / 2

    return f"""
    <div class="chart-wrap">
      <div class="chart-legend">
        <span>{html.escape(title)}</span>
        <span>Min {minimum:g} · Max {maximum:g} {html.escape(unit)}</span>
      </div>
      <svg viewBox="0 0 {width} {height}" class="chart"
           role="img"
           aria-label="{html.escape(title)} za posledních 30 dní">
        <line x1="{left}" y1="{top}"
              x2="{width-right}" y2="{top}"
              stroke="#38383a" stroke-dasharray="4"/>
        <line x1="{left}" y1="{top+plot_h/2}"
              x2="{width-right}" y2="{top+plot_h/2}"
              stroke="#38383a" stroke-dasharray="4"/>
        <line x1="{left}" y1="{top+plot_h}"
              x2="{width-right}" y2="{top+plot_h}"
              stroke="#38383a" stroke-dasharray="4"/>
        <text x="2" y="{top+4}" fill="#999" font-size="9">{maximum:g}</text>
        <text x="2" y="{top+plot_h/2+4}" fill="#999" font-size="9">{mid:g}</text>
        <text x="2" y="{top+plot_h+4}" fill="#999" font-size="9">{minimum:g}</text>
        <polyline fill="none"
                  stroke="{stroke}"
                  stroke-width="2.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  points="{polyline}"/>
        {''.join(circles)}
        {''.join(value_labels)}
        {''.join(date_labels)}
      </svg>
      <div class="muted">
        Klepni nebo najeď na bod pro přesné datum a hodnotu.
      </div>
    </div>
    """


# ---------------------------------------------------------
# HTML DASHBOARD
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(refresh: bool = False):

    metrics, debug_log = fetch_garmin_data_safe(
        force_refresh=refresh
    )

    (
        title,
        summary,
        training,
        nutrition,
        longevity,
    ) = generate_advice(metrics)

    def card(label, value, suffix="", note=""):

        display_value = (
            value
            if isinstance(value, str)
            else fmt(value, suffix)
        )

        return f"""
        <div class="metric">
          <div class="muted">{safe_text(label)}</div>
          <div class="metric-value">{safe_text(display_value)}</div>
          <div class="note">{safe_text(note)}</div>
        </div>
        """

    history = metrics["history"]

    hr_chart = make_svg_chart(
        history,
        "hr",
        "bpm",
        "#ff9f0a",
        "Klidový tep",
    )

    hrv_chart = make_svg_chart(
        history,
        "hrv",
        "ms",
        "#30d158",
        "Noční HRV",
    )

    stress_chart = make_svg_chart(
        history,
        "stress",
        "bodů",
        "#ff453a",
        "Denní průměr stresu",
    )

    steps_chart = make_svg_chart(
        history,
        "steps",
        "kroků",
        "#0a84ff",
        "Denní kroky",
    )

    intensity_html = ""

    for key, label in (
        ("intensity_curr_week", "Od pondělí"),
        ("intensity_week", "Posledních 7 dní"),
        ("intensity_month", "30 dní"),
        ("intensity_90d", "90 dní"),
    ):

        intensity_html += (
            '<div class="intensity-item">'
            f'<span class="muted">{label}</span>'
            f'<strong>{safe_text(fmt(metrics[key], " min"))}</strong>'
            '</div>'
        )

    activities_html = ""

    for activity in metrics["activities_list"]:

        activities_html += f"""
        <div class="activity">
          <div>
            <strong>{safe_text(activity["name"])}</strong>
            <div class="muted">
              {safe_text(activity["date"])} ·
              {safe_text(fmt(activity["duration"], " min", 1))}
            </div>
          </div>
          <strong>
            {safe_text(fmt(activity["distance"], " km", 2))}
          </strong>
        </div>
        """

    if not activities_html:

        activities_html = (
            '<p class="muted">'
            'Žádné nedávné aktivity nebo data nejsou dostupná.'
            '</p>'
        )

    debug_html = "".join(
        f'<div class="log-line">{safe_text(x)}</div>'
        for x in debug_log
    )

    weight = user_stats_cache["weight"]
    body_fat = user_stats_cache["body_fat"]

    sync_time = metrics.get("last_sync")

    sync_label = (
        datetime.datetime.fromisoformat(sync_time)
        .astimezone()
        .strftime("%d.%m.%Y %H:%M:%S")
        if sync_time
        else "Nedostupné"
    )

    page = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#000000">
<title>Garmin – Zdraví a výkon</title>

<style>
* {{ box-sizing: border-box; }}

body {{
    margin: 0;
    background: #000;
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Arial, sans-serif;
}}

.container {{
    max-width: 820px;
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
    margin-top: 10px;
    overflow-wrap: anywhere;
}}

h1 {{ font-size: 29px; font-weight: 850; margin: 4px 0; }}
h2 {{ font-size: 19px; font-weight: 800; margin: 24px 0 12px; }}
h3 {{ font-size: 14px; font-weight: 800; margin: 4px 0 12px; }}

.blue {{ color: #0a84ff; }}
.green {{ color: #30d158; }}
.orange {{ color: #ff9f0a; }}

.chart {{
    width: 100%;
    height: auto;
    overflow: visible;
    display: block;
}}

.chart-wrap {{ margin-top: 12px; }}

.chart-legend {{
    display: flex;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 11px;
    color: #bbb;
}}

.activity {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 0;
    border-bottom: 1px solid #333;
    font-size: 13px;
}}

.activity:last-child {{ border-bottom: 0; }}

.intensity-item {{
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #333;
}}

.log-line {{
    color: #6ee7a0;
    font: 11px monospace;
    padding: 3px 0;
    overflow-wrap: anywhere;
}}

input {{
    width: 100%;
    background: #000;
    border: 1px solid #444;
    color: white;
    padding: 11px;
    border-radius: 10px;
    margin-top: 5px;
}}

button, .button {{
    display: block;
    width: 100%;
    border: 0;
    border-radius: 11px;
    padding: 13px;
    margin-top: 12px;
    background: #0a84ff;
    color: white;
    font-weight: 750;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
}}

.button-secondary {{ background: #29292c; color: #65aaff; }}
.advice {{ line-height: 1.65; font-size: 13px; color: #ddd; }}

.small-title {{
    font-size: 11px;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

summary {{ cursor: pointer; font-weight: 700; }}
details[open] summary {{ margin-bottom: 12px; }}

.toggle-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}}

.toggle-row input {{
    width: auto;
    margin: 0;
    accent-color: #0a84ff;
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
    <div class="small-title">
        Garmin Connect · osobní přehled
    </div>
    <h1>Zdraví & výkon</h1>
    <div class="muted">
        Profil: {safe_text(user_stats_cache["user"])}
    </div>
    <div class="muted">
        Poslední načtení: {safe_text(sync_label)}
        · živá cache 5 minut
    </div>
</header>

<details class="panel">
    <summary>Stav Garmin API a diagnostika</summary>
    {debug_html}
    <a class="button button-secondary" href="/?refresh=true">
        Vynutit synchronizaci Garmin
    </a>
</details>

<h2>Klíčové metriky</h2>

<div class="grid">
    {card("Klidový tep", metrics["resting_heart_rate"], " bpm", "Dnešní záznam")}
    {card("HRV – noční průměr", metrics["hrv_ms"], " ms")}
    {card("Délka spánku", metrics["sleep_hours"], " hod")}
    {card("Skóre spánku", metrics["sleep_score"], " / 100")}
    {card("Body Battery – poslední", metrics["body_battery"], " / 100", metrics["body_battery_time"] or "Poslední dostupný vzorek")}
    {card("Body Battery – denní rozsah",
        (f'{fmt(metrics["body_battery_min"])}–{fmt(metrics["body_battery_max"])}'
         if metrics["body_battery_min"] is not None else None))}
    {card("Stres – denní průměr", metrics["stress_avg"], " / 100", "Není to živá hodnota stresu")}
    {card("Dnešní kroky", metrics["steps"])}
    {card("Dechová frekvence", metrics["respiration_avg"], " / min")}
</div>

<h2>Kondice a aktivita</h2>

<div class="panel">
    <h3>Intenzivní minuty (vigorous počítány 2×)</h3>
    {intensity_html}
    <div class="muted" style="margin-top:10px">
        WHO doporučuje dospělým alespoň 150–300 minut
        středně intenzivní nebo 75–150 minut intenzivní
        aerobní aktivity týdně.
    </div>
</div>

<div class="panel">
    <div class="grid">
        <div>
            <div class="muted">Fitness věk Garmin</div>
            <div class="metric-value blue">
                {safe_text(fmt(metrics["fitness_age"], " let"))}
            </div>
        </div>
        <div>
            <div class="muted">Dosažitelný fitness věk</div>
            <div class="metric-value green">
                {safe_text(fmt(metrics["achievable_fitness_age"], " let"))}
            </div>
        </div>
        <div>
            <div class="muted">Aktivní kalorie</div>
            <div class="metric-value">
                {safe_text(fmt(metrics["active_calories"], " kcal"))}
            </div>
        </div>
        <div>
            <div class="muted">Celkové kalorie</div>
            <div class="metric-value">
                {safe_text(fmt(metrics["total_calories"], " kcal"))}
            </div>
        </div>
    </div>
</div>

<h2>Trendy – posledních 30 dní</h2>

<div class="panel">
    <h3>Klidový tep</h3>
    <div class="metric-value orange">
        {safe_text(fmt(metrics["monthly_avg_hr"], " bpm", 1))}
    </div>
    <div class="muted">Průměr dostupných denních záznamů</div>
    {hr_chart}
</div>

<div class="panel">
    <h3>Noční HRV</h3>
    <div class="metric-value green">
        {safe_text(fmt(metrics["monthly_avg_hrv"], " ms", 1))}
    </div>
    <div class="muted">Průměr dostupných nočních záznamů</div>
    {hrv_chart}
</div>

<div class="panel">
    <h3>Stres – denní průměr</h3>
    {stress_chart}
</div>

<div class="panel">
    <h3>Kroky</h3>
    {steps_chart}
</div>

<div class="panel" id="activities-panel">
    <div class="toggle-row">
        <h3 style="margin:0">Poslední aktivity</h3>
        <label class="muted">
            <input id="activities-toggle" type="checkbox" checked>
            Zobrazit
        </label>
    </div>
    <div id="activities-content" style="margin-top:10px">
        {activities_html}
    </div>
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

<h2>Trénink a regenerace</h2>

<div class="panel">
    <div class="small-title">Denní vyhodnocení</div>
    <h3 class="blue" style="font-size:18px;margin-top:8px">
        {safe_text(title)}
    </h3>
    <p class="advice">{safe_text(summary)}</p>

    <h3 class="orange" style="margin-top:20px">
        Tréninkové doporučení
    </h3>
    <p class="advice">{safe_text(training)}</p>

    <h3 class="green" style="margin-top:20px">Výživa</h3>
    <p class="advice">{safe_text(nutrition)}</p>

    <h3 class="blue" style="margin-top:20px">Longevity</h3>
    <p class="advice">{safe_text(longevity)}</p>
</div>

<a class="button" href="/?refresh=true">
    Synchronizovat s Garmin Connect
</a>

<div class="muted" style="text-align:center;margin-top:18px">
    Garmin metriky jsou orientační a nenahrazují lékařské vyšetření.
</div>

</div>

<script>
(function() {{
    const checkbox = document.getElementById("activities-toggle");
    const content = document.getElementById("activities-content");
    const key = "garminActivitiesVisible";

    let visible = true;

    try {{
        const saved = localStorage.getItem(key);

        if (saved !== null) {{
            visible = saved === "1";
        }}
    }} catch(e) {{}}

    checkbox.checked = visible;
    content.hidden = !visible;

    checkbox.addEventListener("change", function() {{
        content.hidden = !checkbox.checked;

        try {{
            localStorage.setItem(
                key,
                checkbox.checked ? "1" : "0"
            );
        }} catch(e) {{}}
    }});
}})();
</script>

</body>
</html>"""

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

    return RedirectResponse(
        url="/",
        status_code=303,
    )


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@app.get("/health")
def health():

    return {
        "status": "ok",

        "garmin_api_key_configured": bool(
            GARMIN_PERSONAL_API_KEY
        ),

        "live_cache_age_seconds": (
            round(time.time() - live_cache["timestamp"])
            if live_cache["timestamp"]
            else None
        ),

        "history_cache_age_seconds": (
            round(time.time() - history_cache["timestamp"])
            if history_cache["timestamp"]
            else None
        ),

        "hrv_history_days": HRV_HISTORY_DAYS,

        "api_request_interval": MIN_REQUEST_INTERVAL,
    }