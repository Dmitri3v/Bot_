# config.py
# Configuración del Bot de Telegram para Descarga de Música

import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Directorio base del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# 🔑 CONFIGURACIÓN DE TELEGRAM
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))

# ==========================================
# 🎵 CONFIGURACIÓN DE SPOTIFY
# ==========================================
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# ==========================================
# 🌊 CONFIGURACIÓN DE TIDAL
# ==========================================
# Para tiddl (CLI downloader)
TIDDL_AUTH_KEY = os.getenv("TIDDL_AUTH_KEY", "")

# Para tidalapi (búsquedas y metadatos)
SESSION_FILE = os.path.join(BASE_DIR, "tidal-session.json")

# ==========================================
# 📁 CONFIGURACIÓN DE DIRECTORIOS
# ==========================================
# Carpeta donde se almacena la biblioteca musical local
MUSIC_FOLDER = os.getenv("MUSIC_FOLDER", os.path.join(BASE_DIR, "music"))

# Carpeta temporal donde tiddl descarga las canciones
TIDDL_DIR = os.getenv("TIDDL_DIR", os.path.join(BASE_DIR, "tiddl_downloads"))

# Crear directorios si no existen
os.makedirs(MUSIC_FOLDER, exist_ok=True)
os.makedirs(TIDDL_DIR, exist_ok=True)

# ==========================================
# ⚙️ CONFIGURACIÓN ADICIONAL
# ==========================================
# Timeout para requests HTTP (segundos)
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))

# Número máximo de reintentos para descargas fallidas
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# Límite de tamaño de archivo para Telegram (50MB por defecto)
TELEGRAM_FILE_LIMIT_MB = int(os.getenv("TELEGRAM_FILE_LIMIT_MB", "50"))
