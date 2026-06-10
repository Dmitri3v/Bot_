import os
import glob
import shutil
import asyncio
import re
import logging
import io
from unidecode import unidecode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes, ConversationHandler
from telegram.request import HTTPXRequest

from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_ID, MUSIC_FOLDER, TIDDL_DIR
from core.scanner import load_manifest, generate_manifest, MANIFEST_FILE
from core.spotify_client import get_spotify_client, get_playlist_tracks as get_spotify_playlist
from core.tidal_client import get_tidal_session, find_track_on_tidal
from core.downloader import download_with_tiddl
from core.metadata_enrichment import enrich_metadata
from utils.matcher import generate_fingerprints, clean_text
from utils.helpers import sanitize_filename
from core.spotify_credentials import (
    load_spotify_credentials, 
    save_spotify_credentials, 
    delete_spotify_credentials,
    is_spotify_configured
)

# --- 📜 SISTEMA DE LOGS ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# --- 🧠 INICIALIZACIÓN GLOBAL ---
logger.info("🔑 Inicializando clientes y escaneando biblioteca...")

# Spotify es OPCIONAL - puede ser None
sp_client = get_spotify_client()
spotify_status = "✅ Configurado" if sp_client else "❌ No configurado (usando solo Tidal)"
logger.info(f"🎵 Estado de Spotify: {spotify_status}")

tidal_session = get_tidal_session()
local_fingerprints, local_metadata = load_manifest()
logger.info(f"✅ Sistema listo. {len(local_fingerprints)} huellas en biblioteca local.")

# --- Estados para ConversationHandler ---
WAITING_CLIENT_ID, WAITING_CLIENT_SECRET = range(2)

# --- 🛠️ FUNCIONES AUXILIARES ---
def get_tidal_playlist_tracks(session, url):
    match = re.search(r'tidal.com/(?:browse/)?playlist/([a-zA-Z0-9-]+)', url)
    if not match: return None
    pl = session.playlist(match.group(1))
    tracks = []
    for t in pl.tracks():
        tracks.append({
            'isrc': getattr(t, 'isrc', None),
            'artist': t.artist.name,
            'title': t.name,
            'duration': t.duration,
            'album': t.album.name if hasattr(t, 'album') else None
        })
    return tracks

async def send_audio_with_retry(bot, chat_id, file_path, artist, title, album=None, duration=None, max_retries=3):
    filename = os.path.basename(file_path)
    logger.info(f"📤 Intentando enviar audio: {filename} ({artist} - {title})")
    for attempt in range(max_retries):
        try:
            with open(file_path, 'rb') as audio:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=audio,
                    title=title,
                    performer=artist,
                    duration=int(duration) if duration else None,
                    caption=f"🎧 {artist} - {title}" + (f"\n💿 {album}" if album else ""),
                    parse_mode='Markdown'
                )
            logger.info(f"✅ Audio enviado exitosamente: {filename}")
            return True
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"❌ Error en intento {attempt + 1}/{max_retries}: {e}")
            if "request entity too large" in error_str or "too large" in error_str:
                logger.warning(f"⚠️ Archivo muy grande para Telegram: {filename}")
                return "too_large"
            if "audio" in error_str or "wrong file type" in error_str:
                logger.warning(f"⚠️ Formato no soportado como audio, intentando como documento")
                try:
                    with open(file_path, 'rb') as doc:
                        await bot.send_document(chat_id=chat_id, document=doc, filename=filename)
                    logger.info(f"✅ Enviado como documento: {filename}")
                    return True
                except Exception as doc_e:
                    logger.error(f"❌ También falló como documento: {doc_e}")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Reintentando en 5 segundos...")
                await asyncio.sleep(5)
    logger.error(f"❌ Fallaron todos los intentos de envío para: {filename}")
    return False

def clear_tiddl_dir():
    files = glob.glob(os.path.join(TIDDL_DIR, "**", "*.*"), recursive=True)
    for f in files:
        if f.lower().endswith(('.flac', '.m4a', '.mp3', '.jpg', '.png')):
            try: os.remove(f)
            except: pass

async def animated_progress(message_obj, phase, base_text):
    spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    dots = ['', '.', '..', '...']
    phase_emoji = {'search': '🔍', 'tidal': '🌊', 'download': '💾', 'enrich': '💎', 'upload': '📤', 'done': '✅'}.get(phase, '⚙️')
    i = 0
    try:
        while True:
            spinner = spinners[i % len(spinners)]
            dot = dots[i % len(dots)]
            text = f"{phase_emoji} {base_text}{dot}\n`{spinner}`"
            try: await message_obj.edit_text(text, parse_mode='Markdown')
            except Exception: pass
            await asyncio.sleep(1.5)
            i += 1
    except asyncio.CancelledError:
        pass

def process_and_move_track(tidal_id):
    global local_fingerprints, local_metadata
    clear_tiddl_dir()
    tidal_url = f"https://tidal.com/track/{tidal_id}"
    if not download_with_tiddl(tidal_url): return None
        
    files = glob.glob(os.path.join(TIDDL_DIR, "**", "*.*"), recursive=True)
    audio_files = [f for f in files if f.lower().endswith(('.flac', '.m4a'))]
    if not audio_files:
        logger.error("❌ tiddl descargó pero no hay archivos de audio en la carpeta temporal")
        return None
        
    newest_file = max(audio_files, key=os.path.getctime)
    try:
        t_track = tidal_session.track(tidal_id)
        enrich_metadata(newest_file, t_track)
    except Exception as e:
        logger.warning(f"⚠️ No se pudieron enriquecer metadatos: {e}")

    dest = os.path.join(MUSIC_FOLDER, os.path.basename(newest_file))
    try:
        if os.path.exists(dest): os.remove(dest)
        shutil.move(newest_file, dest)
        logger.info(f"📂 Movido a biblioteca: {os.path.basename(dest)}")
        local_fingerprints, local_metadata = load_manifest()
        return dest
    except Exception as e:
        logger.error(f"❌ Error moviendo archivo: {e}")
        return newest_file

def find_local_file_by_title(title):
    safe_title = sanitize_filename(title)
    pattern = os.path.join(MUSIC_FOLDER, f"{safe_title}.*")
    matches = glob.glob(pattern)
    if matches:
        logger.info(f"🔍 Archivo local encontrado: {os.path.basename(matches[0])}")
        return matches[0]
    return None

def is_fuzzy_match(sp_artist, sp_title, local_metadata):
    """Motor de Rescate: Compara palabras clave ignorando puntuación y feats."""
    sp_text_orig = clean_text(f"{sp_artist} {sp_title}")
    sp_text_trans = clean_text(unidecode(f"{sp_artist} {sp_title}"))
    
    sp_tokens_orig = set(sp_text_orig.split())
    sp_tokens_trans = set(sp_text_trans.split())
    
    stopwords = {'remix', 'vip', 'feat', 'live', 'acoustic', 'original', 'mix', 'version', 'edit', 'the', 'a', 'and', 'of', 'pt', 'ii', 'iii', 'part', 'vol'}
    
    sp_core_orig = sp_tokens_orig - stopwords
    sp_core_trans = sp_tokens_trans - stopwords
    
    if not sp_core_orig: sp_core_orig = sp_tokens_orig
    if not sp_core_trans: sp_core_trans = sp_tokens_trans
        
    for item in local_metadata:
        local_text_orig = clean_text(f"{item.get('artist', '')} {item.get('title', '')}")
        local_text_trans = clean_text(unidecode(f"{item.get('artist', '')} {item.get('title', '')}"))
        
        local_tokens_orig = set(local_text_orig.split())
        local_tokens_trans = set(local_text_trans.split())
        
        matches_orig = sp_core_orig.intersection(local_tokens_orig)
        matches_trans = sp_core_trans.intersection(local_tokens_trans)
        
        threshold_orig = max(2, len(sp_core_orig) * 0.60)
        threshold_trans = max(2, len(sp_core_trans) * 0.60)
        
        if len(matches_orig) >= threshold_orig or len(matches_trans) >= threshold_trans:
            sp_title_tokens = set(clean_text(sp_title).split()) - stopwords
            local_title_tokens = set(clean_text(item.get('title', '')).split()) - stopwords
            if sp_title_tokens.intersection(local_title_tokens):
                return True
                
    return False
