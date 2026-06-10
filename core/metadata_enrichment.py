# core/metadata_enrichment.py
import os
import re
import logging
import requests
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger(__name__)

def is_lrc_format(text):
    """Verifica si el texto contiene marcas de tiempo de letras sincronizadas [mm:ss.xx]"""
    if not text: return False
    return bool(re.search(r'\[\d{2}:\d{2}\.\d{2,3}\]', text))

def fetch_synced_lyrics(artist, title, album, duration):
    """Consulta la API de LRCLIB para obtener letras sincronizadas si Tidal falla."""
    url = "https://lrclib.net/api/get"
    params = {
        "artist_name": artist,
        "track_name": title,
        "album_name": album,
        "duration": duration
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Prioriza la sincronizada, si no, devuelve la plana
            return data.get("syncedLyrics") or data.get("plainLyrics")
    except Exception as e:
        logger.debug(f"LRCLIB no encontró coincidencia o falló: {e}")
    return None

def enrich_metadata(filepath, t_track):
    """Verifica y rellena metadatos faltantes, priorizando letras sincronizadas (LRC)."""
    ext = os.path.splitext(filepath)[1].lower()
    logger.info(f"🔍 Verificando y enriqueciendo metadatos para: {os.path.basename(filepath)}")
    
    # 1. Recopilar datos de Tidal
    artist = t_track.artist.name
    title = t_track.name
    album = t_track.album.name if hasattr(t_track, 'album') else ""
    duration = t_track.duration
    
    album_artist = t_track.album.artist.name if hasattr(t_track.album, 'artist') else artist
    track_num = t_track.track_num
    disc_num = t_track.volume_num
    release_date = str(t_track.album.year) if hasattr(t_track.album, 'year') else None
    copyright_info = getattr(t_track, 'copyright', None)
    isrc = getattr(t_track, 'isrc', None)
    
    cover_url = None
    try:
        cover_url = t_track.album.image(1280)
    except: pass

    # 2. Obtener Letras (Tidal + Fallback a LRCLIB)
    lyrics_text = None
    try:
        lyrics_obj = t_track.lyrics()
        if lyrics_obj and lyrics_obj.text:
            lyrics_text = lyrics_obj.text
    except Exception: pass

    # Si Tidal no dio letras sincronizadas, preguntamos a LRCLIB
    if lyrics_text and not is_lrc_format(lyrics_text):
        logger.info(f"📡 Tidal dio texto plano. Buscando LRC sincronizado en LRCLIB...")
        synced = fetch_synced_lyrics(artist, title, album, duration)
        if synced and is_lrc_format(synced):
            lyrics_text = synced
            logger.info(f"✅ ¡Letras sincronizadas (LRC) encontradas en LRCLIB!")
    elif not lyrics_text:
        logger.info(f"📡 Tidal no tiene letras. Buscando en LRCLIB...")
        synced = fetch_synced_lyrics(artist, title, album, duration)
        if synced:
            lyrics_text = synced
            if is_lrc_format(synced):
                logger.info(f"✅ ¡Letras sincronizadas (LRC) encontradas en LRCLIB!")
            else:
                logger.info(f"✅ Letras de texto plano encontradas en LRCLIB.")

    # 3. Inyectar en el archivo
    try:
        if ext == '.flac':
            audio = FLAC(filepath)
            modified = False
            
            # 🎤 INCRUSTAR LETRAS (Sincronizadas y Planas)
            if lyrics_text:
                if is_lrc_format(lyrics_text):
                    audio['SYNCEDLYRICS'] = lyrics_text # Estándar para LRC en FLAC
                    audio['LYRICS'] = lyrics_text       # Fallback para reproductores viejos
                else:
                    audio['LYRICS'] = lyrics_text
                modified = True
                
            if cover_url and len(audio.pictures) == 0:
                img_data = requests.get(cover_url).content
                image = Picture()
                image.type = 3
                image.mime = 'image/jpeg'
                image.data = img_data
                audio.add_picture(image)
                modified = True
                logger.info(f"🖼️ Carátula 1280px incrustada")
                
            if 'albumartist' not in audio and album_artist: audio['albumartist'] = album_artist; modified = True
            if 'tracknumber' not in audio and track_num: audio['tracknumber'] = str(track_num); modified = True
            if 'discnumber' not in audio and disc_num: audio['discnumber'] = str(disc_num); modified = True
            if 'date' not in audio and release_date: audio['date'] = release_date; modified = True
            if 'copyright' not in audio and copyright_info: audio['copyright'] = copyright_info; modified = True
            if 'isrc' not in audio and isrc: audio['isrc'] = isrc; modified = True
            
            if modified:
                audio.save()
                logger.info(f"💾 Metadatos FLAC guardados")
                
        elif ext == '.m4a':
            audio = MP4(filepath)
            modified = False
            
            # 🎤 INCRUSTAR LETRAS EN M4A
            if lyrics_text:
                audio['\xa9lyr'] = lyrics_text # Los reproductores modernos leen LRC desde aquí
                modified = True
                
            if cover_url and 'covr' not in audio:
                img_data = requests.get(cover_url).content
                audio['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                modified = True
                logger.info(f"🖼️ Carátula incrustada")
                
            if 'aART' not in audio and album_artist: audio['aART'] = album_artist; modified = True
            if 'trkn' not in audio and track_num: audio['trkn'] = [(track_num, 0)]; modified = True
            if 'disk' not in audio and disc_num: audio['disk'] = [(disc_num, 0)]; modified = True
            if '\xa9day' not in audio and release_date: audio['\xa9day'] = release_date; modified = True
            if 'cprt' not in audio and copyright_info: audio['cprt'] = copyright_info; modified = True
            
            if modified:
                audio.save()
                logger.info(f"💾 Metadatos M4A guardados")
                
    except Exception as e:
        logger.error(f"❌ Error enriqueciendo metadatos: {e}", exc_info=True)