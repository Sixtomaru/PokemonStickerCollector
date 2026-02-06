# database.py
import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

# Intenta obtener la URL de la base de datos de las variables de entorno
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    """Establece conexión con la base de datos PostgreSQL o SQLite."""
    if not DATABASE_URL:
        # Fallback a SQLite si no hay URL (para pruebas locales)
        return sqlite3.connect("pokesticker.db")
    return psycopg2.connect(DATABASE_URL, sslmode='require')


def init_db():
    conn = get_connection()
    is_sqlite = not DATABASE_URL

    if is_sqlite:
        cursor = conn.cursor()
    else:
        conn.autocommit = True
        cursor = conn.cursor()

    # Tipos de datos
    id_type = "INTEGER" if is_sqlite else "BIGINT"
    serial_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"

    # Tablas Principales
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS users (
        user_id {id_type} PRIMARY KEY, username TEXT, money INTEGER DEFAULT 1000,
        last_daily_claim TEXT DEFAULT NULL, capture_chance INTEGER DEFAULT 100,
        stickers_this_month INTEGER DEFAULT 0, kanto_completed INTEGER DEFAULT 0
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS collection (
        user_id {id_type}, pokemon_id INTEGER, is_shiny INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(user_id), PRIMARY KEY (user_id, pokemon_id, is_shiny)
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS groups (
        chat_id {id_type} PRIMARY KEY, group_name TEXT, is_active INTEGER DEFAULT 1, is_banned INTEGER DEFAULT 0
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS group_members (
        chat_id {id_type}, user_id {id_type}, PRIMARY KEY (chat_id, user_id)
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS group_pokedex (
        chat_id {id_type}, pokemon_id INTEGER, PRIMARY KEY (chat_id, pokemon_id)
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS mailbox (
        mail_id {serial_type}, recipient_user_id {id_type} NOT NULL, item_type TEXT NOT NULL,
        item_details TEXT NOT NULL, message TEXT, claimed INTEGER DEFAULT 0,
        FOREIGN KEY(recipient_user_id) REFERENCES users(user_id)
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS inventory (
        user_id {id_type}, item_id TEXT NOT NULL, quantity INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id), PRIMARY KEY (user_id, item_id)
    )''')

    cursor.execute(f'''CREATE TABLE IF NOT EXISTS group_events (
        chat_id {id_type}, event_id TEXT, completed INTEGER DEFAULT 1, PRIMARY KEY (chat_id, event_id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS system_flags (flag_name TEXT PRIMARY KEY, value INTEGER DEFAULT 0)''')

    # Tabla CÓDIGOS DE AMIGO
    # Guardamos el timestamp de caducidad (expiry)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS friend_codes (
            user_id {id_type},
            game_nick TEXT,
            region TEXT,
            code TEXT,
            expiry_timestamp REAL,
            PRIMARY KEY (user_id, code) 
        )''')

    # --- MIGRACIONES MANUALES (A prueba de fallos) ---
    # Intentamos añadir las columnas una a una. Si ya existen, el error se ignora.
    migraciones = [
        "ALTER TABLE users ADD COLUMN last_daily_claim TEXT DEFAULT NULL",
        "ALTER TABLE groups ADD COLUMN is_active INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN capture_chance INTEGER DEFAULT 100",
        "ALTER TABLE users ADD COLUMN stickers_this_month INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN kanto_completed INTEGER DEFAULT 0",
        "ALTER TABLE groups ADD COLUMN group_name TEXT",
        "ALTER TABLE groups ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN notifications_enabled INTEGER DEFAULT 1",
        "ALTER TABLE group_members ADD COLUMN stickers_this_month INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN code_notifications_enabled INTEGER DEFAULT 1",

        # --- NUEVO PARA INTERCAMBIOS ---
        "ALTER TABLE collection ADD COLUMN quantity INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN daily_trades INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN last_trade_date TEXT DEFAULT NULL"
    ]

    for cmd in migraciones:
        try:
            cursor.execute(cmd)
            if not is_sqlite: conn.commit()
        except Exception:
            if not is_sqlite: conn.rollback()
            pass

    if is_sqlite: conn.commit()
    conn.close()



# --- HELPERS DE CONSULTA ---
def query_db(query, args=(), one=False, dict_cursor=False):
    """Ejecuta una consulta y devuelve resultados."""
    conn = get_connection()

    if DATABASE_URL and dict_cursor:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    elif not DATABASE_URL and dict_cursor:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    else:
        cursor = conn.cursor()

    if DATABASE_URL:
        query = query.replace('?', '%s')

    try:
        cursor.execute(query, args)
        if query.strip().upper().startswith("SELECT"):
            rv = cursor.fetchall()
            conn.close()
            if not DATABASE_URL and dict_cursor:
                rv = [dict(row) for row in rv]

            return (rv[0] if rv else None) if one else rv
        else:
            conn.commit()
            conn.close()
            return cursor.rowcount
    except Exception as e:
        if DATABASE_URL: conn.rollback()
        conn.close()
        raise e


# --- FUNCIONES DE LÓGICA ---

def get_user_capture_chance(user_id):
    res = query_db("SELECT capture_chance FROM users WHERE user_id = ?", (user_id,), one=True)
    return res[0] if res and res[0] is not None else 100


def update_user_capture_chance(user_id, new_chance):
    query_db("UPDATE users SET capture_chance = ? WHERE user_id = ?", (new_chance, user_id))


def increment_monthly_stickers(user_id):
    query_db("UPDATE users SET stickers_this_month = stickers_this_month + 1 WHERE user_id = ?", (user_id,))


def get_monthly_ranking():
    return query_db(
        "SELECT user_id, username, stickers_this_month FROM users WHERE stickers_this_month > 0 ORDER BY stickers_this_month DESC")


def reset_monthly_stickers():
    query_db("UPDATE users SET stickers_this_month = 0")


def register_user_in_group(user_id, chat_id):
    if DATABASE_URL:
        query_db("INSERT INTO group_members (chat_id, user_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                 (chat_id, user_id))
    else:
        query_db("INSERT OR IGNORE INTO group_members (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))


def get_users_in_group(chat_id):
    rows = query_db("SELECT user_id FROM group_members WHERE chat_id = ?", (chat_id,))
    return [row[0] for row in rows]


def get_user_unique_kanto_count(user_id):
    res = query_db("SELECT COUNT(DISTINCT pokemon_id) FROM collection WHERE user_id = ? AND pokemon_id <= 151",
                   (user_id,), one=True)
    return res[0] if res else 0


def is_kanto_completed_by_user(user_id):
    res = query_db("SELECT kanto_completed FROM users WHERE user_id = ?", (user_id,), one=True)
    return res[0] if res else 0


def set_kanto_completed_by_user(user_id):
    query_db("UPDATE users SET kanto_completed = 1 WHERE user_id = ?", (user_id,))


# --- MODIFICADO: Sistema de Pokedex Grupal Independiente ---
def add_pokemon_to_group_pokedex(chat_id, pokemon_id):
    """Registra que un Pokémon ha sido avistado/capturado en este grupo."""
    if DATABASE_URL:
        query_db("INSERT INTO group_pokedex (chat_id, pokemon_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                 (chat_id, pokemon_id))
    else:
        query_db("INSERT OR IGNORE INTO group_pokedex (chat_id, pokemon_id) VALUES (?, ?)", (chat_id, pokemon_id))


def get_group_unique_kanto_ids(chat_id):
    """
    Devuelve los IDs únicos capturados EN ESTE GRUPO.
    Ya no mira los bolsillos de los usuarios (collection), mira la tabla group_pokedex.
    """
    rows = query_db('SELECT pokemon_id FROM group_pokedex WHERE chat_id = ? AND pokemon_id <= 151', (chat_id,))
    return {row[0] for row in rows}


def reset_group_pokedex(chat_id):
    """Elimina el progreso del reto grupal para un grupo específico (Admin)."""
    query_db("DELETE FROM group_pokedex WHERE chat_id = ?", (chat_id,))
    # Opcional: También podríamos resetear el evento 'kanto_group_challenge' para que puedan ganar el premio otra vez
    query_db("DELETE FROM group_events WHERE chat_id = ? AND event_id = 'kanto_group_challenge'", (chat_id,))


def increment_group_monthly_stickers(user_id, chat_id):
    """Suma 1 punto al ranking de ESTE grupo."""
    # Primero aseguramos que el usuario esté registrado en el grupo
    if DATABASE_URL:
        query_db("INSERT INTO group_members (chat_id, user_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                 (chat_id, user_id))
    else:
        query_db("INSERT OR IGNORE INTO group_members (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))

    query_db("UPDATE group_members SET stickers_this_month = stickers_this_month + 1 WHERE chat_id = ? AND user_id = ?",
             (chat_id, user_id))


def get_group_monthly_ranking(chat_id):
    """Obtiene el ranking completo de los miembros de ESTE grupo."""
    sql = """
    SELECT gm.user_id, u.username, gm.stickers_this_month 
    FROM group_members gm
    JOIN users u ON gm.user_id = u.user_id
    WHERE gm.chat_id = ? AND gm.stickers_this_month > 0
    ORDER BY gm.stickers_this_month DESC
    """
    # ¡OJO! Hemos quitado el LIMIT 10
    return query_db(sql, (chat_id,), dict_cursor=False)


def reset_group_monthly_stickers():
    """Resetea el contador de TODOS los grupos (se ejecuta a fin de mes)."""
    query_db("UPDATE group_members SET stickers_this_month = 0")
# ------------------------------------------------------------


def get_user_money(user_id):
    res = query_db("SELECT money FROM users WHERE user_id = ?", (user_id,), one=True)
    return res[0] if res else 0


def remove_sticker_from_collection(user_id, pokemon_id, is_shiny):
    count = query_db("DELETE FROM collection WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
                     (user_id, pokemon_id, 1 if is_shiny else 0))
    return count > 0


def set_group_active(chat_id, is_active):
    query_db("UPDATE groups SET is_active = ? WHERE chat_id = ?", (1 if is_active else 0, chat_id))


def get_active_groups():
    rows = query_db("SELECT chat_id FROM groups WHERE is_active = 1")
    return [row[0] for row in rows]


def get_user_inventory(user_id):
    return query_db("SELECT item_id, quantity FROM inventory WHERE user_id = ?", (user_id,), dict_cursor=True)


def add_item_to_inventory(user_id, item_id, quantity=1):
    if DATABASE_URL:
        query_db('''
            INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
        ''', (user_id, item_id, quantity))
    else:
        query_db('''
            INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity
        ''', (user_id, item_id, quantity))


def remove_item_from_inventory(user_id, item_id, quantity=1):
    query_db("UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
             (quantity, user_id, item_id))
    query_db("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
             (user_id, item_id))


def get_last_daily_claim(user_id):
    res = query_db("SELECT last_daily_claim FROM users WHERE user_id = ?", (user_id,), one=True)
    return res[0] if res else None


def update_last_daily_claim(user_id, date_str):
    query_db("UPDATE users SET last_daily_claim = ? WHERE user_id = ?", (date_str, user_id))


def get_all_user_stickers(user_id):
    rows = query_db("SELECT pokemon_id, is_shiny FROM collection WHERE user_id = ?", (user_id,))
    return set(rows)


def add_mail(recipient_id, item_type, item_details, message):
    query_db(
        "INSERT INTO mailbox (recipient_user_id, item_type, item_details, message) VALUES (?, ?, ?, ?)",
        (recipient_id, item_type, item_details, message)
    )


def get_user_mail(user_id):
    return query_db("SELECT * FROM mailbox WHERE recipient_user_id = ? AND claimed = 0", (user_id,), dict_cursor=True)


def get_mail_item_by_id(mail_id):
    res = query_db("SELECT * FROM mailbox WHERE mail_id = ?", (mail_id,), one=True, dict_cursor=True)
    return res


def claim_mail_item(mail_id):
    query_db("UPDATE mailbox SET claimed = 1 WHERE mail_id = ?", (mail_id,))


def add_group(chat_id, group_name=None):
    """Añade un grupo. Actualiza el nombre si ya existe."""
    if DATABASE_URL:
        query_db("""
            INSERT INTO groups (chat_id, group_name) VALUES (?, ?) 
            ON CONFLICT (chat_id) DO UPDATE SET group_name = EXCLUDED.group_name
        """, (chat_id, group_name))
    else:
        # SQLite upsert emulation simple
        query_db("INSERT OR IGNORE INTO groups (chat_id, group_name) VALUES (?, ?)", (chat_id, group_name))
        if group_name:
            query_db("UPDATE groups SET group_name = ? WHERE chat_id = ?", (group_name, chat_id))


def get_all_groups_info():
    """Devuelve lista de diccionarios con info de grupos (para admin)."""
    return query_db("SELECT chat_id, group_name FROM groups", dict_cursor=True)


def get_all_groups():
    rows = query_db("SELECT chat_id FROM groups")
    return [row[0] for row in rows]


def get_or_create_user(user_id, username):
    res = query_db("SELECT user_id FROM users WHERE user_id = ?", (user_id,), one=True)
    if not res:
        query_db("INSERT INTO users (user_id, username) VALUES (?, ?)",
                 (user_id, username if username else f"User_{user_id}"))
    elif username:
        query_db("UPDATE users SET username = ? WHERE user_id = ? AND username != ?", (username, user_id, username))


def check_sticker_owned(user_id, pokemon_id, is_shiny):
    res = query_db("SELECT 1 FROM collection WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
                   (user_id, pokemon_id, 1 if is_shiny else 0), one=True)
    return res is not None


def add_sticker_to_collection(user_id, pokemon_id, is_shiny):
    if DATABASE_URL:
        query_db("INSERT INTO collection (user_id, pokemon_id, is_shiny) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                 (user_id, pokemon_id, 1 if is_shiny else 0))
    else:
        query_db("INSERT OR IGNORE INTO collection (user_id, pokemon_id, is_shiny) VALUES (?, ?, ?)",
                 (user_id, pokemon_id, 1 if is_shiny else 0))


def update_money(user_id, amount):
    query_db("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))


def get_all_user_ids():
    rows = query_db("SELECT user_id FROM users")
    return [row[0] for row in rows]


def clear_user_mailbox(user_id):
    return query_db("DELETE FROM mailbox WHERE recipient_user_id = ? AND claimed = 0", (user_id,))


def clear_all_mailboxes():
    return query_db("DELETE FROM mailbox WHERE claimed = 0")


def remove_mail_item_by_id(mail_id):
    count = query_db("DELETE FROM mailbox WHERE mail_id = ?", (mail_id,))
    return count > 0


def clear_user_collection(user_id):
    return query_db("DELETE FROM collection WHERE user_id = ?", (user_id,))


def mark_event_completed(chat_id, event_id):
    if DATABASE_URL:
        query_db("INSERT INTO group_events (chat_id, event_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                 (chat_id, event_id))
    else:
        query_db("INSERT OR IGNORE INTO group_events (chat_id, event_id) VALUES (?, ?)", (chat_id, event_id))


def is_event_completed(chat_id, event_id):
    res = query_db("SELECT 1 FROM group_events WHERE chat_id = ? AND event_id = ?", (chat_id, event_id), one=True)
    return res is not None


def set_money(user_id, amount):
    query_db("UPDATE users SET money = ? WHERE user_id = ?", (amount, user_id))


def get_user_id_by_username(username):
    """Busca la ID de un usuario por su @nombre."""
    clean_name = username.lstrip('@') # Quitar la @ si la tiene
    # Buscamos en la base de datos (ignorando mayúsculas/minúsculas)
    res = query_db("SELECT user_id FROM users WHERE LOWER(username) = ?", (clean_name.lower(),), one=True)
    return res[0] if res else None

# --- SISTEMA DE BANEOS ---

def ban_group(chat_id):
    """Banea un grupo asegurándose de que existe en la BD."""
    # Insertamos el grupo si no existe, o actualizamos si existe
    if DATABASE_URL: # Postgres
        sql = """
        INSERT INTO groups (chat_id, group_name, is_active, is_banned)
        VALUES (%s, 'Banned Group', 0, 1)
        ON CONFLICT (chat_id) DO UPDATE SET is_active = 0, is_banned = 1;
        """
    else: # SQLite
        sql = """
        INSERT INTO groups (chat_id, group_name, is_active, is_banned)
        VALUES (?, 'Banned Group', 0, 1)
        ON CONFLICT(chat_id) DO UPDATE SET is_active = 0, is_banned = 1;
        """
    query_db(sql, (chat_id,))

def unban_group(chat_id):
    query_db("UPDATE groups SET is_banned = 0 WHERE chat_id = ?", (chat_id,))

def is_group_banned(chat_id):
    # Devuelve True si is_banned es 1
    res = query_db("SELECT is_banned FROM groups WHERE chat_id = ?", (chat_id,), one=True)
    return res[0] == 1 if res else False

def get_banned_groups():
    return query_db("SELECT chat_id, group_name FROM groups WHERE is_banned = 1", dict_cursor=True)

def set_user_notification(user_id, enabled):
    """Activa (1) o desactiva (0) las notificaciones privadas."""
    val = 1 if enabled else 0
    query_db("UPDATE users SET notifications_enabled = ? WHERE user_id = ?", (val, user_id))

def is_user_notification_enabled(user_id):
    """Comprueba si el usuario quiere notificaciones (Por defecto True)."""
    res = query_db("SELECT notifications_enabled FROM users WHERE user_id = ?", (user_id,), one=True)
    # Si es 1 o None (por defecto), es True. Si es 0, es False.
    return res[0] != 0 if res else True

def add_sticker_smart(user_id, pokemon_id, is_shiny):
    """
    Lógica inteligente de captura:
    - Si no lo tiene: Lo añade (qty=1). Retorna 'NEW'.
    - Si tiene 1: Lo sube a 2. Retorna 'DUPLICATE'.
    - Si tiene 2: No hace nada (se debe vender fuera). Retorna 'MAX'.
    """
    # Verificamos estado actual
    res = query_db("SELECT quantity FROM collection WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
                   (user_id, pokemon_id, 1 if is_shiny else 0), one=True)

    if not res:
        # No lo tiene, insertar
        add_sticker_to_collection(user_id, pokemon_id, is_shiny)
        return 'NEW'

    qty = res[0]
    if qty == 1:
        # Tiene 1, subimos a 2
        query_db("UPDATE collection SET quantity = 2 WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
                 (user_id, pokemon_id, 1 if is_shiny else 0))
        return 'DUPLICATE'

    # Tiene 2 o más
    return 'MAX'


def get_user_duplicates(user_id, region_ids=None):
    """Obtiene los pokémon donde quantity >= 2."""
    sql = "SELECT pokemon_id, is_shiny FROM collection WHERE user_id = ? AND quantity >= 2"
    args = [user_id]

    rows = query_db(sql, tuple(args))

    # Filtrar por región si se especifica (lo haremos en python para no complicar el SQL con rangos dinámicos)
    # Devolvemos lista de tuplas (id, is_shiny)
    return rows


def check_trade_daily_limit(user_id):
    """Devuelve True si puede intercambiar hoy (Hora España)."""
    from datetime import datetime
    import pytz

    # Usamos la zona horaria correcta
    TZ_SPAIN = pytz.timezone('Europe/Madrid')
    today = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d')

    res = query_db("SELECT daily_trades, last_trade_date FROM users WHERE user_id = ?", (user_id,), one=True)

    # Si no existe registro o es la primera vez
    if not res: return True

    count, last_date = res[0], res[1]

    # Si la fecha guardada es distinta a la de hoy (España), reseteamos
    if last_date != today:
        query_db("UPDATE users SET daily_trades = 0, last_trade_date = ? WHERE user_id = ?", (today, user_id))
        return True

    # Si es el mismo día, comprobamos el límite
    return count < 2


def execute_trade(user_a, pokemon_a, is_shiny_a, user_b, pokemon_b, is_shiny_b):
    """
    Ejecuta el intercambio atómico.
    User A da Pokemon A -> Recibe Pokemon B.
    User B da Pokemon B -> Recibe Pokemon A.
    """
    # 1. Restar 1 a la cantidad de los pokémon ofrecidos (pasan de 2 a 1)
    # (Asumimos que ya validamos que tienen duplicados antes de llamar a esto)
    query_db("UPDATE collection SET quantity = quantity - 1 WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
             (user_a, pokemon_a, 1 if is_shiny_a else 0))

    query_db("UPDATE collection SET quantity = quantity - 1 WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
             (user_b, pokemon_b, 1 if is_shiny_b else 0))

    # 2. Sumar el pokémon recibido (usamos add_sticker_smart para manejar si ya lo tenían o no)
    # Nota: Si add_sticker_smart devuelve 'MAX', significa que ya tenían 2, así que en el bot daremos dinero.
    status_a = add_sticker_smart(user_a, pokemon_b, is_shiny_b)
    status_b = add_sticker_smart(user_b, pokemon_a, is_shiny_a)

    # 3. Actualizar contadores diarios
    query_db("UPDATE users SET daily_trades = daily_trades + 1 WHERE user_id IN (?, ?)", (user_a, user_b))

    return status_a, status_b

# --- SISTEMA DE CÓDIGOS DE AMIGO ---

def add_friend_code(user_id, nick, region, code, days_valid=30):
    """Añade o actualiza un código de amigo."""
    import time
    expiry = time.time() + (days_valid * 86400)

    if DATABASE_URL:
        # Postgres upsert
        sql = """
        INSERT INTO friend_codes (user_id, game_nick, region, code, expiry_timestamp)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, code) DO UPDATE SET expiry_timestamp = EXCLUDED.expiry_timestamp;
        """
    else:
        # SQLite replace
        sql = "INSERT OR REPLACE INTO friend_codes (user_id, game_nick, region, code, expiry_timestamp) VALUES (?, ?, ?, ?, ?)"

    query_db(sql, (user_id, nick, region, code, expiry))


def get_all_friend_codes():
    """Obtiene todos los códigos ordenados por caducidad (los que más tiempo les queda, primero)."""
    return query_db("SELECT * FROM friend_codes ORDER BY expiry_timestamp DESC", dict_cursor=True)


def check_user_has_code_count(user_id):
    """Devuelve el número de códigos que tiene un usuario."""
    res = query_db("SELECT COUNT(*) FROM friend_codes WHERE user_id = ?", (user_id,), one=True)
    return res[0] if res else 0


def check_code_exists(code):
    """Devuelve True si el código ya existe en la BD."""
    res = query_db("SELECT 1 FROM friend_codes WHERE code = ?", (code,), one=True)
    return res is not None


def renew_friend_code(user_id):
    """Renueva los códigos del usuario por 30 días desde HOY."""
    import time
    new_expiry = time.time() + (30 * 86400)

    # Verificamos si tiene AL MENOS UN código (count > 0)
    if check_user_has_code_count(user_id) == 0:
        return False

    query_db("UPDATE friend_codes SET expiry_timestamp = ? WHERE user_id = ?", (new_expiry, user_id))
    return True

def delete_expired_codes():
    """Borra códigos caducados."""
    import time
    now = time.time()
    query_db("DELETE FROM friend_codes WHERE expiry_timestamp < ?", (now,))

def get_code_owner(code):
    """Devuelve el ID del usuario dueño de un código."""
    res = query_db("SELECT user_id FROM friend_codes WHERE code = ?", (code,), one=True)
    return res[0] if res else None

def delete_friend_code(code):
    """Elimina un código específico de la base de datos."""
    query_db("DELETE FROM friend_codes WHERE code = ?", (code,))

# --- AJUSTES NOTIFICACIONES CÓDIGOS ---

def set_code_notification(user_id, enabled):
    """Activa (1) o desactiva (0) el recordatorio de códigos."""
    val = 1 if enabled else 0
    # Aseguramos que el usuario existe
    get_or_create_user(user_id, None)
    query_db("UPDATE users SET code_notifications_enabled = ? WHERE user_id = ?", (val, user_id))

def is_code_notification_enabled(user_id):
    """Comprueba si el usuario quiere recordatorios de códigos (Por defecto True)."""
    res = query_db("SELECT code_notifications_enabled FROM users WHERE user_id = ?", (user_id,), one=True)
    return res[0] != 0 if res else True

def has_duplicate(user_id, pokemon_id, is_shiny):
    """Verifica si el usuario tiene al menos 1 repetido (cantidad >= 2) de un Pokémon específico."""
    res = query_db(
        "SELECT quantity FROM collection WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?",
        (user_id, pokemon_id, 1 if is_shiny else 0),
        one=True
    )
    return res and res[0] >= 2

# Iniciar la DB
init_db()
