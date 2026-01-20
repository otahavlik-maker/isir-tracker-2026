import zeep
import requests
from requests import Session
from zeep.transports import Transport
import urllib3
import re
from datetime import datetime, timedelta

# Disable SSL warnings for secure communication
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# OFFICIAL ENDPOINTS
WSDL_PUBLIC = "https://isir.justice.cz:8443/isir_public_ws/IsirWsPublicService?wsdl"
WSDL_CUZK = "https://isir.justice.cz:8443/isir_cuzk_ws/IsirWsCuzkService?wsdl"

def find_start_id_for_date(target_date):
    """Traces back the sequence to find starting ID for specific date."""
    session = Session()
    session.verify = False
    transport = Transport(session=session, timeout=30)
    try:
        client = zeep.Client(wsdl=WSDL_PUBLIC, transport=transport)
        last_id_resp = client.service.getIsirWsPublicPodnetPosledniId()
        raw_id = last_id_resp.cisloPosledniId
        current_id = int(raw_id[0] if isinstance(raw_id, list) else raw_id)
        
        step = 100000 
        found_id = current_id
        while found_id > step:
            resp = client.service.getIsirWsPublicPodnetId(idPodnetu=found_id - step)
            if not resp or not hasattr(resp, 'data') or not resp.data: break
            first_date = resp.data[0].datumZverejneniUdalosti.replace(tzinfo=None)
            if first_date <= target_date:
                for item in resp.data:
                    if item.datumZverejneniUdalosti.replace(tzinfo=None) >= target_date:
                        return item.id, current_id
                break
            found_id -= step
        return current_id - 10000, current_id
    except Exception:
        raise ConnectionError("Server ISIR (503) je dočasně mimo provoz.")

def fetch_auctions_by_date(start_date, progress_callback=None):
    """Paging through the registry to find all auctions in given timeframe."""
    session = Session()
    session.verify = False
    transport = Transport(session=session, timeout=30)
    try:
        start_id, last_id = find_start_id_for_date(start_date)
        client = zeep.Client(wsdl=WSDL_PUBLIC, transport=transport)
        results = []
        current_batch_id = start_id
        batch_count = 0
        
        while current_batch_id < last_id and batch_count < 100:
            batch_count += 1
            if progress_callback: progress_callback(batch_count, 100)
            response = client.service.getIsirWsPublicPodnetId(idPodnetu=current_batch_id)
            if not response or not hasattr(response, 'data') or not response.data: break
            
            for item in response.data:
                desc = getattr(item, 'popisUdalosti', '') or ''
                if any(kw in desc.lower() for kw in ["dražba", "dražební"]):
                    # Fixed document URL logic
                    original_url = getattr(item, 'dokumentUrl', '') or ''
                    doc_id_match = re.search(r'idDokument=(\d+)', original_url)
                    public_url = f"https://isir.justice.cz:8443/isir_public_ws/doc/Document?idDokument={doc_id_match.group(1)}" if doc_id_match else None
                    results.append({
                        "type": "DRAŽBA",
                        "name": getattr(item, 'spisovaZnacka', 'N/A'),
                        "event": desc,
                        "date": item.datumZverejneniUdalosti,
                        "doc_id": getattr(item, 'id', None),
                        "pdf_url": public_url
                    })
            current_batch_id = response.data[-1].id + 1
        return results, last_id, None
    except Exception as e:
        return None, None, str(e)

def search_by_ic(ic):
    """Manual lookup on port 8443."""
    session = Session()
    session.verify = False
    transport = Transport(session=session, timeout=30)
    try:
        client = zeep.Client(wsdl=WSDL_CUZK, transport=transport)
        response = client.service.getIsirWsCuzkData(ic=str(ic))
        return (response.isirWsCuzkData, None) if response and hasattr(response, 'isirWsCuzkData') else ([], None)
    except Exception as e:
        return None, str(e)

def download_pdf(url, local_filename):
    if not url: return False
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, headers=headers, stream=True, verify=False, timeout=30) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except Exception: return False