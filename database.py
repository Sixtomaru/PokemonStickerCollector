# database.py
import os
import sqlite3  # <--- MOVIDO AQUÍ PARA CORREGIR EL ERROR
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

    # Tabla USERS
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS users (
        user_id {id_type} PRIMARY KEY,
        username TEXT,
        money INTEGER DEFAULT 1000,
        last_daily_claim TEXT DEFAULT NULL,
        capture_chance INTEGER DEFAULT 100,
        stickers_this_month INTEGER DEFAULT 0,
        kanto_completed INTEGER DEFAULT 0
    )''')

    # Tabla COLLECTION
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS collection (
        user_id {id_type},
        pokemon_id INTEGER,
        is_shiny INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        PRIMARY KEY (user_id, pokemon_id, is_shiny)
    )''')

    # Tabla GROUPS
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS groups (
        chat_id {id_type} PRIMARY KEY,
        is_active INTEGER DEFAULT 1
    )''')

    # Tabla GROUP_MEMBERS
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS group_members (
        chat_id {id_type},
        user_id {id_type},
        PRIMARY KEY (chat_id, user_id)
    )''')

    # Tabla MAILBOX
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS mailbox (
        mail_id {serial_type},
        recipient_user_id {id_type} NOT NULL,
        item_type TEXT NOT NULL,
        item_details TEXT NOT NULL,
        message TEXT,
        claimed INTEGER DEFAULT 0,
        FOREIGN KEY(recipient_user_id) REFERENCES users(user_id)
    )''')

    # Tabla INVENTORY
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS inventory (
        user_id {id_type},
        item_id TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        PRIMARY KEY (user_id, item_id)
    )''')

    # Tabla GROUP_EVENTS
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS group_events (
        chat_id {id_type},
        event_id TEXT,
        completed INTEGER DEFAULT 1,
        PRIMARY KEY (chat_id, event_id)
    )''')

    # Tabla SYSTEM_FLAGS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_flags (
            flag_name TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        )''')

    # Migraciones
    alter_commands = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily_claim TEXT DEFAULT NULL",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS capture_chance INTEGER DEFAULT 100",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stickers_this_month INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS kanto_completed INTEGER DEFAULT 0"
    ]

    if is_sqlite:
        for cmd in alter_commands:
            try:
                clean_cmd = cmd.replace("IF NOT EXISTS", "")
                cursor.execute(clean_cmd)
            except:
                pass
    else:
        for cmd in alter_commands:
            try:
                cursor.execute(cmd)
            except psycopg2.Error:
                conn.rollback()

    conn.commit()
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


def get_group_unique_kanto_ids(chat_id):
    rows = query_db('''
        SELECT DISTINCT c.pokemon_id 
        FROM collection c
        JOIN group_members gm ON c.user_id = gm.user_id
        WHERE c.pokemon_id <= 151 AND gm.chat_id = ?
    ''', (chat_id,))
    return {row[0] for row in rows}


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


def add_group(chat_id):
    if DATABASE_URL:
        query_db("INSERT INTO groups (chat_id) VALUES (?) ON CONFLICT DO NOTHING", (chat_id,))
    else:
        query_db("INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (chat_id,))


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


# Iniciar la DB
init_db()