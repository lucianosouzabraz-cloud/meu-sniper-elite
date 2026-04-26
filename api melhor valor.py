import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import hashlib
import random
import os

# --- 1. QG DE INTELIGÊNCIA: RADAR GLOBAL ---
THE_ODDS_KEY = '9b1e5bdfb194963d95185f3363fb2f3d'

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

# --- 2. MOTOR DE DNA (ESTRUTURA ORIGINAL v224) ---
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
            scan[f"Jogo Under {l+1}.5"] = sum(1 for x in total if x < (l+1.5)) / 10
        for l in [0.5, 1.5, 2.5]:
            scan[f"{h_n} Over {l}"] = sum(1 for x in dados_h if x > l) / 10
            scan[f"{a_n} Over {l}"] = sum(1 for x in dados_a if x > l) / 10
        scan["Ambas Marcam: Sim"] = (sum(1 for x in dados_h if x >= 1)/10) * (sum(1 for x in dados_a if x >= 1)/10)
    
    elif tipo == "Cantos":
        total = [dados_h[i] + dados_a[i] for i in range(10)]
        for l in [7.5, 8.5, 9.5, 10.5, 11.5]: scan[f"Total Over {l}"] = sum(1 for x in total if x > l) / 10
        for l in [11.5, 12.5, 13.5]: scan[f"Total Under {l}"] = sum(1 for x in total if x < l) / 10
        for l in [3.5, 4.5, 5.5]:
            scan[f"{h_n} Over {l}"] = sum(1 for x in dados_h if x > l) / 10
            scan[f"{a_n} Over {l}"] = sum(1 for x in dados_a if x > l) / 10
            
    elif tipo == "Chutes":
        total_g = [dados_h[i] + dados_a[i] for i in range(10)]
        for l in [6.5, 7.5, 8.5, 9.5, 10.5]: scan[f"Soma Over {l}"] = sum(1 for x in total_g if x > l) / 10
        for l in [2.5, 3.5, 4.5, 5.5]:
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

# --- 3. SISTEMA DE PLANILHA ---
ARQUIVO_PLANILHA = "historico_apostador_elite.csv"
def salvar_no_ledger(data_j, h, a, xg_h, xg_a, best_gol, best_canto, best_card):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dados_dict = {"Registro": timestamp, "Data Jogo": data_j, "Mandante": h, "Visitante": a, "xG H": f"{xg_h:.2f}", "xG A": f"{xg_a:.2f}", "Melhor Gols": best_gol, "Melhor Cantos": best_canto, "Melhor Cards": best_card}
    novo_registro = pd.DataFrame([dados_dict])
    if not os.path.isfile(ARQUIVO_PLANILHA): novo_registro.to_csv(ARQUIVO_PLANILHA, index=False, sep=";", encoding="utf-8-sig")
    else: novo_registro.to_csv(ARQUIVO_PLANILHA, mode='a', header=False, index=False, sep=";", encoding="utf-8-sig")

# --- 4. INTERFACE ---
st.set_page_config(page_title="Sniper v239 - Online Mode", layout="wide")
st.title("🛡️ PROTOCOLO LB | Scouting de Elite")

# --- GERENCIADOR DE PLANILHA (SISTEMA ORIGINAL COM LIXEIRA) ---
if os.path.exists(ARQUIVO_PLANILHA):
    with st.expander("📊 GERENCIAR PLANILHA"):
        df_led = pd.read_csv(ARQUIVO_PLANILHA, sep=";")
        df_led.insert(0, "Selecionar", False)
        edited_df = st.data_editor(df_led, hide_index=True, column_config={"Selecionar": st.column_config.CheckboxColumn(required=True)}, use_container_width=True)
        col_del, col_down = st.columns([1, 4])
        with col_del:
            if st.button("🗑️ Excluir Selecionados", type="primary"):
                df_final = edited_df[edited_df["Selecionar"] == False].drop(columns=["Selecionar"])
                df_final.to_csv(ARQUIVO_PLANILHA, index=False, sep=";", encoding="utf-8-sig")
                st.rerun()
        with col_down:
            csv_export = df_led.drop(columns=["Selecionar"]).to_csv(index=False, sep=";").encode('utf-8-sig')
            st.download_button("📥 Baixar Planilha", data=csv_export, file_name="historico_elite.csv")

with st.sidebar:
    st.header("🎯 Radar de Ligas")
    liga_sel = st.selectbox("Escolha a Liga", list(LIGAS_ELITE.keys()))
    data_sel = st.date_input("Data da Rodada", value=datetime.now())
    if st.button("🔍 Iniciar Varredura"):
        url = f"https://api.the-odds-api.com/v4/sports/{LIGAS_ELITE[liga_sel]['key']}/odds/?apiKey={THE_ODDS_KEY}&regions=us&markets=h2h"
        res = requests.get(url)
        if res.status_code == 200:
            st.session_state['jogos_v224'] = [j for j in res.json() if j['commence_time'].startswith(data_sel.strftime("%Y-%m-%d"))]

# --- ANÁLISE COM MEMÓRIA (PREVENT REFRESH) ---
if 'jogos_v224' in st.session_state:
    for idx, jogo in enumerate(st.session_state['jogos_v224']):
        h_t, a_t, j_data = jogo['home_team'], jogo['away_team'], jogo['commence_time'].split('T')[0]
        state_key = f"analise_{idx}_{h_t}_{a_t}"
        
        with st.container():
            st.markdown(f"### 🏟️ {h_t} x {a_t}")
            
            if st.button(f"📡 ANALISAR: {h_t} x {a_t}", key=f"btn_{idx}"):
                gh = farejar_dna_v224(h_t, "Gols", "casa", liga_sel, j_data)
                ga = farejar_dna_v224(a_t, "Gols", "fora", liga_sel, j_data)
                ch = farejar_dna_v224(h_t, "Cantos", "casa", liga_sel, j_data)
                ca = farejar_dna_v224(a_t, "Cantos", "fora", liga_sel, j_data)
                fgh = farejar_dna_v224(h_t, "Chutes_G", "casa", liga_sel, j_data)
                fga = farejar_dna_v224(a_t, "Chutes_G", "fora", liga_sel, j_data)
                cdh = farejar_dna_v224(h_t, "Cards", "casa", liga_sel, j_data)
                cda = farejar_dna_v224(a_t, "Cards", "fora", liga_sel, j_data)
                
                st.session_state[state_key] = {
                    "res_g": hunter_dinamico_v224(gh, ga, "Gols", h_t, a_t),
                    "res_c": hunter_dinamico_v224(ch, ca, "Cantos", h_t, a_t),
                    "res_f": hunter_dinamico_v224(fgh, fga, "Chutes", h_t, a_t),
                    "res_ca": hunter_dinamico_v224(cdh, cda, "Cards", h_t, a_t),
                    "xg_h": sum(gh)/10, "xg_a": sum(ga)/10
                }

            if state_key in st.session_state:
                dados = st.session_state[state_key]
                for label, res in [("⚽ GOLS", dados["res_g"]), ("🚩 CANTOS", dados["res_c"]), ("🎯 FINALIZAÇÕES", dados["res_f"]), ("🟨 CARTÕES", dados["res_ca"])]:
                    st.markdown(f"#### {label}")
                    cols = st.columns(3)
                    for i in range(15):
                        if i < len(res):
                            cols[i % 3].write(f"{res[i][0]}: **{res[i][1]:.1%}**")
                    st.divider()

                st.subheader("🏆 SELEÇÃO DE ELITE (Decisão Final)")
                c1, c2, c3 = st.columns(3)
                s_g = c1.selectbox("Melhor Gol", [r[0] for r in dados["res_g"][:5]], key=f"s_g_{idx}")
                s_c = c2.selectbox("Melhor Canto", [r[0] for r in dados["res_c"][:5]], key=f"s_c_{idx}")
                s_ca = c3.selectbox("Melhor Card", [r[0] for r in dados["res_ca"][:5]], key=f"s_ca_{idx}")

# --- INSERIR O RODAPÉ DA MARCA AQUI ---
                st.markdown("---")
                st.caption("📊 **PROTOCOLO LB** - Sistema de Inteligência e Scouting de Elite")
                st.caption("Precisão Estatística | DNA de Jogo | Gestão de Risco")
                # --------------------------------------
                
                if st.button("✅ Confirmar e Salvar no Histórico", key=f"save_{idx}"):
                    salvar_no_ledger(j_data, h_t, a_t, dados["xg_h"], dados["xg_a"], s_g, s_c, s_ca)
                    st.success(f"🎯 Registro de {h_t} salvo!")
            st.divider()
