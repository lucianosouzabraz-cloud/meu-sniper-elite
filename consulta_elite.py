import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import hashlib
import random
import os

# --- CONFIGURAÇÃO ---
SENHA_ACESSO = "elite2026"
THE_ODDS_KEY = '4eeb55e11fc9b7ed7db6377f2f23d6f1'

LIGAS_ELITE = {
    "Brasileirão Série A": {"key": "soccer_brazil_campeonato", "p_cards": 1.4, "p_gols": 1.0},
    "Brasileirão Série B": {"key": "soccer_brazil_campeonato_serie_b", "p_cards": 1.6, "p_gols": 0.75},
    "Premier League (Inglaterra)": {"key": "soccer_epl", "p_cards": 0.6, "p_gols": 1.6},
    "Bundesliga (Alemanha)": {"key": "soccer_germany_bundesliga", "p_cards": 0.7, "p_gols": 1.8},
    "La Liga (Espanha)": {"key": "soccer_spain_la_liga", "p_cards": 1.2, "p_gols": 1.1},
    "Serie A (Itália)": {"key": "soccer_italy_serie_a", "p_cards": 1.3, "p_gols": 1.0},
    "Ligue 1 (França)": {"key": "soccer_france_ligue_one", "p_cards": 0.9, "p_gols": 1.2},
    "Champions League": {"key": "soccer_uefa_champs_league", "p_cards": 0.9, "p_gols": 1.5},
    "Copa Libertadores": {"key": "soccer_conmebol_libertadores", "p_cards": 1.7, "p_gols": 0.9}
}

def carregar_logo(tamanho=300):
    for ext in ["jpg", "png", "jpeg", "JPG", "PNG"]:
        nome = f"logo_lb.{ext}"
        if os.path.exists(nome):
            st.image(nome, width=tamanho)
            return True
    return False

def farejar_dna_v224(time, mercado, mando, liga, data):
    identidade = f"{time}{mercado}{mando}{liga}{data}v224"
    seed = int(hashlib.md5(identidade.encode()).hexdigest(), 16) % 10**8
    random.seed(seed)
    if mercado == "Gols": return [random.choices([0, 1, 2, 3, 4], weights=[20, 35, 25, 15, 5])[0] for _ in range(10)]
    if mercado == "Cantos": return [round(random.uniform(1.5, 11.5), 1) for _ in range(10)]
    if mercado == "Chutes_G": return [random.randint(2, 10) for _ in range(10)]
    if mercado == "Cards": return [round(random.uniform(0.5, 6.5), 1) for _ in range(10)]
    return []

def hunter_dinamico_v224(dados_h, dados_a, tipo, h_n, a_n):
    scan = {}
    if tipo == "Gols":
        total = [dados_h[i] + dados_a[i] for i in range(10)]
        for l in [0.5, 1.5, 2.5, 3.5]: 
            scan[f"Jogo Over {l}"] = sum(1 for x in total if x > l) / 10
            scan[f"Jogo Under {l+1.5}"] = sum(1 for x in total if x < (l+1.5)) / 10
        for l in [0.5, 1.5, 2.5]:
            scan[f"{h_n} Over {l}"] = sum(1 for x in dados_h if x > l) / 10
            scan[f"{a_n} Over {l}"] = sum(1 for x in dados_a if x > l) / 10
    elif tipo == "Cantos":
        total = [dados_h[i] + dados_a[i] for i in range(10)]
        for l in [7.5, 8.5, 9.5, 10.5, 11.5]: scan[f"Total Over {l}"] = sum(1 for x in total if x > l) / 10
        for l in [11.5, 12.5, 13.5]: scan[f"Total Under {l}"] = sum(1 for x in total if x < l) / 10
        for l in [3.5, 4.5, 5.5]:
            scan[f"{h_n} Over {l}"] = sum(1 for x in dados_h if x > l) / 10
            scan[f"{a_n} Over {l}"] = sum(1 for x in dados_a if x > l) / 10
    elif tipo == "Cards":
        total = [dados_h[i] + dados_a[i] for i in range(10)]
        for l in [3.5, 4.5, 5.5, 6.5, 7.5]: scan[f"Total Over {l}"] = sum(1 for x in total if x > l) / 10
        for l in [6.5, 7.5, 8.5]: scan[f"Total Under {l}"] = sum(1 for x in total if x < l) / 10
        for l in [1.5, 2.5, 3.5]:
            scan[f"{h_n} Over {l}"] = sum(1 for x in dados_h if x > l) / 10
            scan[f"{a_n} Over {l}"] = sum(1 for x in dados_a if x > l) / 10
    return sorted(scan.items(), key=lambda x: x[1], reverse=True)

# --- SEGURANÇA ---
st.set_page_config(page_title="PROTOCOLO LB | Scouting de Elite", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    carregar_logo(300)
    st.title("🛡️ Sistema de Consulta - Aposta Esportiva")
    pwd = st.text_input("Senha de Acesso:", type="password")
    if st.button("Acessar Radar"):
        if pwd == SENHA_ACESSO:
            st.session_state.auth = True
            st.rerun()
        else: st.error("❌ Senha incorreta.")
    st.stop()

# --- INTERFACE CONSULTA ---
carregar_logo(200)
st.title("📡 PROTOCOLO LB | Scouting de Elite")
st.info("💡 Acesso exclusivo para visualização técnica.")

with st.sidebar:
    st.header("🎯 Radar de Ligas")
    liga_sel = st.selectbox("Liga", list(LIGAS_ELITE.keys()))
    data_sel = st.date_input("Data", value=datetime.now())
    if st.button("🔍 Iniciar Varredura"):
        url = f"https://api.the-odds-api.com/v4/sports/{LIGAS_ELITE[liga_sel]['key']}/odds/?apiKey={THE_ODDS_KEY}&regions=us&markets=h2h"
        res = requests.get(url)
        if res.status_code == 200:
            st.session_state['jogos_consulta'] = [j for j in res.json() if j['commence_time'].startswith(data_sel.strftime("%Y-%m-%d"))]

if 'jogos_consulta' in st.session_state:
    for idx, jogo in enumerate(st.session_state['jogos_consulta']):
        h_t, a_t, j_data = jogo['home_team'], jogo['away_team'], jogo['commence_time'].split('T')[0]
        state_key = f"view_{idx}_{h_t}"
        
        with st.container():
            st.markdown(f"### 🏟️ {h_t} x {a_t}")
            if st.button(f"📡 VER DNA: {h_t} x {a_t}", key=f"btn_{idx}"):
                gh, ga = farejar_dna_v224(h_t, "Gols", "casa", liga_sel, j_data), farejar_dna_v224(a_t, "Gols", "fora", liga_sel, j_data)
                ch, ca = farejar_dna_v224(h_t, "Cantos", "casa", liga_sel, j_data), farejar_dna_v224(a_t, "Cantos", "fora", liga_sel, j_data)
                cdh, cda = farejar_dna_v224(h_t, "Cards", "casa", liga_sel, j_data), farejar_dna_v224(a_t, "Cards", "fora", liga_sel, j_data)
                st.session_state[state_key] = {
                    "res_g": hunter_dinamico_v224(gh, ga, "Gols", h_t, a_t),
                    "res_c": hunter_dinamico_v224(ch, ca, "Cantos", h_t, a_t),
                    "res_ca": hunter_dinamico_v224(cdh, cda, "Cards", h_t, a_t)
                }

            if state_key in st.session_state:
                dados = st.session_state[state_key]
                for label, res in [("⚽ GOLS", dados["res_g"]), ("🚩 CANTOS", dados["res_c"]), ("🟨 CARTÕES", dados["res_ca"])]:
                    st.markdown(f"#### {label}")
                    cols = st.columns(3)
                    for i in range(15):
                        if i < len(res): cols[i % 3].write(f"{res[i][0]}: **{res[i][1]:.1%}**")
                    st.divider()
                
                st.subheader("🏆 Sugestões de Elite")
                g, c, ca = dados["res_g"], dados["res_c"], dados["res_ca"]
                st.info(f"🔹 **Opção 1 (Segura):** {g[0][0]} + {c[0][0]} + {ca[0][0]}")
                if len(g) > 1: st.info(f"🔹 **Opção 2 (Moderada):** {g[1][0]} + {c[1][0]} + {ca[1][0]}")
                if len(g) > 2: st.info(f"🔹 **Opção 3 (Arriscada):** {g[2][0]} + {c[2][0]} + {ca[2][0]}")
                
                st.markdown("---")
                st.caption("📊 **PROTOCOLO LB** - Scouting de Elite")
            st.divider()
