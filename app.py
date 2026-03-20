import streamlit as st
import datetime
import requests
from google import genai
import time
import json
import os
import dateutil.parser

# UI Configuration
st.set_page_config(
    page_title="Football AI",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items=None
)

# --- Disk Caching System ---
CACHE_DIR = "/tmp/data_cache"
try:
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)
except Exception:
    CACHE_DIR = "/tmp"

def get_disk_cache(key):
    safe_key = key.replace("/", "_")
    file_path = os.path.join(CACHE_DIR, f"{safe_key}.json")
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
    if expiry_dt is None:
        expiry_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    safe_key = key.replace("/", "_")
    file_path = os.path.join(CACHE_DIR, f"{safe_key}.json")
    try:
        with open(file_path, "w") as f:
            json.dump({'data': data, 'expiry': expiry_dt.isoformat()}, f)
    except: pass

# Time Handling
now_mm = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6, minutes=30)
today_mm = now_mm.date()

# ၁။ Dictionary & Session State
if 'lang' not in st.session_state: st.session_state.lang = 'EN'
if 'h_teams' not in st.session_state: st.session_state.h_teams = ["Select Team"]
if 'a_teams' not in st.session_state: st.session_state.a_teams = ["Select Team"]
if 'display_matches' not in st.session_state: st.session_state.display_matches = []
if 'check_performed' not in st.session_state: st.session_state.check_performed = False

def toggle_lang():
    st.session_state.lang = 'MM' if st.session_state.lang == 'EN' else 'EN'

d = {
    'EN': {
        'title1': 'Predictions', 'sel_league': 'Select League', 'sel_date': 'Select Date',
        'btn_check': 'Check Matches Now', 'title2': 'Select Team',
        'home': 'HOME TEAM', 'away': 'AWAY TEAM', 'btn_gen': 'Generate Predictions',
        'trans_btn': 'မြန်မာဘာသာသို့ ပြောင်းရန်',
        'date_opts': ["Manual Date", "Within 24 Hours", "Within 48 Hours"],
        'no_fixture': 'No matches available for this date.'
    },
    'MM': {
        'title1': 'ပွဲကြိုခန့်မှန်းချက်များ', 'sel_league': 'လိဂ်ကို ရွေးချယ်ပါ', 'sel_date': 'ရက်စွဲကို ရွေးချယ်ပါ',
        'btn_check': 'ပွဲစဉ်များကို စစ်ဆေးမည်', 'title2': 'အသင်းကို ရွေးချယ်ပါ',
        'home': 'အိမ်ရှင်အသင်း', 'away': 'ဧည့်သည်အသင်း', 'btn_gen': 'ခန့်မှန်းချက် ထုတ်ယူမည်',
        'trans_btn': 'Switch to English',
        'date_opts': ["ရက်စွဲတပ်၍ရှာမည်", "၂၄ နာရီအတွင်း", "၄၈ နာရီအတွင်း"],
        'no_fixture': 'ရွေးထားသော ရက်စွဲတွင် ပွဲစဉ်မရှိပါ။'
    }
}
lang = st.session_state.lang

# Competitions (၁၇) ခုစာရင်း (Football-Data & API-Sports IDs)
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

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

col_space, col_lang = st.columns([7, 3])
with col_lang:
    st.button(d[lang]["trans_btn"], key="lang_btn", on_click=toggle_lang, use_container_width=True)

st.markdown(f'<div class="title-style">{d[lang]["title1"]}</div>', unsafe_allow_html=True)

# ၂။ Select League & Date
st.markdown(f'<p style="color:#aaa; margin-left:15px;">{d[lang]["sel_league"]}</p>', unsafe_allow_html=True)
league_name = st.selectbox("L", list(league_map.keys()), index=0, label_visibility="collapsed")

st.markdown(f'<p style="color:#aaa; margin-left:15px; margin-top:15px;">{d[lang]["sel_date"]}</p>', unsafe_allow_html=True)
date_option = st.radio("Date Option", d[lang]['date_opts'], horizontal=True, label_visibility="collapsed")
sel_date = st.date_input("D", value=today_mm, min_value=today_mm, label_visibility="collapsed")

# ၃။ Check Matches Logic (Hybrid Fetching)
check_click = st.button(d[lang]["btn_check"], key="check_btn", use_container_width=True)

if check_click:
    st.session_state.check_performed = True
    st.session_state.display_matches = []
    l_info = league_map[league_name]
    
    # ရက်စွဲစာရင်း ပြင်ဆင်ခြင်း
    target_dates = [sel_date]
    if date_option == d[lang]['date_opts'][1]: target_dates = [today_mm, today_mm + datetime.timedelta(days=1)]
    elif date_option == d[lang]['date_opts'][2]: target_dates = [today_mm, today_mm + datetime.timedelta(days=1), today_mm + datetime.timedelta(days=2)]

    try:
        # Step A: Football-Data.org
        if l_info["fd"]:
            fd_token = st.secrets["api_keys"]["FOOTBALL_DATA_KEY"]
            d_from, d_to = target_dates[0], target_dates[-1] + datetime.timedelta(days=1)
            url = f"https://api.football-data.org/v4/competitions/{l_info['fd']}/matches?dateFrom={d_from}&dateTo={d_to}"
            res = requests.get(url, headers={'X-Auth-Token': fd_token}).json()
            if 'matches' in res:
                for m in res['matches']:
                    utc_dt = datetime.datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
                    mm_dt = utc_dt + datetime.timedelta(hours=6, minutes=30)
                    st.session_state.display_matches.append({
                        'datetime': mm_dt.strftime("%d/%m %H:%M"), 'home': m['homeTeam']['name'], 'away': m['awayTeam']['name'],
                        'h_logo': m['homeTeam'].get('crest', ''), 'a_logo': m['awayTeam'].get('crest', ''), 'league': league_name
                    })

        # Step B: API-Sports (Football-Data တွင်မရှိသော Cup များအတွက်)
        if not st.session_state.display_matches:
            as_key = st.secrets["api_keys"]["API_SPORTS_KEY"]
            for t_date in target_dates:
                as_url = f"https://v3.football.api-sports.io/fixtures?league={l_info['as']}&season=2025&date={t_date}"
                as_res = requests.get(as_url, headers={'x-rapidapi-key': as_key}).json()
                for f in as_res.get('response', []):
                    utc_dt = datetime.datetime.fromisoformat(f['fixture']['date'].replace('+00:00', ''))
                    mm_dt = utc_dt + datetime.timedelta(hours=6, minutes=30)
                    st.session_state.display_matches.append({
                        'datetime': mm_dt.strftime("%d/%m %H:%M"), 'home': f['teams']['home']['name'], 'away': f['teams']['away']['name'],
                        'h_logo': f['teams']['home'].get('logo', ''), 'a_logo': f['teams']['away'].get('logo', ''), 'league': league_name
                    })
        
        h_set = {m['home'] for m in st.session_state.display_matches}
        a_set = {m['away'] for m in st.session_state.display_matches}
        st.session_state.h_teams = ["Select Team"] + sorted(list(h_set)) if h_set else ["No matches found"]
        st.session_state.a_teams = ["Select Team"] + sorted(list(a_set)) if a_set else ["No matches found"]
        
    except Exception as e: st.error(f"Error: {e}")

# Display Matches
if st.session_state.display_matches:
    st.markdown(f'<div style="color:#FFD700; font-weight:bold; margin:15px;">🏆 {league_name}</div>', unsafe_allow_html=True)
    for idx, m in enumerate(st.session_state.display_matches, 1):
        st.markdown(f"""
            <div class="match-row" style="padding:15px 10px; border-bottom:1px solid #333; display:flex; align-items:center; justify-content:space-between;">
                <div style="flex:1; font-size:11px; color:#888;">#{idx}<br>{m['datetime']}</div>
                <div style="flex:2; text-align:center;"><img src="{m['h_logo']}" width="25"> {m['home']}</div>
                <div style="flex:0.5; text-align:center; color:#FFD700; font-weight:bold;">VS</div>
                <div style="flex:2; text-align:center;">{m['away']} <img src="{m['a_logo']}" width="25"></div>
            </div>
        """, unsafe_allow_html=True)
elif st.session_state.check_performed:
    st.warning(d[lang]['no_fixture'])

# ၄။ Select Team Title
st.markdown(f'<div class="title-style" style="font-size:45px; margin-top:20px;">{d[lang]["title2"]}</div>', unsafe_allow_html=True)

# Gemini Model (gemini-flash-latest) - Rotation ဖြုတ်၍ တိုက်ရိုက်ခေါ်ခြင်း
def get_gemini_response_rotated(prompt):
    gm_key = st.secrets["api_keys"]["GEMINI_KEY"]
    try:
        client = genai.Client(api_key=gm_key)
        response = client.models.generate_content(model='gemini-flash-latest', contents=prompt)
        return response.text
    except Exception as e: return f"AI Error: {str(e)}"
    
    

# ၅။ Home vs Away Section
c1, cvs, c2 = st.columns([2, 1, 2])
with c1:
    st.markdown(f'<p style="color:white; text-align:center; font-weight:900; font-size:12px;">{d[lang]["home"]}</p>', unsafe_allow_html=True)
    # Session state မှ team စာရင်းကို သုံးရန်
    h_team = st.selectbox("H", st.session_state.get('h_teams', ["Select Team"]), key="h", label_visibility="collapsed")
with cvs:
    st.markdown('<div style="display: flex; justify-content: center; align-items: center; height: 100%; margin-top: 25px;"><div class="vs-ball" style="background: #FFD700; color: black; border-radius: 50%; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 0 0 15px #FFD700;">vs</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<p style="color:white; text-align:center; font-weight:900; font-size:12px;">{d[lang]["away"]}</p>', unsafe_allow_html=True)
    a_team = st.selectbox("A", st.session_state.get('a_teams', ["Select Team"]), key="a", label_visibility="collapsed")

st.markdown('<div class="gen-btn-wrapper" style="margin-top: 20px;">', unsafe_allow_html=True)
gen_click = st.button(d[lang]["btn_gen"], key="gen_btn", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

if gen_click:
    # အသင်းရွေးချယ်မှု ရှိမရှိ အရင်စစ်ဆေးခြင်း
    if h_team and a_team and h_team not in ["Select Team", "No matches found"]:
        # Match Table ထဲတွင် အမှန်တကယ် ပါမပါ ရှာဖွေခြင်း
        match_obj = next((m for m in st.session_state.get('display_matches', []) if m['home'] == h_team and m['away'] == a_team), None)
        
        if match_obj:
            progress_bar = st.progress(0)
            for percent_complete in range(100):
                time.sleep(0.005)
                progress_bar.progress(percent_complete + 1)
                
            with st.spinner('AI is analyzing real-time data from API...'):
                # Cache Key သတ်မှတ်ခြင်း (ရက်စွဲအလိုက်)
                cache_key = f"pred_final_v12_{h_team}_{a_team}_{today_mm}"
                cached_result = get_disk_cache(cache_key)

                if cached_result:
                    st.markdown(cached_result, unsafe_allow_html=True)
                else:
                    # API-Sports မှ Data ဆွဲထုတ်ခြင်း
                    real_data = get_api_sports_stats(h_team, a_team, today_mm.isoformat())
                    if real_data:
                        h_id, a_id = real_data['h_id'], real_data['a_id']
                        injury_list = [f"{i['player']['name']} ({i['player']['reason']})" for i in real_data.get('injuries', [])]
                        
                        # Ratings logic
                        h_top, a_top = [], []
                        if real_data.get('h_ratings'):
                            for p in real_data['h_ratings'][0].get('players', []):
                                r = p['statistics'][0]['games'].get('rating')
                                if r and float(r) > 7.0: h_top.append(f"{p['player']['name']} ({r})")
                        if real_data.get('a_ratings'):
                            for p in real_data['a_ratings'][0].get('players', []):
                                r = p['statistics'][0]['games'].get('rating')
                                if r and float(r) > 7.0: a_top.append(f"{p['player']['name']} ({r})")

                        # Next Match Schedule
                        h_n, a_n = (real_data['h_schedule'][0] if real_data['h_schedule'] else None), (real_data['a_schedule'][0] if real_data['a_schedule'] else None)
                        h_next = f"vs {h_n['teams']['away']['name'] if h_n['teams']['home']['id']==h_id else h_n['teams']['home']['name']}" if h_n else "N/A"
                        a_next = f"vs {a_n['teams']['away']['name'] if a_n['teams']['home']['id']==a_id else a_n['teams']['home']['name']}" if a_n else "N/A"

                        stats_context = f"""
                        [SOURCE: API-SPORTS VERIFIED DATA]
                        - Match: {h_team} vs {a_team}
                        - Tournament: {real_data['league_name']}
                        - STANDINGS: {real_data['standings']}
                        - INJURIES: {', '.join(injury_list) if injury_list else 'None'}
                        - TOP PLAYERS: {h_team}: {', '.join(h_top[:3])} | {a_team}: {', '.join(a_top[:3])}
                        - NEXT MATCH: {h_team}: {h_next} | {a_team}: {a_next}
                        """

                        prompt = f"""
                        SYSTEM: You are a professional 2026 football tactical analyst.
                        Analyze using ONLY verified [SOURCE] data. 
                        Target Language: Burmese (Unicode).
                        
                        {stats_context}

                        OUTPUT FORMAT:
                        # သုံးသပ်ချက်
                        **{h_team} ခြေစွမ်းနှင့် ရပ်တည်မှု** (၅ ကြောင်း)
                        **{a_team} ခြေစွမ်းနှင့် ရပ်တည်မှု** (၅ ကြောင်း)
                        **ပွဲစဉ်ဦးစားပေးမှုနှင့် Squad Rotation** (လာမည့်ပွဲများအပေါ်မူတည်၍ ၅ ကြောင်း)
                        **နည်းဗျူဟာပိုင်းဆိုင်ရာ ခွဲခြမ်းစိတ်ဖြာမှု** (၅ ကြောင်း)

                        ### **Summarize Table**
                        | Category | Prediction |
                        | :--- | :--- |
                        | Winner Team | [Team Name] |
                        | Correct Score | [Score] |
                        | Goal under/over | [U/O] |
                        | BTTS | [Yes/No] |

                        # **🏆 အကျိုးအကြောင်းခိုင်လုံဆုံးရွေးချယ်မှု: [Result]**
                        Reasoning: (Domestic League Ranking နှင့် Schedule ကို ကိုးကား၍ ၆ ကြောင်း တိကျစွာဖြေဆိုပါ)
                        """
                        # Gemini Model ခေါ်ယူခြင်း (gemini-flash-latest)
                        response_text = get_gemini_response_rotated(prompt)
                        final_output = f'<div style="background:#0c0c0c; padding:20px; border-radius:15px; border:1px solid #FFD700; color:white;">{response_text}</div>'
                        
                        # Cache သိမ်းဆည်းခြင်း
                        set_disk_cache(cache_key, final_output)
                        st.markdown(final_output, unsafe_allow_html=True)
                    else:
                        st.error("Real-time data fetch failed. Check your API-Sports Key.")
        else:
            st.error(f"⚠️ {d[lang].get('no_match', 'No match found in current list.')}")
    else:
        st.warning("Please select valid teams from the Match Table first!")
        
