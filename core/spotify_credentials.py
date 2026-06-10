# core/spotify_credentials.py
# Gestión dinámica de credenciales de Spotify
# Permite configurar las credenciales desde Telegram

import os
import json
from config import BASE_DIR

CREDENTIALS_FILE = os.path.join(BASE_DIR, "spotify_credentials.json")

def load_spotify_credentials():
    """Carga las credenciales de Spotify desde archivo JSON"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                data = json.load(f)
                return {
                    'client_id': data.get('client_id', ''),
                    'client_secret': data.get('client_secret', ''),
                    'configured': bool(data.get('client_id') and data.get('client_secret'))
                }
        except Exception as e:
            print(f"Error cargando credenciales: {e}")
    
    # Si no hay archivo, verificar variables de entorno
    from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    configured = bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)
    return {
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET,
        'configured': configured
    }

def save_spotify_credentials(client_id: str, client_secret: str) -> bool:
    """Guarda las credenciales de Spotify en archivo JSON"""
    try:
        data = {
            'client_id': client_id.strip(),
            'client_secret': client_secret.strip()
        }
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error guardando credenciales: {e}")
        return False

def delete_spotify_credentials() -> bool:
    """Elimina las credenciales guardadas"""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)
        return True
    except Exception as e:
        print(f"Error eliminando credenciales: {e}")
        return False

def is_spotify_configured() -> bool:
    """Verifica si Spotify está configurado"""
    creds = load_spotify_credentials()
    return creds['configured']
