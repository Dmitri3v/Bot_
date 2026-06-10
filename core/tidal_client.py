import logging
import json
import os
import tidalapi
from config import SESSION_FILE

logger = logging.getLogger(__name__)

def get_tidal_session():
    """Carga la sesión guardada o inicia un nuevo login OAuth."""
    session = tidalapi.Session()
    
    # 1. Intentar cargar sesión existente desde el JSON
    if SESSION_FILE and os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # tidalapi requiere estos 3 parámetros para restaurar la sesión
            if session.load_session(
                session_data.get('session_id'), 
                session_data.get('country_code'), 
                session_data.get('user_id')
            ):
                logger.info("✅ Sesión de Tidal cargada desde caché.")
                return session
            else:
                logger.warning("⚠️ La sesión guardada expiró o es inválida. Generando una nueva...")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo cargar la sesión guardada: {e}")

    # 2. Iniciar nuevo login OAuth (Imprimirá la URL en la terminal)
    logger.info("⏳ Iniciando nuevo login en Tidal...")
    session.login_oauth_simple()
    
    # 3. Guardar la nueva sesión manualmente en un archivo JSON
    if SESSION_FILE and session.check_login():
        try:
            session_data = {
                'session_id': session.session_id,
                'country_code': session.country_code,
                'user_id': session.user.id if hasattr(session, 'user') and session.user else None
            }
            with open(SESSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=4)
            logger.info("✅ Nueva sesión de Tidal guardada exitosamente.")
        except Exception as e:
            logger.error(f"❌ Error al guardar la sesión: {e}")
            
    return session

def find_track_on_tidal(session, artist, title, isrc=None):
    """Busca en Tidal usando lógica nativa (Sin dependencias externas)."""
    try:
        # 🚨 ESPACIO AÑADIDO ENTRE ARTISTA Y TÍTULO
        query = f"{artist} {title}"
        results = session.search(query, models=[tidalapi.Track])
        tracks = results.get('tracks', [])
        
        if not tracks:
            return None

        artist_lower = artist.lower()
        title_lower = title.lower()

        # 1. Búsqueda de ISRC (El estándar de oro)
        if isrc:
            for track in tracks:
                if hasattr(track, 'isrc') and track.isrc == isrc:
                    return track.id

        # 2. Búsqueda por Coincidencia de Cadenas (Nativa)
        for track in tracks:
            track_artists = [a.name.lower() for a in track.artists]
            track_title = track.name.lower()
            
            artist_match = any(artist_lower in ta or ta in artist_lower for ta in track_artists)
            title_match = title_lower in track_title or track_title in title_lower
            
            if artist_match and title_match:
                return track.id

        # 3. Fallback: Si el título es muy similar, devolvemos el primero
        if tracks and title_lower in tracks[0].name.lower():
            return tracks[0].id

        return None

    except Exception as e:
        logger.error(f"❌ Error en búsqueda de Tidal: {e}", exc_info=True)
        return None