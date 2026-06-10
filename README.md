# 🤖 Telegram Music Bot - Tidal & Spotify Sync

Bot de Telegram para descargar música desde Tidal usando **tiddl**, con búsquedas minuciosas en Spotify y Tidal.

## ⚠️ IMPORTANTE SOBRE TIDDL

Este bot utiliza **tiddl** como motor de descarga principal. Asegúrate de tenerlo instalado:

```bash
pip install tiddl
```

Y configura tu clave de autenticación en el archivo `.env`.

## 📋 Características

- 🔍 **Búsqueda Dual**: Busca en Spotify y Tidal simultáneamente
- 💾 **Descarga FLAC Lossless**: Usa tiddl para descargar en máxima calidad
- 🎯 **Coincidencia Inteligente**: 
  - Huellas digitales por ISRC
  - Coincidencia fuzzy de artista/título
  - Motor de rescate para variaciones de nombres
- 📀 **Metadatos Enriquecidos**: 
  - Carátulas en alta resolución
  - Letras sincronizadas (LRC) desde LRCLIB
  - Todos los metadatos de Tidal
- 🔄 **Sincronización de Playlists**: Compara playlists completas y descarga solo lo faltante
- 💬 **Interfaz Interactiva**: Botones inline para confirmar descargas

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <repo-url>
cd <project-folder>
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
pip install tiddl
```

### 3. Configurar variables de entorno

Copia el archivo de ejemplo y completa tus credenciales:

```bash
cp .env.example .env
```

Edita `.env` con tus datos:

```env
# Telegram
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
ALLOWED_USER_ID=tu_id_de_telegram

# Spotify (opcional, para búsquedas)
SPOTIFY_CLIENT_ID=tu_client_id
SPOTIFY_CLIENT_SECRET=tu_client_secret

# Tidal (OBLIGATORIO)
TIDDL_AUTH_KEY=tu_auth_key_de_tiddl

# Directorios
MUSIC_FOLDER=/ruta/a/tu/biblioteca
TIDDL_DIR=/ruta/temporal/descargas
```

### 4. Autenticar Tidal

Ejecuta el script de login:

```bash
python login_tidal.py
```

Sigue las instrucciones en terminal para autorizar el acceso.

## 📖 Uso

### Comandos del Bot

- `/start` - Inicia el bot
- `/scan` - Escanea tu biblioteca local y actualiza el índice
- `/logs` - Descarga el archivo de logs del bot

### Funcionamiento

1. **Enviar link de Spotify o Tidal**: El bot analiza la canción/playlist
2. **Verificación automática**: Comprueba si ya tienes la canción en tu biblioteca
3. **Búsqueda en Tidal**: Si no está, la busca en Tidal
4. **Confirmación**: Te muestra un botón para descargar
5. **Descarga con tiddl**: Descarga en FLAC y enriquece metadatos
6. **Envío a Telegram**: Te envía el archivo de audio

### Playlists

Cuando envías un link de playlist:
- El bot compara todas las canciones con tu biblioteca
- Te dice cuántas faltan
- Puedes descargar todas las faltantes de una vez

## 🏗️ Estructura del Proyecto

```
├── bot.py                  # Main del bot de Telegram
├── config.py               # Configuración y variables
├── login_tidal.py          # Script de autenticación Tidal
├── requirements.txt        # Dependencias Python
├── core/
│   ├── tidal_client.py     # Cliente de Tidal API
│   ├── spotify_client.py   # Cliente de Spotify API
│   ├── downloader.py       # Wrapper para tiddl
│   ├── scanner.py          # Escaneo de biblioteca local
│   └── metadata_enrichment.py # Metadatos y letras LRC
└── utils/
    ├── matcher.py          # Algoritmos de coincidencia
    ├── helpers.py          # Funciones auxiliares
    └── fingerprint.py      # Generación de huellas
```

## 🔧 Configuración Avanzada

### Optimizar coincidencias

El sistema usa múltiples estrategias:
1. **ISRC**: Identificador único (más preciso)
2. **Fingerprints**: Combinaciones artista|título normalizadas
3. **Fuzzy Match**: Compara palabras clave ignorando feats, remixes, etc.

### Personalizar timeouts

En `.env`:
```env
HTTP_TIMEOUT=30  # Segundos para requests HTTP
MAX_RETRIES=3    # Reintentos en descargas fallidas
```

## ⚠️ Consideraciones Legales

Este bot es para uso personal con contenido que tengas derecho a descargar. Respeta los términos de servicio de Tidal y Spotify.

## 🐛 Solución de Problemas

### "tiddl no está instalado"
```bash
pip install tiddl
# Verifica que esté en PATH
which tiddl
```

### "Sesión de Tidal expirada"
Ejecuta nuevamente `python login_tidal.py`

### "Archivo muy grande para Telegram"
Telegram tiene límite de 50MB. Las canciones en FLAC muy largas pueden excederlo.

### Logs de error
Usa `/logs` para descargar el archivo de logs y diagnosticar problemas.

## 📝 Notas sobre tiddl

- tiddl debe estar configurado independientemente
- La clave `TIDDL_AUTH` se obtiene tras hacer login en tiddl
- Las descargas van a `TIDDL_DIR` temporalmente
- El bot mueve los archivos a `MUSIC_FOLDER` tras procesarlos

## 🤝 Contribuciones

Las mejoras son bienvenidas. Por favor, crea un issue primero para discutir cambios grandes.

## 📄 Licencia

Uso personal únicamente.
