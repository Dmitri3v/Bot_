# utils/fingerprint.py

def get_fingerprint(isrc, artist, title):
    """
    Crea una huella digital única para identificar una canción.
    Prioriza ISRC, fallback a artista|título en minúsculas.
    """
    if isrc:
        return str(isrc).upper().strip()
    if artist and title:
        return f"{str(artist).lower().strip()}|{str(title).lower().strip()}"
    return None