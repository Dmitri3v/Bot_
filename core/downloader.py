# core/downloader.py
import subprocess
import os
from config import TIDDL_AUTH_KEY, TIDDL_DIR

def download_with_tiddl(tidal_url, env=None):
    """
    Ejecuta tiddl para descargar una canción.
    Devuelve True si fue exitoso, False si falló.
    """
    if env is None:
        env = os.environ.copy()
    env["TIDDL_AUTH"] = TIDDL_AUTH_KEY
    
    try:
        subprocess.run(
            ['tiddl', '-nc', 'url', tidal_url, 'download'],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error de tiddl: {e.stderr}")
        return False