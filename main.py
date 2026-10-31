import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from google import genai

app = FastAPI()

GARMIN_PERSONAL_API_KEY = os.environ.get("GARMIN_PERSONAL_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def get_garmin_data():
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
            return "<div style='background: #090d16; color: #ff5555; padding: 40px; text-align: center; font-family: sans-serif;'><h2>Chyba: Chybí GEMINI_API_KEY v proměnných prostředí na Renderu!</h2></div>"
        
        data = get_garmin_data()

        # Gemini AI analýza
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Jsi elitní síla a kondiční trenér a sportovní fyziolog. Tvým svěřencem je "Drsňák", který primárně cvičí fitness a fullbody tréninky.
        Analyzuj následující data:
        - Spánkové skóre: {data['sleep_score']}/100
        - Stav HRV: {data['hrv_status']}
        - Max Body Battery: {data['body_battery_max']}/100
        - Klidový tep: {data['resting_heart_rate']} bpm
        - Včerejší trénink: {data['yesterday_workout']}

        Poskytni vysoce profesionální, odborné a energické hodnocení rozdělené přesně na tyto 4 body (použij na začátku každého bodu odpovídající nadpis):
        1. Fyziologický stav a regenerace CNS
        2. Zdravotní doporučení a prevence
        3. Odborný trenérský verdikt
        4. Doporučený dnešní trénink
        """
        
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )
        
        raw_text = response.text

        # HTML Šablona s prémiovým designem
        html_content = f"""
        <!DOCTYPE html>
        <html lang="cs">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Garmin AI Fitness Trenér</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-[#030712] text-slate-100 font-sans min-h-screen pb-12">
            
            <!-- Vrchní lišta -->
            <div class="bg-gradient-to-b from-slate-900 to-[#030712] border-b border-slate-800/80 sticky top-0 z-50 backdrop-blur-md bg-opacity-90">
                <div class="max-w-md md:max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
                    <div class="flex items-center gap-2.5">
                        <div class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_#10b981]"></div>
                        <span class="font-bold tracking-wider text-sm uppercase text-slate-300">Garmin AI Coach</span>
                    </div>
                    <div class="text-xs bg-slate-800/80 text-blue-400 border border-slate-700/50 px-3 py-1 rounded-full font-medium">
                        Svěřenec: <span class="text-white font-bold">{data['user']}</span>
                    </div>
                </div>
            </div>

            <div class="max-w-md md:max-w-2xl mx-auto px-4 mt-6">
                
                <!-- Hlavní nadpis -->
                <div class="mb-6">
                    <h1 class="text-2xl md:text-3xl font-black tracking-tight text-white">Dnešní připravenost</h1>
                    <p class="text-slate-400 text-xs md:text-sm mt-0.5">Analýza centrální nervové soustavy a silového potenciálu</p>
                </div>

                <!-- Metriky - Grid karet -->
                <div class="grid grid-cols-2 gap-3 mb-6">
                    <!-- Spánek -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800/80 shadow-xl relative overflow-hidden">
                        <div class="absolute -right-4 -bottom-4 w-16 h-16 bg-emerald-500/5 rounded-full blur-xl"></div>
                        <div class="text-slate-400 text-[11px] uppercase tracking-wider font-semibold">Spánek</div>
                        <div class="text-2xl md:text-3xl font-black text-emerald-400 mt-1">{data['sleep_score']}<span class="text-xs text-slate-500 font-normal">/100</span></div>
                        <div class="text-[10px] text-slate-500 mt-1">Kvalita noční regenerace</div>
                    </div>

                    <!-- Body Battery -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800/80 shadow-xl relative overflow-hidden">
                        <div class="absolute -right-4 -bottom-4 w-16 h-16 bg-blue-500/5 rounded-full blur-xl"></div>
                        <div class="text-slate-400 text-[11px] uppercase tracking-wider font-semibold">Body Battery</div>
                        <div class="text-2xl md:text-3xl font-black text-blue-400 mt-1">{data['body_battery_max']}</div>
                        <div class="text-[10px] text-slate-500 mt-1">Celková energetická reserva</div>
                    </div>

                    <!-- HRV Status -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800/80 shadow-xl relative overflow-hidden">
                        <div class="absolute -right-4 -bottom-4 w-16 h-16 bg-purple-500/5 rounded-full blur-xl"></div>
                        <div class="text-slate-400 text-[11px] uppercase tracking-wider font-semibold">HRV Status</div>
                        <div class="text-sm md:text-base font-extrabold text-purple-400 mt-2 truncate">{data['hrv_status']}</div>
                        <div class="text-[10px] text-slate-500 mt-1">Aktivita autonomního nervstva</div>
                    </div>

                    <!-- Klidový tep -->
                    <div class="bg-gradient-to-br from-slate-900 to-slate-900/40 p-4 rounded-2xl border border-slate-800/80 shadow-xl relative overflow-hidden">
                        <div class="absolute -right-4 -bottom-4 w-16 h-16 bg-orange-500/5 rounded-full blur-xl"></div>
                        <div class="text-slate-400 text-[11px] uppercase tracking-wider font-semibold">Klidový tep</div>
                        <div class="text-2xl md:text-3xl font-black text-orange-400 mt-1">{data['resting_heart_rate']} <span class="text-xs text-slate-500 font-normal">bpm</span></div>
                        <div class="text-[10px] text-slate-500 mt-1">Základní kardio metrika</div>
                    </div>
                </div>

                <!-- AI Zhodnocení - Box -->
                <div class="bg-slate-900/80 backdrop-blur-xl rounded-3xl p-5 md:p-6 border border-slate-800 shadow-2xl relative">
                    <div class="flex items-center justify-between mb-5 border-b border-slate-800 pb-3">
                        <div class="flex items-center gap-2">
                            <div class="p-1.5 bg-blue-500/10 rounded-lg border border-blue-500/20 text-blue-400">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                            </div>
                            <h2 class="text-sm font-bold tracking-wide uppercase text-slate-200">Trenérská analýza</h2>
                        </div>
                        <span class="text-[10px] bg-slate-800 text-slate-400 px-2.5 py-1 rounded-md font-mono border border-slate-700/50">Gemini 3.8 Flash</span>
                    </div>

                    <div class="text-slate-300 leading-relaxed text-sm space-y-4">
                        {raw_text.replace(chr(10), '<br>')}
                    </div>
                </div>

                <!-- Refresh tlačítko -->
                <div class="mt-6 text-center">
                    <button onclick="window.location.reload();" class="w-full py-3 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 font-semibold text-xs uppercase tracking-wider rounded-xl transition shadow-lg active:scale-[0.98]">
                        Obnovit analýzu
                    </button>
                </div>

            </div>
        </body>
        </html>
        """
        return html_content
        
    except Exception as e:
        return f"<div style='background: #030712; color: #ff5555; padding: 40px; font-family: sans-serif;'><h3>Chyba serveru: {str(e)}</h3></div>"
