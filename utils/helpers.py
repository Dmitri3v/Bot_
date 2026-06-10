# utils/helpers.py
import re

def sanitize_filename(name):
    """Elimina caracteres inválidos para nombres de archivo en Windows/Linux."""
    if not name:
        return "Unknown"
    return re.sub(r'[\\/*?:"<>|]', "", str(name).strip())