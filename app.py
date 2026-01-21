import streamlit as st
import isir_service
import ai_service
import os
import base64
import unicodedata
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIG ---
st.set_page_config(page_title="AI ISIR Tracker Pro", layout="centered")

def clean_text(text):
    """Robustní vyčištění textu pro PDF (odstraňuje diakritiku a nahrazuje Unicode znaky)."""
    if not text: return ""
    # Mapa pro náhradu Unicode znaků, které Helvetica neumí
    mapping = {
        ord('–'): '-', ord('—'): '-', ord('“'): '"', ord('”'): '"',
        ord('‘'): "'", ord('’'): "'", ord('•'): '*', ord('…'): '...',
        ord('²'): '2', ord('³'): '3', ord(' '): ' ' # neodstranitelná mezera
    }
    text = str(text).translate(mapping)
    # Odstranění zbylé diakritiky
    return "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def get_pdf_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

# Session State Init
if 'lang' not in st.session_state: st.session_state.lang = "cs"
if 'watchlist' not in st.session_state: st.session_state.watchlist = {}
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_auction' not in st.session_state: st.session_state.selected_auction = None
if 'ins_manual_res' not in st.session_state: st.session_state.ins_manual_res = None

# --- DESIGN ---
st.markdown("""
    <style>
    .fixed-footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #212529; color: white; text-align: center; padding: 12px; z-index: 1000; font-size: 14px; }
    .main .block-container { padding-bottom: 120px; }
    .auction-card {
        border-radius: 8px; padding: 15px; background-color: #f8f9fa;
        border-left: 10px solid #dc3545; margin-bottom: 15px; color: #212529;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# --- SIDEBAR (WATCHLIST) ---
with st.sidebar:
    st.header("Nastavení")
    l_choice = st.selectbox("Language / Jazyk", ["Čeština", "English"], index=0 if st.session_state.lang == "cs" else 1)
    st.session_state.lang = "cs" if l_choice == "Čeština" else "en"
    lang = st.session_state.lang
    
    st.divider()
    st.header("📌 Watchlist")
    if st.session_state.watchlist:
        if st.button("📥 Export PDF Report", use_container_width=True, key="side_exp"):
            try:
                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                pdf.set_font("Helvetica", 'B', 16)
                pdf.cell(0, 10, "ISIR Tracker - Report Sledovanych Polozek", ln=True, align='C')
                pdf.ln(5)
                for d_id, item in st.session_state.watchlist.items():
                    pdf.set_font("Helvetica", 'B', 12)
                    pdf.set_fill_color(240, 240, 240)
                    pdf.cell(0, 10, f" Spis: {clean_text(item['name'])}", ln=True, fill=True)
                    pdf.set_font("Helvetica", '', 10)
                    pdf.multi_cell(0, 7, f"Akce: {clean_text(item.get('event', 'N/A'))}")
                    pdf.cell(0, 7, f"Zverejneno: {item['date'].strftime('%d.%m.%Y %H:%M') if 'date' in item else 'N/A'}", ln=True)
                    if 'ai_summary' in item:
                        pdf.set_font("Helvetica", 'I', 9)
                        pdf.multi_cell(0, 6, f"AI Analyza:\n{clean_text(item['ai_summary'])}")
                    pdf.ln(5); pdf.cell(0, 0, "", "T"); pdf.ln(5)
                
                pdf_data = pdf.output()
                st.download_button("Uložit report (PDF)", data=bytes(pdf_data), file_name="isir_report.pdf", mime="application/pdf", use_container_width=True)
            except Exception as e: st.error(f"Chyba PDF: {str(e)}")

        for doc_id, item in list(st.session_state.watchlist.items()):
            c1, c2 = st.columns([4, 1])
            with c1:
                if st.button(f"📍 {item['name']}", key=f"sw_{doc_id}", use_container_width=True):
                    st.session_state.selected_auction = item
            with c2:
                if st.button("❌", key=f"del_{doc_id}"):
                    del st.session_state.watchlist[doc_id]; st.rerun()
    else: st.caption("Watchlist je prázdný.")

# Překlady
t = {
    "title": "⚖️ AI ISIR Tracker Pro", "scan_btn": "🚀 SPUSTIT SKEN VYHLÁŠEK", "ins_head": "🔍 Detail INS (Vizitka subjektu)",
    "preview": "👁️ NÁHLED", "ai_btn": "🤖 AI ANALÝZA", "watch_btn": "⭐ ULOŽIT", "footer": "© 2026 AI ISIR Tracker"
} if lang == "cs" else {
    "title": "⚖️ AI ISIR Tracker Pro", "scan_btn": "🚀 RUN SEARCH", "ins_head": "🔍 INS Detail (Search Subject)",
    "preview": "👁️ PREVIEW", "ai_btn": "🤖 AI ANALYSIS", "watch_btn": "⭐ SAVE", "footer": "© 2026 AI ISIR Tracker"
}

# --- ITEM RENDERER ---
def render_item(item, prefix):
    with st.container():
        st.markdown(f"""<div class="auction-card">
            <h3 style='margin:0;'>⚖️ {item['name']}</h3>
            <p style='margin:0;'><b>Akce:</b> {item.get('event', 'N/A')}</p>
            <p style='margin:0; font-size:12px; color:#666;'><b>Zveřejněno:</b> {item['date'].strftime('%d.%m.%Y %H:%M') if 'date' in item else 'N/A'}</p>
        </div>""", unsafe_allow_html=True)
        
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
        with c1:
            if item.get('pdf_url'):
                if st.button(t["preview"], key=f"p_{prefix}_{item['doc_id']}", use_container_width=True):
                    st.session_state[f"v_{item['doc_id']}"] = not st.session_state.get(f"v_{item['doc_id']}", False)
            else: st.button("Bez PDF", disabled=True, use_container_width=True, key=f"np_{prefix}_{item['doc_id']}")
        with c2:
            if item.get('pdf_url'):
                if st.button(t["ai_btn"], key=f"a_{prefix}_{item['doc_id']}", use_container_width=True):
                    st.session_state[f"ai_{item['doc_id']}"] = True
            else: st.button("Bez AI", disabled=True, use_container_width=True, key=f"na_{prefix}_{item['doc_id']}")
        with c3:
            if st.button(t["watch_btn"], key=f"w_{prefix}_{item['doc_id']}", use_container_width=True):
                st.session_state.watchlist[item['doc_id']] = item
                st.toast("Uloženo!"); st.rerun()
        with c4:
            if item.get('pdf_url'): 
                st.link_button("↗️ Otevřít", item['pdf_url'], use_container_width=True)

        if st.session_state.get(f"v_{item['doc_id']}", False):
            tmp_path = f"t_view_{item['doc_id']}.pdf"
            if isir_service.download_pdf(item['pdf_url'], tmp_path):
                b64 = get_pdf_base64(tmp_path)
                st.markdown(f'<embed src="data:application/pdf;base64,{b64}" width="100%" height="750" type="application/pdf">', unsafe_allow_html=True)

        if st.session_state.get(f"ai_{item['doc_id']}", False):
            if 'ai_summary' in item: 
                st.info(item['ai_summary'])
                # EXPORT AI ANALÝZY
                ac1, ac2 = st.columns(2)
                with ac1:
                    st.download_button("📥 Stáhnout TXT", data=clean_text(item['ai_summary']), file_name=f"ai_{item['name']}.txt", use_container_width=True, key=f"dl_txt_{item['doc_id']}")
                with ac2:
                    try:
                        apdf = FPDF(); apdf.add_page(); apdf.set_font("Helvetica", 'B', 14)
                        apdf.cell(0, 10, f"AI Analyza - {clean_text(item['name'])}", ln=True)
                        apdf.set_font("Helvetica", '', 10); apdf.multi_cell(0, 7, clean_text(item['ai_summary']))
                        st.download_button("📥 Stáhnout PDF", data=bytes(apdf.output()), file_name=f"ai_{item['name']}.pdf", use_container_width=True, key=f"dl_pdf_{item['doc_id']}")
                    except Exception as e: st.error(f"Chyba PDF exportu AI: {e}")
            else:
                with st.spinner("AI provádí rešerši..."):
                    tmp_ai = f"t_ai_{item['doc_id']}.pdf"
                    if isir_service.download_pdf(item['pdf_url'], tmp_ai):
                        res = ai_service.analyze_document(tmp_ai, lang)
                        item['ai_summary'] = res; st.rerun()

# --- MAIN ---
st.title(t["title"])
if st.session_state.selected_auction:
    with st.container(border=True):
        st.subheader("⭐ Detail sledované položky")
        render_item(st.session_state.selected_auction, "det")
        if st.button("Zavřít detail ✖️", key="close_det"): st.session_state.selected_auction = None; st.rerun()

st.divider()
col1, col2 = st.columns([2, 1])
with col1:
    period = st.selectbox("Období:", ["Dnes", "Posledních 7 dní", "Posledních 30 dní", "Vlastní rozsah"], label_visibility="collapsed", key="per_sel")
    s_date = datetime.now().replace(hour=0, minute=0, second=0)
    e_date = datetime.now()
    if period == "Posledních 7 dní": s_date -= timedelta(days=7)
    elif period == "Posledních 30 dní": s_date -= timedelta(days=30)
    elif period == "Vlastní rozsah":
        dr = st.date_input("Od - Do", [datetime.now() - timedelta(days=2), datetime.now()], key="custom_cal")
        if len(dr) == 2:
            s_date = datetime.combine(dr[0], datetime.min.time())
            e_date = datetime.combine(dr[1], datetime.max.time())

with col2:
    if st.button(t["scan_btn"], use_container_width=True, type="primary", key="scan"):
        pb = st.progress(0, text="Navazuji spojení...")
        data, _, err = isir_service.fetch_auctions_by_date(s_date, e_date, lambda p, t: pb.progress(p, text=t))
        if err: st.error(err)
        else: st.session_state.scan_results = data
        pb.empty()

if st.session_state.scan_results:
    st.markdown(f"### 📋 Nalezeno: {len(st.session_state.scan_results)}")
    for item in st.session_state.scan_results: render_item(item, "list")

st.divider()
st.subheader(t["ins_head"])
i1, i2 = st.columns([3, 1])
with i1: ins_v = st.text_input("Zadejte značku (např. INS 12925/2022)", label_visibility="collapsed", key="ins_manual_in")
with i2:
    if st.button("Hledat", use_container_width=True, key="ins_manual_btn"):
        res, err = isir_service.get_subject_info(ins_v)
        if err: st.error(err)
        else: st.session_state.ins_manual_res = res

if st.session_state.ins_manual_res:
    res = st.session_state.ins_manual_res
    with st.container(border=True):
        st.markdown(f"### 👤 {res['jmeno']}\n**Spis:** {res['name']} | **Stav:** :red[{res['stav']}]\n**IČ / RC:** {res['ic']} / {res['rc']} | **Bydliště:** {res['adresa']}")
        if st.button("Zavřít vizitku ✖️", key="close_viz"): st.session_state.ins_manual_res = None; st.rerun()

st.markdown(f'<div class="fixed-footer">{t["footer"]} | otahavlik@gmail.com</div>', unsafe_allow_html=True)