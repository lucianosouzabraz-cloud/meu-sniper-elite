# file: apifootball_odds_telegram_bot.py
# Requisitos: pip install requests python-telegram-bot==13.15

import requests, time, math, sqlite3, json, re
from collections import defaultdict, deque
from threading import Thread
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CallbackQueryHandler, Dispatcher, CommandHandler

# -------- CONFIG ----------
API_SPORTS_KEY = "ba538dc777efdb0d0376872f7c68bfb9"
API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_SPORTS_KEY}
POLL_INTERVAL_SECONDS = 8
EVENT_WINDOW_SECONDS = 300
TELEGRAM_TOKEN = "8386390740:AAF44llD3kbQYrt74Tgsys4BEXUpWrGG-IU"
TELEGRAM_CHAT_ID = "LaLigaaovivo"  # grupo ou usuário
BANKROLL = 1000.0

# DB
DB_FILE = "signals.db"

# -------- estado in-memory ----------
events_by_fixture = defaultdict(lambda: deque())
match_meta = {}  # fixture_id -> metadata

bot = Bot(token=TELEGRAM_TOKEN)

# -------- util ----------
def now_ts(): return int(time.time())
def ensure_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER,
        league TEXT,
        minute INTEGER,
        prob_2 REAL,
        prob_5 REAL,
        odds_used REAL,
        stake REAL,
        stake_fraction REAL,
        sent_ts INTEGER,
        user_action TEXT,
        action_user_id TEXT,
        action_ts INTEGER,
        raw_payload TEXT
    )
    """)
    conn.commit()
    conn.close()

# -------- API-Football helpers ----------
def fetch_live_fixtures():
    url = f"{API_BASE}/fixtures"
    params = {"live":"all"}
    r = requests.get(url, headers=HEADERS, params=params, timeout=8)
    r.raise_for_status()
    return r.json().get("response", [])

def fetch_fixture_events(fixture_id):
    url = f"{API_BASE}/fixtures/events"
    params = {"fixture": fixture_id}
    r = requests.get(url, headers=HEADERS, params=params, timeout=8)
    r.raise_for_status()
    return r.json().get("response", [])

def fetch_odds_for_fixture(fixture_id):
    url = f"{API_BASE}/odds"
    params = {"fixture": fixture_id}
    r = requests.get(url, headers=HEADERS, params=params, timeout=8)
    r.raise_for_status()
    return r.json().get("response", [])

# -------- features / simple model ----------
def compute_features_from_window(fixture_id):
    dq = events_by_fixture[fixture_id]
    minutes_window = max(1.0, EVENT_WINDOW_SECONDS / 60.0)
    corners = sum(1 for t,e in dq if e.get("type","").lower().find("corner")!=-1)
    shots = sum(1 for t,e in dq if any(x in e.get("type","").lower() for x in ("shot","on target","off target")))
    attacks = sum(1 for t,e in dq if "attack" in e.get("type","").lower() or "danger" in e.get("type","").lower())
    return {"corners": corners, "shots": shots, "attacks": attacks, "minutes_window": minutes_window}

def estimate_lambda(features, total_corners_so_far, minute_elapsed):
    minute_elapsed = max(1.0, minute_elapsed)
    base_rate = (total_corners_so_far / minute_elapsed) if total_corners_so_far else 0.02
    recent_score = features['shots'] * 0.7 + features['attacks'] * 0.5 + features['corners'] * 1.2
    alpha = 0.85; beta = 0.18
    lam = alpha * base_rate + beta * (recent_score / features['minutes_window'])
    return max(lam, 1e-6)

def prob_at_least_one(lam_per_minute, delta_minutes):
    return 1.0 - math.exp(-lam_per_minute * delta_minutes)

def kelly_fraction(p, odds, fraction=0.25):
    b = odds - 1.0
    q = 1.0 - p
    if b <= 0: return 0.0
    fstar = (b * p - q) / b
    return max(0.0, fraction * fstar)

# -------- odds parser (heuristic, robust) ----------
def find_best_corner_odd_from_odds_response(odds_response):
    """
    odds_response: list of bookmakers objects from API
    Strategy:
      - search all bookmakers -> markets -> outcomes for keywords
      - prioritize market names containing 'next' and 'corner' with numbers (2,5)
      - otherwise pick markets with 'corner' keyword
      - return (best_decimal_odd, market_name, bookmaker_name, outcome_name)
    """
    if not odds_response:
        return None

    # patterns
    next_time_pattern = re.compile(r"(next|in the next|during the next)\s*(\d+)", re.IGNORECASE)
    corner_pattern = re.compile(r"corner|corners", re.IGNORECASE)

    candidates = []
    # iterate bookies
    for b in odds_response:
        bookie = b.get("bookmaker") or b.get("bookmaker_name") or b.get("name") or b.get("bookmaker_name")
        markets = b.get("markets") or b.get("bets") or b.get("bookmakers") or b.get("bookmaker_markets") or b.get("markets", [])
        # Possible different shapes by plan—try common fields:
        if isinstance(markets, dict):
            # sometimes markets dict keyed; flatten
            markets = list(markets.values())
        for m in markets or []:
            m_name = m.get("key") or m.get("name") or m.get("market")
            if not m_name:
                # some providers nest "label" or "label" in different key
                m_name = m.get("label") or ""
            # detect outcomes
            outcomes = m.get("outcomes") or m.get("values") or m.get("selections") or m.get("bets") or []
            # try find time info:
            m_text = (m_name or "").lower()
            has_corner = bool(corner_pattern.search(m_text))
            next_match = next_time_pattern.search(m_text)
            for out in outcomes:
                # outcome may have 'name' and 'price' or 'odd' or 'price_decimal'
                out_name = out.get("name") or out.get("label") or out.get("title") or ""
                # try decimal price extraction
                price = out.get("price") or out.get("odd") or out.get("price_decimal") or out.get("odds")
                # normalize price to float if possible
                try:
                    price_val = float(price) if price is not None else None
                except:
                    price_val = None
                # prefer outcomes that represent "Yes"/">0" or 'Over 0.5' or 'Anytime' depending on text
                if price_val:
                    score = 0
                    if next_match:
                        # market explicitly mentions 'next N'
                        score += 30
                        # bonus if outcome name indicates Yes/Over/Any
                        if any(x in out_name.lower() for x in ("yes", "over", ">0", "any", "1+")):
                            score += 10
                    if has_corner:
                        score += 20
                        if any(x in out_name.lower() for x in ("yes", "over", ">0", "any", "1+")):
                            score += 8
                    # small bonus for lower price (implies probability) not necessary; we keep score only by match quality
                    # store candidate
                    candidates.append({
                        "score": score,
                        "price": price_val,
                        "market": m_name,
                        "bookmaker": bookie,
                        "outcome": out_name
                    })
    if not candidates:
        return None
    # pick best by score then by best price for our purpose (we want decent b)
    candidates.sort(key=lambda x: (x['score'], x['price']), reverse=True)
    best = candidates[0]
    return best

# -------- Telegram integration (inline buttons) ----------
def compose_signal_message(fixture_id, league, minute, p2, p5, odds_val, stake_amt, stake_frac, features):
    return (
        f"*SINAL ESCANTEIO* — {league}\n"
        f"Fixture ID: `{fixture_id}`  Min: {minute}\n"
        f"P(>=1 escanteio next 2min): *{p2:.1%}*\n"
        f"P(>=1 escanteio next 5min): *{p5:.1%}*\n"
        f"Odds (usadas): {odds_val}\n"
        f"Recomendado stake: *{stake_amt:.2f}* ({stake_frac:.3f} fração do bankroll)\n"
        f"Features (últ. {EVENT_WINDOW_SECONDS//60}min): corners={features['corners']}, shots={features['shots']}, attacks={features['attacks']}"
    )

def send_signal_with_buttons(fixture_id, league, minute, p2, p5, odds_val, stake_amt, stake_frac, features, raw_payload):
    text = compose_signal_message(fixture_id, league, minute, p2, p5, odds_val, stake_amt, stake_frac, features)
    keyboard = [
        [InlineKeyboardButton("✅ Aprovar (executar aposta)", callback_data=json.dumps({"act":"approve","fixture":fixture_id,"odds":odds_val,"stake":stake_amt})),
         InlineKeyboardButton("❌ Ignorar", callback_data=json.dumps({"act":"ignore","fixture":fixture_id}))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent = bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown", reply_markup=reply_markup)
    # persist initial signal (user_action NULL)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
      INSERT INTO signals (fixture_id, league, minute, prob_2, prob_5, odds_used, stake, stake_fraction, sent_ts, raw_payload)
      VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (fixture_id, league, minute, p2, p5, odds_val, stake_amt, stake_frac, now_ts(), json.dumps(raw_payload)))
    conn.commit()
    conn.close()

# Callback handler for inline buttons
def callback_query_handler(update: Update, context):
    query = update.callback_query
    data = json.loads(query.data)
    act = data.get("act")
    fixture = data.get("fixture")
    user_id = query.from_user.id
    ts = now_ts()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if act == "approve":
        odds_used = data.get("odds")
        stake = data.get("stake")
        # mark last inserted signal for this fixture as approved (simplest matching strategy)
        c.execute("""
           UPDATE signals SET user_action=?, action_user_id=?, action_ts=? WHERE fixture_id=? AND user_action IS NULL
           ORDER BY id DESC LIMIT 1
        """, ("approve", str(user_id), ts, fixture))
        # (Opcional) aqui você poderia chamar função para executar aposta via API da casa de apostas
        query.answer(text="Aposta aprovada (registrada).")
    else:
        c.execute("""
           UPDATE signals SET user_action=?, action_user_id=?, action_ts=? WHERE fixture_id=? AND user_action IS NULL
           ORDER BY id DESC LIMIT 1
        """, ("ignore", str(user_id), ts, fixture))
        query.answer(text="Sinal ignorado (registrado).")
    conn.commit()
    conn.close()

# -------- main processing per fixture ----------
def push_event(fixture_id, ev):
    dq = events_by_fixture[fixture_id]
    dq.append((now_ts(), ev))
    while dq and dq[0][0] < now_ts() - EVENT_WINDOW_SECONDS:
        dq.popleft()

def process_fixture(fixture):
    fixture_id = fixture["fixture"]["id"]
    league = fixture["league"]["name"]
    minute = fixture["fixture"].get("status", {}).get("elapsed") or 0
    match_meta[fixture_id] = {"minute": minute, "league": league, "fixture": fixture}

    # events
    try:
        evs = fetch_fixture_events(fixture_id)
    except Exception as e:
        print("Erro events:", e); evs = []
    for ev in evs:
        etype = ev.get("type") or ev.get("detail") or ev.get("event")
        raw_id = ev.get("id") or ev.get("event_id") or None
        normalized = {"type": etype or "", "team": ev.get("team",{}).get("name") if ev.get("team") else None, "minute": ev.get("time",{}).get("elapsed"), "raw": ev}
        if raw_id:
            normalized["event_id"] = raw_id
        push_event(fixture_id, normalized)

    features = compute_features_from_window(fixture_id)
    total_corners_so_far = 0
    # attempt to get total corners from fixture payload (may not exist)
    # some plans include 'statistics' or live summary — if not available leave 0
    try:
        if 'statistics' in fixture and isinstance(fixture['statistics'], list):
            # attempt to find corners stat
            for teamstat in fixture['statistics']:
                # provider dependent; skip — left as example
                pass
    except:
        pass

    lam = estimate_lambda(features, total_corners_so_far, minute)
    p2 = prob_at_least_one(lam, 2.0)
    p5 = prob_at_least_one(lam, 5.0)

    # fetch odds and pick best match for our market
    odds_resp = []
    try:
        odds_resp = fetch_odds_for_fixture(fixture_id)
    except Exception as e:
        print("Erro fetch odds:", e)
    best = find_best_corner_odd_from_odds_response(odds_resp)
    if best:
        odds_val = best['price']
    else:
        odds_val = 3.0  # fallback

    stake_frac = kelly_fraction(p2, odds_val, fraction=0.25)
    stake_amt = stake_frac * BANKROLL

    # simple signal criteria
    if p2 > 0.35 and stake_frac > 0.001:
        raw_payload = {"features": features, "odds_best": best}
        send_signal_with_buttons(fixture_id, league, minute, p2, p5, odds_val, stake_amt, stake_frac, features, raw_payload)
        print("SINAL enviado", fixture_id, p2, stake_amt)
    else:
        print("Sem sinal:", fixture_id, f"p2={p2:.2f}", f"stake_frac={stake_frac:.4f}")

# -------- polling loop ----------
def main_loop():
    ensure_db()
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CallbackQueryHandler(callback_query_handler))
    updater.start_polling()  # para receber callbacks inline
    print("Bot Telegram iniciado (polling).")

    while True:
        try:
            fixtures = fetch_live_fixtures()
            for f in fixtures:
                # opcional: filtrar só LaLiga por f['league']['id'] == 140
                process_fixture(f)
        except Exception as e:
            print("Erro no loop principal:", e)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main_loop()
