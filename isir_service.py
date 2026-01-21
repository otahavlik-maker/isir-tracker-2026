import zeep
import requests
from requests import Session
from zeep.transports import Transport
import urllib3
import re
import time
from datetime import datetime, timedelta

# Vypnutí SSL varování pro port 8443
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WSDL_PUBLIC = "https://isir.justice.cz:8443/isir_public_ws/IsirWsPublicService?wsdl"
WSDL_CUZK = "https://isir.justice.cz:8443/isir_cuzk_ws/IsirWsCuzkService?wsdl"

session = Session()
session.verify = False
transport = Transport(session=session, timeout=30)

def call_with_retry(func, *args, retries=5, delay=2, **kwargs):
    """Opakuje volání při chybě serveru justice.cz."""
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i == retries - 1: raise e
            time.sleep(delay)
    return None

def find_start_id_for_date(target_date):
    """Najde počáteční ID v rejstříku bez přeskakování záznamů."""
    try:
        client = zeep.Client(wsdl=WSDL_PUBLIC, transport=transport)
        last_id_resp = call_with_retry(client.service.getIsirWsPublicPodnetPosledniId)
        current_id = int(last_id_resp.cisloPosledniId[0] if isinstance(last_id_resp.cisloPosledniId, list) else last_id_resp.cisloPosledniId)
        
        step = 25000 
        check_id = current_id
        while check_id > step:
            resp = call_with_retry(client.service.getIsirWsPublicPodnetId, idPodnetu=check_id - step)
            if not resp or not hasattr(resp, 'data') or not resp.data: break
            if resp.data[0].datumZverejneniUdalosti.replace(tzinfo=None) <= target_date:
                return (check_id - step), current_id
            check_id -= step
        return current_id - 50000, current_id
    except: return 0, 0

def fetch_auctions_by_date(start_date, end_date, progress_callback=None):
    """Skenuje historii rejstříku přesně podle technické dokumentace."""
    try:
        start_id, last_id = find_start_id_for_date(start_date)
        if start_id == 0: return None, None, "Server ISIR neodpovídá."
        
        client = zeep.Client(wsdl=WSDL_PUBLIC, transport=transport)
        results = []
        current_query_id = start_id
        processed_count = 0
        total_range = last_id - start_id
        
        while current_query_id < last_id:
            resp = call_with_retry(client.service.getIsirWsPublicPodnetId, idPodnetu=current_query_id)
            if not resp or not hasattr(resp, 'data') or not resp.data: break
            
            for item in resp.data:
                processed_count += 1
                item_date = item.datumZverejneniUdalosti.replace(tzinfo=None)
                
                # Okamžité zastavení, pokud jsme mimo zvolený rozsah
                if item_date > end_date:
                    return results, last_id, None
                    
                desc = getattr(item, 'popisUdalosti', '') or ''
                if "dražební vyhláška" in desc.lower() or "drazebni vyhlaska" in desc.lower():
                    if item_date >= start_date:
                        url = getattr(item, 'dokumentUrl', '') or ''
                        doc_match = re.search(r'idDokument=(\d+)', url)
                        p_url = f"https://isir.justice.cz:8443/isir_public_ws/doc/Document?idDokument={doc_match.group(1)}" if doc_match else None
                        
                        results.append({
                            "name": getattr(item, 'spisovaZnacka', 'N/A'),
                            "event": desc,
                            "date": item_date,
                            "doc_id": item.id,
                            "pdf_url": p_url
                        })
            
            current_query_id = resp.data[-1].id
            if progress_callback:
                prog = min(processed_count / (total_range if total_range > 0 else 1), 0.99)
                progress_callback(prog, f"Skenuji do: {resp.data[-1].datumZverejneniUdalosti.strftime('%d.%m. %H:%M')}")
        
        return results, last_id, None
    except Exception as e: return None, None, str(e)

def get_subject_info(ins_znacka):
    """Lustrace subjektu s robustním rozkladem značky."""
    try:
        # Regex zvládne "INS 123/2024" i "101 INS 123/2024"
        match = re.search(r"(?P<druhVec>[A-Z]+)\s+(?P<bcVec>\d+)/(?P<rocnik>\d+)", ins_znacka.strip().upper())
        if not match:
            return None, "Neplatný formát. Zadejte např. INS 12925/2022"
            
        client = zeep.Client(wsdl=WSDL_CUZK, transport=transport)
        res = call_with_retry(client.service.getIsirWsCuzkData, 
                             druhVec=match.group("druhVec"),
                             bcVec=int(match.group("bcVec")),
                             rocnik=int(match.group("rocnik")))
                             
        if res and hasattr(res, 'isirWsCuzkData') and res.isirWsCuzkData:
            s = res.isirWsCuzkData[0]
            return {
                "jmeno": getattr(s, 'nazevOsoby', 'N/A'),
                "ic": getattr(s, 'ic', 'N/A'),
                "rc": getattr(s, 'rodneCislo', 'N/A') or getattr(s, 'datumNarozeni', 'N/A'),
                "adresa": f"{getattr(s, 'mesto', '')}, {getattr(s, 'ulice', '')}".strip(", "),
                "stav": getattr(s, 'druhStavKonkursu', 'N/A'),
                "name": getattr(s, 'spisovaZnacka', 'N/A'),
                "doc_id": "m_" + str(int(time.time()))
            }, None
        return None, "Subjekt pod touto značkou nebyl nalezen."
    except Exception as e: return None, str(e)

def download_pdf(url, local_filename):
    if not url: return False
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, headers=headers, stream=True, verify=False, timeout=20) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except: return False