# core/downloader.py
import subprocess
import os
import shutil
import logging
from config import TIDDL_AUTH_KEY, TIDDL_DIR, HTTP_TIMEOUT

logger = logging.getLogger(__name__)

def check_tiddl_installed():
    """Verifica si tiddl está instalado y disponible en PATH."""
    return shutil.which('tiddl') is not None

def download_with_tiddl(tidal_url, env=None):
    """
    Ejecuta tiddl para descargar una canción.
    Devuelve True si fue exitoso, False si falló.
    """
    # Verificar que tiddl esté instalado
    if not check_tiddl_installed():
        logger.error("❌ tiddl no está instalado o no está en PATH")
        logger.error("💡 Instala tiddl con: pip install tiddl")
        return False
    
    if env is None:
        env = os.environ.copy()
    env["TIDDL_AUTH"] = TIDDL_AUTH_KEY
    
    try:
        # Usar subprocess.run compatible con Linux/Windows
        result = subprocess.run(
            ['tiddl', '-nc', 'url', tidal_url, 'download'],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=HTTP_TIMEOUT * 3  # Timeout generoso para descargas
        )
        logger.info(f"✅ tiddl completó descarga: {tidal_url[:50]}...")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Timeout en descarga de tiddl: {tidal_url}")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error de tiddl (código {e.returncode}): {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("❌ tiddl no encontrado. ¿Está instalado?")
        return False
    except Exception as e:
        logger.error(f"❌ Error inesperado en tiddl: {e}")
        return False