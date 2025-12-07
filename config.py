# config.py
import os

# Buscamos el token en las variables de entorno del servidor.
# Si no lo encuentra (por ejemplo en tu PC sin configurar), dará error o None.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# El ID del admin puede ser público sin tanto riesgo, pero también podrías ocultarlo igual.
# De momento lo dejamos así o lo cogemos del entorno si prefieres.
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", 118012153))
