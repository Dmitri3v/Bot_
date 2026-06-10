import unicodedata
import re
from unidecode import unidecode

def clean_text(text: str) -> str:
    """Limpia, normaliza y estandariza cualquier texto para comparación."""
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', str(text))
    text = text.strip().lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def generate_fingerprints(isrc: str, artist: str, title: str) -> set:
    """Genera un conjunto de huellas digitales para maximizar las coincidencias."""
    fps = set()
    
    if isrc:
        fps.add(f"isrc:{isrc.strip().upper()}")
        
    clean_artist = clean_text(artist)
    clean_title = clean_text(title)
    
    if clean_artist and clean_title:
        fps.add(f"{clean_artist}|{clean_title}")
        fps.add(f"{clean_title}|{clean_artist}") 
        
        # 🚨 BLINDAJE: Artista Principal (Resuelve "OSTY, Klavdia" vs "OSTY")
        if ',' in clean_artist:
            main_artist = clean_artist.split(',')[0].strip()
            fps.add(f"{main_artist}|{clean_title}")
            fps.add(f"{clean_title}|{main_artist}")
            
        tr_artist = clean_text(unidecode(artist))
        tr_title = clean_text(unidecode(title))
        
        if tr_artist != clean_artist or tr_title != clean_title:
            fps.add(f"{tr_artist}|{tr_title}")
            fps.add(f"{tr_title}|{tr_artist}")
            if ',' in tr_artist:
                main_tr_artist = tr_artist.split(',')[0].strip()
                fps.add(f"{main_tr_artist}|{tr_title}")
                fps.add(f"{tr_title}|{main_tr_artist}")
                
    if clean_title:
        fps.add(f"title:{clean_title}")
        fps.add(f"title:{clean_text(unidecode(title))}")

    return fps