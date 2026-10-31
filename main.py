import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from google import genai

app = FastAPI()

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def get_garmin_data():
    # Připraveno pro budoucí přímé volání Garmin API
    if not GARMIN_PERSONAL_API_KEY:
        print("Varování: GARMIN_PERSONAL_API_KEY není nastaven v prostředí.")

    # Data zaměřená na fitness a fullbody silový trénink
    return {
        "user": "Drsňák",
        "sleep_score": 75,
        "hrv_status": "Balanced (42 ms)",
        "body_battery_max": 70,
        "resting_heart_rate": 56,
        "yesterday_workout": "Fullbody posilovna (těžké dřepy, benchpress, záda)"
    }

@app.get("/", response_class=HTMLResponse)
def home():
    try:
        if not GEMINI_API_KEY:
            return "<h2 style='color: red; text-align: center; margin-top: 50px;'>Chyba: Chybí GEMINI_API_KEY v proměnných prostředí na Renderu!</h2>"
        
        # Získání dat
        data = get_garmin_data()

        # Gemini AI analýza zaměřená na fitness, silový trénink a regeneraci CNS
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Jsi elitní síla a kondiční trenér a sportovní fyziolog. Tvým svěřencem je "Drsňák", který primárně cvičí fitness a fullbody tréninky.
        Analyzuj následující data:
        - Spánkové skóre: {data['sleep_score']}/100
        - Stav HRV: {data['hrv_status']}
        - Max Body Battery: {data['body_battery_max']}/100
        - Klidový tep: {data['resting_heart_rate']} bpm
        - Včerejší trénink: {data['yesterday_workout']}

        Poskytni vysoce profesionální, odborné a energické hodnocení zaměřené na silový trénink rozdělené do těchto bloků:
        1. **Fyziologický stav a regenerace CNS** (jak se tělo a nervová soustava vyrovnaly s včerejší zátěží)
        2. **Zdravotní doporučení a prevence** (výživa, hydratace, kloubní výživa, spánek, prevence přetížení šlach a úponů)
        3. **Odborný trenérský verdikt** (připravenost na silový výkon)
        4. **Doporučený dnešní trénink** (specifikuj, zda jet fullbody, zařadit lehkou hypertrofii, nebo zvolit kompletní rest day/aktivní regeneraci)
        """
        
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )
        
        ai_text = response.text.replace('\n', '<br>')

        # HTML Šablona
        html_content = f"""
        <!DOCTYPE html>
        <html lang="cs">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Garmin AI Fitness Trenér</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-slate-950 text-slate-100 font-sans min-h-screen p-4 md:p-8">
            <div class="max-w-3xl mx-auto">
                <header class="mb-8 text-center">
                    <h1 class="text-3xl font-black tracking-wider text-blue-500 uppercase">Garmin AI Fitness Trenér</h1>
                    <p class="text-slate-400 text-sm mt-1">Osobní silový dashboard pro svěřence: <span class="text-white font-semibold">Drsňák</span></p>
                </header>

                <!-- Metriky karty -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                    <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow-lg">
                        <div class="text-slate-400 text-xs uppercase tracking-wider font-medium">Spánek</div>
                        <div class="text-2xl font-extrabold text-emerald-400 mt-1">{data['sleep_score']}<span class="text-sm text-slate-500">/100</span></div>
                    </div>
                    <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow-lg">
                        <div class="text-slate-400 text-xs uppercase tracking-wider font-medium">Body Battery</div>
                        <div class="text-2xl font-extrabold text-blue-400 mt-1">{data['body_battery_max']}</div>
                    </div>
                    <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow-lg">
                        <div class="text-slate-400 text-xs uppercase tracking-wider font-medium">HRV Status</div>
                        <div class="text-sm font-extrabold text-purple-400 mt-2 truncate">{data['hrv_status']}</div>
                    </div>
                    <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow-lg">
                        <div class="text-slate-400 text-xs uppercase tracking-wider font-medium">Klidový tep</div>
                        <div class="text-2xl font-extrabold text-orange-400 mt-1">{data['resting_heart_rate']} <span class="text-xs text-slate-500">bpm</span></div>
                    </div>
                </div>

                <!-- AI Zhodnocení -->
                <div class="bg-slate-900 rounded-2xl p-6 md:p-8 border border-slate-800 shadow-2xl">
                    <div class="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
                        <h2 class="text-lg font-bold text-slate-200 flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse"></span>
                            Fitness AI Analýza & Regenerace CNS
                        </h2>
                        <span class="text-xs bg-blue-500/10 text-blue-400 px-2.5 py-1 rounded-full font-medium">Gemini 3.8 Flash</span>
                    </div>
                    <div class="text-slate-300 leading-relaxed space-y-3 text-sm md:text-base">
                        {ai_text}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html_content
        
    except Exception as e:
        return f"<h3 style='color: red; padding: 20px;'>Chyba serveru: {str(e)}</h3>"
