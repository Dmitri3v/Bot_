# core/spotify_client.py
import re
import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, BASE_DIR
import os

logger = logging.getLogger(__name__)

def get_spotify_client():
    cache_path = os.path.join(BASE_DIR, ".spotify_cache")
    
    auth_manager = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri="https://example.com/callback",
        scope="playlist-read-private playlist-read-collaborative user-library-read",
        open_browser=True,
        cache_path=cache_path
    )
    
    sp = spotipy.Spotify(auth_manager=auth_manager)
    # Forzar autenticación si no hay caché
    auth_manager.get_access_token(as_dict=False)
    return sp

def get_playlist_tracks(client, url):
    match = re.search(r'spotify\.com/(?:intl-[a-z]+/)?playlist/([a-zA-Z0-9]+)', url)
    if not match: return None
        
    playlist_id = match.group(1)
    logger.info(f"🎯 ID de Playlist detectado: {playlist_id}")
    
    tracks = []
    results = client.playlist_tracks(playlist_id)
    page = 1
    
    while results:
        items = results.get('items', [])
        logger.info(f"📦 Procesando página {page} con {len(items)} items...")
        
        for i, item in enumerate(items):
            # 🚨 RAYOS X EXTREMOS: Inspeccionar solo el primer item de la primera página
            if i == 0 and page == 1:
                logger.info(f"🔍 Claves del item: {list(item.keys())}")
                t_raw = item.get('track')
                if t_raw:
                    logger.info(f"🔍 Claves de 'track': {list(t_raw.keys())}")
                    logger.info(f"🔍 Nombre en track: {t_raw.get('name')}")
                else:
                    logger.warning(f"⚠️ 'track' es None. Claves del item: {list(item.keys())}")
            
            t = item.get('track') or item.get('item')
            if not t:
                continue 
                
            try:
                artist_name = t['artists'][0]['name'] if t.get('artists') else "Unknown Artist"
                track_name = t.get('name', "Unknown Title")
                
                tracks.append({
                    'isrc': t.get('external_ids', {}).get('isrc'),
                    'artist': artist_name,
                    'title': track_name
                })
            except Exception as e:
                logger.warning(f"⚠️ Error extrayendo: {e}")
                
        if results.get('next'):
            page += 1
            results = client.next(results)
        else:
            break
            
    logger.info(f"✅ Extracción finalizada. Total de pistas recolectadas: {len(tracks)}")
    return tracks