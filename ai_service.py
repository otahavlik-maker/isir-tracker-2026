import os
import google.generativeai as genai
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

def get_api_key():
    key = os.getenv("GOOGLE_API_KEY")
    if key: return key
    try:
        if "GOOGLE_API_KEY" in st.secrets: return st.secrets["GOOGLE_API_KEY"]
    except: pass
    return None

api_key = get_api_key()
if api_key: genai.configure(api_key=api_key)

def analyze_document(file_path, lang="cs"):
    if not api_key: return "Chyba: API klíč nenalezen."
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        uploaded_file = genai.upload_file(path=file_path)
        prompt = "Stručná rešerše: Předmět dražby, Cena, Datum, Rizika. V bodech česky." if lang == "cs" else "Deep analysis: Item, Price, Date, Risks. English."
        response = model.generate_content([uploaded_file, prompt])
        genai.delete_file(uploaded_file.name)
        return response.text
    except Exception as e:
        return f"AI Error: {str(e)}"