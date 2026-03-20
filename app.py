import streamlit as st
import datetime
import requests
from google import genai
import json
import os

# UI Configuration
st.set_page_config(page_title="Football AI", layout="wide", initial_sidebar_state="collapsed")

# --- Disk Caching System ---
CACHE_DIR = "/tmp/data_cache"
if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR, exist_ok=True)

def get_disk_cache(key):
    file_path = os.path.join(CACHE_DIR, f"{key.replace('/', '_')}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                cache_data = json.load(f)
                expiry = datetime.datetime.fromisoformat(cache_data['expiry'])
                if datetime.datetime.now(datetime.timezone.utc) < expiry.replace(tzinfo=datetime.timezone.utc):
                    return cache_data['data']
        except: return None
    return None

def set_disk_cache(key, data, expiry_dt=None, days=1):
    if expiry_dt is None: expiry_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    file_path = os.path.join(CACHE_DIR, f"{key.replace('/', '_')}.json")
    try:
        with open(file_path, "w") as f: json.dump({'data': data, 'expiry': expiry_dt.isoformat()}, f)
    except: pass

# Time Handling
now_mm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6, minutes=30)
today_mm = now_mm.date()

# ၁။ Dictionary & Session State
if 'lang' not in st.session_state: st.session_state.lang = 'EN'
if 'display_matches' not in st.session_state: st.session_state.display_matches = []
if 'check_performed' not in st.session_state: st.session_state.check_performed = False

d = {
    'EN': {
        'title1': 'Predictions', 'sel_league': 'Select League', 'sel_date': 'Select Date',
        'btn_check': 'Check Matches Now', 'title2': 'Select Team',
        'date_opts': ["Manual Date", "Within 24 Hours", "Within 48 Hours"],
        'no_fixture': 'No matches available for this date.'
    },
    'MM': {
        'title1': 'ပွဲကြိုခန့်မှန်းချက်များ', 'sel_league': 'လိဂ်ကို ရွေးချယ်ပါ', 'sel_date': 'ရက်စွဲကို ရွေးချယ်ပါ',
        'btn_check': 'ပွဲစဉ်များကို စစ်ဆေးမည်', 'title2': 'အသင်းကို ရွေးချယ်ပါ',
        'date_opts': ["ရက်စွဲတပ်၍ရှာမည်", "၂၄ နာရီအတွင်း", "၄၈ နာရီအတွင်း"],
        'no_fixture': 'ရွေးထားသော ရက်စွဲတွင် ပွဲစဉ်မရှိပါ။'
    }
}
lang = st.session_state.lang

league_map = {
    "Premier League (England)": {"fd": "PL", "as": 39},
    "Championship (England)": {"fd": "ELC", "as": 40},
    "FA Cup (England)": {"fd": None, "as": 45},
    "Carabao Cup (England)": {"fd": None, "as": 48},
    "Champions League (Europe)": {"fd": "CL", "as": 2},
    "Europa League (Europe)": {"fd": "EL", "as": 3},
    "Conference League (Europe)": {"fd": "ECL", "as": 848},
    "La Liga (Spain)": {"fd": "PD", "as": 140},
    "Copa del Rey (Spain)": {"fd": None, "as": 143},
    "Bundesliga (Germany)": {"fd": "BL1", "as": 78},
    "DFB Pokal (Germany)": {"fd": None, "as": 175},
    "Serie A (Italy)": {"fd": "SA", "as": 135},
    "Coppa Italia (Italy)": {"fd": None, "as": 137},
    "Ligue 1 (France)": {"fd": "FL1", "as": 61},
    "Eredivisie (Netherlands)": {"fd": "DED", "as": 88},
    "Primeira Liga (Portugal)": {"fd": "PPL", "as": 94},
    "Serie A (Brazil)": {"fd": "BSA", "as": 71}
}

st.markdown(f'<div class="title-style">{d[lang]["title1"]}</div>', unsafe_allow_html=True)

# ၂။ Select League & Date
league_name = st.selectbox(d[lang]["sel_league"], list(league_map.keys()))
date_option = st.radio("Option", d[lang]['date_opts'], horizontal=True)
sel_date = st.date_input("Date", value=today_mm)

# ၃။ Check Matches Logic
if st.button(d[lang]["btn_check"], use_container_width=True):
    st.session_state.check_performed = True
    st.session_state.display_matches = []
    l_info = league_map[league_name]
    
    # ရက်စွဲစာရင်းကို API-Sports အတွက် တိကျအောင်လုပ်ခြင်း
    if date_option == d[lang]['date_opts'][1]: # 24h
        target_dates = [today_mm, today_mm + datetime.timedelta(days=1)]
    elif date_option == d[lang]['date_opts'][2]: # 48h
        target_dates = [today_mm, today_mm + datetime.timedelta(days=1), today_mm + datetime.timedelta(days=2)]
    else: # Manual
        target_dates = [sel_date]

    try:
        # A. Football-Data.org
        if l_info["fd"]:
            fd_token = st.secrets["api_keys"]["FOOTBALL_DATA_KEY"]
            d_from = target_dates[0]
            d_to = target_dates[-1] + datetime.timedelta(days=1)
            url = f"https://api.football-data.org/v4/competitions/{l_info['fd']}/matches?dateFrom={d_from}&dateTo={d_to}"
            res = requests.get(url, headers={'X-Auth-Token': fd_token}).json()
            if 'matches' in res:
                for m in res['matches']:
                    utc_dt = datetime.datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
                    mm_dt = utc_dt + datetime.timedelta(hours=6, minutes=30)
                    st.session_state.display_matches.append({
                        'datetime': mm_dt.strftime("%d/%m %H:%M"), 'home': m['homeTeam']['name'], 'away': m['awayTeam']['name'],
                        'h_logo': m['homeTeam'].get('crest', ''), 'a_logo': m['awayTeam'].get('crest', '')
                    })

        # B. API-Sports (Football-Data မှာမရှိရင် သို့မဟုတ် ပွဲမတွေ့ရင်)
        if not st.session_state.display_matches:
            as_key = st.secrets["api_keys"]["API_SPORTS_KEY"]
            for t_date in target_dates:
                # Season ကို Carabao Cup အတွက် 2025 ပြောင်းစမ်းကြည့်ခြင်း
                as_url = f"https://v3.football.api-sports.io/fixtures?league={l_info['as']}&season=2025&date={t_date}"
                as_res = requests.get(as_url, headers={'x-rapidapi-key': as_key}).json()
                for f in as_res.get('response', []):
                    utc_dt = datetime.datetime.fromisoformat(f['fixture']['date'].replace('+00:00', ''))
                    mm_dt = utc_dt + datetime.timedelta(hours=6, minutes=30)
                    st.session_state.display_matches.append({
                        'datetime': mm_dt.strftime("%d/%m %H:%M"), 'home': f['teams']['home']['name'], 'away': f['teams']['away']['name'],
                        'h_logo': f['teams']['home'].get('logo', ''), 'a_logo': f['teams']['away'].get('logo', '')
                    })
        
        h_set = {m['home'] for m in st.session_state.display_matches}
        a_set = {m['away'] for m in st.session_state.display_matches}
        st.session_state.h_teams = ["Select Team"] + sorted(list(h_set)) if h_set else ["No matches found"]
        st.session_state.a_teams = ["Select Team"] + sorted(list(a_set)) if a_set else ["No matches found"]
        
    except Exception as e: st.error(f"Error: {e}")

# Display Table
if st.session_state.display_matches:
    st.markdown(f'<div style="color:#FFD700; font-weight:bold; margin: 15px 0 5px 15px;">🏆 {league_name}</div>', unsafe_allow_html=True)
    for idx, m in enumerate(st.session_state.display_matches, 1):
        st.markdown(f"""
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; border-bottom: 1px solid #333; background: rgba(255,255,255,0.03); margin-bottom: 5px; border-radius: 8px;">
                <div style="font-size: 10px; color: #888; flex: 0.8;">#{idx}<br>{m['datetime']}</div>
                <div style="text-align: right; flex: 2; font-size: 13px;"><img src="{m['h_logo']}" width="20" style="vertical-align: middle; margin-left: 5px;"> {m['home']}</div>
                <div style="font-weight: bold; color: #FFD700; flex: 0.5; text-align: center;">VS</div>
                <div style="text-align: left; flex: 2; font-size: 13px;">{m['away']} <img src="{m['a_logo']}" width="20" style="vertical-align: middle; margin-right: 5px;"></div>
            </div>
        """, unsafe_allow_html=True)
elif st.session_state.check_performed:
    st.warning(d[lang]['no_fixture'])

st.markdown(f'<div class="title-style" style="font-size:45px; margin-top:20px;">{d[lang]["title2"]}</div>', unsafe_allow_html=True)

def get_gemini_response_rotated(prompt):
    gm_key = st.secrets["api_keys"]["GEMINI_KEY"]
    try:
        client = genai.Client(api_key=gm_key)
        response = client.models.generate_content(model='gemini-flash-latest', contents=prompt)
        return response.text
    except Exception as e: return f"Error: {e}"
    


# ၅။ Home vs Away Section
c1, cvs, c2 = st.columns([2, 1, 2])
with c1:
    st.markdown(f'<p style="color:white; text-align:center; font-weight:900; font-size:12px;">{d[lang]["home"]}</p>', unsafe_allow_html=True)
    h_team = st.selectbox("H", st.session_state.h_teams, key="h", label_visibility="collapsed")
with cvs:
    st.markdown('<div style="display: flex; justify-content: center; align-items: center; height: 100%;"><div class="vs-ball">vs</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<p style="color:white; text-align:center; font-weight:900; font-size:12px;">{d[lang]["away"]}</p>', unsafe_allow_html=True)
    a_team = st.selectbox("A", st.session_state.a_teams, key="a", label_visibility="collapsed")

st.markdown('<div class="gen-btn-wrapper">', unsafe_allow_html=True)
gen_click = st.button(d[lang]["btn_gen"], key="gen_btn", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

if gen_click:
    if h_team and a_team and h_team not in ["Select Team", "No matches found"]:
        match_obj = next((m for m in st.session_state.display_matches if m['home'] == h_team and m['away'] == a_team), None)
        if match_obj:
            progress_bar = st.progress(0)
            for percent_complete in range(100):
                time.sleep(0.01)
                progress_bar.progress(percent_complete + 1)
                
            with st.spinner('AI is analyzing real-time data from API...'):
                match_utc = datetime.datetime.strptime(match_obj['utc_str'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                expiry_dt_naive = datetime.datetime.now() + (match_utc + datetime.timedelta(hours=1) - datetime.datetime.now(datetime.timezone.utc))
                
                cache_key = f"pred_final_v12_major_{h_team}_{a_team}_{today_mm}"
                cached_result = get_disk_cache(cache_key)

                if cached_result:
                    st.markdown(cached_result, unsafe_allow_html=True)
                else:
                    real_data = get_api_sports_stats(h_team, a_team, today_mm.isoformat())
                    if real_data:
                        h_id, a_id = real_data['h_id'], real_data['a_id']
                        injury_list = [f"{i['player']['name']} ({i['player']['reason']})" for i in real_data.get('injuries', [])]
                        
                        h_top = []
                        if real_data.get('h_ratings') and len(real_data['h_ratings']) > 0:
                            for p in real_data['h_ratings'][0].get('players', []):
                                r = p['statistics'][0]['games'].get('rating')
                                if r and float(r) > 7.0: h_top.append(f"{p['player']['name']} ({r})")
                            
                        a_top = []
                        if real_data.get('a_ratings') and len(real_data['a_ratings']) > 0:
                            for p in real_data['a_ratings'][0].get('players', []):
                                r = p['statistics'][0]['games'].get('rating')
                                if r and float(r) > 7.0: a_top.append(f"{p['player']['name']} ({r})")

                        h_n, a_n = (real_data['h_schedule'][0] if real_data['h_schedule'] else None), (real_data['a_schedule'][0] if real_data['a_schedule'] else None)
                        h_next = f"[{h_n['league']['name']}] vs {h_n['teams']['away']['name'] if h_n['teams']['home']['id']==h_id else h_n['teams']['home']['name']}" if h_n else "N/A"
                        a_next = f"[{a_n['league']['name']}] vs {a_n['teams']['away']['name'] if a_n['teams']['home']['id']==a_id else a_n['teams']['home']['name']}" if a_n else "N/A"

                        stats_context = f"""
                        [SOURCE: API-SPORTS VERIFIED DATA]
                        - Match Context: {h_team} vs {a_team}
                        - Tournament: {real_data['league_name']}
                        - STANDINGS (Points/Rank): {real_data['standings']}
                        - SQUAD UPDATE (Injuries): {', '.join(injury_list) if injury_list else 'None Reported'}
                        - TOP PERFORMERS: {h_team}: {', '.join(h_top[:3]) if h_top else 'N/A'} | {a_team}: {', '.join(a_top[:3]) if a_top else 'N/A'}
                        - NEXT MATCH (Schedule): {h_team} vs {h_next} | {a_team} vs {a_next}
                        """

                        prompt = f"""
                        SYSTEM INSTRUCTION: You are a professional 2026 tactical analyst.
                        - STRICT: Use ONLY provided [SOURCE] data for facts.
                        - KNOWLEDGE: Domestic Major Leagues are Premier League, La Liga, Serie A, Bundesliga, Ligue 1.
                        - COMPARISON: Compare current {real_data['league_name']} standings with Domestic League status.
                        - LOGIC: If a team is safe in Champions League but has a crucial Domestic title race/derby next, predict heavy rotation.
                        
                        {stats_context}

                        Respond strictly in BURMESE (Unicode).

                        OUTPUT FORMAT:
                        # သုံးသပ်ချက်
                        **{h_team} ခြေစွမ်းနှင့် ပြိုင်ပွဲစုံရပ်တည်မှု** (ပြည်တွင်းလိဂ်နှင့် {real_data['league_name']} အဆင့်ကို နှိုင်းယှဉ်၍ ၅ ကြောင်း)
                        **{a_team} ခြေစွမ်းနှင့် ပြိုင်ပွဲစုံရပ်တည်မှု** (ပြည်တွင်းလိဂ်နှင့် {real_data['league_name']} အဆင့်ကို နှိုင်းယှဉ်၍ ၅ ကြောင်း)
                        **ပွဲစဉ်ဦးစားပေးမှုနှင့် Squad Rotation** (လာမည့် ပြည်တွင်းလိဂ်ပွဲ၏အရေးကြီးပုံကို ကိုးကား၍ ၅ ကြောင်း)
                        **နည်းဗျူဟာပိုင်းဆိုင်ရာ ခွဲခြမ်းစိတ်ဖြာမှု** (၅ ကြောင်း)

                        ### **Summarize Table**
                        | Category | Prediction |
                        | :--- | :--- |
                        | Winner Team | [မြန်မာလို] |
                        | Correct Score | [Result] |
                        | Goal under/over | [Result] |
                        | BTTS (Yes/No) | [Result] |

                        # **🏆 အကျိုးအကြောင်းခိုင်လုံဆုံးရွေးချယ်မှု: [ရလဒ်]**
                        Reasoning: (Domestic League Ranking, Current Tournament Standing နှင့် Schedule တို့ကို ပေါင်းစပ်၍ ၆ ကြောင်း တိကျစွာဖြေဆိုပါ)
                        """
                        response_text = get_gemini_response_rotated(prompt)
                        final_output = f'<div style="background:#0c0c0c; padding:20px; border-radius:15px; border:1px solid #39FF14; color:white;">{response_text}</div>'
                        set_disk_cache(cache_key, final_output, expiry_dt=expiry_dt_naive)
                        st.markdown(final_output, unsafe_allow_html=True)
                    else:
                        st.error("No real-time data available from API.")
        else:
            st.error(f"⚠️ {d[lang]['no_match']}")
    else:
        st.warning("Please select teams first!")
