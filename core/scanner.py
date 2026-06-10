import os
import json
import logging
import concurrent.futures
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from utils.matcher import generate_fingerprints
from config import MUSIC_FOLDER, BASE_DIR

logger = logging.getLogger(__name__)
MANIFEST_FILE = os.path.join(BASE_DIR, "library_manifest.json")

def _extract_metadata(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(filename)[0]

    fallback_artist = "Unknown Artist"
    fallback_title = name_without_ext
    if " - " in name_without_ext:
        parts = name_without_ext.split(" - ", 1)
        fallback_artist = parts[0].strip()
        fallback_title = parts[1].strip()

    isrc = None
    artist = fallback_artist
    title = fallback_title

    try:
        if ext == '.flac':
            audio = FLAC(file_path)
            isrc = audio.get('isrc', [None])[0]
            artist = audio.get('artist', [None])[0] or fallback_artist
            title = audio.get('title', [None])[0] or fallback_title
        elif ext == '.m4a':
            audio = MP4(file_path)
            artist = audio.get('\xa9ART', [None])[0] or fallback_artist
            title = audio.get('\xa9nam', [None])[0] or fallback_title
        elif ext == '.mp3':
            audio = ID3(file_path)
            isrc = audio.get('TSRC', [None])[0] if audio.get('TSRC') else None
            artist = audio.get('TPE1', [None])[0] if audio.get('TPE1') else fallback_artist
            title = audio.get('TIT2', [None])[0] if audio.get('TIT2') else fallback_title
    except Exception as e:
        logger.debug(f"Error leyendo etiquetas de {filename}, usando nombre de archivo: {e}")

    fps = generate_fingerprints(isrc, artist, title)
    if fps:
        return {
            'fingerprints': list(fps),
            'artist': artist.strip(),
            'title': title.strip(),
            'file': filename
        }
    return None

def generate_manifest():
    logger.info(f"⏳ Iniciando escaneo profundo en {MUSIC_FOLDER}...")
    audio_extensions = {'.flac', '.m4a', '.mp3', '.ogg', '.opus', '.wav', '.alac', '.aiff'}
    audio_files = []

    for root, dirs, files in os.walk(MUSIC_FOLDER):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in audio_extensions:
                audio_files.append(os.path.join(root, file))
                
    logger.info(f"🔍 Se encontraron {len(audio_files)} archivos de audio en total. Extrayendo metadatos...")
    manifest = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(_extract_metadata, audio_files)
        for res in results:
            if res:
                manifest.append(res)
                    
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        
    logger.info(f"✅ Manifiesto guardado exitosamente: {len(manifest)} canciones registradas.")
    return manifest

def load_manifest():
    if not os.path.exists(MANIFEST_FILE):
        logger.warning("⚠️ No se encontró manifiesto previo. Generando uno nuevo...")
        manifest = generate_manifest()
    else:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    
    all_fps = set()
    clean_metadata = []
    
    for item in manifest:
        # 🧹 LIMPIADOR DE CLAVES AL VUELO (Inmunidad a espacios como "artist ")
        clean_item = {str(k).strip(): v for k, v in item.items()}
        clean_metadata.append(clean_item)
        
        fps_list = clean_item.get('fingerprints') or clean_item.get('fingerprint') or []
        if isinstance(fps_list, str):
            all_fps.add(fps_list.strip())
        elif isinstance(fps_list, list):
            all_fps.update([fp.strip() for fp in fps_list if fp])
            
    logger.info(f"⚡ Manifiesto cargado en RAM: {len(all_fps)} huellas únicas.")
    return all_fps, clean_metadata