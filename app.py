import streamlit as st
import isir_service
import ai_service
import os
import pandas as pd
import base64
import unicodedata
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIG ---
st.set_page_config(page_title="AI ISIR Tracker Pro", layout="centered")

# --- POMOCNÁ FUNKCE PRO PDF (Odstranění diakritiky pro stabilitu) ---
def clean_text(text):
    """Odstraní háčky a čárky, aby PDF nespadlo na Unicode chybě."""
    if not text: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')

# --- STYLY (Viditelné karty i v Light modu) ---
st.markdown("""
    <style>
    .fixed-footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #343a40; border-top: 1px solid #dee2e6;
        color: white; text-align: center; font-size: 14px; padding: 12px; z-index: 1000;
    }
    .main .block-container { padding-bottom: 100px; }
    .auction-card {
        border-radius: 10px; padding: 15px; 
        background-color: #f0f2f6; /* Světle šedá pro viditelnost */
        color: #1f1f1f;
        border-left: 5px solid #ff4b4b; margin-bottom: 15px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    </style>
    <div class="fixed-footer">
        © 2026 <b>AI ISIR Tracker</b> | Kontakt: otahavlik@gmail.com
    </div>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'watchlist' not in st.session_state: st.session_state.watchlist = {}
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_auction' not in st.session_state: st.session_state.selected_auction = None

# --- SIDEBAR (Stabilní nastavení) ---
with st.sidebar:
    st.header("Nastavení / Settings")
    lang_choice = st.selectbox("Jazyk / Language", ["Čeština", "English"])
    lang = "cs" if lang_choice == "Čeština" else "en"
    
    st.divider()
    st.header("📌 Watchlist")
    if st.session_state.watchlist:
        # PDF Report Button
        if st.button("📥 Export Report (PDF)", use_container_width=True):
            try:
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, "ISIR Tracker - Report", ln=True, align='C')
                for d_id, item in st.session_state.watchlist.items():
                    pdf.set_font("Arial", 'B', 11)
                    pdf.cell(0, 10, f"Spis: {clean_text(item['name'])}", ln=True)
                    pdf.set_font("Arial", '', 9)
                    pdf.multi_cell(0, 5, f"Udalost: {clean_text(item['event'])}")
                    if 'ai_summary' in item:
                        pdf.multi_cell(0, 5, f"AI: {clean_text(item['ai_summary'])}")
                    pdf.ln(5); pdf.cell(0, 0, "", "T"); pdf.ln(5)
                
                pdf_output = pdf.output(dest='S').encode('latin-1', errors='replace')
                st.download_button("Klikněte pro stažení PDF", data=pdf_output, file_name="isir_report.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Chyba PDF: {e}")

        st.divider()
        for doc_id, item in list(st.session_state.watchlist.items()):
            c1, c2 = st.columns([4, 1])
            with c1:
                if st.button(f"📍 {item['name']}", key=f"sw_{doc_id}", use_container_width=True):
                    st.session_state.selected_auction = item
            with c2:
                if st.button("❌", key=f"del_{doc_id}"):
                    del st.session_state.watchlist[doc_id]; st.rerun()
    else:
        st.caption("Seznam je prázdný.")

# --- TRANSLATIONS ---
t = {
    "title": "⚖️ AI ISIR Tracker Pro",
    "scan_btn": "🚀 SPUSTIT SKEN",
    "ic_head": "🔍 Lustrace IČO",
    "preview": "👁️ NÁHLED",
    "ai_btn": "🤖 AI ANALÝZA",
    "watch_btn": "⭐ ULOŽIT",
} if lang == "cs" else {
    "title": "⚖️ AI ISIR Tracker Pro",
    "scan_btn": "🚀 RUN SCAN",
    "ic_head": "🔍 IČO Lookup",
    "preview": "👁️ PREVIEW",
    "ai_btn": "🤖 AI ANALYSIS",
    "watch_btn": "⭐ SAVE",
}

# --- MAIN RENDERER ---
def render_item(item, key_p):
    with st.container():
        st.markdown(f"""<div class="auction-card">
            <b>{item['name']}</b> | {item['date'].strftime('%d.%m. %H:%M')}<br>
            <small>{item['event'][:130]}...</small>
        </div>""", unsafe_allow_html=True)
        
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1:
            if st.button(t["preview"], key=f"p_{key_p}_{item['doc_id']}", use_container_width=True):
                st.session_state[f"v_{item['doc_id']}"] = not st.session_state.get(f"v_{item['doc_id']}", False)
        with c2:
            if st.button(t["ai_btn"], key=f"a_{key_p}_{item['doc_id']}", use_container_width=True):
                st.session_state[f"run_{item['doc_id']}"] = True
        with c3:
            if st.button(t["watch_btn"], key=f"w_{key_p}_{item['doc_id']}", use_container_width=True):
                st.session_state.watchlist[item['doc_id']] = item; st.toast("Uloženo!")
        with c4:
            if item.get('pdf_url'): st.link_button("📄 PDF", item['pdf_url'], use_container_width=True)

        if st.session_state.get(f"v_{item['doc_id']}", False):
            tmp = f"pre_{item['doc_id']}.pdf"
            if isir_service.download_pdf(item['pdf_url'], tmp):
                with open(tmp, "rb") as f: b64 = base64.b64encode(f.read()).decode('utf-8')
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="700"></iframe>', unsafe_allow_html=True)
                os.remove(tmp)

        if st.session_state.get(f"run_{item['doc_id']}", False):
            if 'ai_summary' in item: st.info(item['ai_summary'])
            else:
                with st.spinner("AI..."):
                    tmp = f"ai_{item['doc_id']}.pdf"
                    if isir_service.download_pdf(item['pdf_url'], tmp):
                        res = ai_service.analyze_document(tmp, lang)
                        item['ai_summary'] = res; st.info(res); os.remove(tmp)

# --- APP FLOW ---
st.title(t["title"])
if st.session_state.selected_auction:
    with st.container(border=True):
        st.subheader("⭐ Detail sledované položky")
        render_item(st.session_state.selected_auction, "det")
        if st.button("Zavřít detail ✖️"): st.session_state.selected_auction = None; st.rerun()

st.divider()

# Skenování
col1, col2 = st.columns([2, 1])
with col1:
    period = st.selectbox("Rozsah:", ["Dnes", "Tento týden", "Tento měsíc", "Vlastní"], label_visibility="collapsed")
    s_date = datetime.now().replace(hour=0, minute=0, second=0)
    if period == "Tento týden": s_date -= timedelta(days=7)
    elif period == "Tento měsíc": s_date -= timedelta(days=30)
    elif period == "Vlastní":
        dr = st.date_input("Kalendář", [datetime.now() - timedelta(days=7), datetime.now()])
        if len(dr) == 2: s_date = datetime.combine(dr[0], datetime.min.time())
with col2:
    if st.button(t["scan_btn"], use_container_width=True, type="primary"):
        with st.spinner("Hledám..."):
            data, _, err = isir_service.fetch_auctions_by_date(s_date)
            if err: st.error(err)
            else: st.session_state.scan_results = data

if st.session_state.scan_results:
    st.markdown(f"### 📋 Výsledky: {len(st.session_state.scan_results)}")
    for item in st.session_state.scan_results: render_item(item, "list")

st.divider()
st.subheader(t["ic_head"])
i1, i2 = st.columns([3, 1])
with i1: ic_v = st.text_input("IČO", placeholder="24282925", label_visibility="collapsed")
with i2:
    if st.button("Lustrovat", use_container_width=True):
        res, err = isir_service.search_by_ic(ic_v)
        if err: st.error(err)
        elif res: st.success(f"Nalezen: {res[0].nazevOsoby}")