import os
import glob
import shutil
import asyncio
import re
import logging
import io
from unidecode import unidecode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
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

# --- Estados para ConversationHandler ---
WAITING_CLIENT_ID, WAITING_CLIENT_SECRET = range(2)

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

# --- 🤖 HANDLERS DE TELEGRAM ---
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ALLOWED_USER_ID: return
    log_file = "bot.log"
    if os.path.exists(log_file):
        await update.message.reply_document(document=open(log_file, 'rb'), filename="bot.log", caption="📜 Logs del servidor")
    else:
        await update.message.reply_text("❌ No hay archivo de logs aún.")

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ALLOWED_USER_ID: return
    status_msg = await update.message.reply_text("⏳ Iniciando escaneo profundo de la red...")
    progress_task = asyncio.create_task(animated_progress(status_msg, 'search', "Leyendo metadatos en red"))
    try:
        manifest = await asyncio.to_thread(generate_manifest)
        global local_fingerprints, local_metadata
        local_fingerprints, local_metadata = load_manifest()
        progress_task.cancel()
        try: await progress_task
        except asyncio.CancelledError: pass
        await status_msg.edit_text(f"✅ *Inventario Actualizado*\n\n🎵 {len(manifest)} canciones registradas.\n⚡ El bot ahora iniciará en milisegundos.", parse_mode='Markdown')
    except Exception as e:
        progress_task.cancel()
        await status_msg.edit_text(f"❌ Error escaneando: {e}")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ALLOWED_USER_ID: return
    text = update.message.text.strip()
    logger.info(f"📨 Mensaje recibido: {text[:100]}...")

    if context.user_data.get('downloading'):
        await update.message.reply_text("⏳ Estoy ocupado con otra descarga. Espera a que termine.")
        return

    # Detectar si es link de Spotify pero no hay credenciales configuradas
    if 'spotify.com' in text and not sp_client:
        await update.message.reply_text(
            "⚠️ *Spotify no configurado*\n\n"
            "Has enviado un link de Spotify pero no tienes las credenciales API configuradas.\n\n"
            "Puedes:\n"
            "1️⃣ Configurar Spotify ahora con /setspotify\n"
            "2️⃣ Copiar el nombre del track y buscarlo manualmente en Tidal\n\n"
            "El bot funcionará solo con Tidal hasta que configures Spotify.",
            parse_mode='Markdown'
        )
        return

    if 'spotify.com' not in text and 'tidal.com' not in text: return
    status_msg = await update.message.reply_text("⏳ Analizando enlace...")

    try:
        is_playlist = 'playlist' in text
        if not is_playlist:
            sp_match = re.search(r'spotify\.com/(?:intl-[a-z]+/)?track/([a-zA-Z0-9]+)', text)
            td_match = re.search(r'tidal\.com/(?:browse/)?track/(\d+)', text)
            artist, title, isrc, duration, album = "", "", None, None, None
            
            if sp_match and sp_client:
                sp_track = sp_client.track(sp_match.group(1))
                artist = sp_track['artists'][0]['name']
                title = sp_track['name']
                isrc = sp_track.get('external_ids', {}).get('isrc')
                duration = sp_track.get('duration_ms', 0) // 1000
                album = sp_track.get('album', {}).get('name')
                await status_msg.edit_text(f"🟢 Spotify: {artist} - {title}")
            elif td_match:
                t_track = tidal_session.track(int(td_match.group(1)))
                artist = t_track.artist.name
                title = t_track.name
                isrc = getattr(t_track, 'isrc', None)
                duration = t_track.duration
                album = t_track.album.name if hasattr(t_track, 'album') else None
                await status_msg.edit_text(f"🌊 Tidal: {artist} - {title}")
            else:
                await status_msg.edit_text("❌ Link no soportado.")
                return

            # CAPA 1: Coincidencia Exacta
            track_fps = generate_fingerprints(isrc, artist, title)
            if track_fps and track_fps.intersection(local_fingerprints):
                local_file = find_local_file_by_title(title)
                if local_file:
                    await status_msg.edit_text(f"✅ *Ya está en tu biblioteca*\n📤 Enviando desde caché...", parse_mode='Markdown')
                    result = await send_audio_with_retry(context.bot, update.effective_chat.id, local_file, artist, title, album, duration)
                    if result == "too_large":
                        await status_msg.edit_text(f"⚠️ *Pesa más de 50MB*\n📂 `{os.path.basename(local_file)}`", parse_mode='Markdown')
                    elif result:
                        try: await status_msg.delete()
                        except: pass
                    return
            
            # CAPA 2: Motor de Rescate
            if is_fuzzy_match(artist, title, local_metadata):
                local_file = find_local_file_by_title(title)
                if local_file:
                    await status_msg.edit_text(f"✅ *Ya está en tu biblioteca*\n📤 Enviando desde caché...", parse_mode='Markdown')
                    result = await send_audio_with_retry(context.bot, update.effective_chat.id, local_file, artist, title, album, duration)
                    if result == "too_large":
                        await status_msg.edit_text(f"⚠️ *Pesa más de 50MB*\n📂 `{os.path.basename(local_file)}`", parse_mode='Markdown')
                    elif result:
                        try: await status_msg.delete()
                        except: pass
                    return

            await status_msg.edit_text("🔍 Buscando en Tidal...")
            tidal_id = find_track_on_tidal(tidal_session, artist, title, isrc)
            if not tidal_id:
                await status_msg.edit_text(f"❌ No se encontró *{title}* en Tidal.", parse_mode='Markdown')
                return
            
            context.user_data['pending_track'] = {'tidal_id': tidal_id, 'artist': artist, 'title': title, 'album': album, 'duration': duration}
            report = f"🎵 *{artist} - {title}*\n💿 {album or 'Single'}\n\n⚠️ *No está en tu biblioteca local*"
            keyboard = [
                [InlineKeyboardButton("✅ Descargar (FLAC Lossless)", callback_data='track_yes')],
                [InlineKeyboardButton("❌ Cancelar", callback_data='track_no')]
            ]
            await status_msg.edit_text(report, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

        else:
            await status_msg.edit_text("📚 Leyendo playlist y comparando huellas...")
            tracks, platform = [], ""
            if 'spotify.com' in text:
                tracks = get_spotify_playlist(sp_client, text)
                platform = "Spotify"
            elif 'tidal.com' in text:
                tracks = get_tidal_playlist_tracks(tidal_session, text)
                platform = "Tidal"
                
            if not tracks:
                await status_msg.edit_text("❌ No se pudo leer la playlist.")
                return
            
            missing = []
            for t in tracks:
                # CAPA 1: Exacta
                track_fps = generate_fingerprints(t.get('isrc'), t.get('artist'), t.get('title'))
                if track_fps.intersection(local_fingerprints):
                    continue
                # CAPA 2: Rescate
                if is_fuzzy_match(t.get('artist'), t.get('title'), local_metadata):
                    continue
                missing.append(t)
                    
            msg = f"📊 *Playlist de {platform}*\n\n🎵 Total: {len(tracks)} canciones\n✅ Ya tienes: {len(tracks) - len(missing)}\n⚠️ *Faltan: {len(missing)}*"
            if not missing:
                await status_msg.edit_text(msg + "\n\n🎉 ¡Perfectamente sincronizada!", parse_mode='Markdown')
                return
                
            context.user_data['pending'] = missing
            keyboard = [
                [InlineKeyboardButton(f"✅ Descargar {len(missing)} faltantes", callback_data='dl_yes')],
                [InlineKeyboardButton("🔍 Ver lista de faltantes", callback_data='show_missing')],
                [InlineKeyboardButton("❌ Cancelar", callback_data='dl_no')]
            ]
            await status_msg.edit_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error:\n`{str(e)}`", parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if context.user_data.get('downloading'):
        await query.answer("⏳ Ya estoy procesando una descarga, ten paciencia 🦊", show_alert=True)
        return
        
    await query.answer()
    context.user_data['downloading'] = True

    try:
        if query.data == 'show_missing':
            missing = context.user_data.get('pending', [])
            if not missing:
                await query.answer("No hay canciones faltantes.", show_alert=True)
                return
                
            await query.answer("Generando reporte...")
            
            text_lines = [f"🎵 *Canciones Faltantes ({len(missing)})*\n"]
            for i, t in enumerate(missing, 1):
                text_lines.append(f"*{i}.* {t.get('artist', 'Desconocido')} - {t.get('title', 'Desconocido')}")
                
            full_text = "\n".join(text_lines)
            
            if len(full_text) < 4000:
                await context.bot.send_message(
                    chat_id=query.message.chat_id, 
                    text=full_text, 
                    parse_mode='Markdown'
                )
            else:
                file_content = "\n".join([f"{i}. {t.get('artist', 'Desconocido')} - {t.get('title', 'Desconocido')}" for i, t in enumerate(missing, 1)])
                bio = io.BytesIO(file_content.encode('utf-8'))
                bio.name = 'canciones_faltantes.txt'
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=bio,
                    caption=f"📜 Son {len(missing)} canciones. Te las dejo en un archivo de texto."
                )
            
            context.user_data['downloading'] = False 
            return

        if query.data == 'track_no':
            await query.edit_message_text("❌ Descarga cancelada.")
            context.user_data.pop('pending_track', None)
            return
        
        if query.data == 'track_yes':
            track = context.user_data.get('pending_track')
            if not track: return
            
            progress_task = asyncio.create_task(animated_progress(query.message, 'download', f"Descargando *{track['title']}*"))
            try:
                final_path = await asyncio.to_thread(process_and_move_track, track['tidal_id'])
            finally:
                progress_task.cancel()
                try: await progress_task
                except asyncio.CancelledError: pass
            
            if not final_path:
                await query.edit_message_text("❌ No se pudo descargar esta pista.")
                context.user_data.pop('pending_track', None)
                return
                
            progress_task2 = asyncio.create_task(animated_progress(query.message, 'upload', "Subiendo a Telegram"))
            try:
                result = await send_audio_with_retry(context.bot, query.message.chat_id, final_path, track['artist'], track['title'], track['album'], track['duration'])
            finally:
                progress_task2.cancel()
                try: await progress_task2
                except asyncio.CancelledError: pass
            
            if result == "too_large":
                await query.edit_message_text(f"✅ Descargada, pero pesa >50MB.\n📂 `{os.path.basename(final_path)}`", parse_mode='Markdown')
            elif result:
                try: await query.message.delete()
                except: pass
            
            context.user_data.pop('pending_track', None)
            return

        if query.data == 'dl_no':
            await query.edit_message_text("❌ Cancelado.")
            context.user_data.pop('pending', None)
            return
            
        if query.data == 'dl_yes':
            missing = context.user_data.get('pending', [])
            if not missing: return
            
            total = len(missing)
            success, fail = 0, 0
            failed_tracks = []
            
            for i, t in enumerate(missing, 1):
                track_info = f"{t.get('artist')} - {t.get('title')}"
                progress_task = asyncio.create_task(animated_progress(query.message, 'download', f"Descargando {i}/{total}: *{t.get('title')}*"))
                
                try:
                    logger.info(f"🔍 [{i}/{total}] Buscando en Tidal: {track_info}")
                    tidal_id = find_track_on_tidal(tidal_session, t.get('artist'), t.get('title'), t.get('isrc'))
                    
                    if tidal_id:
                        logger.info(f"✅ [{i}/{total}] Encontrada en Tidal: ID={tidal_id}")
                        if await asyncio.to_thread(process_and_move_track, tidal_id):
                            success += 1
                        else:
                            fail += 1
                            failed_tracks.append({'track': track_info, 'error': 'Fallo al procesar/mover'})
                    else:
                        logger.error(f"❌ [{i}/{total}] NO encontrada en Tidal: {track_info}")
                        fail += 1
                        failed_tracks.append({'track': track_info, 'error': 'No existe en Tidal'})
                except Exception as e:
                    logger.error(f"❌ [{i}/{total}] Excepción: {e}", exc_info=True)
                    fail += 1
                    failed_tracks.append({'track': track_info, 'error': str(e)})
                finally:
                    progress_task.cancel()
                    try: await progress_task
                    except asyncio.CancelledError: pass
                        
            final_msg = f"✅ *Sincronización Completa*\n📥 Descargadas: {success}\n❌ Fallidas: {fail}\n\n"
            if failed_tracks:
                final_msg += "*Detalles de fallos:*\n"
                for ft in failed_tracks[:5]:
                    final_msg += f"• {ft['track']}\n  → {ft['error']}\n"
                if len(failed_tracks) > 5:
                    final_msg += f"\n_Y {len(failed_tracks) - 5} más... Usa /logs para ver todos_\n"
                    
            await context.bot.send_message(chat_id=query.message.chat_id, text=final_msg, parse_mode='Markdown')
            context.user_data.pop('pending', None)
            
    except Exception as e:
        logger.error(f"❌ Error en button_handler: {e}", exc_info=True)
        await query.edit_message_text("❌ Error inesperado. Usa /logs para ver qué pasó.")
    finally:
        context.user_data['downloading'] = False

def main():
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0, write_timeout=60.0, pool_timeout=30.0)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("🟢 Servidor Sincronizador de Foxy (v9.0 - Armored & Diagnostic) iniciado.")
    app.run_polling()

if __name__ == '__main__':
    main()