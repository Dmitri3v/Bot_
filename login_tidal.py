import tidalapi
import json
import time

print("🌊 Iniciando conexión oficial con Tidal...")
session = tidalapi.Session()

# 1. Solicitar el código de vinculación
session.login_pkce()

print("\n" + "="*50)
print("⏳ ESPERANDO AUTORIZACIÓN...")
print("Ve a tu navegador, inicia sesión en Tidal y dale a 'Autorizar'.")
print("Esta consola lo detectará mágicamente en cuanto lo hagas.")
print("="*50 + "\n")

# 2. Bucle de espera: Revisa cada 3 segundos si Tidal ya nos dio acceso
while not session.check_login():
    time.sleep(3)

# 3. Guardar la sesión
print("\n✅ ¡Autenticación exitosa! Guardando credenciales...")

# 🪄 EL ARREGLO: Convertimos la fecha a texto (string)
expiry_str = session.expiry_time.isoformat() if session.expiry_time else None

session_data = {
    "token_type": session.token_type,
    "access_token": session.access_token,
    "refresh_token": session.refresh_token,
    "expiry_time": expiry_str
}

with open("tidal-session.json", "w") as f:
    json.dump(session_data, f)
    
print("💾 Sesión guardada en 'tidal-session.json'.")
print("🎉 ¡El motor de Tidal está listo! Ya puedes borrar este script.")