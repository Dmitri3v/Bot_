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
            
            # Verificar si tenemos todos los datos necesarios
            required_fields = ['session_id', 'country_code', 'user_id', 'token_type', 'access_token', 'refresh_token', 'expiry_time']
            has_all_fields = all(field in session_data for field in required_fields)
            
            if has_all_fields:
                # Restaurar sesión completa con tokens
                session.session_id = session_data['session_id']
                session.country_code = session_data['country_code']
                
                # Configurar tokens manualmente
                session.token_type = session_data['token_type']
                session.access_token = session_data['access_token']
                session.refresh_token = session_data['refresh_token']
                session.expiry_time = session_data['expiry_time']
                
                # Verificar si la sesión es válida
                if session.check_login():
                    logger.info("✅ Sesión de Tidal cargada desde caché.")
                    return session
                else:
                    logger.warning("⚠️ La sesión guardada expiró. Intentando refrescar...")
                    
                    # Intentar refrescar el token
                    try:
                        session.token_refresh()
                        if session.check_login():
                            # Guardar sesión actualizada
                            save_tidal_session(session, SESSION_FILE)
                            logger.info("✅ Sesión de Tidal refrescada exitosamente.")
                            return session
                    except Exception as refresh_error:
                        logger.warning(f"⚠️ No se pudo refrescar la sesión: {refresh_error}")
            else:
                logger.warning("⚠️ La sesión guardada está incompleta. Generando una nueva...")
                
        except Exception as e:
            logger.warning(f"⚠️ No se pudo cargar la sesión guardada: {e}")

    # 2. Iniciar nuevo login OAuth (Imprimirá la URL en la terminal)
    logger.info("⏳ Iniciando nuevo login en Tidal...")
    session.login_oauth_simple()
    
    # 3. Guardar la nueva sesión manualmente en un archivo JSON
    if SESSION_FILE and session.check_login():
        save_tidal_session(session, SESSION_FILE)
            
    return session

def save_tidal_session(session, session_file):
    """Guarda toda la información de la sesión de Tidal incluyendo tokens."""
    try:
        session_data = {
            'session_id': session.session_id,
            'country_code': session.country_code,
            'user_id': session.user.id if hasattr(session, 'user') and session.user else None,
            'token_type': session.token_type,
            'access_token': session.access_token,
            'refresh_token': session.refresh_token,
            'expiry_time': session.expiry_time
        }
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=4)
        logger.info("✅ Nueva sesión de Tidal guardada exitosamente.")
    except Exception as e:
        logger.error(f"❌ Error al guardar la sesión: {e}")

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