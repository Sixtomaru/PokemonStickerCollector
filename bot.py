# bot.py
import logging
import random
import time  # <--- Este es el módulo time original (necesario para time.time)
import asyncio
import re
import requests

# --- CORRECCIÓN IMPORTS: Renombramos time a dt_time para evitar conflicto ---
from datetime import datetime, time as dt_time, timedelta
import pytz
import math
from typing import cast
import os
from threading import Thread

# --- Importamos Flask y Waitress ---
from flask import Flask
from flask_cors import CORS
from waitress import serve

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
    BotCommandScopeDefault, BotCommandScopeAllGroupChats, Message, User, MessageEntity, Bot, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, BaseHandler, ChatMemberHandler
)
from telegram.error import BadRequest, RetryAfter

from telegram.ext import filters, MessageHandler

import database as db
from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from pokemon_data import POKEMON_REGIONS, ALL_POKEMON, POKEMON_BY_ID, ALL_POKEMON_SPAWNABLE, ALL_POKEMON_PACKS, UNOWN_IDS
from bot_utils import format_money, get_rarity, RARITY_VISUALS, DUPLICATE_MONEY_VALUES, get_formatted_name
from events import EVENTS, KANTO_EVENT_KEYS, JOHTO_EVENT_KEYS

from flask import request, jsonify, make_response
from telegram import WebAppInfo # Añade WebAppInfo a tus imports de telegram


# --- CONFIGURACIÓN DEL SERVIDOR WEB ---
app = Flask('')

CORS(app)

@app.route('/')
def home():
    return "¡El bot está vivo y coleando!"


def run():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run)
    t.start()


@app.route('/api/win_minigame', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def win_minigame():
    # 1. Seguridad CORS (Preflight)
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    # 2. Por si el navegador hace un GET por error al redirigir
    if request.method == 'GET':
        return jsonify({"status": "El servidor está escuchando, pero debes enviar un POST."}), 200

    # 3. El procesamiento real de la victoria (POST)
    try:
        data = request.json
        if not data:
            return jsonify({"error": "no_data"}), 400

        user_id = int(data.get('user_id'))
        first_name = data.get('first_name')
        chat_id = int(data.get('chat_id'))
        msg_id = int(data.get('msg_id'))

        # Obtenemos el juego de la Base de Datos
        state = db.get_minigame(chat_id, msg_id)
        if not state:
            return jsonify({"error": "event_not_found"}), 200

        # Comprobamos si ya ganó
        if user_id in state['winners']:
            return jsonify({"error": "already_played"}), 200

        # Lotería Unown
        if random.random() < 0.80:
            prize_id = random.choice(['pack_small_unown', 'pack_medium_unown', 'pack_large_unown'])
        else:
            prize_id = random.choice(
                ['pack_magic_small_unown', 'pack_magic_medium_unown', 'pack_magic_large_unown', 'pack_special_unown'])

        prize_name = SHOP_CONFIG[prize_id]['name']

        # Entregamos premio
        db.get_or_create_user(user_id, first_name)
        db.add_item_to_inventory(user_id, prize_id, 1)

        # Guardamos la victoria en la BD
        safe_name = first_name.replace('*', '').replace('_', '')
        result_text = f"👤 {safe_name}: {prize_name} ✅"
        db.update_minigame_winner(chat_id, msg_id, user_id, result_text)

        updated_state = db.get_minigame(chat_id, msg_id)

        # Actualizamos el mensaje en Telegram
        text_final = "🎲 **¡Un Minijuego ha aparecido!**\nResuelve el puzzle de las Ruinas Alfa.\n\n"
        text_final += "**Resultados:**\n" + "\n".join(updated_state['results'])

        url_tg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": msg_id,
            "text": text_final,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [[{"text": "Ir al juego ↗", "url": updated_state['group_btn_url']}]]
            }
        }
        requests.post(url_tg, json=payload)

        return jsonify({"success": True, "prize_name": prize_name})

    except Exception as e:
        print(f"Error grave en Flask: {e}")
        return jsonify({"error": str(e)}), 500


def get_seconds_until_end_of_week():
    """Calcula los segundos exactos que faltan hasta el domingo a las 23:59:59."""
    now = datetime.now(TZ_SPAIN)
    # days_ahead: Si hoy es jueves (3), faltan 3 días para el domingo (6)
    days_ahead = 6 - now.weekday()

    # Creamos la fecha límite: este domingo a las 23:59:59
    end_of_week = now.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days_ahead)

    # Calculamos la diferencia en segundos
    diff = (end_of_week - now).total_seconds()
    return max(0, int(diff))  # Por seguridad, nunca devolvemos números negativos

# ---------------------------------------------------------

# --- Configuración Inicial ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
PROBABILITIES = {'C': 0.50, 'B': 0.32, 'A': 0.16, 'S': 0.02}
SHINY_CHANCE = 0.02
TZ_SPAIN = pytz.timezone('Europe/Madrid')

# --- Probabilidad del 15% ---
EVENT_CHANCE = 0.15

# --- ALMACÉN DE LA TÓMBOLA (GLOBAL) ---
# Estructura: { chat_id: {'msg_id': 123, 'winners': []} }
TOMBOLA_STATE = {}
# --- ESTADOS GLOBALES ---
DELIBIRD_STATE = {}
MIN_SPAWN_TIME = 7200  # 2 horas
MAX_SPAWN_TIME = 14400  # 4 horas

# --- ALMACÉN DEL RANKING (GLOBAL) ---
RANKING_ARCHIVE = {}

# --- CONFIGURACIÓN DE OBJETOS Y SOBRES ---
SHOP_CONFIG = {
    # NACIONALES
    'pack_small_national': {'name': 'Sobre Pequeño Nacional', 'price': 1000, 'size': 3, 'is_magic': False,
                            'desc': 'Contiene 3 stickers al azar de cualquier región.'},
    'pack_medium_national': {'name': 'Sobre Mediano Nacional', 'price': 1500, 'size': 5, 'is_magic': False,
                             'desc': 'Contiene 5 stickers al azar de cualquier región.'},
    'pack_large_national': {'name': 'Sobre Grande Nacional', 'price': 1900, 'size': 7, 'is_magic': False,
                            'desc': 'Contiene 7 stickers al azar de cualquier región.'},
    'pack_magic_small_national': {'name': 'Sobre Mágico Peq. Nacional', 'price': 1600, 'size': 1, 'is_magic': True, 'desc': 'Contiene 1 sticker que no tienes de cualquier región.'},
    'pack_magic_medium_national': {'name': 'Sobre Mágico Med. Nacional', 'price': 2100, 'size': 3, 'is_magic': True, 'desc': 'Contiene 3 stickers que no tienes de cualquier región.'},
    'pack_magic_large_national': {'name': 'Sobre Mágico Gra. Nacional', 'price': 2500, 'size': 5, 'is_magic': True, 'desc': 'Contiene 5 stickers que no tienes de cualquier región.'},

    # KANTO
    'pack_small_kanto': {'name': 'Sobre Pequeño Kanto', 'price': 1000, 'size': 3, 'region_filter': 'Kanto',
                         'desc': 'Contiene 3 stickers al azar de Kanto.'},
    'pack_medium_kanto': {'name': 'Sobre Mediano Kanto', 'price': 1500, 'size': 5, 'region_filter': 'Kanto',
                          'desc': 'Contiene 5 stickers al azar de Kanto.'},
    'pack_large_kanto': {'name': 'Sobre Grande Kanto', 'price': 1900, 'size': 7, 'region_filter': 'Kanto',
                         'desc': 'Contiene 7 stickers al azar de Kanto.'},
    'pack_magic_small_kanto': {'name': 'Sobre Mágico Peq. Kanto', 'price': 1600, 'size': 1, 'is_magic': True,
                               'region_filter': 'Kanto', 'desc': 'Contiene 1 sticker que no tienes de Kanto.'},
    'pack_magic_medium_kanto': {'name': 'Sobre Mágico Med. Kanto', 'price': 2100, 'size': 3, 'is_magic': True,
                                'region_filter': 'Kanto', 'desc': 'Contiene 3 stickers que no tienes de Kanto.'},
    'pack_magic_large_kanto': {'name': 'Sobre Mágico Gra. Kanto', 'price': 2500, 'size': 5, 'is_magic': True,
                               'region_filter': 'Kanto', 'desc': 'Contiene 5 stickers que no tienes de Kanto.'},

    # JOHTO
    'pack_small_johto': {'name': 'Sobre Pequeño Johto', 'price': 1000, 'size': 3, 'region_filter': 'Johto',
                         'desc': 'Contiene 3 stickers al azar de Johto.'},
    'pack_medium_johto': {'name': 'Sobre Mediano Johto', 'price': 1500, 'size': 5, 'region_filter': 'Johto',
                          'desc': 'Contiene 5 stickers al azar de Johto.'},
    'pack_large_johto': {'name': 'Sobre Grande Johto', 'price': 1900, 'size': 7, 'region_filter': 'Johto',
                         'desc': 'Contiene 7 stickers al azar de Johto.'},
    'pack_magic_small_johto': {'name': 'Sobre Mágico Peq. Johto', 'price': 1600, 'size': 1, 'is_magic': True,
                               'region_filter': 'Johto', 'desc': 'Contiene 1 sticker que no tienes de Johto.'},
    'pack_magic_medium_johto': {'name': 'Sobre Mágico Med. Johto', 'price': 2100, 'size': 3, 'is_magic': True,
                                'region_filter': 'Johto', 'desc': 'Contiene 3 stickers que no tienes de Johto.'},
    'pack_magic_large_johto': {'name': 'Sobre Mágico Gra. Johto', 'price': 2500, 'size': 5, 'is_magic': True,
                               'region_filter': 'Johto', 'desc': 'Contiene 5 stickers que no tienes de Johto.'},

    # --- SOBRES DE EVENTO (OCULTOS) ---
    'pack_shiny_kanto': {'name': 'Sobre Brillante Kanto', 'price': 0, 'size': 1, 'is_magic': False,
                         'desc': 'Garantiza 1 Shiny.', 'hidden': True},
    'pack_shiny_johto': {'name': 'Sobre Brillante Johto', 'price': 0, 'size': 1, 'is_magic': False, 'desc': 'Garantiza 1 Shiny Johto.', 'hidden': True},

    # Sobres Elementales
    'pack_elem_fuego': {'name': 'Sobre Fuego Kanto', 'price': 0, 'size': 5, 'desc': '5 Pokémon de tipo Fuego.',
                        'hidden': True, 'type_filter': 'Fuego', 'emoji': '🔥'},
    'pack_elem_agua': {'name': 'Sobre Agua Kanto', 'price': 0, 'size': 7, 'desc': '7 Pokémon de tipo Agua.',
                       'hidden': True, 'type_filter': 'Agua', 'emoji': '💧'},
    'pack_elem_planta': {'name': 'Sobre Planta Kanto', 'price': 0, 'size': 5, 'desc': '5 Pokémon de tipo Planta.',
                         'hidden': True, 'type_filter': 'Planta', 'emoji': '🌱'},
    'pack_elem_electrico': {'name': 'Sobre Eléctrico Kanto', 'price': 0, 'size': 3,
                            'desc': '3 Pokémon de tipo Eléctrico.', 'hidden': True, 'type_filter': 'Eléctrico',
                            'emoji': '⚡'},
    'pack_elem_hielo': {'name': 'Sobre Hielo Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Hielo.',
                        'hidden': True, 'type_filter': 'Hielo', 'emoji': '❄️'},
    'pack_elem_lucha': {'name': 'Sobre Lucha Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Lucha.',
                        'hidden': True, 'type_filter': 'Lucha', 'emoji': '👊'},
    'pack_elem_veneno': {'name': 'Sobre Veneno Kanto', 'price': 0, 'size': 7, 'desc': '7 Pokémon de tipo Veneno.',
                         'hidden': True, 'type_filter': 'Veneno', 'emoji': '☠️'},
    'pack_elem_tierra': {'name': 'Sobre Tierra Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Tierra.',
                         'hidden': True, 'type_filter': 'Tierra', 'emoji': '⛰️'},
    'pack_elem_roca': {'name': 'Sobre Roca Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Roca.',
                       'hidden': True, 'type_filter': 'Roca', 'emoji': '🪨'},
    'pack_elem_volador': {'name': 'Sobre Volador Kanto', 'price': 0, 'size': 4, 'desc': '4 Pokémon de tipo Volador.',
                          'hidden': True, 'type_filter': 'Volador', 'emoji': '🦅'},
    'pack_elem_psiquico': {'name': 'Sobre Psíquico Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Psíquico.',
                           'hidden': True, 'type_filter': 'Psíquico', 'emoji': '🔮'},
    'pack_elem_fantasma': {'name': 'Sobre Fantasma Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Fantasma.',
                           'hidden': True, 'type_filter': 'Fantasma', 'emoji': '👻'},
    'pack_elem_bicho': {'name': 'Sobre Bicho Kanto', 'price': 0, 'size': 4, 'desc': '4 Pokémon de tipo Bicho.',
                        'hidden': True, 'type_filter': 'Bicho', 'emoji': '🐛'},
    'pack_elem_normal': {'name': 'Sobre Normal Kanto', 'price': 0, 'size': 5, 'desc': '5 Pokémon de tipo Normal.',
                         'hidden': True, 'type_filter': 'Normal', 'emoji': '⚪'},
    'pack_elem_dragon': {'name': 'Sobre Dragón Kanto', 'price': 0, 'size': 3, 'desc': '3 Pokémon de tipo Dragón.',
                         'hidden': True, 'type_filter': 'Dragón', 'emoji': '🐉'},
    'pack_elem_hada': {'name': 'Sobre Hada Kanto', 'price': 0, 'size': 2, 'desc': '2 Pokémon de tipo Hada.',
                       'hidden': True, 'type_filter': 'Hada', 'emoji': '🧚'},
    'pack_elem_acero': {'name': 'Sobre Acero Kanto', 'price': 0, 'size': 2, 'desc': '2 Pokémon de tipo Acero.',
                        'hidden': True, 'type_filter': 'Acero', 'emoji': '🔩'},
    'pack_elem_especial': {'name': 'Sobre Especial Kanto', 'price': 0, 'size': 7, 'desc': 'Probabilidad shiny doble.',
                           'hidden': True, 'emoji': '✨🔺'},
    'pack_special_johto': {'name': 'Sobre Especial Johto', 'price': 0, 'size': 7, 'desc': 'Probabilidad shiny doble de Johto.',
                           'hidden': True, 'emoji': '✨🔺'},

# --- SOBRES UNOWN (EVENTO) ---
    'pack_small_unown': {'name': 'Sobre Pequeño Unown', 'price': 0, 'size': 2, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 2 stickers de Unown.', 'emoji': '🎴'},
    'pack_medium_unown': {'name': 'Sobre Mediano Unown', 'price': 0, 'size': 4, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 4 stickers de Unown.', 'emoji': '🎴'},
    'pack_large_unown': {'name': 'Sobre Grande Unown', 'price': 0, 'size': 6, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 6 stickers de Unown.', 'emoji': '🎴'},
'pack_magic_small_unown': {'name': 'Sobre Mágico Peq. Unown', 'price': 0, 'size': 1, 'is_magic': True, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 1 sticker que no tienes de Unown.', 'emoji': '🎴'},
    'pack_magic_medium_unown': {'name': 'Sobre Mágico Med. Unown', 'price': 0, 'size': 2, 'is_magic': True, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 2 stickers que no tienes de Unown.', 'emoji': '🎴'},
    'pack_magic_large_unown': {'name': 'Sobre Mágico Gra. Unown', 'price': 0, 'size': 3, 'is_magic': True, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 3 stickers que no tienes de Unown.', 'emoji': '🎴'},
    'pack_special_unown': {'name': 'Sobre Especial Unown', 'price': 0, 'size': 6, 'hidden': True, 'region_filter': 'Unown', 'desc': 'Contiene 6 stickers de Unown con probabilidad brillante doble.', 'emoji': '✨🔺'},
    'pack_shiny_unown': {'name': 'Sobre Brillante Unown', 'price': 0, 'size': 1, 'hidden': True, 'desc': 'Garantiza 1 Unown Shiny.', 'emoji': '✨🎴'},
}

# (Esto déjalo igual, se actualiza solo)
ITEM_NAMES = {item_id: details['name'] for item_id, details in SHOP_CONFIG.items()}

# --- CORRECCIÓN: Usamos .get() para que no de error si falta el dato 'is_magic' ---
PACK_CONFIG = {
    item_id: {
        'size': details.get('size', 1),
        'is_magic': details.get('is_magic', False)
    }
    for item_id, details in SHOP_CONFIG.items()
}

SPECIAL_ITEMS_DATA = {
    'pluma_naranja': {
        'name': 'Pluma Naranja',
        'emoji': '🪶',
        'desc': 'Es una especie de pluma que se calienta rápidamente al exponerla al sol, caída de un ave legendaria de Kanto.'
    },
    'pluma_amarilla': {
        'name': 'Pluma Amarilla',
        'emoji': '🪶',
        'desc': 'Es una pluma erizada que se carga fácilmente de electricidad estática con solo agitarla, caída de un ave legendaria de Kanto.'
    },
    'pluma_azul': {
        'name': 'Pluma Azul',
        'emoji': '🪶',
        'desc': 'Es una pluma de tacto frío y cristalino, caída de un ave legendaria de Kanto.'
    },
    'foto_psiquica': {
        'name': 'Foto Psíquica(?)',
        'emoji': '🖼',
        'desc': 'Una fotografía hecha con el Álbumdex. Sales tú con cara de asombro y un Pokémon legendario humanoide levitando tras de ti.'
    },
    'pluma_arcoiris': {
        'name': 'Pluma Arcoíris',
        'emoji': '🪶',
        'desc': 'Misteriosa pluma que brilla con todos los colores del arcoíris al ser expuesta a la luz.'
    }
}
# ------------------------------------------------------------------

# --- Emojis de dinero y Tómbola ---
DAILY_PRIZES = [
    {'type': 'money', 'value': 100, 'emoji': '🟤',
     'msg': '¡{usuario} sacó la bola 🟤!\n¡Obtuvo *100₽* 💰! ¡Menos es nada!'},
    {'type': 'money', 'value': 200, 'emoji': '🟢',
     'msg': '¡{usuario} sacó la bola 🟢!\n¡Genial, *200₽* 💰 que se lleva!'},
    {'type': 'money', 'value': 400, 'emoji': '🔵',
     'msg': '¡{usuario} sacó la bola 🔵!\n¡Fantástico! ¡Ha ganado *400₽* 💰!'},
    {'type': 'item', 'value': 'pack_magic_medium_national', 'emoji': '🟡',
     'msg': '¡Sacó la bola 🟡!\n¡¡PREMIO GORDO!! ¡{usuario} ha conseguido un *Sobre Mágico Mediano Nacional*! 🎴'}
]

# --- SOBRES DE DELIBIRD ---
DELIBIRD_PACKS = {
    'Fuego': {'size': 5, 'emoji': '🔥'},
    'Agua': {'size': 7, 'emoji': '💧'},
    'Planta': {'size': 5, 'emoji': '🌱'},
    'Eléctrico': {'size': 3, 'emoji': '⚡'},
    'Hielo': {'size': 3, 'emoji': '❄️'},
    'Lucha': {'size': 3, 'emoji': '👊'},
    'Veneno': {'size': 7, 'emoji': '☠️'},
    'Tierra': {'size': 3, 'emoji': '⛰️'},
    'Roca': {'size': 3, 'emoji': '🪨'},
    'Volador': {'size': 4, 'emoji': '🦅'},
    'Psíquico': {'size': 3, 'emoji': '🔮'},
    'Fantasma': {'size': 3, 'emoji': '👻'},
    'Bicho': {'size': 4, 'emoji': '🐛'},
    'Normal': {'size': 5, 'emoji': '⚪'},
    'Dragón': {'size': 3, 'emoji': '🐉'},
    'Hada': {'size': 2, 'emoji': '🧚'},
    'Acero': {'size': 2, 'emoji': '🔩'},
    'Especial': {'size': 7, 'emoji': '✨🔺'} # Kanto Especial
}

# Añadimos nombres manuales para que el bot los reconozca en otros menús
ITEM_NAMES['pack_magic_medium_national'] = SHOP_CONFIG['pack_magic_medium_national']['name']
ITEM_NAMES['pluma_naranja'] = 'Pluma Naranja'
ITEM_NAMES['pluma_amarilla'] = 'Pluma Amarilla'
ITEM_NAMES['pluma_azul'] = 'Pluma Azul'
ITEM_NAMES['foto_psiquica'] = 'Foto Psíquica(?)'
ITEM_NAMES['pluma_arcoiris'] = 'Pluma Arcoíris'

DAILY_WEIGHTS = [50, 32, 16, 2]
USER_FRIENDLY_ITEM_IDS = {'sobremagicomedianonacional': 'pack_magic_medium_national'}
MULTISOBRE_IDS = {
    'pequeñonacional': 'pack_small_national',
    'medianonacional': 'pack_medium_national',
    'grandenacional': 'pack_large_national',
    'magicopequeñonacional': 'pack_magic_small_national',
    'magicomedianonacional': 'pack_magic_medium_national',
    'magicograndenacional': 'pack_magic_large_national',

    'pequeñokanto': 'pack_small_kanto',
    'medianokanto': 'pack_medium_kanto',
    'grandekanto': 'pack_large_kanto',
    'magicopequeñokanto': 'pack_magic_small_kanto',
    'magicomedianokanto': 'pack_magic_medium_kanto',
    'magicograndekanto': 'pack_magic_large_kanto',

    'pequeñojohto': 'pack_small_johto',
    'medianojohto': 'pack_medium_johto',
    'grandejohto': 'pack_large_johto',
    'magicopequeñojohto': 'pack_magic_small_johto',
    'magicomedianojohto': 'pack_magic_medium_johto',
    'magicograndejohto': 'pack_magic_large_johto',

    'pequeñounown': 'pack_small_unown',
    'medianounown': 'pack_medium_unown',
    'grandeunown': 'pack_large_unown',
    'magicopequeñounown': 'pack_magic_small_unown',
    'magicomedianounown': 'pack_magic_medium_unown',
    'magicograndeunown': 'pack_magic_large_unown',
    'especialunown': 'pack_special_unown'
}
POKEMON_BY_CATEGORY = {cat: [] for cat in PROBABILITIES.keys()}
for pokemon_item in ALL_POKEMON:
    # FILTRO: Solo añadimos Kanto (1-151) al pool de salvajes
    if pokemon_item['id'] <= 151:
        POKEMON_BY_CATEGORY[pokemon_item['category']].append(pokemon_item)
POKEMON_PER_PAGE = 52
PACK_OPEN_COOLDOWN = 30


# --- FUNCIONES AUXILIARES ---

async def is_group_qualified(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, ADMIN_USER_ID)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
    except BadRequest:
        pass
    users_in_group = db.get_users_in_group(chat_id)
    if len(users_in_group) >= 3:
        return True
    return False


async def check_and_unlock_johto(chat_id, context):
    """Verifica si el grupo ha alcanzado el 75% de Kanto y desbloquea Johto."""
    # Solo si no está desbloqueado ya
    if not db.is_event_completed(chat_id, 'amelia_johto_unlock'):
        group_unique_kanto = db.get_group_unique_kanto_ids(chat_id)
        if len(group_unique_kanto) >= 113:
            db.mark_event_completed(chat_id, 'amelia_johto_unlock')

            amelia_text = (
                "💬 <b>¡Hola a tod@s, aquí Amelia!</b>\nLo estáis haciendo muy bien, habéis recorrido todo Kanto y visto muchas especies de Pokémon.\n\n"
                "Gracias a todo el esfuerzo que habéis hecho, las autoridades regionales han oído hablar de nosotros, y nos van a financiar la agencia, además de darnos permiso para operar por todo Kanto. "
                "Además, ¡en Johto también quieren nuestros servicios!, siento que todo está yendo muy rápido, pero eso es buena señal.\n\n"
                "<b>A partir de ahora, también podemos movernos por Johto, así que: ¡¡A seguir esforzándonos!!</b>"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=amelia_text, parse_mode='HTML')
            except:
                pass

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.delete_message(chat_id=context.job.data['chat_id'], message_id=context.job.data['message_id'])
    except BadRequest:
        logger.info(f"El mensaje a borrar ({context.job.data['message_id']}) ya no existía.")
    except Exception as e:
        logger.error(f"Error al borrar mensaje programado: {e}")


async def resolve_safari_catch_job(context: ContextTypes.DEFAULT_TYPE):
    """Resuelve la Lotería de Captura pasados los 60 segundos."""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    text_msg_id = job_data['text_msg_id']
    sticker_msg_id = job_data['sticker_msg_id']
    pokemon_id = job_data['pokemon_id']
    is_shiny = job_data['is_shiny']
    rarity = job_data['rarity']
    p_name = job_data['p_name']

    # 1. Borramos el sticker (porque huye)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=sticker_msg_id)
    except:
        pass

    # 2. Recuperamos a los participantes usando la ruta de la aplicación central (Infalible)
    chat_data = context.application.chat_data.get(chat_id, {})
    state = chat_data.get('safari_spawns', {}).pop(text_msg_id, None)

    # Si nadie jugó o falló la memoria
    if not state or not state.get('participants'):
        text = f"El <b>{p_name}</b> huyó sin dejar rastro 💨"
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=text_msg_id, text=text, parse_mode='HTML')
        except:
            pass
        return

    # 3. Elegir al ganador al azar
    participants = state['participants']
    winner = random.choice(participants)

    # Separamos a los perdedores para la lista final
    losers = [p for p in participants if p['id'] != winner['id']]

    # 4. Entregar el premio (Lógica estándar de captura)
    user_id = winner['id']
    first_name = winner['first_name']
    user_mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'

    db.get_or_create_user(user_id, first_name)
    if chat_id in db.get_active_groups():
        db.register_user_in_group(user_id, chat_id)
        db.add_pokemon_to_group_pokedex(chat_id, pokemon_id)
        db.increment_group_monthly_stickers(user_id, chat_id)

    pokemon_data = POKEMON_BY_ID.get(pokemon_id)
    p_display = get_formatted_name(pokemon_data, is_shiny)
    rarity_emoji = RARITY_VISUALS.get(rarity, '')

    status = db.add_sticker_smart(user_id, pokemon_id, is_shiny)

    reward_text = ""
    if status == 'NEW':
        reward_text = f"🎉 ¡Felicidades, {user_mention}! Has conseguido un sticker de {p_display} {rarity_emoji}. Lo has registrado en tu Álbumdex."
    elif status == 'DUPLICATE':
        reward_text = f"♻ ¡Genial, {user_mention}! Conseguiste un sticker de {p_display} {rarity_emoji}. Como solo tenías 1, te lo guardas para intercambiarlo."
    else:
        money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
        db.update_money(user_id, money)
        reward_text = f"✔️ ¡Genial, {user_mention}! Conseguiste un sticker de {p_display} {rarity_emoji}. Como ya lo tienes repetido, se convierte en <b>{format_money(money)}₽</b> 💰."

    # --- Premios Extra (Kanto/Johto Completos) ---
    if not db.is_kanto_completed_by_user(user_id) and db.get_user_unique_kanto_count(user_id) >= 151:
        db.set_kanto_completed_by_user(user_id)
        db.update_money(user_id, 3000)
        db.add_item_to_inventory(user_id, 'pack_shiny_kanto', 1)
        reward_text += f"\n\n🎊 ¡Felicidades {user_mention}, has completado <b>Kanto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

    if not db.is_johto_completed_by_user(user_id) and db.get_user_unique_johto_count(user_id) >= 100:
        db.set_johto_completed_by_user(user_id)
        db.update_money(user_id, 3000)
        db.add_item_to_inventory(user_id, 'pack_shiny_johto', 1)
        reward_text += f"\n\n🎊 ¡Felicidades {user_mention}, has completado <b>Johto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"

    if not db.is_unown_completed_by_user(user_id) and db.get_user_unique_unown_count(user_id) >= 28:
        db.set_unown_completed_by_user(user_id)
        db.update_money(user_id, 2000)
        db.add_item_to_inventory(user_id, 'pack_shiny_unown', 1)
        reward_text += f"\n\n🎊 ¡Felicidades {user_mention}, has completado el <b>Álbum Unown</b>! 🎊\n¡Recibes 2000₽ y un Sobre Brillante Unown!"

    # 5. Construir y enviar el texto final
    final_text = (
        f"¡El <b>{p_name}</b> ha huido, pero ✔️{first_name} consiguió escanearlo!\n\n"
        f"{reward_text}\n\n"
    )

    if losers:
        final_text += "Han intentado escanearlo:\n"
        for loser in losers:
            safe_name = loser['first_name'].replace('<', '').replace('>', '')
            final_text += f"✖️ {safe_name}\n"

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=text_msg_id,
            text=final_text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Fallo al resolver Safari: {e}")


async def rescue_spawn_job(context: ContextTypes.DEFAULT_TYPE):
    """Intenta enviar el botón a un sticker huérfano por culpa de la red."""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    sticker_msg_id = job_data['sticker_msg_id']
    text_message = job_data['text_message']
    reply_markup = job_data['reply_markup']
    current_time = job_data['timestamp']
    intentos = job_data.get('intentos', 0)

    # Datos extra para la memoria del Safari
    is_special_hunt = job_data.get('is_special_hunt', False)

    try:
        text_msg = await context.bot.send_message(
            chat_id=chat_id, text=text_message, parse_mode='HTML',
            reply_markup=reply_markup, read_timeout=20, write_timeout=20
        )

        # ¡Éxito! Lo guardamos en la memoria RAM CORRECTA
        if is_special_hunt:
            context.chat_data.setdefault('safari_spawns', {})
            context.chat_data['safari_spawns'][text_msg.message_id] = {
                'sticker_id': sticker_msg_id,
                'pokemon_id': job_data['pokemon_id'],
                'is_shiny': job_data['is_shiny'],
                'rarity': job_data['rarity'],
                'p_name': job_data['p_name'],
                'participants': [],
                'job_started': False  # El reloj empieza parado
            }
        else:
            context.chat_data.setdefault('active_spawns', {})
            context.chat_data['active_spawns'][text_msg.message_id] = {
                'sticker_id': sticker_msg_id,
                'text_id': text_msg.message_id,
                'timestamp': current_time
            }
        logger.info(f"✅ ¡Rescate exitoso en {chat_id}!")

    except Exception as e:
        intentos += 1
        if intentos < 12:
            context.job_queue.run_once(rescue_spawn_job, 5, data={**job_data, 'intentos': intentos},
                                       name=f"rescue_{chat_id}_{sticker_msg_id}")
        else:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=sticker_msg_id)
            except:
                pass


async def check_and_unlock_johto(chat_id, context):
    """Verifica si el grupo ha alcanzado el 75% de Kanto y desbloquea Johto."""
    # Solo si no está desbloqueado ya
    if not db.is_event_completed(chat_id, 'amelia_johto_unlock'):
        group_unique_kanto = db.get_group_unique_kanto_ids(chat_id)
        if len(group_unique_kanto) >= 113:
            db.mark_event_completed(chat_id, 'amelia_johto_unlock')

            amelia_text = (
                "💬 <b>¡Hola a tod@s, aquí Amelia!</b>\nLo estáis haciendo muy bien, habéis recorrido todo Kanto y visto muchas especies de Pokémon.\n\n"
                "Gracias a todo el esfuerzo que habéis hecho, las autoridades regionales han oído hablar de nosotros, y nos van a financiar la agencia, además de darnos permiso para operar por todo Kanto. "
                "Además, ¡en Johto también quieren nuestros servicios!, siento que todo está yendo muy rápido, pero eso es buena señal.\n\n"
                "<b>A partir de ahora, también podemos movernos por Johto, así que: ¡¡A seguir esforzándonos!!</b>"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=amelia_text, parse_mode='HTML')
            except:
                pass

def schedule_message_deletion(context: ContextTypes.DEFAULT_TYPE, message: Message, delay_seconds: int = 60):
    if context.job_queue and message:
        context.job_queue.run_once(
            delete_message_job,
            delay_seconds,
            data={'chat_id': message.chat_id, 'message_id': message.message_id},
            name=f"delete_{message.chat_id}_{message.message_id}"
        )


def cancel_scheduled_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    if context.job_queue:
        job_name = f"delete_{chat_id}_{message_id}"
        jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in jobs:
            job.schedule_removal()


def refresh_deletion_timer(context: ContextTypes.DEFAULT_TYPE, message: Message, timeout: int = 60):
    if not message: return
    cancel_scheduled_deletion(context, message.chat_id, message.message_id)
    schedule_message_deletion(context, message, timeout)


# --- RANKING MENSUAL ---
async def check_monthly_job(context: ContextTypes.DEFAULT_TYPE, force=False):
    """Tarea mensual: Ranking por grupo y reseteo."""
    now = datetime.now(TZ_SPAIN)

    if now.day == 1 or force:
        active_groups = db.get_active_groups()

        groups_data = {}
        global_pack_winners = set()

        # 1. Recopilar datos
        for chat_id in active_groups:
            group_users = db.get_users_in_group(chat_id)
            if len(group_users) < 4: continue

            ranking = db.get_group_monthly_ranking(chat_id)
            if not ranking: continue

            groups_data[chat_id] = {
                'ranking': ranking,
                'prizes_pool': ['pack_large_national', 'pack_medium_national', 'pack_small_national'],
                'lines': []
            }

        # 2. Procesamiento Horizontal
        max_rank_depth = 10

        for i in range(max_rank_depth):
            for chat_id, data in groups_data.items():
                ranking = data['ranking']
                if i < len(ranking):
                    user_row = ranking[i]
                    uid, uname, count = user_row[0], user_row[1], user_row[2]
                    prize_text = ""

                    if i < 10:
                        if uid in global_pack_winners:
                            prize_text = "_(👑 Ya premiado)_"
                        else:
                            pool = data['prizes_pool']
                            if len(pool) > 0:
                                prize_item = pool.pop(0)
                                p_name = "Sobre Grande" if 'large' in prize_item else "Sobre Mediano" if 'medium' in prize_item else "Sobre Pequeño"
                                db.add_mail(uid, 'inventory_item', prize_item, f"🏆 Premio Ranking Grupo {chat_id}")
                                global_pack_winners.add(uid)
                                prize_text = f"(+ {p_name} 🎴)"
                            else:
                                db.add_mail(uid, 'money', '500', f"Premio Ranking Grupo {chat_id}")
                                prize_text = "(+500₽)"

                    medals = ["🥇", "🥈", "🥉"]
                    visual_rank = medals[i] if i < 3 else f"{i + 1}."
                    line = f"{visual_rank} {uname}: {count} stickers {prize_text}"
                    data['lines'].append(line)

        # 3. Envío y Guardado
        for chat_id, data in groups_data.items():
            lines = data['lines']
            if not lines: continue

            # --- CORRECCIÓN: USAR VARIABLE GLOBAL ---
            RANKING_ARCHIVE[chat_id] = lines
            # ----------------------------------------

            await send_ranking_page(context.bot, chat_id, lines, 0)

        # 4. Reseteo
        db.reset_group_monthly_stickers()
        db.reset_monthly_stickers()


async def send_ranking_page(bot, chat_id, lines, page):
    ITEMS_PER_PAGE = 20
    total_pages = math.ceil(len(lines) / ITEMS_PER_PAGE)

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_lines = lines[start:end]

    text = f"🏆 **Ranking Mensual del Grupo** 🏆\n(Página {page + 1}/{total_pages})\n\n"
    text += "\n".join(current_lines)
    text += "\n\n_¡Los premios han sido enviados al buzón!_ 📬"

    # Botones de navegación
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"rank_nav_{page - 1}"))
    if end < len(lines):
        nav_row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"rank_nav_{page + 1}"))

    if nav_row: keyboard.append(nav_row)
    markup = InlineKeyboardMarkup(keyboard) if nav_row else None

    # Enviamos o Editamos (según contexto, pero aquí siempre es enviar nuevo al inicio)
    # Como esta función la llamamos desde el Job (sin update), usamos bot.send_message
    # Pero para la navegación usaremos edit_message_text.

    # Truco: Si viene del Job, enviamos. Si viene del botón, editamos.
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode='Markdown')
    except Exception:
        pass


async def ranking_navigation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id

    try:
        page = int(query.data.split('_')[2])
    except:
        return

    # --- CORRECCIÓN: LEER DE VARIABLE GLOBAL ---
    lines = RANKING_ARCHIVE.get(chat_id)
    # -------------------------------------------

    if not lines:
        await query.answer("Este ranking ha caducado (reinicio del bot).", show_alert=True)
        return

    ITEMS_PER_PAGE = 20
    total_pages = math.ceil(len(lines) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_lines = lines[start:end]

    text = f"🏆 **Ranking Mensual del Grupo** 🏆\n(Página {page + 1}/{total_pages})\n\n"
    text += "\n".join(current_lines)
    text += "\n\n_¡Los premios han sido enviados al buzón!_ 📬"

    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"rank_nav_{page - 1}"))
    if end < len(lines):
        nav_row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"rank_nav_{page + 1}"))

    if nav_row: keyboard.append(nav_row)
    markup = InlineKeyboardMarkup(keyboard) if nav_row else None

    await query.answer()
    await query.edit_message_text(text=text, reply_markup=markup, parse_mode='Markdown')


# --- MENSAJE DE BIENVENIDA ---
async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    new_member = result.new_chat_member
    if new_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        text = (
            "💬 ¡Hola, gracias por invitarme al grupo! Me presento, soy Amelia. He sido periodista, pero llevo tiempo queriendo abrir un negocio propio, os cuento:\n\n"
            "Desde hace mucho, admiro el trabajo de Ranger. Para el que no lo sepa, los rangers son una especie de policía; ayudan a Pokémon, personas y el medio ambiente. El inconveniente es que cada vez hay menos gente que se dedique a ello, por eso, junto a un grupo de personas, inventamos un dispositivo móvil con herramientas útiles para este tipo de trabajos: el Álbumdex.\n\n"
            "¿Por qué se llama así?, os preguntaréis, pues es porque, el Álbumdex tiene un escaner que es capaz de crear un sticker con tan solo una foto de un Pokémon. Poco a poco, iréis rellenando un Álbum de stickers. No os preocupéis, si conseguís uno que ya tengáis, os recompensaré por ello. Los stickers son solo un aliciente, si tenéis muchos, quiere decir que estáis viendo mundo y lo estáis haciendo bien.\n\n"
            "La idea es que todos uséis este dispositivo mientras exploráis, y si un día surje una emergencia, se avisará a la persona más cercana al suceso. Cuanta más gente lo use, más rápido llegará la ayuda a quien lo necesite.\n\n"
            "No me enrollo más, os doy un Álbumdex a cada uno.\n\n"
            "¡Mucha suerte en vuestra aventura!, ¡¡A conseguirlos todos!!🔥\n\n\n"
            "_Este es un bot de colección de stickers. Estos aparecerán cada cierto tiempo en el grupo. Quien antes pulse el botón para atraparlo, lo conseguirá. A veces, aparecerán eventos con elecciones; una vez alguien acepte el evento, solo podrá jugarlo esa persona._"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='Markdown')


# --- COMANDOS Y HANDLERS ---
async def albumdex_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = update.effective_user
    cmd_msg_id = None
    owner_user = None

    is_panel = (query and query.data == "panel_album")

    if query:
        if is_panel:
            owner_user = interactor_user
        else:
            try:
                parts = query.data.split('_')
                if parts[1] == "main":
                    owner_id = int(parts[2])
                    if len(parts) > 3 and parts[3].isdigit(): cmd_msg_id = int(parts[3])
                else:
                    owner_id = int(parts[-2] if len(parts) > 4 and parts[-1].isdigit() else parts[-1])
                    if parts[-1].isdigit() and parts[-2].isdigit():
                        owner_id = int(parts[-2])
                        cmd_msg_id = int(parts[-1])
                    elif parts[-1].isdigit():
                        owner_id = int(parts[-1])

                if interactor_user.id != owner_id:
                    await query.answer("Este álbumdex no es tuyo.", show_alert=True)
                    return
                owner_user = interactor_user
            except (ValueError, IndexError):
                await query.answer("Error en el botón.", show_alert=True)
                return
    else:
        owner_user = interactor_user
        if update.message: cmd_msg_id = update.message.message_id

    db.get_or_create_user(owner_user.id, owner_user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(owner_user.id, update.effective_chat.id)

    user_collection = db.get_all_user_stickers(owner_user.id)

    user_collection = db.get_all_user_stickers(owner_user.id)

    # --- 1. LÓGICA DE CONTEO NACIONAL ---
    national_unique = set()  # Contará especies únicas (Normal o Shiny, da igual)
    national_shiny = set()

    for pid, is_shiny in user_collection:
        mapped_id = 201 if pid in UNOWN_IDS else pid

        # Lo añadimos a las especies únicas sí o sí
        national_unique.add(mapped_id)

        # Si es shiny, lo añadimos al contador de brillantes
        if is_shiny == 1:
            national_shiny.add(mapped_id)

    owned_unique = len(national_unique)
    owned_shiny = len(national_shiny)

    # Conteo específico de letras Unown
    owned_unown = len({s[0] for s in user_collection if s[0] in UNOWN_IDS})
    total_pokemon_count = 251  # Base inamovible (Kanto 151 + Johto 100)

    # --- 2. CONTEO DE RAREZAS ---
    rarity_counts = {rarity: 0 for rarity in RARITY_VISUALS.keys()}
    for pokemon_id, is_shiny in user_collection:
        pokemon_data = POKEMON_BY_ID.get(pokemon_id)
        if pokemon_data:
            final_rarity = get_rarity(pokemon_data['category'], is_shiny)
            if final_rarity in rarity_counts: rarity_counts[final_rarity] += 1

    # --- 3. DISEÑO VISUAL ---
    rarity_lines = [f"{emoji}{rarity_counts[code]}" for code, emoji in RARITY_VISUALS.items()]

    text = (f"📖 *Álbumdex Nacional de {owner_user.first_name}*\n\n"
            f"🐱 Stickers: *{owned_unique}/{total_pokemon_count}*\n"
            f"✨ Brillantes: *{owned_shiny}/{total_pokemon_count}*\n\n"
            f"👁‍🗨 Unown: *{owned_unown}/28*\n\n"
            f"Rarezas: {', '.join(rarity_lines)}\n\n"
            "Selecciona una opción:")

    keyboard = []

    # --- NUEVO BOTÓN: VER REPETIDOS ---
    cb_dupes = f"album_dupe_menu_{owner_user.id}"
    if cmd_msg_id: cb_dupes += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("♻ Ver repetidos", callback_data=cb_dupes)])
    # ----------------------------------

    for name in POKEMON_REGIONS.keys():
        cb_data = f"album_{name}_0_{owner_user.id}"
        if cmd_msg_id: cb_data += f"_{cmd_msg_id}"
        keyboard.append([InlineKeyboardButton(f"🔍 Ver Álbum de {name}", callback_data=cb_data)])

    close_cb_data = f"album_close_{owner_user.id}"
    if cmd_msg_id: close_cb_data += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Cerrar Álbum", callback_data=close_cb_data)])

    if query and not is_panel:
        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except BadRequest:
            msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                                 disable_notification=True)
            schedule_message_deletion(context, msg, 60)
    else:
        msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                             reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                             disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        if update.message:
            schedule_message_deletion(context, update.message, 5)


async def album_dupe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts = query.data.split('_')
        owner_id = int(parts[3])
        cmd_msg_id = parts[4] if len(parts) > 4 else ""

        if query.from_user.id != owner_id:
            await query.answer("Este menú no es tuyo.", show_alert=True)
            return
    except:
        return

    text = "♻ **Stickers Repetidos**\n\nElige la región:"

    keyboard = []
    # Botón Kanto
    cb_kanto = f"album_dupe_show_kanto_{owner_id}"
    if cmd_msg_id: cb_kanto += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("🔸 Kanto", callback_data=cb_kanto)])

    # --- NUEVO: Botón Johto ---
    cb_johto = f"album_dupe_show_johto_{owner_id}"
    if cmd_msg_id: cb_johto += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("🔹 Johto", callback_data=cb_johto)])

    # Botón Volver
    cb_back = f"album_main_{owner_id}"
    if cmd_msg_id: cb_back += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=cb_back)])

    refresh_deletion_timer(context, query.message, 60)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def album_dupe_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts = query.data.split('_')
        region = parts[3]  # kanto o johto
        owner_id = int(parts[4])
        cmd_msg_id = parts[5] if len(parts) > 5 else ""

        if query.from_user.id != owner_id:
            await query.answer("Este menú no es tuyo.", show_alert=True)
            return
    except:
        return

    # Obtener repetidos
    duplicates = db.get_user_duplicates(owner_id)

    # Filtrar por región y ordenar alfabéticamente
    names_list = []

    for pid, is_shiny in duplicates:
        # Filtro Kanto (1-151)
        if region == 'kanto' and 1 <= pid <= 151:
            p_data = POKEMON_BY_ID[pid]
            # Usamos get_formatted_name si quieres emojis, o texto plano como tenías
            name_display = f"{p_data['name']}{'✨' if is_shiny else ''}"
            names_list.append(name_display)

        # Filtro Johto (152-251)
        elif region == 'johto' and 152 <= pid <= 251:
            p_data = POKEMON_BY_ID[pid]
            name_display = f"{p_data['name']}{'✨' if is_shiny else ''}"
            names_list.append(name_display)

    # Ordenar alfabéticamente
    names_list.sort()

    text = f"🔄 **Repetidos de {region.capitalize()}:**\n\n"
    if not names_list:
        text += "_No tienes repetidos en esta región._"
    else:
        text += ", ".join(names_list)

    cb_back = f"album_dupe_menu_{owner_id}"
    if cmd_msg_id: cb_back += f"_{cmd_msg_id}"
    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data=cb_back)]]

    refresh_deletion_timer(context, query.message, 60)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


# --- SISTEMA DE GUARDERÍA ---

async def guarderia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Detectar si viene del panel
    is_panel = (query and query.data == "panel_guarderia")

    if query and not is_panel:
        message = query.message
        user_id = query.from_user.id
    else:
        message = update.effective_message
        user_id = update.effective_user.id
        if update.message: schedule_message_deletion(context, update.message, 60)

    db.get_or_create_user(user_id, update.effective_user.first_name)

    text = (
        "🏡 <b>Guardería Pokémon:</b>\n\n"
        "💬 <b>¡Hola!, esta es la guardería de Pokémon. Veo que tienes un Álbumdex, por lo que eres de esas personas que viajan ayudando a los demás, ¿verdad?</b>\n\n"
        "<b>Nos vendría bien que nos echaras una mano, ¿podrías quedarte con uno de nuestros huevos e incubarlo?</b>\n\n"
        "<i>Para saber cuándo se ha abierto el huevo, tendrás que iniciar el bot del juego en su chat privado: @PokeStickerCollectorBot. Es por ahí por donde se notifica.</i>"
    )

    keyboard = [[InlineKeyboardButton("Recibir 🥚", callback_data=f"egg_claim_{user_id}")]]

    if query and not is_panel:
        refresh_deletion_timer(context, message, 60)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML',
                                       disable_notification=True)
        schedule_message_deletion(context, msg, 60)


async def egg_claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Validar usuario
    try:
        owner_id = int(query.data.split('_')[2])
        if user_id != owner_id:
            await query.answer("Este menú no es tuyo.", show_alert=True)
            return
    except:
        pass

    # 1. Comprobar si ya tiene huevo
    if db.get_user_egg(user_id):
        await query.answer("💬 Con uno que cuides, de momento es suficiente, gracias.", show_alert=True)
        return

    # 2. Generar Huevo
    # Lista de bebés: Pichu, Cleffa, Igglybuff, Togepi, Tyrogue, Smoochum, Elekid, Magby
    BABY_POOL = [172, 173, 174, 175, 236, 238, 239, 240]

    pokemon_id = random.choice(BABY_POOL)
    is_shiny = random.random() < SHINY_CHANCE

    # Tiempo de eclosión: 40 a 70 horas (en segundos)
    # 40h = 144000s, 70h = 252000s
    wait_time = random.randint(144000, 252000)
    hatch_timestamp = time.time() + wait_time

    # Guardar en BD
    db.add_egg_to_incubator(user_id, hatch_timestamp, pokemon_id, is_shiny)

    await query.answer("¡Conseguiste un huevo! Con el tiempo se abrirá. Puedes ver su estado en tu mochila.", show_alert=True)


async def test_minijuego_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    chat_id = update.effective_chat.id

    msg = await update.message.reply_text("Generando minijuego...", disable_notification=True)

    # URL DE TU WEB
    base_web_url = "https://minijuegos-pokestickercollector.netlify.app/"
    full_url = f"{base_web_url}/?c={chat_id}&m={msg.message_id}"

    bot_username = context.bot.username
    deep_link = f"https://t.me/{bot_username}?start=game_{chat_id}_{msg.message_id}"

    # GUARDAMOS EN LA BASE DE DATOS (No en RAM)
    db.create_minigame(chat_id, msg.message_id, full_url, deep_link)

    text = (
        "🎲 **¡Un Minijuego ha aparecido!**\n"
        "Resuelve el puzzle de las Ruinas Alfa.\n\n"
        "**Resultados:**\n_Aún nadie ha jugado_"
    )

    if update.effective_chat.type == 'private':
        keyboard = [[InlineKeyboardButton("Jugar", web_app=WebAppInfo(url=full_url))]]
    else:
        keyboard = [[InlineKeyboardButton("Ir al juego ↗", url=deep_link)]]

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg.message_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_ban_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Banea un grupo por su ID de forma silenciosa."""
    if update.effective_user.id != ADMIN_USER_ID: return

    try:
        target_chat_id = int(context.args[0])

        # 1. Marcar en BD
        db.ban_group(target_chat_id)

        # 2. Detener procesos activos
        jobs = context.job_queue.get_jobs_by_name(f"spawn_{target_chat_id}")
        for job in jobs:
            job.schedule_removal()

        # 3. Confirmar
        await update.message.reply_text(f"🚫 Grupo `{target_chat_id}` ha sido **BANEADO** silenciosamente.",
                                        parse_mode='Markdown', disable_notification=True)

    except (IndexError, ValueError):
        await update.message.reply_text("Uso: `/bangroup <chat_id>`", disable_notification=True)
    except Exception as e:
        # AQUÍ ATRAPAMOS CUALQUIER OTRO ERROR (Como el de la base de datos)
        logger.error(f"Error al banear grupo: {e}")
        await update.message.reply_text(f"❌ Error interno al banear: `{e}`", parse_mode='Markdown',
                                        disable_notification=True)

async def admin_fix_johto_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de emergencia para reparar la columna faltante."""
    if update.effective_user.id != ADMIN_USER_ID: return

    try:
        # Forzamos la ejecución del comando SQL directamente
        # Nota: Si usas Postgres, esto lanzará error si ya existe, lo cual nos confirmará el estado.
        db.query_db("ALTER TABLE users ADD COLUMN johto_completed INTEGER DEFAULT 0")
        await update.message.reply_text("✅ **ÉXITO:** Columna `johto_completed` creada manualmente.", parse_mode='Markdown')
    except Exception as e:
        # Si falla, te dirá exactamente por qué
        await update.message.reply_text(f"⚠️ **Resultado:** {e}", parse_mode='Markdown')

async def admin_unban_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desbanea un grupo."""
    if update.effective_user.id != ADMIN_USER_ID: return

    try:
        target_chat_id = int(context.args[0])
        db.unban_group(target_chat_id)
        await update.message.reply_text(f"✅ Grupo `{target_chat_id}` ha sido **DESBANEADO**.", parse_mode='Markdown',
                                        disable_notification=True)
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: `/unbangroup <chat_id>`", disable_notification=True)


async def admin_list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista los grupos baneados."""
    if update.effective_user.id != ADMIN_USER_ID: return

    banned = db.get_banned_groups()
    if not banned:
        await update.message.reply_text("🟢 No hay grupos baneados.", disable_notification=True)
        return

    text = "🚫 **GRUPOS BANEADOS:**\n\n"
    for group in banned:
        text += f"🔸 {group['group_name']} (ID: `{group['chat_id']}`)\n"

    await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)


async def check_pack_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return

    # Nombre del pack tal cual sale en tu captura
    pack_name = "MiniStickersKanto"

    try:
        # El bot busca el pack en los servidores de Telegram
        sticker_set = await context.bot.get_sticker_set(pack_name)

        # Cogemos el primer sticker (Bulbasaur)
        sticker = sticker_set.stickers[0]

        text = (
            f"📦 **Pack:** {sticker_set.title}\n"
            f"🔢 **Nombre:** {sticker_set.name}\n\n"
            f"🔍 **ID REAL que necesita el bot:**\n`{sticker.custom_emoji_id}`\n\n"
            f"📜 **ID que tienes en tu lista:**\n`5814460952195636965`"
        )

        await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error buscando el pack: {e}\nAsegúrate de que el nombre 'MiniStickersKanto' es exacto.")

async def admin_send_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return

    # Uso: /sendtogroup -100123456 combo 1000 pack_shiny_kanto Mensaje
    try:
        args = context.args
        if len(args) < 3:
            return await update.message.reply_text("Uso: `/sendtogroup <chat_id> <tipo/combo> <args...>`",
                                                   disable_notification=True)

        target_chat_id = int(args[0])
        # Reconstruimos los argumentos como si fuera send_to_all pero desplazados
        # args[0] es chat_id, así que pasamos args[1:] a la lógica de envío

        # Obtenemos usuarios de ESE grupo
        group_users = db.get_users_in_group(target_chat_id)
        if not group_users:
            return await update.message.reply_text("❌ No hay usuarios registrados en ese grupo o el grupo no existe.",
                                                   disable_notification=True)

        # --- REUTILIZAMOS LÓGICA DE ENVÍO ---
        # (Copia simplificada de la lógica de send_to_all adaptada a una lista concreta)

        first_arg = args[1].lower()
        msg_context = args[2:]

        if first_arg == 'combo':
            money = int(msg_context[0])
            item = msg_context[1]
            msg_text = ' '.join(msg_context[2:]) or "¡Regalo de grupo!"

            final_item = USER_FRIENDLY_ITEM_IDS.get(item, item)

            for uid in group_users:
                db.add_mail(uid, 'money', str(money), msg_text)
                db.add_mail(uid, 'inventory_item', final_item, msg_text)
                # Notificación (Opcional, copia el bloque try/except de send_to_all si quieres avisarles)

        # ... (Puedes añadir lógica para 'money' o 'sticker' sueltos si quieres, siguiendo el patrón) ...
        # Para simplificar, este ejemplo asume que usarás mayormente 'combo' o 'inventory_item'

        else:
            # Lógica genérica simple
            item_val = msg_context[0]
            msg_text = ' '.join(msg_context[1:])

            type_map = {
                'money': 'money',
                'sticker': 'single_sticker'
            }
            db_type = type_map.get(first_arg, 'inventory_item')
            if first_arg not in type_map and first_arg not in ITEM_NAMES and first_arg not in USER_FRIENDLY_ITEM_IDS and first_arg != 'pack_shiny_kanto':
                return await update.message.reply_text("Tipo inválido.")

            for uid in group_users:
                db.add_mail(uid, db_type, item_val, msg_text)

        await update.message.reply_text(
            f"✅ Regalo enviado a los {len(group_users)} miembros del grupo `{target_chat_id}`.",
            disable_notification=True)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}", disable_notification=True)


async def album_region_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    cmd_msg_id = None

    try:
        parts = query.data.split('_')
        region_name = parts[1]
        page = int(parts[2])
        owner_id = int(parts[3])

        if len(parts) > 4 and parts[4].isdigit(): cmd_msg_id = int(parts[4])

        sort_mode = 'num'
        if parts[-1] in ['num', 'az']: sort_mode = parts[-1]

        if interactor_user.id != owner_id:
            await query.answer("Este álbum no es tuyo.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en los datos del álbum.", show_alert=True)
        return

    raw_list = POKEMON_REGIONS.get(region_name)
    if not raw_list:
        await query.answer("Región no encontrada.", show_alert=True)
        return

    # Lógica de ordenación
    pokemon_list_region = raw_list[:]
    if sort_mode == 'az':
        pokemon_list_region.sort(key=lambda x: x['name'])
    else:
        pokemon_list_region.sort(key=lambda x: x['id'])

    await query.answer()
    refresh_deletion_timer(context, query.message, 60)

    user_collection = db.get_all_user_stickers(owner_id)

    # --- CÁLCULO DE PROGRESO ---
    region_ids = {p['id'] for p in raw_list}
    unique_owned_ids = {pid for pid, _ in user_collection}

    # EFECTO ESPEJO UNOWN (Solo para Johto)
    if region_name == "Johto":
        if any(uid in unique_owned_ids for uid in UNOWN_IDS):
            unique_owned_ids.add(201)

    owned_in_region = len(unique_owned_ids.intersection(region_ids))
    # ---------------------------

    total_region = len(pokemon_list_region)
    total_pages = math.ceil(total_region / POKEMON_PER_PAGE)

    start_index = page * POKEMON_PER_PAGE
    end_index = (page + 1) * POKEMON_PER_PAGE
    pokemon_on_page = pokemon_list_region[start_index:end_index]

    order_icon = "🔤" if sort_mode == 'az' else "🔢"

    text = (f"📖 <b>Álbumdex de {region_name}</b> ({order_icon})\n"
            f"📊 <b>{owned_in_region}/{total_region}</b>\n"
            f"(Pág. {page + 1}/{total_pages})")

    keyboard, row = [], []
    for pokemon in pokemon_on_page:

        # --- EFECTO ESPEJO UNOWN (Botones) ---
        if pokemon['id'] == 201:
            has_normal = any((uid, 0) in user_collection for uid in UNOWN_IDS)
            has_shiny = any((uid, 1) in user_collection for uid in UNOWN_IDS)
        else:
            has_normal = (pokemon['id'], 0) in user_collection
            has_shiny = (pokemon['id'], 1) in user_collection
        # -------------------------------------

        if has_normal or has_shiny:
            # Formato bonito para ocultar el ID numérico en el álbum de Unowns
            if pokemon['id'] > 1000:
                button_text = f"{pokemon['name']}"
            else:
                button_text = f"#{pokemon['id']:03} {pokemon['name']}"

            if has_shiny:
                button_text += f" ✨{RARITY_VISUALS.get(get_rarity(pokemon['category'], True), '')}"
            elif has_normal:
                button_text += f" {RARITY_VISUALS.get(get_rarity(pokemon['category'], False), '')}"

            cb_data = f"showsticker_{region_name}_{page}_{pokemon['id']}_{owner_id}"
            if cmd_msg_id: cb_data += f"_{cmd_msg_id}"
            callback_data = cb_data
        else:
            # Fallback bonito para los Unown que aún no tienes
            if pokemon['id'] > 1000:
                letra = pokemon['name'].split('(')[1][0] if '(' in pokemon['name'] else '?'
                button_text = f"--- ({letra})"
            else:
                button_text = f"#{pokemon['id']:03} ---"

            callback_data = "missing_sticker"

        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row: keyboard.append(row)

    pagination_row = []
    if page == 0:
        new_sort = 'num' if sort_mode == 'az' else 'az'
        btn_sort_text = "Orden 🔢" if sort_mode == 'az' else "Orden 🔤"
        cb_sort = f"album_{region_name}_0_{owner_id}"
        if cmd_msg_id: cb_sort += f"_{cmd_msg_id}"
        cb_sort += f"_{new_sort}"
        pagination_row.append(InlineKeyboardButton(btn_sort_text, callback_data=cb_sort))

    if page > 0:
        prev_cb = f"album_{region_name}_{page - 1}_{owner_id}"
        if cmd_msg_id: prev_cb += f"_{cmd_msg_id}"
        prev_cb += f"_{sort_mode}"
        pagination_row.append(InlineKeyboardButton("⬅️", callback_data=prev_cb))

    if end_index < total_region:
        next_cb = f"album_{region_name}_{page + 1}_{owner_id}"
        if cmd_msg_id: next_cb += f"_{cmd_msg_id}"
        next_cb += f"_{sort_mode}"
        pagination_row.append(InlineKeyboardButton("➡️", callback_data=next_cb))

    if pagination_row: keyboard.append(pagination_row)

    back_cb = f"album_main_{owner_id}"
    if cmd_msg_id: back_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver al Álbum Nacional", callback_data=back_cb)])

    close_cb = f"album_close_{owner_id}"
    if cmd_msg_id: close_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Cerrar Álbumdex", callback_data=close_cb)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def album_close_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    try:
        parts = query.data.split('_')
        owner_id = int(parts[2])
        cmd_msg_id = int(parts[3]) if len(parts) > 3 else None
        message = cast(Message, query.message)
        if interactor_user.id != owner_id:
            await query.answer("No puedes cerrar el álbum de otra persona.", show_alert=True)
            return
        cancel_scheduled_deletion(context, message.chat_id, message.message_id)
        await message.delete()
        if cmd_msg_id:
            try:
                await context.bot.delete_message(chat_id=message.chat_id, message_id=cmd_msg_id)
            except BadRequest:
                pass
        await query.answer()
    except (ValueError, IndexError):
        await query.answer("Error al procesar el botón de cerrar.", show_alert=True)


async def missing_sticker_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("No tienes este sticker.", show_alert=True)


async def choose_sticker_version_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    try:
        parts = query.data.split('_')
        # showsticker_REGION_PAGE_POKEMONID_OWNERID_MSGID
        region_name = parts[1]
        page_str = parts[2]
        pokemon_id_str = parts[3]
        owner_id_str = parts[4]
        cmd_msg_id_str = parts[5] if len(parts) > 5 else None

        pokemon_id, owner_id = int(pokemon_id_str), int(owner_id_str)
        if interactor_user.id != owner_id:
            await query.answer("Este menú no es tuyo.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error al obtener el sticker.", show_alert=True)
        return

        # --- NUEVO: INTERCEPTOR DEL UNOWN #201 EN JOHTO ---
    if pokemon_id == 201:
        text = "Para ver los Unown que tienes y sus versiones (Normal/Brillante), visita su propia sección en el **Álbumdex Nacional**."

        keyboard = []
        back_cb_data = f"album_{region_name}_{page_str}_{owner_id}"
        if cmd_msg_id_str:
            back_cb_data += f"_{cmd_msg_id_str}"
        back_cb_data += "_num"

        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=back_cb_data)])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    refresh_deletion_timer(context, query.message, 60)
    user_collection = db.get_all_user_stickers(owner_id)
    has_normal = (pokemon_id, 0) in user_collection
    has_shiny = (pokemon_id, 1) in user_collection
    pokemon_name = POKEMON_BY_ID.get(pokemon_id, {}).get("name", "Desconocido")
    text = f"Elige qué versión de *{pokemon_name}* quieres mostrar:"

    keyboard, row = [], []
    if has_normal:
        row.append(InlineKeyboardButton("Normal", callback_data=f"sendsticker_{pokemon_id}_0_{owner_id}"))
    if has_shiny:
        row.append(InlineKeyboardButton("Brillante ✨", callback_data=f"sendsticker_{pokemon_id}_1_{owner_id}"))
    keyboard.append(row)

    # --- BOTÓN VOLVER ---
    # Al volver, por defecto volvemos al modo numérico ('num') para evitar complicaciones
    back_cb_data = f"album_{region_name}_{page_str}_{owner_id}"
    if cmd_msg_id_str:
        back_cb_data += f"_{cmd_msg_id_str}"

    # Añadimos '_num' explícito al final para que album_region_handler lo entienda
    back_cb_data += "_num"

    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=back_cb_data)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def send_sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    message = cast(Message, query.message)

    if not message:
        await query.answer("El mensaje original no está disponible.", show_alert=True)
        return

    # --- LÓGICA DE COOLDOWN (2 veces cada 30 min) ---
    now = time.time()
    COOLDOWN_SECONDS = 1800
    MAX_SHOWS = 2

    if 'show_history' not in context.user_data:
        context.user_data['show_history'] = []

    context.user_data['show_history'] = [
        t for t in context.user_data['show_history']
        if now - t < COOLDOWN_SECONDS
    ]

    if len(context.user_data['show_history']) >= MAX_SHOWS:
        oldest_time = context.user_data['show_history'][0]
        wait_time = int(COOLDOWN_SECONDS - (now - oldest_time))
        minutes = wait_time // 60
        seconds = wait_time % 60
        await query.answer(
            f"⛔ Límite alcanzado (2/30min).\nEspera: {minutes}m {seconds}s.",
            show_alert=True
        )
        return
    # ------------------------------------------------

    image_path = ""
    try:
        _, pokemon_id_str, is_shiny_str, owner_id_str = query.data.split('_')
        pokemon_id, is_shiny, owner_id = int(pokemon_id_str), bool(int(is_shiny_str)), int(owner_id_str)

        if interactor_user.id != owner_id:
            await query.answer("No puedes enviar un sticker desde el álbum de otro usuario.", show_alert=True)
            return

        pokemon_data = POKEMON_BY_ID.get(pokemon_id)
        if not pokemon_data:
            await query.answer("No se encontraron los datos de este Pokémon.", show_alert=True)
            return

        context.user_data['show_history'].append(now)

        # Formato HTML y Emoji
        pokemon_display = get_formatted_name(pokemon_data, is_shiny)
        final_rarity = get_rarity(pokemon_data['category'], is_shiny)
        rarity_emoji = RARITY_VISUALS.get(final_rarity, "")

        message_text = f"{interactor_user.first_name} mostró su {pokemon_display} {rarity_emoji}"

        await context.bot.send_message(
            chat_id=message.chat_id,
            text=message_text,
            parse_mode='HTML',
            disable_notification=True
        )

        # --- RUTA DINÁMICA KANTO / JOHTO ---
        region_folder = "Johto" if pokemon_id > 151 else "Kanto"
        image_path = f"Stickers/{region_folder}/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"

        with open(image_path, 'rb') as sticker_file:
            await context.bot.send_sticker(
                chat_id=message.chat_id,
                sticker=sticker_file,
                disable_notification=True
            )

        await query.answer()

    except (ValueError, IndexError):
        await query.answer("Error al procesar la solicitud.", show_alert=True)
    except FileNotFoundError:
        logger.error(f"Sticker no encontrado: {image_path}")
        await query.answer("¡Uy! No encuentro la imagen de ese sticker.", show_alert=True)


async def refresh_codes_board(bot: Bot, chat_id: int):
    """Actualiza el mensaje fijo de códigos (si existe)."""
    board_msg_id = db.get_codes_board_msg(chat_id)
    if not board_msg_id: return

    db.delete_expired_codes()
    all_codes = db.get_all_friend_codes()

    regions = {'Europa': [], 'América': [], 'Asia': []}
    current_time = time.time()

    for row in all_codes:
        r = row['region']
        if r not in regions: r = 'Europa'
        days_left = int((row['expiry_timestamp'] - current_time) / 86400)

        # --- SOLUCIÓN: Limpiamos los nombres peligrosos para Markdown ---
        safe_nick = str(row['game_nick']).replace('_', '').replace('*', '').replace('`', '')

        line = f"🔹️ {safe_nick} - `{row['code']}` ({days_left} días)"
        regions[r].append(line)

    text = (
        "📌 **TABLÓN DE CÓDIGOS DE AMIGO** 📌\n\n"
        "🔄 Lista actualizada de códigos de amigo de Pokémon Shuffle (cada código se eliminará automáticamente en 30 días, si no se renueva antes manualmente en este mensaje):\n\n"
    )
    text += "🔶*Europa:*\n" + ("\n".join(regions['Europa']) if regions['Europa'] else "_Vacío_") + "\n\n"
    text += "🔶*América:*\n" + ("\n".join(regions['América']) if regions['América'] else "_Vacío_") + "\n\n"
    text += "🔶*Asia:*\n" + ("\n".join(regions['Asia']) if regions['Asia'] else "_Vacío_") + "\n\n"
    text += "ℹ Para añadir tu código a la lista, escribe en este chat un mensaje con el siguiente formato:\n\n Nick Región Código\n\n • Ejemplo: Sixtomaru Europa 6T4A2944 \n\n _Para eliminar un código de la lista, escribe /borrarcodigo seguido del código a eliminar, por ejemplo: /borrarcodigo 6T4A2944_"

    keyboard = [
        [InlineKeyboardButton("🔄 Renovar Código", callback_data="codes_menu_renew")]
    ]

    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=board_msg_id, text=text,
                                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        if "Message to edit not found" in str(e):
            db.query_db("DELETE FROM system_flags WHERE flag_name = ?", (f"codes_board_{chat_id}",))
        print(f"Error actualizando tablón de códigos: {e}")

def choose_random_pokemon():
    chosen_category = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
    chosen_pokemon = random.choice(POKEMON_BY_CATEGORY[chosen_category])
    is_shiny = random.random() < SHINY_CHANCE
    return chosen_pokemon, is_shiny, get_rarity(chosen_pokemon['category'], is_shiny)


async def spawn_event(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    context.chat_data.setdefault('active_events', {})

    # Limpieza de eventos viejos (3 días = 259200 segundos)
    current_time = time.time()
    TIMEOUT_SECONDS = 259200
    for msg_id, data in list(context.chat_data['active_events'].items()):
        if current_time - data.get('timestamp', 0) > TIMEOUT_SECONDS:
            del context.chat_data['active_events'][msg_id]
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except BadRequest:
                pass

    is_qualified = await is_group_qualified(chat_id, context)
    johto_unlocked = db.is_event_completed(chat_id, 'amelia_johto_unlock')

    # --- CHEQUEO DE EVENTO REGIONAL DIARIO ---
    today_str = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d')
    active_regional_event = db.get_scheduled_event(today_str)
    # ----------------------------------------

    available_events = []
    legendary_missions = ['mision_moltres', 'mision_zapdos', 'mision_articuno', 'mision_mewtwo', 'mision_hooh_lugia', 'mision_perros']

    for ev_id in EVENTS.keys():
        # Filtro de grupo cualificado para legendarios Kanto
        if not is_qualified and ev_id in legendary_missions:
            continue

        # Filtro de misiones únicas (si ya se hizo, no sale más)
        if ev_id in legendary_missions and db.is_event_completed(chat_id, ev_id):
            continue

        # --- FILTRO EVENTO ESPECIAL DE FIN DE SEMANA ---
        if active_regional_event == 'Kanto' and ev_id not in KANTO_EVENT_KEYS:
            continue
        if active_regional_event == 'Johto' and ev_id not in JOHTO_EVENT_KEYS:
            continue

        # --- FILTRO NORMAL (Si no hay evento especial) ---
        if not active_regional_event:
            # Si el evento es de Johto, el grupo DEBE haberlo desbloqueado
            if ev_id in JOHTO_EVENT_KEYS and not johto_unlocked:
                continue

        available_events.append(ev_id)

    if not available_events:
        return

    event_id = random.choice(available_events)

    # Texto especial si es un evento doble
    # --- CASO ESPECIAL: ES UN MINIJUEGO ---
    if event_id == 'minijuego_unown':
        msg = await context.bot.send_message(chat_id=chat_id, text="Generando minijuego...", disable_notification=True)

        # URL DE TU WEB (La misma que usaste en testminijuego)
        base_web_url = "https://minijuegos-pokestickercollector.netlify.app/"
        full_url = f"{base_web_url}/?c={chat_id}&m={msg.message_id}"

        bot_username = context.bot.username
        deep_link = f"https://t.me/{bot_username}?start=game_{chat_id}_{msg.message_id}"

        db.create_minigame(chat_id, msg.message_id, full_url, deep_link)

        text = (
            "🎲 **¡Un Minijuego ha aparecido!**\n"
            "Resuelve el puzzle de las Ruinas Alfa.\n\n"
            "**Resultados:**\n_Aún nadie ha jugado_"
        )

        keyboard = [[InlineKeyboardButton("Ir al juego ↗", url=deep_link)]]

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return  # Terminamos aquí porque el minijuego va por su propio camino

    # --- CASO NORMAL: EVENTOS DE HISTORIA ---
    if event_id.startswith("doble_"):
        text = "👥 <b>¡Ha aparecido un Evento Doble!</b>"
    else:
        text = "👤 <b>¡Un Evento ha aparecido!</b>"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔍 Aceptar evento", callback_data=f"event_claim_{event_id}")]])

    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='HTML')

    # Guardamos el evento con la hora actual
    context.chat_data['active_events'][msg.message_id] = {
        'event_id': event_id,
        'claimed_by': None,
        'timestamp': time.time()
    }

# --- VERSIÓN CORREGIDA Y ROBUSTA DE SPAWN_POKEMON ---
async def spawn_pokemon(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    spawned_something = False
    sticker_msg = None

    try:
        # 1. Evento
        if random.random() < EVENT_CHANCE:
            await spawn_event(context)
            spawned_something = True

        # 2. Pokémon (si no hubo evento)
        if not spawned_something:
            context.chat_data.setdefault('active_spawns', {})
            current_time = time.time()

            # Limpieza (3 días)
            TIMEOUT_SECONDS = 259200

            for msg_id in list(context.chat_data.get('active_spawns', {}).keys()):
                if current_time - context.chat_data['active_spawns'][msg_id].get('timestamp', 0) > TIMEOUT_SECONDS:
                    spawn_data = context.chat_data['active_spawns'].pop(msg_id, None)
                    if spawn_data:
                        for key in ['sticker_id', 'text_id']:
                            try:
                                await context.bot.delete_message(chat_id=chat_id, message_id=spawn_data[key])
                            except BadRequest:
                                pass

            # --- SELECCIÓN DE REGIÓN INTELIGENTE ---
            today_str = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d')
            active_regional_event = db.get_scheduled_event(today_str)

            chosen_region = 'Kanto'  # Valor por defecto seguro

            if active_regional_event:
                # Si hay evento forzado, usamos esa región
                chosen_region = active_regional_event
            else:
                # Flujo normal: Kanto siempre, Johto si está desbloqueado
                available_regions = ['Kanto']
                if db.is_event_completed(chat_id, 'amelia_johto_unlock'):
                    available_regions.append('Johto')
                chosen_region = random.choice(available_regions)

            # Elegimos categoría
            category = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]

            # Filtramos ALL_POKEMON_SPAWNABLE (Sin bebés ni Unown ni legendarios bloqueados)
            if chosen_region == 'Kanto':
                candidates = [p for p in ALL_POKEMON_SPAWNABLE if p['category'] == category and p['id'] <= 151]
            else:  # Johto
                candidates = [p for p in ALL_POKEMON_SPAWNABLE if p['category'] == category and 152 <= p['id'] <= 251]

            if not candidates:
                candidates = [p for p in ALL_POKEMON_SPAWNABLE if p['category'] == category]  # Fallback global

            pokemon_data = random.choice(candidates)
            is_shiny = random.random() < SHINY_CHANCE
            rarity = get_rarity(pokemon_data['category'], is_shiny)
            # ----------------------------------------

            # --- LÓGICA INTELIGENTE DE LEGENDARIOS (Rango S) ---
            LEGENDARY_MISSIONS = {
                144: 'mision_articuno',
                145: 'mision_zapdos',
                146: 'mision_moltres',
                150: 'mision_mewtwo',
                249: 'mision_hooh_lugia',
                250: 'mision_hooh_lugia',
                243: 'mision_perros',
                244: 'mision_perros',
                245: 'mision_perros'
            }

            if pokemon_data['category'] == 'S':
                mision_necesaria = LEGENDARY_MISSIONS.get(pokemon_data['id'])

                # Si el Pokémon elegido necesita misión y NO está completada, está BLOQUEADO
                if mision_necesaria and not db.is_event_completed(chat_id, mision_necesaria):

                    # 1. Buscamos TODOS los Legendarios ('S') de la región actual
                    if chosen_region == 'Kanto':
                        region_s_pool = [p for p in ALL_POKEMON_SPAWNABLE if p['category'] == 'S' and p['id'] <= 151]
                    else:
                        region_s_pool = [p for p in ALL_POKEMON_SPAWNABLE if
                                         p['category'] == 'S' and 152 <= p['id'] <= 251]

                    # 2. Filtramos dejando SOLO los que están desbloqueados o libres por defecto (como Mew/Celebi)
                    unlocked_s = []
                    for p in region_s_pool:
                        m = LEGENDARY_MISSIONS.get(p['id'])
                        if not m or db.is_event_completed(chat_id, m):
                            unlocked_s.append(p)

                    # 3. Elegimos uno de los libres (Siempre habrá al menos uno gracias a Mew y Celebi)
                    pokemon_data = random.choice(unlocked_s)
            # ----------------------------------------------------

            pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"

            region_folder = "Johto" if pokemon_data['id'] > 151 else "Kanto"
            image_path = f"Stickers/{region_folder}/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"

            # --- DADOS PARA EVENTO ESPECIAL DE CAZA (10% de probabilidad) ---
            is_special_hunt = random.random() < 0.10

            if is_special_hunt:
                text_message = f"¡Un <b>{pokemon_name}</b> ha aparecido, pero se ha escondido entre la hierba alta!\n<i>Tratad de conseguir una foto antes de que se vaya.</i>"
                callback_data = f"safari_hunt_{pokemon_data['id']}"
            else:
                text_message = f"¡Un <b>{pokemon_name}</b> {RARITY_VISUALS.get(rarity, '')} salvaje apareció!"
                callback_data = f"claim_0_{pokemon_data['id']}_{int(is_shiny)}_{rarity}"

            # --- ENVÍO CON AGENTE DE RESCATE ---
            try:
                with open(image_path, 'rb') as sticker_file:
                    sticker_msg = await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file, read_timeout=20,
                                                                 write_timeout=20)

                # Pausa mágica de 1 segundo para desatascar la red
                await asyncio.sleep(1.0)

                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("¡Capturar! 📷", callback_data=callback_data)]])

                text_msg = await context.bot.send_message(
                    chat_id=chat_id, text=text_message, parse_mode='HTML', reply_markup=reply_markup, read_timeout=20,
                    write_timeout=20
                )

                if is_special_hunt:
                    # Guardamos la sala de caza pero NO encendemos el reloj aún
                    context.chat_data.setdefault('safari_spawns', {})
                    context.chat_data['safari_spawns'][text_msg.message_id] = {
                        'sticker_id': sticker_msg.message_id,
                        'pokemon_id': pokemon_data['id'],
                        'is_shiny': is_shiny,
                        'rarity': rarity,
                        'p_name': pokemon_name,
                        'participants': [],
                        'job_started': False  # El reloj empieza apagado
                    }
                else:
                    context.chat_data.setdefault('active_spawns', {})
                    context.chat_data['active_spawns'][text_msg.message_id] = {
                        'sticker_id': sticker_msg.message_id,
                        'text_id': text_msg.message_id,
                        'timestamp': current_time
                    }

            except FileNotFoundError:
                logger.error(f"No se encontró la imagen: {image_path}")

            except Exception as e:
                logger.error(f"⚠️ Micro-corte en spawn para chat {chat_id}: {e}")
                if sticker_msg:
                    context.job_queue.run_once(
                        rescue_spawn_job,
                        2,
                        data={
                            'chat_id': chat_id,
                            'sticker_msg_id': sticker_msg.message_id,
                            'text_message': text_message,
                            'reply_markup': reply_markup,
                            'timestamp': current_time,
                            'is_special_hunt': is_special_hunt,  # Chivato para el Agente
                            'pokemon_id': pokemon_data['id'],
                            'is_shiny': is_shiny,
                            'rarity': rarity,
                            'p_name': pokemon_name
                        },
                        name=f"rescue_start_{chat_id}"
                    )

    except Exception as e:
        logger.error(f"⚠️ Error crítico en el ciclo de spawn para el chat {chat_id}: {e}")

    finally:
        # Reprogramar siempre
        try:
            if chat_id in db.get_active_groups():
                next_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
                context.job_queue.run_once(spawn_pokemon, next_delay, chat_id=chat_id, name=f"spawn_{chat_id}")
                logger.info(f"Próximo spawn en chat {chat_id} en {next_delay} segundos.")
        except Exception as e:
            logger.error(f"Error crítico reprogramando spawn: {e}")


# --- COMANDO SECRETO PARA EL ADMIN: FORZAR APARICIÓN ---
async def force_spawn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return

    chat_id = update.effective_chat.id
    pokemon_data, is_shiny, rarity = choose_random_pokemon()

    # Usamos nombre limpio (Sin Emoji) y formato HTML
    pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
    text_message = f"¡Un <b>{pokemon_name}</b> {RARITY_VISUALS.get(rarity, '')} salvaje apareció!"

    image_path = f"Stickers/Kanto/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"

    try:
        with open(image_path, 'rb') as sticker_file:
            sticker_msg = await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file)

        callback_data = f"claim_0_{pokemon_data['id']}_{int(is_shiny)}_{rarity}"
        button_text = "¡Capturar! 📷"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=callback_data)]])

        text_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

        context.chat_data.setdefault('active_spawns', {})
        context.chat_data['active_spawns'][text_msg.message_id] = {
            'sticker_id': sticker_msg.message_id,
            'text_id': text_msg.message_id,
            'timestamp': time.time()
        }
        await update.message.delete()

    except FileNotFoundError:
        logger.error(f"No se encontró la imagen: {image_path}")

# --- PANEL DE CONTROL / MENÚ FIJO ---

async def setup_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Solo para el admin (tú)
    if update.effective_user.id != ADMIN_USER_ID: return

    text = (
        "🔷**MENÚ DE COMANDOS**🔷\n\n"
    )

    keyboard = [
        [InlineKeyboardButton("🎒 Mochila", callback_data="panel_mochila"),
         InlineKeyboardButton("📖 Álbumdex", callback_data="panel_album")],
        [InlineKeyboardButton("🏪 Tienda", callback_data="panel_tienda"),
         InlineKeyboardButton("♻ Intercambios", callback_data="panel_intercambios")],  # <--- AQUÍ
        [InlineKeyboardButton("🏡 Guardería", callback_data="panel_guarderia")],
        [InlineKeyboardButton("🎟️ Tómbola", callback_data="panel_tombola"),
         InlineKeyboardButton("📬 Buzón", callback_data="panel_buzon")],
        [InlineKeyboardButton("💰 Dinero", callback_data="panel_dinero"),
         InlineKeyboardButton("👥 Códigos", callback_data="panel_codigos")],
        [InlineKeyboardButton("🤝 Retos Grupales", callback_data="panel_retos")]
    ]

    # Enviamos el panel (este mensaje NO se borra nunca)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    # Borramos tu comando /setup para dejarlo limpio
    await update.message.delete()


async def panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Redirigimos los botones a las funciones existentes

    if query.data == "panel_mochila":
        await inventory_cmd(update, context)
        await query.answer()

    elif query.data == "panel_dinero":
        await dinero(update, context)
        await query.answer()

    elif query.data == "panel_retos":
        await retos_cmd(update, context)
        # retos_cmd gestiona su propio flujo, no hacemos answer aquí para evitar conflictos si edita mensaje

    elif query.data == "panel_buzon":
        await buzon(update, context)
        await query.answer()

    elif query.data == "panel_tienda":
        await tienda_cmd(update, context)
        # tienda_cmd gestiona su propio flujo

    elif query.data == "panel_album":
        await albumdex_cmd(update, context)
        # albumdex_cmd gestiona su propio flujo

    elif query.data == "panel_tombola":
        await tombola_claim(update, context)
        # tombola_claim gestiona su propio flujo (alertas/edición)

    elif query.data == "panel_codigos":
        await codigos_cmd(update, context)
        # codigos_cmd gestiona su propio flujo

    elif query.data == "panel_intercambios":
        await intercambio_cmd(update, context)
        # intercambio_cmd gestiona sus propias alertas (answer) o mensajes nuevos

    elif query.data == "panel_guarderia": await guarderia_cmd(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user: return

    # --- CAMBIO: Registramos al usuario SIEMPRE, sea grupo o privado ---
    db.get_or_create_user(user.id, user.first_name)
    # -----------------------------------------------------------------
    # RECOGER JUGADORES DEL MINIJUEGO
    # RECOGER JUGADORES DEL MINIJUEGO
    if context.args and context.args[0].startswith("game_"):
        parts = context.args[0].split("_")
        if len(parts) == 3:
            try:
                c_id, m_id = int(parts[1]), int(parts[2])
                state = db.get_minigame(c_id, m_id)  # Leer de BD
                if state:
                    keyboard = [[InlineKeyboardButton("Jugar", web_app=WebAppInfo(url=state['web_url']))]]
                    await update.message.reply_text(
                        "Minijuego de las Ruinas Alfa.",
                        reply_markup=InlineKeyboardMarkup(keyboard))
                    return
                else:
                    await update.message.reply_text("Este minijuego ya ha expirado o no existe.")
                    return
            except ValueError:
                pass

    if chat.type in ['group', 'supergroup']:
        # --- CHEQUEO DE BANEO (SHADOW BAN) ---
        if db.is_group_banned(chat.id):
            msg = await update.message.reply_text(
                "⚠️ Error: No se pudo sincronizar con la base de datos regional. Inténtalo más tarde.",
                disable_notification=True
            )
            return

        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator'] and user.id != ADMIN_USER_ID:
            await update.message.reply_text("⛔ Este comando solo puede ser usado por administradores.",
                                            disable_notification=True)
            return

        member_count = await context.bot.get_chat_member_count(chat.id)
        if member_count < 10 and user.id != ADMIN_USER_ID:
            await update.message.reply_text("⚠️ El bot solo funciona en grupos con al menos 10 miembros.",
                                            disable_notification=True)
            return

        is_creator = (user.id == ADMIN_USER_ID)
        active_users_count = len(db.get_users_in_group(chat.id))

        if not is_creator and active_users_count < 4:
            await update.message.reply_text(
                f"⛔ Para comenzar la aventura, necesito calibrar el Álbumdex. Se requiere que al menos 4 personas usen algún comando (como /albumdex, /tienda, /mochila, /tombola, /buzon, /retos, /dinero, o /regalar) en este grupo.\n\n"
                f"📉 *Progreso actual:* {active_users_count}/4 usuarios validados.",
                parse_mode='Markdown', disable_notification=True
            )
            return

        db.add_group(chat.id, chat.title)
        db.set_group_active(chat.id, True)

        current_jobs = context.job_queue.get_jobs_by_name(f"spawn_{chat.id}")
        if not current_jobs:
            initial_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
            context.job_queue.run_once(spawn_pokemon, initial_delay, chat_id=chat.id, name=f"spawn_{chat.id}")
            msg = await update.message.reply_text("✅ Aparición de Pokémon salvajes activada.",
                                                  disable_notification=True)
            logger.info(f"Juego iniciado en {chat.id}. Spawn inicial en {initial_delay}s.")
        else:
            msg = await update.message.reply_text("El bot ya está en funcionamiento.", disable_notification=True)

        schedule_message_deletion(context, update.message, 5)
        schedule_message_deletion(context, msg, 30)

    else:
        # Chat privado
        await update.message.reply_text(
            "👋 ¡Hola! Ya te he registrado en la base de datos.\n"
            "A partir de ahora te avisaré por aquí si recibes premios especiales.\n\n"
            "⚠️ Recuerda: Para jugar, debes añadirme a un grupo.",
            disable_notification=True
        )

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or not update.effective_user:
        return
    if chat.type == 'private':
        await update.message.reply_text("Este comando solo funciona en grupos.")
        return
    member = await context.bot.get_chat_member(chat.id, update.effective_user.id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("⛔ Este comando solo puede ser usado por administradores.", disable_notification=True)
        return

    jobs = context.job_queue.get_jobs_by_name(f"spawn_{chat.id}")
    if not jobs:
        msg = await update.message.reply_text("El juego ya está detenido.", disable_notification=True)
        schedule_message_deletion(context, update.message, 5)
        schedule_message_deletion(context, msg, 30)
        return
    for job in jobs:
        job.schedule_removal()

    db.set_group_active(chat.id, False)
    msg = await update.message.reply_text("❌ La aparición de Pokémon salvajes se ha desactivado.", disable_notification=True)
    schedule_message_deletion(context, update.message, 5)
    schedule_message_deletion(context, msg, 30)


async def admin_regional_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Programa un evento regional para el finde."""
    if update.effective_user.id != ADMIN_USER_ID: return

    args = context.args
    if len(args) < 2:
        return await update.message.reply_text("Uso: `/eventoregion <Kanto/Johto> <sabado/domingo/finde>`",
                                               parse_mode='Markdown', disable_notification=True)

    region = args[0].capitalize()
    if region not in ['Kanto', 'Johto']:
        return await update.message.reply_text("❌ Región inválida. Usa Kanto o Johto.", disable_notification=True)

    day_arg = args[1].lower()
    today = datetime.now(TZ_SPAIN).date()
    dates_to_save = []

    # Calcular fechas (0=Lunes, 5=Sábado, 6=Domingo)
    if day_arg == 'sabado':
        days_ahead = (5 - today.weekday()) % 7
        dates_to_save.append(today + timedelta(days=days_ahead))
    elif day_arg == 'domingo':
        days_ahead = (6 - today.weekday()) % 7
        dates_to_save.append(today + timedelta(days=days_ahead))
    elif day_arg == 'finde':
        d_sat = (5 - today.weekday()) % 7
        d_sun = (6 - today.weekday()) % 7
        dates_to_save.append(today + timedelta(days=d_sat))
        dates_to_save.append(today + timedelta(days=d_sun))
    else:
        return await update.message.reply_text("❌ Día inválido. Usa sabado, domingo o finde.",
                                               disable_notification=True)

    for d in dates_to_save:
        db.add_scheduled_event(d.strftime('%Y-%m-%d'), region)

    fechas_str = ', '.join([d.strftime('%d/%m/%Y') for d in dates_to_save])
    await update.message.reply_text(f"✅ Evento de **{region}** programado para: {fechas_str}", parse_mode='Markdown',
                                    disable_notification=True)


async def admin_regalo_delibird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Regala un sobre aleatorio de Delibird a un usuario directo a la mochila."""
    if update.effective_user.id != ADMIN_USER_ID: return

    # Obtener objetivo
    target_user, _ = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text("Uso: Responde a un usuario o menciónalo: `/regalodelibird @usuario`",
                                               disable_notification=True)

    # 1. Seleccionar premio aleatorio (Como hace Delibird)
    possible_packs = [k for k in SHOP_CONFIG.keys() if k.startswith('pack_elem_')]
    prize_id = random.choice(possible_packs)
    prize_info = SHOP_CONFIG[prize_id]

    db.get_or_create_user(target_user.id, target_user.first_name)

    # 2. Guardar DIRECTAMENTE en mochila
    db.add_item_to_inventory(target_user.id, prize_id, 1)

    # 3. Mensaje público en el grupo
    await update.message.reply_text(
        f"✅ {target_user.first_name} ha recibido un sobre de Delibird ({prize_info['name']}), se ha guardado en su /mochila.",
        disable_notification=True
    )


async def admin_check_delibird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return

    # Obtenemos el timestamp de la base de datos
    saved_timestamp = db.get_delibird_schedule()

    if not saved_timestamp:
        # Si no hay fecha guardada, es que ya ha salido y borró su rastro
        await update.message.reply_text(
            "🐧💤 **Delibird ya ha pasado por aquí esta semana**",
            parse_mode='Markdown', disable_notification=True
        )
        return

    current_time = time.time()
    diff = saved_timestamp - current_time

    if diff <= 0:
        await update.message.reply_text("🐧 ¡Delibird debería estar al caer de un momento a otro!",
                                        disable_notification=True)
        return

    # Cálculos matemáticos de la cuenta atrás
    from datetime import timedelta
    td = timedelta(seconds=diff)
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    time_str = ""
    if days > 0: time_str += f"**{days}** días, "
    if hours > 0: time_str += f"**{hours}** horas, "
    if minutes > 0: time_str += f"**{minutes}** minutos y "
    time_str += f"**{seconds}** segundos"

    # Fecha absoluta en hora de España
    trigger_date = datetime.fromtimestamp(saved_timestamp, TZ_SPAIN)
    dias_es = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves',
               'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
    dia_ingles = trigger_date.strftime('%A')
    fecha_formateada = f"{dias_es.get(dia_ingles, dia_ingles)}, {trigger_date.strftime('%d/%m/%Y a las %H:%M:%S')}"

    text = (
        f"🐧 **Próximo Delibird programado:**\n"
        f"🗓 {fecha_formateada}\n\n"
        f"⏳ **Llegará en exactamente:**\n{time_str}"
    )

    await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)

async def force_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fuerza la aparición de un Evento de Historia en el grupo actual."""
    if update.effective_user.id != ADMIN_USER_ID:
        return

    chat_id = update.effective_chat.id

    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Este comando solo funciona en grupos.", disable_notification=True)
        return

    # Mismas validaciones que un spawn normal
    is_qualified = await is_group_qualified(chat_id, context)
    johto_unlocked = db.is_event_completed(chat_id, 'amelia_johto_unlock')

    available_events = []
    legendary_missions = ['mision_moltres', 'mision_zapdos', 'mision_articuno', 'mision_mewtwo', 'mision_hooh_lugia', 'mision_perros']

    for ev_id in EVENTS.keys():
        if not is_qualified and ev_id in legendary_missions:
            continue
        if ev_id in legendary_missions and db.is_event_completed(chat_id, ev_id):
            continue

        # Filtro Johto (usamos la lista oficial de claves que hemos creado)
        if ev_id in JOHTO_EVENT_KEYS and not johto_unlocked:
            continue

        available_events.append(ev_id)

    if not available_events:
        await update.message.reply_text("❌ No hay eventos disponibles para este grupo ahora mismo.",
                                        disable_notification=True)
        return

    event_id = random.choice(available_events)

    # --- CASO ESPECIAL: ES UN MINIJUEGO ---
    if event_id == 'minijuego_unown':
        msg = await context.bot.send_message(chat_id=chat_id, text="Generando minijuego...", disable_notification=True)

        # ---> PON TU ENLACE DE RENDER AQUÍ (EL DE TU WEB EN REACT/VERCEL) <---
        base_web_url = "https://minijuegos-pokestickercollector.netlify.app/"
        full_url = f"{base_web_url}/?c={chat_id}&m={msg.message_id}"

        bot_username = context.bot.username
        deep_link = f"https://t.me/{bot_username}?start=game_{chat_id}_{msg.message_id}"

        # Guardamos en la base de datos
        db.create_minigame(chat_id, msg.message_id, full_url, deep_link)

        text = (
            "🎲 **¡Un Minijuego ha aparecido!**\n"
            "Resuelve el puzzle de las Ruinas Alfa.\n\n"
            "**Resultados:**\n_Aún nadie ha jugado_"
        )

        keyboard = [[InlineKeyboardButton("Ir al juego ↗", url=deep_link)]]

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        await update.message.delete()
        return

    # --- CASO NORMAL: EVENTOS DE HISTORIA ---
    if event_id.startswith("doble_"):
        text = "👥 <b>¡Ha aparecido un Evento Doble!</b>\n"
    else:
        text = "👤 <b>¡Un Evento ha aparecido!</b>"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔍 Aceptar evento", callback_data=f"event_claim_{event_id}")]])

    # Usamos HTML igual que en el original
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='HTML')

    context.chat_data.setdefault('active_events', {})
    context.chat_data['active_events'][msg.message_id] = {
        'event_id': event_id,
        'claimed_by': None,
        'timestamp': time.time()
    }

    # Borrar el comando del admin para que no ensucie
    await update.message.delete()


async def claim_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message = cast(Message, query.message)
    if not message:
        await query.answer()
        return

    user = query.from_user
    db.get_or_create_user(user.id, user.first_name)

    if message.chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, message.chat.id)

    try:
        _, _, pokemon_id_str, is_shiny_str, rarity = query.data.split('_')
        msg_id = message.message_id
        pokemon_id, is_shiny = int(pokemon_id_str), int(is_shiny_str)
    except (ValueError, IndexError):
        await query.answer()
        return

    context.chat_data.setdefault('active_spawns', {})

    if msg_id not in context.chat_data['active_spawns']:
        await query.answer("¡Alguien ha sido más rápido que tú! 💨", show_alert=True)
        return

    spawn_data = context.chat_data['active_spawns'].get(msg_id)
    if spawn_data:
        user_cooldowns = spawn_data.get('cooldowns', {})
        last_attempt_time = user_cooldowns.get(user.id, 0)
        current_time = time.time()

        cooldown_duration = 30
        if current_time - last_attempt_time < cooldown_duration:
            time_left = math.ceil(cooldown_duration - (current_time - last_attempt_time))
            await query.answer(
                f"Espera unos {time_left} segundos a que se recargue la energía del Álbumdex antes de intentarlo de nuevo.",
                show_alert=True)
            return

    current_chance = db.get_user_capture_chance(user.id)

    if random.randint(1, 100) <= current_chance:
        claimed_spawn = context.chat_data['active_spawns'].pop(msg_id, None)
        if not claimed_spawn:
            await query.answer("¡Alguien ha sido más rápido que tú! 💨", show_alert=True)
            return

        await query.answer()

        new_chance = max(80, current_chance - 5)
        db.update_user_capture_chance(user.id, new_chance)

        # --- RANKING LOCAL (Sumar puntos al grupo) ---
        if message.chat.type in ['group', 'supergroup']:
            db.increment_group_monthly_stickers(user.id, message.chat.id)
        # ---------------------------------------------

        for key in ['sticker_id', 'text_id']:
            try:
                await context.bot.delete_message(chat_id=message.chat_id, message_id=claimed_spawn[key])
            except BadRequest:
                pass

        pokemon_data = POKEMON_BY_ID.get(pokemon_id)

        # Formato HTML
        pokemon_display = get_formatted_name(pokemon_data, is_shiny)
        rarity_emoji = RARITY_VISUALS.get(rarity, '')
        user_link = user.mention_html()

        # --- LÓGICA SMART (Captura) ---
        status = db.add_sticker_smart(user.id, pokemon_id, is_shiny)
        message_text = ""

        if status == 'NEW':
            message_text = f"🎉 ¡Felicidades, {user_link}! Has conseguido un sticker de {pokemon_display} {rarity_emoji}. Lo has registrado en tu Álbumdex."
        elif status == 'DUPLICATE':
            message_text = f"♻ ¡Genial, {user_link}! Conseguiste un sticker de {pokemon_display} {rarity_emoji}. Como solo tenías 1, te lo guardas para intercambiarlo."
        else:
            money_earned = DUPLICATE_MONEY_VALUES.get(rarity, 100)
            db.update_money(user.id, money_earned)
            message_text = f"✔️ ¡Genial, {user_link}! Conseguiste un sticker de {pokemon_display} {rarity_emoji}. Como ya lo tienes repetido, se convierte en <b>{format_money(money_earned)}₽</b> 💰."

        # --- RETO GRUPAL & DESBLOQUEO JOHTO ---
        if message.chat.type in ['group', 'supergroup']:
            db.add_pokemon_to_group_pokedex(message.chat.id, pokemon_id)
            await check_and_unlock_johto(message.chat.id, context)

        # --- PREMIOS INDIVIDUALES ---

        # Kanto (151)
        if not db.is_kanto_completed_by_user(user.id):
            if db.get_user_unique_kanto_count(user.id) >= 151:
                db.set_kanto_completed_by_user(user.id)
                db.update_money(user.id, 3000)
                db.add_item_to_inventory(user.id, 'pack_shiny_kanto', 1)
                message_text += f"\n\n🎊 ¡Felicidades {user_link}, has completado <b>Kanto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

        # Johto (91)
        if not db.is_johto_completed_by_user(user.id):
            if db.get_user_unique_johto_count(user.id) >= 100:
                db.set_johto_completed_by_user(user.id)
                db.update_money(user.id, 3000)
                db.add_item_to_inventory(user.id, 'pack_shiny_johto', 1)
                message_text += f"\n\n🎊 ¡Felicidades {user_link}, has completado <b>Johto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"

        # --- PREMIOS RETOS GRUPALES (ESTO AHORA ESTÁ FUERA DE LOS IFs INDIVIDUALES) ---
        is_qualified = await is_group_qualified(message.chat.id, context)
        chat_id = message.chat.id

        if message.chat.type in ['group', 'supergroup']:
            # 1. RETO KANTO (151)
            if not db.is_event_completed(chat_id, 'kanto_group_challenge'):
                group_unique_ids = db.get_group_unique_kanto_ids(chat_id)
                if len(group_unique_ids) >= 151:
                    db.mark_event_completed(chat_id, 'kanto_group_challenge')
                    if is_qualified:
                        group_users = db.get_users_in_group(chat_id)
                        for uid in group_users:
                            db.add_mail(uid, 'money', '2000', "Premio Reto Grupal: Kanto")
                            db.add_mail(uid, 'inventory_item', 'pack_shiny_kanto', "Premio Reto Grupal: Kanto")
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! ¡Habéis completado el reto de <b>Kanto</b>! Cada jugador ha recibido 2000₽ y un Sobre Brillante Kanto en su buzón."
                    else:
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! ¡Habéis completado el reto de <b>Kanto</b>!"

            # 2. RETO JOHTO (91)
            excluded_johto = {172, 173, 174, 175, 201, 236, 238, 239, 240}
            if not db.is_event_completed(chat_id, 'johto_group_challenge'):
                raw_johto_ids = db.get_group_unique_johto_ids(chat_id)
                valid_johto_ids = [pid for pid in raw_johto_ids if pid not in excluded_johto]
                if len(valid_johto_ids) >= 91:
                    db.mark_event_completed(chat_id, 'johto_group_challenge')
                    if is_qualified:
                        group_users = db.get_users_in_group(chat_id)
                        for uid in group_users:
                            db.add_mail(uid, 'money', '2000', "Premio Reto Grupal: Johto")
                            db.add_mail(uid, 'inventory_item', 'pack_shiny_johto', "Premio Reto Grupal: Johto")
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! ¡Habéis completado el reto de <b>Johto</b>! Cada jugador ha recibido 2000₽ y un Sobre Brillante Johto en su buzón."
                    else:
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! ¡Habéis completado el reto de <b>Johto</b>!"

        await context.bot.send_message(chat_id=message.chat_id, text=message_text, parse_mode='HTML')

    else:
        await query.answer()
        # Fallo
        new_chance = min(100, current_chance + 5)
        db.update_user_capture_chance(user.id, new_chance)

        spawn_data = context.chat_data['active_spawns'].get(msg_id)
        if spawn_data:
            if 'cooldowns' not in spawn_data: spawn_data['cooldowns'] = {}
            spawn_data['cooldowns'][user.id] = time.time()

        fail_message = await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"❌ La foto de {user.mention_html()} salió movida y no escaneó al pokémon.",
            parse_mode='HTML',
            reply_to_message_id=msg_id
        )
        schedule_message_deletion(context, fail_message, 30)


async def claim_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    message = cast(Message, query.message)
    if not message: return await query.answer()

    message_id = message.message_id
    context.chat_data.setdefault('active_events', {})
    event_info = context.chat_data['active_events'].get(message_id)

    if not event_info:
        await query.answer("Este evento ya no está disponible.", show_alert=True)
        return

    event_id = event_info['event_id']
    is_double = event_id.startswith("doble_")

    if 'participants' not in event_info:
        event_info['participants'] = []

    participants = event_info['participants']

    if any(p['id'] == user.id for p in participants):
        await query.answer("¡Ya te has unido al evento!", show_alert=True)
        return

    participants.append({'id': user.id, 'name': user.first_name, 'mention': user.mention_html()})

    if message.chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, message.chat.id)

    # CASO 1: Falta gente para evento doble
    if is_double and len(participants) < 2:
        await query.answer("¡Te has unido! Esperando a otro jugador...")
        text = f"👥 <b>¡Un Evento Doble apareció!</b>\n\n✅ <b>{user.first_name}</b> se ha unido.\n⏳ Esperando a 1 persona más..."
        await message.edit_text(text, reply_markup=message.reply_markup, parse_mode='HTML')
        return

    # CASO 2: Ya estamos todos (o es evento simple)
    await query.answer("¡El evento comienza!")

    # --- CAMBIO IMPORTANTE: Inicializamos memoria de votos ---
    if is_double:
        event_info['votes'] = {}  # Creamos el diccionario vacío para guardar elecciones
    # ---------------------------------------------------------

    event_data = EVENTS[event_id]
    step_data = event_data['steps']['start']

    if is_double:
        result = step_data['get_text_and_keyboard'](participants)
    else:
        result = step_data['get_text_and_keyboard'](user)

    text = result['text']
    keyboard_rows = []

    if 'keyboard' in result and result['keyboard']:
        for row in result['keyboard']:
            users_str = "_".join([str(p['id']) for p in participants])
            keyboard_rows.append([
                InlineKeyboardButton(button['text'], callback_data=f"{button['callback_data']}|{users_str}")
                for button in row
            ])

    reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None

    # --- CAMBIO IMPORTANTE: EDITAMOS (NO BORRAMOS) ---
    # Al editar, mantenemos el mismo message_id, así la memoria no se pierde.
    await message.edit_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def event_step_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    message = cast(Message, query.message)
    if not message: return await query.answer()

    try:
        parts = query.data.split('|')
        event_id = parts[1]
        step_id = parts[2]

        # --- LÓGICA DE RECUPERACIÓN DE PARTICIPANTES ---
        # 1. Intentamos leer de la memoria del chat (Más seguro)
        active_event = context.chat_data.get('active_events', {}).get(message.message_id)
        owner_id_str = ""

        if active_event and 'participants' in active_event:
            # Si el evento está activo en memoria, cogemos los IDs de ahí
            p_ids = [str(p['id']) for p in active_event['participants']]
            owner_id_str = "_".join(p_ids)

            raw_decision = parts[3:]

            # Si la ID del usuario se pegó al final del botón, la quitamos.
            if raw_decision and raw_decision[-1] == owner_id_str:
                decision_parts = raw_decision[:-1]
            else:
                # Si no coincide exactamente, significa que la ID no se pegó por límite de caracteres.
                # ¡NO BORRAMOS NADA! Porque lo último es el ID del Pokémon.
                decision_parts = raw_decision

        else:
            # 2. Si no está en memoria (Reinicio), leemos del botón (Fallback)
            owner_id_str = parts[-1]
            decision_parts = parts[3:-1]
        # ------------------------------------------------

        # Validar permisos
        if not owner_id_str:
            await query.answer("Este evento ha caducado.", show_alert=True)
            return

        if '_' in owner_id_str:
            valid_owners = [int(x) for x in owner_id_str.split('_')]
            if user.id not in valid_owners:
                await query.answer("Solo los participantes pueden elegir.", show_alert=True)
                return
        else:
            if user.id != int(owner_id_str):
                await query.answer("No puedes interactuar.", show_alert=True)
                return

    except (IndexError, ValueError) as e:
        logger.warning(f"Error procesando evento: {e}")
        await query.answer("Error procesando evento.", show_alert=True)
        return

    event_data = EVENTS.get(event_id)
    if not event_data:
        await query.answer(f"Error: Evento {event_id} no encontrado.", show_alert=True)
        return
    step_data = event_data['steps'].get(step_id)
    if not step_data:
        await query.answer(f"Error: Paso {step_id} no encontrado.", show_alert=True)
        return

    if 'action' in step_data:
        full_decision = decision_parts + [owner_id_str]

        # Recuperar estado (si existe)
        current_state = active_event if active_event else {}

        try:
            result = step_data['action'](
                user, full_decision,
                original_text=message.text_html,
                chat_id=message.chat_id,
                game_state=current_state
            )
        except TypeError:
            # Compatibilidad con eventos antiguos
            result = step_data['action'](
                user, full_decision,
                original_text=message.text_html,
                chat_id=message.chat_id
            )

        if result.get('event_completed') and result.get('event_id'):
            db.mark_event_completed(message.chat.id, result['event_id'])

        final_text = result.get('text', '...')

        reply_markup = None
        if 'keyboard' in result and result['keyboard']:
            keyboard_rows = []
            for row in result['keyboard']:
                # Soporte inteligente: Si es una lista simple (1D) la envuelve, si es (2D) la deja igual
                items = [row] if isinstance(row, dict) else row

                button_row = []
                for button in items:
                    base_data = button['callback_data']

                    # Intentamos pegar la ID solo si cabe
                    if len(base_data) + len(owner_id_str) < 60:
                        final_data = f"{base_data}|{owner_id_str}"
                    else:
                        final_data = base_data

                    button_row.append(InlineKeyboardButton(button['text'], callback_data=final_data))

                keyboard_rows.append(button_row)
            reply_markup = InlineKeyboardMarkup(keyboard_rows)

        try:
            await query.edit_message_text(text=final_text, reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest:
            pass

        await query.answer()

        if message.chat.type in ['group', 'supergroup']:
            await check_and_unlock_johto(message.chat.id, context)


async def safari_hunt_btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apunta al jugador en la lotería de captura y arranca el reloj si es el primero."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    msg_id = query.message.message_id

    state = context.chat_data.get('safari_spawns', {}).get(msg_id)

    if not state:
        return await query.answer("Este Pokémon ya ha huido o el evento ha caducado.", show_alert=True)

    if any(p['id'] == user.id for p in state['participants']):
        return await query.answer("La energía del Álbumdex se agotó.", show_alert=True)

    # Apuntamos al jugador
    state['participants'].append({
        'id': user.id,
        'first_name': user.first_name
    })

    # SI ES EL PRIMERO EN PULSAR, ARRANCAMOS EL RELOJ DE 60 SEGUNDOS
    if not state.get('job_started'):
        state['job_started'] = True

        context.job_queue.run_once(
            resolve_safari_catch_job,
            60,
            chat_id=chat_id,  # <--- ¡ESTA ERA LA LÍNEA MÁGICA QUE FALTABA!
            data={
                'chat_id': chat_id,
                'text_msg_id': msg_id,
                'sticker_msg_id': state['sticker_id'],
                'pokemon_id': state['pokemon_id'],
                'is_shiny': state['is_shiny'],
                'rarity': state['rarity'],
                'p_name': state['p_name']
            },
            name=f"safari_resolve_{chat_id}_{msg_id}"
        )

    await query.answer("¡Tomaste una foto!", show_alert=True)


async def buzon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = update.effective_user
    owner_user = None

    if query:
        # --- CORRECCIÓN: Detectar si viene del panel ---
        if query.data == "panel_buzon":
            owner_user = interactor_user
        else:
            try:
                parts = query.data.split('_')
                owner_id = int(parts[-1]) if len(parts) > 1 else interactor_user.id
                if interactor_user.id != owner_id:
                    await query.answer("Este buzón no es tuyo.", show_alert=True)
                    return
                owner_user = interactor_user
            except (ValueError, IndexError):
                await query.answer("Error en el botón.", show_alert=True)
                return
    else:
        owner_user = interactor_user

    db.get_or_create_user(owner_user.id, owner_user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(owner_user.id, update.effective_chat.id)

    mails = db.get_user_mail(owner_user.id)
    text_empty = "📭 Tu buzón está vacío."

    # Lógica de visualización
    if not mails:
        if query and query.data != "panel_buzon":  # Si es refresco interno, editamos
            try:
                if getattr(query.message, 'text', '') != text_empty:
                    await query.edit_message_text(text_empty)
            except BadRequest:
                pass
        else:
            # Si es comando o viene del panel, mandamos mensaje nuevo temporal
            sent_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=text_empty,
                                                          disable_notification=True)
            schedule_message_deletion(context, sent_message)
            if update.message: schedule_message_deletion(context, update.message)
        return

    text = "📬 Tienes los siguientes regalos pendientes:\n\n"
    keyboard = []

    # --- NUEVO: BOTÓN RECLAMAR TODO ---
    if len(mails) > 1:  # Solo lo mostramos si hay más de 1 correo
        keyboard.append([InlineKeyboardButton("📦 RECLAMAR TODO", callback_data=f"claimall_{owner_user.id}")])
    # ----------------------------------

    for mail in mails:
        button_text = "🎁 Reclamar: "
        if mail['item_type'] == 'money':
            button_text += f"*{format_money(int(mail['item_details']))}₽*"
        elif mail['item_type'] == 'single_sticker':
            poke_id, is_shiny = map(int, mail['item_details'].split('_'))
            poke_name = POKEMON_BY_ID.get(poke_id, {}).get('name', '?')
            button_text += f"{poke_name}{' Brillante' if is_shiny else ''}"
        else:
            button_text += ITEM_NAMES.get(mail['item_details'], "Objeto")
        text += f"✉️ *De:* Administrador (ID: `{mail['mail_id']}`)\n*Mensaje:* _{mail['message']}_\n\n"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=f"claimmail_{mail['mail_id']}_{owner_user.id}")])

    keyboard.append([InlineKeyboardButton("🔄 Actualizar", callback_data=f"buzon_refresh_{owner_user.id}")])

    if query and query.data != "panel_buzon":
        # Navegación interna (refrescar) -> Editar
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        # Comando o Panel -> Mensaje Nuevo
        sent_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                                      reply_markup=InlineKeyboardMarkup(keyboard),
                                                      parse_mode='Markdown', disable_notification=True)
        schedule_message_deletion(context, sent_message)
        if update.message:
            schedule_message_deletion(context, update.message)

async def notib_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not user: return

            db.get_or_create_user(user.id, user.first_name)
            db.set_user_notification(user.id, True)

            msg = await update.message.reply_text(
                "🔔 **Notificaciones activadas.**\nTe avisaré por privado cuando recibas regalos.\n_Para volver a desactivarlas, escribe:_ /notiboff.",
                parse_mode='Markdown', disable_notification=True)
            schedule_message_deletion(context, msg, 10)
            schedule_message_deletion(context, update.message, 10)

async def notib_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not user: return

            db.get_or_create_user(user.id, user.first_name)
            db.set_user_notification(user.id, False)

            msg = await update.message.reply_text(
                "🔕 **Notificaciones desactivadas.**\n_Para activarlas de nuevo, escribe:_ /notibon.",
                parse_mode='Markdown', disable_notification=True)
            schedule_message_deletion(context, msg, 10)
            schedule_message_deletion(context, update.message, 10)


async def claim_mail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    message = cast(Message, query.message)
    if not message:
        await query.answer("Error: El mensaje original no es accesible.", show_alert=True)
        return

    try:
        _, mail_id_str, owner_id_str = query.data.split('_')
        mail_id, owner_id = int(mail_id_str), int(owner_id_str)
        if interactor_user.id != owner_id:
            await query.answer("Este regalo no es para ti.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en el botón de reclamar.", show_alert=True)
        return

    mail_item = db.get_mail_item_by_id(mail_id)
    if not mail_item or mail_item['claimed'] or mail_item['recipient_user_id'] != owner_id:
        await query.answer("Este regalo no es para ti o ya ha sido reclamado.", show_alert=True)
        return

    db.claim_mail_item(mail_id)
    user = interactor_user
    item_type, item_details = mail_item['item_type'], mail_item['item_details']
    user_mention = user.mention_markdown()
    message_text = ""

    if item_type == 'money':
        money_amount = int(item_details)
        db.update_money(user.id, money_amount)
        message_text = f"📬 {user_mention} ha reclamado *{format_money(money_amount)}₽* de su buzón."

    elif item_type == 'inventory_item':
        db.add_item_to_inventory(user.id, item_details, 1)
        item_name = ITEM_NAMES.get(item_details, "un objeto especial")
        message_text = f"📬 {user_mention} ha reclamado *{item_name}* y lo ha guardado en su /mochila."

    elif item_type == 'single_sticker':
        poke_id, is_shiny_int = map(int, item_details.split('_'))
        is_shiny = bool(is_shiny_int)
        pokemon_data = POKEMON_BY_ID.get(poke_id)

        if not pokemon_data:
            logger.error(f"Error al reclamar mail: Pokémon ID {poke_id} no encontrado.")
            message_text = f"{user_mention}, intentaste reclamar un Pokémon que ya no existe."
        else:
            pokemon_name = get_formatted_name(pokemon_data, is_shiny)
            rarity = get_rarity(pokemon_data['category'], is_shiny)
            rarity_emoji = RARITY_VISUALS.get(rarity, '')

            # --- NUEVA LÓGICA SMART (1º, 2º, 3º+) ---
            status = db.add_sticker_smart(user.id, poke_id, is_shiny)

            if status == 'NEW':
                # 1ª Vez
                message_text = f"📬 ¡Felicidades, {user_mention}! Has reclamado un sticker de *{pokemon_name} {rarity_emoji}*. Lo has registrado en tu Álbumdex."
            elif status == 'DUPLICATE':
                # 2ª Vez
                message_text = f"📬 ¡Genial, {user_mention}! Has reclamado un sticker de *{pokemon_name} {rarity_emoji}*. Como solo tenías 1, te lo guardas para intercambiarlo."
            else:
                # 3ª Vez (MAX) -> Dinero
                money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                db.update_money(user.id, money)
                message_text = f"📬 {user_mention} reclamó *{pokemon_name} {rarity_emoji}*. Ya lo tenía repe, ¡así que recibe *{format_money(money)}₽*!"
            # ----------------------------------------

            # Nota: Al venir del buzón (regalo global), NO se suma al reto grupal ni ranking
            # para no desbalancear competiciones locales con regalos externos.

    if message_text:
        await context.bot.send_message(chat_id=message.chat_id, text=message_text, parse_mode='Markdown')
    await buzon(update, context)


async def claim_all_mail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reclama todos los correos del buzón de golpe y muestra un resumen."""
    query = update.callback_query
    interactor_user = query.from_user

    try:
        owner_id = int(query.data.split('_')[1])
        if interactor_user.id != owner_id:
            await query.answer("Este buzón no es tuyo.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en el botón.", show_alert=True)
        return

    # 1. Recuperamos todos los correos sin leer
    mails = db.get_user_mail(owner_id)
    if not mails:
        await query.answer("Tu buzón ya está vacío.", show_alert=True)
        return await buzon(update, context)

    total_money = 0
    items_collected = {}  # Para agrupar los sobres iguales (Ej: 3 Sobre Grande Nacional)
    stickers_collected = []  # Para listar los Pokémon sueltos

    # 2. Procesamos cada correo
    for mail in mails:
        mail_id = mail['mail_id']
        item_type = mail['item_type']
        item_details = mail['item_details']

        # Marcamos como leído en la base de datos
        db.claim_mail_item(mail_id)

        if item_type == 'money':
            total_money += int(item_details)

        elif item_type == 'inventory_item':
            db.add_item_to_inventory(owner_id, item_details, 1)
            item_name = ITEM_NAMES.get(item_details, "Objeto Desconocido")
            items_collected[item_name] = items_collected.get(item_name, 0) + 1

        elif item_type == 'single_sticker':
            poke_id, is_shiny_int = map(int, item_details.split('_'))
            is_shiny = bool(is_shiny_int)
            pokemon_data = POKEMON_BY_ID.get(poke_id)

            if pokemon_data:
                p_display = get_formatted_name(pokemon_data, is_shiny)
                rarity = get_rarity(pokemon_data['category'], is_shiny)
                r_emoji = RARITY_VISUALS.get(rarity, '')

                status = db.add_sticker_smart(owner_id, poke_id, is_shiny)
                if status == 'NEW':
                    stickers_collected.append(f"🔸 🆕 {p_display} {r_emoji}")
                elif status == 'DUPLICATE':
                    stickers_collected.append(f"🔸 ♻️ {p_display} {r_emoji}")
                else:
                    money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                    total_money += money
                    stickers_collected.append(f"🔸 ✔️ {p_display} {r_emoji} (+{format_money(money)}₽)")

    # 3. Dar el dinero total acumulado (si hay)
    if total_money > 0:
        db.update_money(owner_id, total_money)

    # 4. Construir el Mensaje de Resumen
    summary_text = f"📦 **¡Buzón Vaciado!**\n{interactor_user.mention_markdown()} ha recogido:\n\n"

    if items_collected:
        for name, qty in items_collected.items():
            summary_text += f"- {qty}x {name}\n"

    if stickers_collected:
        summary_text += "\n**Stickers:**\n" + "\n".join(stickers_collected) + "\n"

    if total_money > 0:
        summary_text += f"\n💰 **Dinero total recogido:** {format_money(total_money)}₽"

    # 5. Enviar mensaje y recargar buzón
    await context.bot.send_message(chat_id=query.message.chat_id, text=summary_text, parse_mode='Markdown')
    await buzon(update, context)


async def buzon_refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await buzon(update, context)


async def tombola_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return

    db.get_or_create_user(user.id, user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, update.effective_chat.id)

    # Obtenemos la ID del mensaje del usuario para borrarlo luego
    cmd_msg_id = update.message.message_id if update.message else 0

    # Verificar si ya jugó
    if db.get_last_daily_claim(user.id) == datetime.now(TZ_SPAIN).strftime('%Y-%m-%d'):
        msg = await update.message.reply_text("⏳ Ya has probado suerte hoy. ¡Vuelve mañana!", disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        schedule_message_deletion(context, update.message, 5)
        return

    text = ("🎟️ *Tómbola Diaria* 🎟️\n\n"
            "Prueba suerte una vez al día para ganar premios.\n"
            "🟤 100₽ | 🟢 200₽ | 🔵 400₽ | 🟡 ¡Sobre Mágico!")

    # PASAMOS LA ID DEL MENSAJE DEL USUARIO EN EL CALLBACK
    # Estructura: tombola_claim_USERID_MSGID
    keyboard = [[InlineKeyboardButton("Probar Suerte ✨", callback_data=f"tombola_claim_{user.id}_{cmd_msg_id}")]]

    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                          disable_notification=True)

    # Programamos borrado por si no pulsa el botón
    schedule_message_deletion(context, update.message, 5)
    schedule_message_deletion(context, msg, 60)

# --- MODIFICADO: Lógica de Tómbola Pública ---
async def tombola_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    message = update.effective_message
    chat_id = message.chat_id

    db.get_or_create_user(interactor_user.id, interactor_user.first_name)

    is_public = (query.data == "tombola_claim_public")
    is_panel = (query.data == "panel_tombola")

    owner_id = interactor_user.id
    user_cmd_msg_id = None

    if not is_public and not is_panel:
        try:
            parts = query.data.split('_')
            owner_id = int(parts[2])
            if len(parts) > 3: user_cmd_msg_id = int(parts[3])

            if interactor_user.id != owner_id:
                await query.answer("No puedes reclamar la tómbola de otra persona.", show_alert=True)
                return
        except (ValueError, IndexError):
            await query.answer("Error en el botón.", show_alert=True)
            return

    # Verificar si ya jugó hoy
    today_str = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d')
    if db.get_last_daily_claim(owner_id) == today_str:
        await query.answer("⏳ Ya has probado suerte hoy. ¡Vuelve mañana!", show_alert=True)
        if not is_public and not is_panel:
            try:
                await message.delete()
                if user_cmd_msg_id: await context.bot.delete_message(chat_id=chat_id, message_id=user_cmd_msg_id)
            except BadRequest:
                pass
        return

    # Dar premio
    db.update_last_daily_claim(owner_id, today_str)
    prize = random.choices(DAILY_PRIZES, weights=DAILY_WEIGHTS, k=1)[0]

    list_line = ""
    alert_text = ""

    if prize['type'] == 'money':
        db.update_money(owner_id, prize['value'])
        safe_name = interactor_user.first_name.replace('*', '').replace('_', '')
        list_line = f"- {safe_name}: {prize['emoji']} {prize['value']}₽"
        alert_text = f"¡{prize['emoji']} Has ganado {prize['value']}₽!"
    else:
        db.add_item_to_inventory(owner_id, prize['value'])
        safe_name = interactor_user.first_name.replace('*', '').replace('_', '')
        list_line = f"- {safe_name}: {prize['emoji']} Sobre Mágico"
        alert_text = f"¡{prize['emoji']} PREMIO GORDO! Un Sobre Mágico."

    # --- ACTUALIZAR LISTA USANDO VARIABLE GLOBAL ---

    # Aseguramos que existe el registro para este chat
    if chat_id not in TOMBOLA_STATE:
        TOMBOLA_STATE[chat_id] = {'msg_id': None, 'winners': []}


    # Añadimos ganador
    TOMBOLA_STATE[chat_id]['winners'].append(list_line)

    base_header = (
        "🎟️ *Tómbola Diaria* 🎟️\n\n"
        "¡Prueba suerte una vez al día!\n Estos son los premios, dependiendo de la bola que saques:\n"
        "🟤 100₽ | 🟢 200₽ | 🔵 400₽ | 🟡 ¡Sobre Mágico!"
    )

    full_text = base_header + "\n\nResultados:\n" + "\n".join(TOMBOLA_STATE[chat_id]['winners'])

    # Recuperamos la ID del mensaje oficial
    daily_msg_id = TOMBOLA_STATE[chat_id]['msg_id']
    keyboard = [[InlineKeyboardButton("Probar Suerte ✨", callback_data="tombola_claim_public")]]

    # Intentar editar el mensaje oficial
    if daily_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=daily_msg_id,
                text=full_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except BadRequest:
            # Si falla (ej: mensaje borrado), enviamos uno nuevo y actualizamos la ID
            msg = await context.bot.send_message(chat_id=chat_id, text=full_text,
                                                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                                 disable_notification=True)
            TOMBOLA_STATE[chat_id]['msg_id'] = msg.message_id
    else:
        # Si no había ID registrada (ej: reinicio), enviamos uno nuevo
        msg = await context.bot.send_message(chat_id=chat_id, text=full_text,
                                             reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                             disable_notification=True)
        TOMBOLA_STATE[chat_id]['msg_id'] = msg.message_id

    # Limpieza comando personal
    if not is_public and not is_panel:
        try:
            await message.delete()
            if user_cmd_msg_id: await context.bot.delete_message(chat_id=chat_id, message_id=user_cmd_msg_id)
        except BadRequest:
            pass

    await query.answer(alert_text, show_alert=True)


async def tienda_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = update.effective_user
    cmd_msg_id = None
    owner_user = None
    is_panel = (query and query.data == "panel_tienda")

    if query:
        if is_panel:
            owner_user = interactor_user
        else:
            try:
                parts = query.data.split('_')
                if len(parts) > 3 and parts[-1].isdigit() and parts[-2].isdigit():
                    owner_id = int(parts[-2])
                    cmd_msg_id = int(parts[-1])
                else:
                    owner_id = int(parts[-1])

                if interactor_user.id != owner_id:
                    await query.answer("Esta tienda no es tuya.", show_alert=True)
                    return
                owner_user = interactor_user
            except:
                return
    else:
        owner_user = interactor_user
        if update.message: cmd_msg_id = update.message.message_id

    db.get_or_create_user(owner_user.id, owner_user.first_name)
    user_money = db.get_user_money(owner_user.id)

    text = (f"🏪 *Tienda de Sobres* 🏪\n\n"
            f"Tu saldo: **{format_money(user_money)}₽**\n\n"
            "Selecciona una categoría:")

    # Preparamos el sufijo de ID
    suffix = f"_{interactor_user.id}"
    if cmd_msg_id: suffix += f"_{cmd_msg_id}"  # <--- IMPORTANTE: Pasamos el ID del mensaje

    keyboard = [
        [InlineKeyboardButton("🗾 Sobres Nacionales", callback_data=f"shop_cat_national{suffix}")],
        [InlineKeyboardButton("🔸 Sobres Kanto", callback_data=f"shop_cat_kanto{suffix}")],
        [InlineKeyboardButton("🔹 Sobres Johto", callback_data=f"shop_cat_johto{suffix}")],
        [InlineKeyboardButton("❌ Salir", callback_data=f"shop_close{suffix}")]
    ]

    if query and not is_panel:
        try:
            refresh_deletion_timer(context, query.message, 60)

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            if query.data.startswith("shop_refresh_"): await query.answer()
        except BadRequest:
            pass
    else:
        msg = await context.bot.send_message(update.effective_chat.id, text,
                                             reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                             disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        if update.message: schedule_message_deletion(context, update.message, 60)


async def tienda_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    cat = parts[2]  # national, kanto, johto
    owner_id = int(parts[3])

    # Intentar recuperar el msg_id del comando original si existe
    cmd_msg_id = parts[4] if len(parts) > 4 else ""

    if query.from_user.id != owner_id:
        await query.answer("Esta tienda no es tuya.", show_alert=True)
        return

    filtered_items = []

    for item_id, details in SHOP_CONFIG.items():
        if details.get('hidden'): continue

        region = details.get('region_filter')

        # Filtro Nacional: Los que NO tienen region_filter Y tienen "national" en el ID
        if cat == 'national' and not region and 'national' in item_id:
            filtered_items.append((item_id, details))

        # Filtro Kanto
        elif cat == 'kanto' and region == 'Kanto':
            filtered_items.append((item_id, details))

        # Filtro Johto
        elif cat == 'johto' and region == 'Johto':
            filtered_items.append((item_id, details))

    # --- CORRECCIÓN DE ORDEN ---
    # Ordenamos por una tupla: (Es Mágico, Precio)
    # Python ordena False (0) antes que True (1), así que los normales salen primero.
    filtered_items.sort(key=lambda x: (x[1].get('is_magic', False), x[1]['price']))
    # ---------------------------

    keyboard = []
    for item_id, details in filtered_items:
        # Pasamos cmd_msg_id al prebuy para que se pueda borrar al final
        cb_data = f"prebuy_{item_id}_{owner_id}"
        if cmd_msg_id: cb_data += f"_{cmd_msg_id}"

        btn_text = f"{details['name']} - {format_money(details['price'])}₽"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

    # Volver (pasando ID mensaje)
    cb_back = f"shop_refresh_{owner_id}"
    if cmd_msg_id: cb_back += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=cb_back)])

    # Obtenemos el dinero actual del usuario
    user_money = db.get_user_money(owner_id)

    # Formateamos el nombre de la categoría
    cat_display = "Nacionales" if cat == 'national' else f"de {cat.capitalize()}"

    text = (f"📂 **Sobres {cat_display}**\n\n"
            f"Tu saldo: **{format_money(user_money)}₽**\n\n"
            f"Elige un sobre:")

    refresh_deletion_timer(context, query.message, 60)

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def prebuy_pack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    try:
        parts = query.data.split('_')
        if parts[-1].isdigit() and parts[-2].isdigit():
            cmd_msg_id = parts[-1]
            owner_id = int(parts[-2])
            item_id = '_'.join(parts[1:-2])
        else:
            cmd_msg_id = ""
            owner_id = int(parts[-1])
            item_id = '_'.join(parts[1:-1])

        if interactor_user.id != owner_id:
            await query.answer("Esta tienda no es tuya.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en el botón.", show_alert=True)
        return

    pack_details = SHOP_CONFIG.get(item_id)
    if not pack_details:
        await query.answer("Este sobre ya no está disponible.", show_alert=True)
        return

    # --- CAMBIO: AÑADIDA LA DESCRIPCIÓN DEL SOBRE ---
    text = (f"🛒 **Confirmar Compra**\n\n"
            f"_{pack_details.get('desc', 'Un sobre misterioso.')}_\n\n"
            f"¿Estás seguro de que quieres comprar:\n"
            f"**{pack_details['name']}** por **{format_money(pack_details['price'])}₽**?")

    confirm_data = f"confirmbuy_{item_id}_{owner_id}"
    if cmd_msg_id: confirm_data += f"_{cmd_msg_id}"

    cancel_data = f"shop_refresh_{owner_id}"
    if cmd_msg_id: cancel_data += f"_{cmd_msg_id}"

    keyboard = [
        [InlineKeyboardButton("✅ Confirmar", callback_data=confirm_data)],
        [InlineKeyboardButton("❌ Cancelar", callback_data=cancel_data)]
    ]

    refresh_deletion_timer(context, query.message, 60)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    await query.answer()

# --- NUEVO: COMPRA REAL (Confirmada) ---
async def confirm_buy_pack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    try:
        parts = query.data.split('_')
        # Formatos posibles:
        # confirmbuy_item_id_OWNERID (Desde Panel)
        # confirmbuy_item_id_OWNERID_MSGID (Desde Comando)

        if len(parts) > 3 and parts[-1].isdigit() and parts[-2].isdigit():
            # Caso con MSG_ID
            owner_id = int(parts[-2])
            item_id = '_'.join(parts[1:-2])
        else:
            # Caso sin MSG_ID (Panel)
            owner_id = int(parts[-1])
            item_id = '_'.join(parts[1:-1])

        if interactor_user.id != owner_id:
            await query.answer("Esta tienda no es tuya.", show_alert=True)
            return

    except (ValueError, IndexError):
        await query.answer("Error en el botón de compra.", show_alert=True)
        return

    pack_details = SHOP_CONFIG.get(item_id)
    if not pack_details:
        await query.answer("Este sobre ya no está disponible.", show_alert=True)
        return

    user_money = db.get_user_money(owner_id)
    pack_price = pack_details['price']

    if user_money >= pack_price:
        db.update_money(owner_id, -pack_price)
        db.add_item_to_inventory(owner_id, item_id, 1)

        await query.answer()  # Quitamos el show_alert de aquí para que no moleste

        # --- NUEVO MENÚ PARA PREGUNTAR SI QUIERE ABRIRLO ---
        text = (f"✅ ¡Has comprado **{pack_details['name']}**!\n\n"
                f"¿Quieres abrirlo?")

        cb_open = f"openpack_{item_id}_{owner_id}"
        cb_no = f"shop_refresh_{owner_id}"

        if len(parts) > 3 and parts[-1].isdigit() and parts[-2].isdigit():
            cb_no += f"_{parts[-1]}"  # Si hay cmd_msg_id, se lo pasamos al botón de NO

        keyboard = [
            [InlineKeyboardButton("✅ Abrir", callback_data=cb_open),
             InlineKeyboardButton("❌ No", callback_data=cb_no)]
        ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    else:
        needed = pack_price - user_money
        await query.answer(f"❌ No tienes suficiente dinero. Te faltan {format_money(needed)}₽.", show_alert=True)
        await tienda_cmd(update, context)

async def tienda_close_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    try:
        parts = query.data.split('_')
        owner_id = int(parts[2])
        cmd_msg_id = int(parts[3]) if len(parts) > 3 else None

        message = cast(Message, query.message)

        if interactor_user.id != owner_id:
            await query.answer("No puedes cerrar la tienda de otra persona.", show_alert=True)
            return

        await message.delete()

        if cmd_msg_id:
            try:
                await context.bot.delete_message(chat_id=message.chat_id, message_id=cmd_msg_id)
            except BadRequest:
                logger.info(f"El mensaje de comando de tienda ({cmd_msg_id}) ya no existía.")
        await query.answer()

    except (ValueError, IndexError):
        await query.answer("Error al procesar el botón de cerrar.", show_alert=True)
        return


async def inventory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detectar origen (Comando/Panel o Botón de cambio de modo)
    query = update.callback_query

    # Por defecto, modo sobres
    mode = "packs"

    if query:
        # Si viene de un botón "inv_mode_MODO_OWNERID"
        if query.data.startswith("inv_mode_"):
            parts = query.data.split("_")
            mode = parts[2]  # packs, special, eggs

            # --- SEGURIDAD: Verificar dueño ---
            if len(parts) > 3:
                owner_id = int(parts[3])
                if query.from_user.id != owner_id:
                    await query.answer("Esta mochila no es tuya.", show_alert=True)
                    return
                user_id = owner_id
            else:
                user_id = query.from_user.id

            refresh_deletion_timer(context, query.message, 60)

        else:
            # Viene del Panel (panel_mochila)
            user_id = query.from_user.id

    else:
        # Viene de comando de texto /mochila
        user_id = update.effective_user.id

    db.get_or_create_user(user_id, "")
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user_id, update.effective_chat.id)

    items = db.get_user_inventory(user_id)
    text = ""
    keyboard_buttons = []
    has_items = False

    # --- BOTONES DE NAVEGACIÓN (CON ID DE DUEÑO) ---
    nav_row = []
    if mode != "packs": nav_row.append(InlineKeyboardButton("🎴 Sobres", callback_data=f"inv_mode_packs_{user_id}"))
    if mode != "eggs": nav_row.append(InlineKeyboardButton("🥚 Huevos", callback_data=f"inv_mode_eggs_{user_id}"))
    if mode != "special": nav_row.append(InlineKeyboardButton("🪶 Otros", callback_data=f"inv_mode_special_{user_id}"))
    keyboard_buttons.append(nav_row)

    # --- MODO HUEVOS ---
    if mode == "eggs":
        text = "🎒 <b>Mochila - Huevos</b>\n\n"
        egg = db.get_user_egg(user_id)

        if egg:
            remaining = egg['hatch_time'] - time.time()
            if remaining <= 0:
                status_text = "¡Está eclosionando! (Revisa tu privado pronto)"
            else:
                status_text = "En incubación"

            text += f"🥚 <b>Huevo Guardería</b>\nEstado: {status_text}"
            keyboard_buttons.append([InlineKeyboardButton("Examinar Huevo", callback_data=f"egg_check_{user_id}")])
            has_items = True
        else:
            text += "<i>No tienes ningún huevo.</i>"
            has_items = True

            # --- MODO SOBRES ---
    elif mode == "packs":
        text = "🎒 <b>Mochila - Sobres</b>\n\n"
        for item in items:
            item_id = item['item_id']
            qty = item['quantity']
            if item_id in PACK_CONFIG:
                raw_name = ITEM_NAMES.get(item_id, 'Objeto')
                item_name = f"{raw_name} 🎴"
                # CORRECCIÓN: Usar user_id en lugar de user.id
                keyboard_buttons.append(
                    [InlineKeyboardButton(f"Abrir {raw_name}", callback_data=f"openpack_{item_id}_{user_id}")])
                text += f"🔸️ {item_name} x{qty}\n"
                has_items = True

    # --- MODO ESPECIALES ---
    else:
        text = "🎒 <b>Mochila - Objetos Especiales</b>\n\n"
        for item in items:
            item_id = item['item_id']
            qty = item['quantity']
            if item_id.startswith('lottery_ticket_') or item_id in SPECIAL_ITEMS_DATA:
                if item_id.startswith('lottery_ticket_'):
                    item_name = "Ticket de lotería ganador"
                else:
                    data = SPECIAL_ITEMS_DATA[item_id]
                    item_name = f"{data['name']} {data['emoji']}"

                # CORRECCIÓN: Usar user_id en lugar de user.id
                row = [
                    InlineKeyboardButton("👀 Ver",
                                         callback_data=f"view{'ticket' if 'ticket' in item_id else 'special'}_{item_id}_{user_id}"),
                    InlineKeyboardButton("📢 Mostrar", callback_data=f"showspecial_{item_id}_{user_id}")
                ]
                keyboard_buttons.append(row)
                text += f"🔸️ {item_name} x{qty}\n"
                has_items = True

    if not has_items and mode != "eggs":
        text += "<i>Bolsillo vacío.</i>"

        # --- AÑADIMOS EL BOTÓN CERRAR AQUÍ ---
    keyboard_buttons.append([InlineKeyboardButton("❌ Cerrar", callback_data=f"inv_close_{user_id}")])

    markup = InlineKeyboardMarkup(keyboard_buttons)

    # ENVÍO O EDICIÓN (TODO EN HTML)
    if query and query.data.startswith("inv_mode_"):
        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
        except BadRequest:
            pass
    else:
        if query: await query.answer()  # Panel

        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=markup,
            parse_mode='HTML',
            disable_notification=True
        )
        schedule_message_deletion(context, sent_message, 60)
        if update.message:
            schedule_message_deletion(context, update.message, 5)


async def inv_close_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cierra y borra el mensaje de la mochila."""
    query = update.callback_query
    try:
        owner_id = int(query.data.split('_')[2])
        if query.from_user.id != owner_id:
            return await query.answer("No es tu mochila.", show_alert=True)

        await query.message.delete()
        await query.answer()
    except:
        await query.answer("Error al cerrar.", show_alert=True)


async def egg_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    # --- SEGURIDAD: Verificar dueño ---
    try:
        # Formato: egg_check_OWNERID
        owner_id = int(query.data.split('_')[2])

        if user.id != owner_id:
            await query.answer("Este menú no es tuyo.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en el botón.", show_alert=True)
        return
    # ----------------------------------

    egg = db.get_user_egg(user.id)
    if not egg:
        await query.answer("Ya no tienes el huevo (quizás ya eclosionó).", show_alert=True)
        return

    remaining = egg['hatch_time'] - time.time()

    # Si ya se pasó el tiempo pero el job no lo ha borrado aún
    if remaining <= 0:
        await query.answer("¡Está eclosionando! Revisa tus mensajes privados.", show_alert=True)
        return

    hours_left = remaining / 3600

    if hours_left > 30:
        text = "Parece que aún falta mucho para que eclosione."
    elif hours_left > 6:
        text = "A veces se mueve, ¿qué saldrá de aquí?"
    else:
        text = "Se oyen ruidos dentro, debe de estar a punto de abrirse."

    await query.answer(text, show_alert=True)


async def egg_hatch_job(context: ContextTypes.DEFAULT_TYPE):
    """Revisa huevos listos para abrirse."""
    current_time = time.time()
    ready_eggs = db.get_ready_eggs(current_time)

    for egg in ready_eggs:
        user_id = egg['user_id']
        pokemon_id = egg['pokemon_id']
        is_shiny = bool(egg['is_shiny'])

        # 1. Borrar huevo y DAR PREMIO POR CUIDARLO
        db.remove_user_egg(user_id)
        db.update_money(user_id, 400)  # <--- PREMIO GUARDERÍA

        # 2. Datos Pokémon
        p_data = POKEMON_BY_ID.get(pokemon_id)
        if not p_data: continue

        p_name_clean = f"{p_data['name']}{' brillante ✨' if is_shiny else ''}"
        p_display = get_formatted_name(p_data, is_shiny)

        # 3. Añadir a colección
        status = db.add_sticker_smart(user_id, pokemon_id, is_shiny)

        # 4. Mensaje Estado
        rarity = get_rarity(p_data['category'], is_shiny)
        r_emoji = RARITY_VISUALS.get(rarity, '')

        final_msg = ""
        if status == 'NEW':
            final_msg = f"🎉 ¡Felicidades! Has conseguido un sticker de {p_display} {r_emoji}. Lo has registrado en tu Álbumdex."
        elif status == 'DUPLICATE':
            final_msg = f"♻ ¡Genial! Conseguiste un sticker de {p_display} {r_emoji}. Como solo tenías 1, te lo guardas para intercambiarlo."
        else:
            money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
            db.update_money(user_id, money)
            final_msg = f"✔️ ¡Genial! Conseguiste un sticker de {p_display} {r_emoji}. Como ya lo tenías repetido, se convierte en <b>{format_money(money)}₽</b> 💰."

        user_name = "El entrenador"
        try:
            chat = await context.bot.get_chat(user_id)
            if chat.first_name: user_name = chat.first_name
        except:
            pass

        # --- DETECTOR DE ÁLBUM COMPLETO ---
        premios_extra = ""
        user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

        if not db.is_kanto_completed_by_user(user_id):
            if db.get_user_unique_kanto_count(user_id) >= 151:
                db.set_kanto_completed_by_user(user_id)
                db.update_money(user_id, 3000)
                db.add_item_to_inventory(user_id, 'pack_shiny_kanto', 1)
                premios_extra += f"\n\n🎊 ¡Felicidades {user_mention}, has completado <b>Kanto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

        if not db.is_johto_completed_by_user(user_id):
            if db.get_user_unique_johto_count(user_id) >= 100:
                db.set_johto_completed_by_user(user_id)
                db.update_money(user_id, 3000)
                db.add_item_to_inventory(user_id, 'pack_shiny_johto', 1)
                premios_extra += f"\n\n🎊 ¡Felicidades {user_mention}, has completado <b>Johto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"
        # -----------------------------------

        text = (
            "🐣 <b>¡Anda!, ¡el huevo se ha abierto!</b>\n\n"
            f"¡Ha nacido un <b>{p_name_clean}</b>!\n\n"
            f"{user_name} lo escanea en su Álbumdex y lo devuelve a la guardería Pokémon.\n\n"
            f"{final_msg}\n\n"
            "La persona encargada de la guardería te da las gracias y <b>400₽</b> por cuidarlo."
            f"{premios_extra}"
        )

        # 5. Notificar
        try:
            # Ruta de imagen dinámica
            if pokemon_id > 20000:
                region_folder = "Unown"
            else:
                region_folder = "Johto" if pokemon_id > 151 else "Kanto"

            path = f"Stickers/{region_folder}/{'Shiny/' if is_shiny else ''}{pokemon_id}{'s' if is_shiny else ''}.png"

            with open(path, 'rb') as f:
                await context.bot.send_sticker(chat_id=user_id, sticker=f)

            # --- AÑADIMOS EL BOTÓN AQUÍ ---
            keyboard = [[InlineKeyboardButton("Recibir otro 🥚", callback_data=f"egg_claim_{user_id}")]]
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass

async def clean_expired_minigames_job(context: ContextTypes.DEFAULT_TYPE):
    """Tarea nocturna para limpiar minijuegos viejos de Supabase."""
    db.delete_expired_minigames()
    logger.info("🧹 Limpieza de minijuegos caducados completada.")

async def delete_pack_stickers(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    for mid in job_data['sticker_ids']:
        try:
            await context.bot.delete_message(chat_id=job_data['chat_id'], message_id=mid)
        except BadRequest:
            pass
    logger.info(f"Borrados {len(job_data['sticker_ids'])} stickers en {job_data['chat_id']}")


async def open_pack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    message = cast(Message, query.message)

    if not message:
        await query.answer("Error: El mensaje original no es accesible.", show_alert=True)
        return

    try:
        parts = query.data.split('_')
        owner_id_str = parts[-1]
        item_id = '_'.join(parts[1:-1])
        owner_id = int(owner_id_str)

        if interactor_user.id != owner_id:
            await query.answer("No puedes abrir el sobre de otra persona.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en el botón de abrir sobre.", show_alert=True)
        return

    user = interactor_user
    current_time = time.time()
    last_open_time = context.chat_data.get('last_pack_open_time', 0)

    if current_time - last_open_time < PACK_OPEN_COOLDOWN:
        time_left = round(PACK_OPEN_COOLDOWN - (current_time - last_open_time))
        await query.answer(f"Hay que esperar {time_left}s para abrir otro sobre en el grupo.", show_alert=True)
        return

    if context.chat_data.get('is_opening_pack', False):
        await query.answer("⏳ Alguien ya está abriendo un sobre. Por favor, espera a que termine.", show_alert=True)
        return

    if not any(i['item_id'] == item_id and i['quantity'] > 0 for i in db.get_user_inventory(user.id)):
        await query.answer("¡No tienes este sobre!", show_alert=True)
        await message.delete()
        return

    try:
        context.chat_data['is_opening_pack'] = True

        # Eliminar el mensaje del inventario
        await message.delete()

        db.remove_item_from_inventory(user.id, item_id, 1)

        opening_message = await context.bot.send_message(
            message.chat_id,
            f"🎴 ¡{user.mention_html()} ha abierto un <b>{ITEM_NAMES.get(item_id)}</b>! ",
            parse_mode='HTML',
            disable_notification=True
        )

        pack_config = SHOP_CONFIG.get(item_id, {})
        pack_size = pack_config.get('size', 1)
        is_magic = pack_config.get('is_magic', False)
        pack_results = []
        message_ids_to_delete = [opening_message.message_id]

        # --- LÓGICA DE GENERACIÓN ---

        # 1. Sobre Brillante Kanto
        if item_id == 'pack_shiny_kanto':
            kanto_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            p_data = random.choice(kanto_pool)
            pack_results.append({'data': p_data, 'is_shiny': True})

        # 2. Sobre Brillante Johto
        elif item_id == 'pack_shiny_johto':
            johto_pool = [p for p in ALL_POKEMON_PACKS if 152 <= p['id'] <= 251]
            p_data = random.choice(johto_pool)
            pack_results.append({'data': p_data, 'is_shiny': True})

        # 2B. Sobre Brillante Unown (NUEVO)
        elif item_id == 'pack_shiny_unown':
            from pokemon_data import POKEMON_UNOWN
            p_data = random.choice(POKEMON_UNOWN)
            pack_results.append({'data': p_data, 'is_shiny': True})

        # 3. Sobre Especial Kanto (Doble probabilidad shiny)
        elif item_id == 'pack_elem_especial':
            kanto_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            for _ in range(pack_size):
                is_shiny = random.random() < (SHINY_CHANCE * 2)
                cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                cat_pool = [p for p in kanto_pool if p['category'] == cat]
                if not cat_pool: cat_pool = kanto_pool
                p_data = random.choice(cat_pool)
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})

        # 3B. Sobre Especial Johto (NUEVO - Doble probabilidad shiny)
        elif item_id == 'pack_special_johto':
            johto_pool = [p for p in ALL_POKEMON_PACKS if 152 <= p['id'] <= 251]
            for _ in range(pack_size):
                is_shiny = random.random() < (SHINY_CHANCE * 2)  # Doble de probabilidad
                cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                cat_pool = [p for p in johto_pool if p['category'] == cat]
                if not cat_pool: cat_pool = johto_pool
                p_data = random.choice(cat_pool)
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})

        # 3C. Sobre Especial Unown (Doble probabilidad shiny)
        elif item_id == 'pack_special_unown':
            from pokemon_data import POKEMON_UNOWN
            for _ in range(pack_size):
                is_shiny = random.random() < (SHINY_CHANCE * 2)
                p_data = random.choice(POKEMON_UNOWN)
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})



        # 4. Sobres Elementales
        elif 'type_filter' in pack_config:
            target_type = pack_config['type_filter']
            type_pool = [p for p in ALL_POKEMON_PACKS if target_type in p.get('types', []) and p['id'] <= 151]
            if not type_pool: type_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            for _ in range(pack_size):
                p_data = random.choice(type_pool)
                is_shiny = random.random() < SHINY_CHANCE
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})

        # 5. Sobres Mágicos
        elif is_magic:
            region_filter = pack_config.get('region_filter')
            base_pool = ALL_POKEMON_PACKS

            if region_filter == 'Kanto':
                base_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            elif region_filter == 'Johto':
                base_pool = [p for p in ALL_POKEMON_PACKS if 152 <= p['id'] <= 251]
            elif region_filter == 'Unown':
                from pokemon_data import POKEMON_UNOWN
                base_pool = POKEMON_UNOWN

            user_quantities = db.get_user_collection_quantities(user.id)

            for _ in range(pack_size):
                s = random.random() < SHINY_CHANCE
                missing_pool = []
                one_qty_pool = []

                for p in base_pool:
                    qty = user_quantities.get((p['id'], s), 0)
                    if qty == 0:
                        missing_pool.append(p)
                    elif qty == 1:
                        one_qty_pool.append(p)

                if missing_pool:
                    p_data = random.choice(missing_pool)
                elif one_qty_pool:
                    p_data = random.choice(one_qty_pool)
                else:
                    pool_by_cat = {'C': [], 'B': [], 'A': [], 'S': []}
                    for p in base_pool: pool_by_cat[p['category']].append(p)
                    cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                    possible = pool_by_cat[cat]
                    if not possible: possible = base_pool
                    p_data = random.choice(possible)

                pack_results.append({'data': p_data, 'is_shiny': s})
                user_quantities[(p_data['id'], s)] = user_quantities.get((p_data['id'], s), 0) + 1

        # 6. Sobres Normales (REPARADO)
        else:
            region_filter = pack_config.get('region_filter')
            base_pool = ALL_POKEMON_PACKS

            if region_filter == 'Kanto':
                base_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            elif region_filter == 'Johto':
                base_pool = [p for p in ALL_POKEMON_PACKS if 152 <= p['id'] <= 251]
            elif region_filter == 'Unown':
                from pokemon_data import POKEMON_UNOWN
                base_pool = POKEMON_UNOWN

            pool_by_cat = {'C': [], 'B': [], 'A': [], 'S': []}
            for p in base_pool:
                pool_by_cat[p['category']].append(p)

            for _ in range(pack_size):
                is_shiny = random.random() < SHINY_CHANCE
                cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                possible = pool_by_cat[cat]
                if not possible: possible = base_pool
                p_data = random.choice(possible)
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})

        # --- PROCESAMIENTO DE RESULTADOS ---
        summary_parts = []

        for result in pack_results:
            p, s = result['data'], result['is_shiny']
            rarity = get_rarity(p['category'], s)

            try:
                # Ruta dinámica (Los Unown con IDs de 5 cifras viven en Johto)
                if p['id'] > 20000:
                    region_folder = "Johto"
                else:
                    region_folder = "Johto" if p['id'] > 151 else "Kanto"

                path = f"Stickers/{region_folder}/{'Shiny/' if s else ''}{p['id']}{'s' if s else ''}.png"
                with open(path, 'rb') as f:
                    msg = await context.bot.send_sticker(chat_id=message.chat_id, sticker=f, disable_notification=True)
                    message_ids_to_delete.append(msg.message_id)
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"Error enviando sticker {p['id']}: {e}")

            p_display = get_formatted_name(p, s)
            r_emoji = RARITY_VISUALS.get(rarity, '')

            if message.chat.type in ['group', 'supergroup']:
                db.add_pokemon_to_group_pokedex(message.chat.id, p['id'])
                await check_and_unlock_johto(message.chat.id, context)

            status = db.add_sticker_smart(user.id, p['id'], s)

            if status == 'NEW':
                summary_parts.append(f"🔸🆕 {p_display} {r_emoji}")
            elif status == 'DUPLICATE':
                summary_parts.append(f"🔸♻️ {p_display} {r_emoji}")
            else:
                money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                db.update_money(user.id, money)
                summary_parts.append(f"🔸✔️ {p_display} {r_emoji} (+{format_money(money)}₽)")

        pack_name = ITEM_NAMES.get(item_id, "Sobre")
        final_text = f"📜 Resultado del <b>{pack_name}</b> de {user.mention_html()}:\n\n" + "\n".join(summary_parts)

        # Precios individuales (Kanto y Johto)
        if not db.is_kanto_completed_by_user(user.id):
            if db.get_user_unique_kanto_count(user.id) >= 151:
                db.set_kanto_completed_by_user(user.id)
                db.update_money(user.id, 3000)
                db.add_item_to_inventory(user.id, 'pack_shiny_kanto', 1)
                final_text += f"\n\n🎊 ¡Felicidades {user.mention_html()}, has completado <b>Kanto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

        if not db.is_johto_completed_by_user(user.id):
            if db.get_user_unique_johto_count(user.id) >= 100:
                db.set_johto_completed_by_user(user.id)
                db.update_money(user.id, 3000)
                db.add_item_to_inventory(user.id, 'pack_shiny_johto', 1)
                final_text += f"\n\n🎊 ¡Felicidades {user.mention_html()}, has completado <b>Johto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"

        if not db.is_unown_completed_by_user(user.id):
            if db.get_user_unique_unown_count(user.id) >= 28:
                db.set_unown_completed_by_user(user.id)
                db.update_money(user.id, 2000)
                db.add_item_to_inventory(user.id, 'pack_shiny_unown', 1)
                final_text += f"\n\n🎊 ¡Felicidades {user.mention_html()}, has completado el <b>Álbum Unown</b>! 🎊\n¡Recibes 2000₽ y un Sobre Brillante Unown!"

        await context.bot.send_message(message.chat_id, text=final_text, parse_mode='HTML', disable_notification=True)

        if message_ids_to_delete:
            context.job_queue.run_once(delete_pack_stickers, 60,
                                       data={'chat_id': message.chat_id, 'sticker_ids': message_ids_to_delete})

        context.chat_data['last_pack_open_time'] = time.time()

    except Exception as e:
        logger.error(f"Error pack: {e}")
    finally:
        context.chat_data['is_opening_pack'] = False


async def multisobre_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    chat_id = update.effective_chat.id

    db.get_or_create_user(user.id, user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, chat_id)

    # 1. Validar Argumentos
    args = context.args
    if not args or len(args) < 2:
        msg = await update.message.reply_text(
            "❌ Uso correcto: <code>/multisobre &lt;tipodesobre&gt; &lt;cantidad&gt;</code>\n"
            "Ejemplo: <code>/multisobre grandenacional 5</code>",
            parse_mode='HTML', disable_notification=True
        )
        schedule_message_deletion(context, msg, 15)
        schedule_message_deletion(context, update.message, 5)
        return

    sobre_input = args[0].lower()

    try:
        cantidad = int(args[1])
    except ValueError:
        msg = await update.message.reply_text("❌ La cantidad debe ser un número entero.")
        schedule_message_deletion(context, msg, 10)
        return

    # 2. Validar reglas del comando (¡LÍMITE SUBIDO A 20!)
    if cantidad < 1 or cantidad > 20:
        msg = await update.message.reply_text("❌ Puedes abrir entre 1 y 20 sobres a la vez.", disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    item_id = MULTISOBRE_IDS.get(sobre_input)
    if not item_id:
        msg = await update.message.reply_text("❌ Tipo de sobre no reconocido. Escríbelo todo junto (ej: pequeñokanto).",
                                              disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    # 3. Comprobar Inventario
    inventory = db.get_user_inventory(user.id)
    user_qty = 0
    for item in inventory:
        if item['item_id'] == item_id:
            user_qty = item['quantity']
            break

    if user_qty < cantidad:
        msg = await update.message.reply_text(
            f"❌ No tienes suficientes sobres. Tienes {user_qty} y quieres abrir {cantidad}.", disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    # 4. Procesar la apertura en bloque
    pack_config = SHOP_CONFIG.get(item_id, {})
    pack_size = pack_config.get('size', 1)
    is_magic = pack_config.get('is_magic', False)
    pack_name = pack_config.get('name', 'Sobre')

    # Restamos todos los sobres de golpe
    db.remove_item_from_inventory(user.id, item_id, cantidad)

    final_text = f"🎴 <b>Apertura Múltiple de {user.mention_html()}</b> 🎴\n<i>{cantidad}x {pack_name}</i>\n\n"
    user_quantities = db.get_user_collection_quantities(user.id)

    # Iteramos por cada sobre
    for i in range(cantidad):
        pack_results = []

        # --- LÓGICA DE GENERACIÓN IDÉNTICA A LA NORMAL ---
        if item_id == 'pack_elem_especial':
            kanto_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            for _ in range(pack_size):
                is_shiny = random.random() < (SHINY_CHANCE * 2)
                cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                cat_pool = [p for p in kanto_pool if p['category'] == cat]
                if not cat_pool: cat_pool = kanto_pool
                pack_results.append({'data': random.choice(cat_pool), 'is_shiny': is_shiny})

        elif item_id == 'pack_special_unown':
            from pokemon_data import POKEMON_UNOWN
            for _ in range(pack_size):
                is_shiny = random.random() < (SHINY_CHANCE * 2)
                pack_results.append({'data': random.choice(POKEMON_UNOWN), 'is_shiny': is_shiny})

        elif is_magic:
            region_filter = pack_config.get('region_filter')
            base_pool = ALL_POKEMON_PACKS
            if region_filter == 'Kanto':
                base_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            elif region_filter == 'Johto':
                base_pool = [p for p in ALL_POKEMON_PACKS if 152 <= p['id'] <= 251]
            elif region_filter == 'Unown':
                from pokemon_data import POKEMON_UNOWN
                base_pool = POKEMON_UNOWN

            for _ in range(pack_size):
                s = random.random() < SHINY_CHANCE
                missing_pool = [p for p in base_pool if user_quantities.get((p['id'], s), 0) == 0]
                one_qty_pool = [p for p in base_pool if user_quantities.get((p['id'], s), 0) == 1]

                if missing_pool:
                    p_data = random.choice(missing_pool)
                elif one_qty_pool:
                    p_data = random.choice(one_qty_pool)
                else:
                    cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                    possible = [p for p in base_pool if p['category'] == cat]
                    p_data = random.choice(possible if possible else base_pool)

                pack_results.append({'data': p_data, 'is_shiny': s})
                user_quantities[(p_data['id'], s)] = user_quantities.get((p_data['id'], s), 0) + 1

        else:
            region_filter = pack_config.get('region_filter')
            base_pool = ALL_POKEMON_PACKS
            if region_filter == 'Kanto':
                base_pool = [p for p in ALL_POKEMON_PACKS if p['id'] <= 151]
            elif region_filter == 'Johto':
                base_pool = [p for p in ALL_POKEMON_PACKS if 152 <= p['id'] <= 251]
            elif region_filter == 'Unown':
                from pokemon_data import POKEMON_UNOWN
                base_pool = POKEMON_UNOWN

            pool_by_cat = {'C': [], 'B': [], 'A': [], 'S': []}
            for p in base_pool: pool_by_cat[p['category']].append(p)

            for _ in range(pack_size):
                is_shiny = random.random() < SHINY_CHANCE
                cat = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
                possible = pool_by_cat[cat]
                pack_results.append({'data': random.choice(possible if possible else base_pool), 'is_shiny': is_shiny})

        # --- EVALUAR LOS RESULTADOS DEL SOBRE ACTUAL ---
        summary_parts = []
        for result in pack_results:
            p, s = result['data'], result['is_shiny']
            rarity = get_rarity(p['category'], s)

            if update.effective_chat.type in ['group', 'supergroup']:
                db.add_pokemon_to_group_pokedex(chat_id, p['id'])
                await check_and_unlock_johto(chat_id, context)

            status = db.add_sticker_smart(user.id, p['id'], s)
            p_display = get_formatted_name(p, s)
            r_emoji = RARITY_VISUALS.get(rarity, '')

            if status == 'NEW':
                summary_parts.append(f"🔸🆕 {p_display} {r_emoji}")
            elif status == 'DUPLICATE':
                summary_parts.append(f"🔸♻️ {p_display} {r_emoji}")
            else:
                money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                db.update_money(user.id, money)
                summary_parts.append(f"🔸✔️ {p_display} {r_emoji} (+{format_money(money)}₽)")

        pack_summary = f"<b>Sobre {i + 1}:</b>\n" + "\n".join(summary_parts) + "\n\n"

        # --- SISTEMA ANTI-LÍMITES DE TELEGRAM ---
        if len(final_text) + len(pack_summary) > 3800:
            await context.bot.send_message(chat_id, text=final_text, parse_mode='HTML', disable_notification=True)
            final_text = ""  # Reseteamos para el siguiente mensaje

        final_text += pack_summary

    # 5. Comprobar si completó alguna región
    premios_extra = ""
    if not db.is_kanto_completed_by_user(user.id) and db.get_user_unique_kanto_count(user.id) >= 151:
        db.set_kanto_completed_by_user(user.id)
        db.update_money(user.id, 3000)
        db.add_item_to_inventory(user.id, 'pack_shiny_kanto', 1)
        premios_extra += f"\n🎊 ¡Felicidades, has completado <b>Kanto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

    if not db.is_johto_completed_by_user(user.id) and db.get_user_unique_johto_count(user.id) >= 100:
        db.set_johto_completed_by_user(user.id)
        db.update_money(user.id, 3000)
        db.add_item_to_inventory(user.id, 'pack_shiny_johto', 1)
        premios_extra += f"\n🎊 ¡Felicidades, has completado <b>Johto</b>! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"

    if not db.is_unown_completed_by_user(user.id) and db.get_user_unique_unown_count(user.id) >= 28:
        db.set_unown_completed_by_user(user.id)
        db.update_money(user.id, 2000)
        db.add_item_to_inventory(user.id, 'pack_shiny_unown', 1)
        premios_extra += f"\n🎊 ¡Felicidades, has completado el <b>Álbum Unown</b>! 🎊\n¡Recibes 2000₽ y un Sobre Brillante Unown!"

    final_text += premios_extra

    # 6. Enviar el último mensaje (o único, si cabía todo)
    if final_text.strip():
        await context.bot.send_message(chat_id, text=final_text, parse_mode='HTML', disable_notification=True)


async def multicompra_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite comprar varios sobres de golpe."""
    user = update.effective_user
    if not user: return
    chat_id = update.effective_chat.id

    db.get_or_create_user(user.id, user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, chat_id)

    # 1. Validar Argumentos
    args = context.args
    if not args or len(args) < 2:
        msg = await update.message.reply_text(
            "❌ Uso correcto: <code>/multicompra &lt;tipodesobre&gt; &lt;cantidad&gt;</code>\n"
            "Ejemplo: <code>/multicompra pequeñokanto 5</code>",
            parse_mode='HTML', disable_notification=True
        )
        schedule_message_deletion(context, msg, 15)
        schedule_message_deletion(context, update.message, 5)
        return

    sobre_input = args[0].lower()

    try:
        cantidad = int(args[1])
    except ValueError:
        msg = await update.message.reply_text("❌ La cantidad debe ser un número entero.")
        schedule_message_deletion(context, msg, 10)
        return

    # 2. Validar cantidad máxima (10 de golpe, igual que multisobre)
    if cantidad < 1 or cantidad > 50:
        msg = await update.message.reply_text("❌ Puedes comprar entre 1 y 50 sobres a la vez.",
                                              disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    # 3. Buscar el sobre
    item_id = MULTISOBRE_IDS.get(sobre_input)
    if not item_id:
        msg = await update.message.reply_text("❌ Tipo de sobre no reconocido. Escríbelo todo junto (ej: pequeñokanto).",
                                              disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    # 4. Validar que el sobre existe y está a la venta
    pack_details = SHOP_CONFIG.get(item_id)
    if not pack_details or pack_details.get('hidden', False):
        msg = await update.message.reply_text("❌ Este sobre no está disponible en la tienda.",
                                              disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    # 5. Comprobar el dinero del jugador
    precio_unitario = pack_details['price']
    precio_total = precio_unitario * cantidad
    user_money = db.get_user_money(user.id)

    if user_money < precio_total:
        faltante = precio_total - user_money
        msg = await update.message.reply_text(
            f"❌ No tienes suficiente dinero.\n"
            f"Comprar {cantidad}x {pack_details['name']} cuesta **{format_money(precio_total)}₽**.\n"
            f"Te faltan **{format_money(faltante)}₽**.",
            parse_mode='Markdown', disable_notification=True
        )
        schedule_message_deletion(context, msg, 15)
        return

    # 6. Cobrar y entregar los sobres
    db.update_money(user.id, -precio_total)
    db.add_item_to_inventory(user.id, item_id, cantidad)
    saldo_restante = user_money - precio_total

    # 7. Mensaje de confirmación
    success_text = (
        f"✅ ¡Compra múltiple realizada con éxito!\n\n"
        f"Has pagado **{format_money(precio_total)}₽** por **{cantidad}x {pack_details['name']}**.\n"
        f"Se han guardado en tu /mochila.\n"
        f"Saldo restante: **{format_money(saldo_restante)}₽**"
    )

    msg = await update.message.reply_text(success_text, parse_mode='Markdown', disable_notification=True)
    schedule_message_deletion(context, msg, 60)
    schedule_message_deletion(context, update.message, 15)


async def view_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts = query.data.split('_')
        owner_id = int(parts[-1])
        winning_number = parts[-2]

        if query.from_user.id != owner_id:
            await query.answer("No puedes ver el ticket de otro usuario.", show_alert=True)
            return

        await query.answer(
            f"Ganaste el premio gordo (50000₽) de la lotería de la estación de Ciudad Azafrán, con el número: {winning_number}",
            show_alert=True)

    except (ValueError, IndexError):
        await query.answer("Error al leer el ticket.", show_alert=True)


async def regalar_objeto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return

    args = context.args
    message = update.message
    targets = set()
    item_id = None

    # LISTA ACTUALIZADA MÁGICA
    VALID_ITEMS = list(ITEM_NAMES.keys())

    for arg in args:
        if arg.lower() in VALID_ITEMS:
            item_id = arg.lower()
            break

    if not item_id:
        return await message.reply_text(
            "❌ No has especificado un objeto válido.\n"
            "Uso: `/regalarobjeto @usuario1 @usuario2 item_id`\n"
            "Ejemplo: `/regalarobjeto @Pepe pack_large_johto`"
        )

    if message.reply_to_message:
        targets.add(message.reply_to_message.from_user.id)

    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntity.TEXT_MENTION:
                targets.add(entity.user.id)
            elif entity.type == MessageEntity.MENTION:
                username = message.text[entity.offset:entity.offset + entity.length]
                uid = db.get_user_id_by_username(username)
                if uid: targets.add(uid)

    for arg in args:
        if arg.startswith("@"):
            uid = db.get_user_id_by_username(arg)
            if uid: targets.add(uid)

    if not targets:
        return await message.reply_text(
            "⚠️ No detecté a ningún usuario. Asegúrate de mencionar (@) o responder a un mensaje.")

    count = 0
    for uid in targets:
        db.get_or_create_user(uid, None)
        msg = "¡Un regalo!"
        db.add_mail(uid, 'inventory_item', item_id, msg)
        count += 1

    item_name = ITEM_NAMES.get(item_id, item_id)
    await message.reply_text(f"✅ Enviado *{item_name}* al buzón de {count} usuarios.", parse_mode='Markdown')


async def view_special_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts = query.data.split('_')
        owner_id = int(parts[-1])
        item_id = "_".join(parts[1:-1])

        if query.from_user.id != owner_id:
            await query.answer("No puedes ver los objetos de otro usuario.", show_alert=True)
            return

        if item_id in SPECIAL_ITEMS_DATA:
            await query.answer(SPECIAL_ITEMS_DATA[item_id]['desc'], show_alert=True)
        else:
            await query.answer("Objeto desconocido.", show_alert=True)

    except (ValueError, IndexError):
        await query.answer("Error.", show_alert=True)


async def show_special_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    message = cast(Message, query.message)

    try:
        parts = query.data.split('_')
        owner_id = int(parts[-1])
        item_id = "_".join(parts[1:-1])

        if user.id != owner_id:
            await query.answer("No puedes mostrar los objetos de otro usuario.", show_alert=True)
            return

        # Verificar que realmente tiene el objeto (Anti-hack)
        inventory = db.get_user_inventory(user.id)
        if not any(i['item_id'] == item_id for i in inventory):
            await query.answer("¡Ya no tienes este objeto!", show_alert=True)
            return

        # Construir el mensaje
        msg_text = ""

        if item_id.startswith('lottery_ticket_'):
            number = item_id.split('_')[-1]
            msg_text = (f"👤 {user.first_name} mostró su *Ticket de lotería ganador* 🎫.\n\n"
                        f"📜 **Descripción:** Un boleto de la lotería de Ciudad Azafrán premiado con el número ganador: `{number}`.")

        elif item_id in SPECIAL_ITEMS_DATA:
            data = SPECIAL_ITEMS_DATA[item_id]
            msg_text = (f"👤 {user.first_name} mostró su *{data['name']}* {data['emoji']}.\n\n"
                        f"📜 **Descripción:** {data['desc']}")

        else:
            await query.answer("Error al mostrar objeto.")
            return

        # ENVIAR AL GRUPO SIN NOTIFICACIÓN
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=msg_text,
            parse_mode='Markdown',
            disable_notification=True  # <--- SILENCIO
        )
        await query.answer("¡Mostrado en el grupo!")

    except (ValueError, IndexError):
        await query.answer("Error.", show_alert=True)

async def _get_target_user_from_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[
    User | None, list[str]]:
    args = context.args or []
    target_user: User | None = None
    if update.message and update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        return target_user, args
    if update.message and update.message.entities:
        for entity in update.message.entities:
            if entity.type == MessageEntity.TEXT_MENTION:
                target_user = entity.user
                args = args[1:]
                return target_user, args
    if args and args[0].isdigit():
        user_id = int(args[0])
        try:
            chat = await context.bot.get_chat(user_id)
            if isinstance(chat, User):
                target_user = chat
                args = args[1:]
        except BadRequest:
            target_user = None
    return target_user, args


async def darobjeto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return

    # 1. Intentamos obtener usuario por los métodos estándar (respuesta, mención, etc.)
    target_user, args = await _get_target_user_from_command(update, context)

    target_id = None
    item_id = None
    message_parts = []

    # ESCENARIO A: Telegram reconoció al usuario (Reply, Mención o ID cacheada)
    if target_user:
        target_id = target_user.id
        # args ya viene recortado por la función auxiliar
        if len(args) > 0:
            item_id = args[0]
            message_parts = args[1:]

    # ESCENARIO B: Telegram NO lo reconoció, pero tú pusiste una ID numérica manualmente
    # (Aquí usamos context.args directamente porque _get_target_user falló)
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        if len(context.args) > 1:
            item_id = context.args[1]
            message_parts = context.args[2:]

    # Validación final
    if not target_id or not item_id:
        return await update.message.reply_text(
            "❌ Error de sintaxis.\nUso: `/darobjeto <ID_o_@usuario> <item_id> [mensaje opcional]`",
            disable_notification=True
        )

    # Ejecución del regalo
    msg = " ".join(message_parts)
    if not msg: msg = "¡Un regalo de la administración!"

    # Aseguramos que el usuario exista en la BD (aunque sea sin nombre real)
    db.get_or_create_user(target_id, f"User_{target_id}")

    # Enviamos al buzón
    db.add_mail(target_id, 'inventory_item', item_id, msg)

    item_name = ITEM_NAMES.get(item_id, item_id)

    # Intentamos notificar por privado (si falla, no importa, el regalo ya está en el buzón)
    try:
        if db.is_user_notification_enabled(target_id):
            await context.bot.send_message(
                chat_id=target_id,
                text=f"📬 **¡TIENES CORREO!**\n\nNota: _{msg}_",
                parse_mode='Markdown'
            )
    except:
        pass

    await update.message.reply_text(
        f"✅ Enviado *{item_name}* al buzón del ID `{target_id}`.",
        parse_mode='Markdown', disable_notification=True
    )

async def moddinero_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID:
        return
    target_user, args = await _get_target_user_from_command(update, context)
    if not target_user:
        await update.message.reply_text(
            "Uso: Responde a un usuario, menciónalo o usa su ID.\n"
            "`/moddinero [@usuario|ID] <cantidad>`"
        )
        return
    try:
        amount = int(args[0])
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Por favor, especifica una cantidad numérica válida.\n"
            "Uso: `/moddinero [@usuario|ID] <cantidad>`\n"
            "Ej: `/moddinero @usuario 500` (añade 500)\n"
            "Ej: `/moddinero @usuario -200` (quita 200)"
        )
        return
    db.get_or_create_user(target_user.id, target_user.first_name)
    db.update_money(target_user.id, amount)
    action_text = "añadido" if amount >= 0 else "quitado"
    abs_amount = abs(amount)
    new_balance = db.get_user_money(target_user.id)
    message_text = (
        f"✅ ¡Operación completada!\n\n"
        f"Se ha {action_text} *{format_money(abs_amount)}₽* a {target_user.mention_markdown()}.\n"
        f"Saldo actual: *{format_money(new_balance)}₽*"
    )
    await update.message.reply_text(message_text, parse_mode='Markdown')


async def resetmoney_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text(
            "Uso: Responde a un mensaje del usuario al que quieres dejar sin dinero.")

    db.get_or_create_user(target_user.id, target_user.first_name)
    db.set_money(target_user.id, 0)
    await update.message.reply_text(
        f"💸 ¡Se ha eliminado todo el dinero de {target_user.mention_markdown()}! Ahora tiene *0₽*.",
        parse_mode='Markdown')


async def send_to_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    try:
        args = context.args
        if not args: return await update.message.reply_text("Uso: /sendtoall <tipo/id|combo> [args] [mensaje]",
                                                            disable_notification=True)

        all_users = db.get_all_user_ids()
        first_arg = args[0].lower()

        # --- LÓGICA ESPECIAL PARA COMBO ---
        if first_arg == 'combo':
            try:
                money_amount = int(args[1])
                item_id_input = args[2]
                message = ' '.join(args[3:]) or "¡Un regalo especial!"
                final_item_id = USER_FRIENDLY_ITEM_IDS.get(item_id_input, item_id_input)
                item_name = ITEM_NAMES.get(final_item_id, final_item_id)
                if final_item_id == 'pack_shiny_kanto': item_name = "Sobre Brillante Kanto"

                notified_count = 0
                skipped_count = 0
                await update.message.reply_text(f"⏳ Enviando COMBO a {len(all_users)} usuarios...",
                                                disable_notification=True)

                for uid in all_users:
                    db.add_mail(uid, 'money', str(money_amount), message)
                    db.add_mail(uid, 'inventory_item', final_item_id, message)

                    # --- CHECK: ¿QUIERE NOTIFICACIONES? ---
                    if db.is_user_notification_enabled(uid):
                        try:
                            await context.bot.send_message(
                                chat_id=uid,
                                text=f"📬 **¡Tienes correo! Ha llegado algo a tu /buzon**\n\n _Para dejar de recibir notificaciones del buzón, escribe:_ /notiboff",
                                parse_mode='Markdown'
                            )
                            notified_count += 1
                            await asyncio.sleep(0.05)
                        except Exception:
                            pass
                    else:
                        skipped_count += 1

                await update.message.reply_text(
                    f"✅ Combo enviado.\n📩 Avisados: {notified_count}\n🔕 Silenciados: {skipped_count}",
                    disable_notification=True)
                return

            except (IndexError, ValueError):
                return await update.message.reply_text("Uso Combo: `/sendtoall combo <dinero> <item_id> [mensaje]`",
                                                       disable_notification=True)

        # --- LÓGICA NORMAL ---
        item_type = ''
        item_details = ''
        message = ''

        if first_arg == 'money':
            item_type = 'money'
            item_details = str(int(args[1]))
            message = ' '.join(args[2:]) or "¡Regalo para la comunidad!"
        elif first_arg == 'sticker':
            item_type = 'single_sticker'
            item_details = f"{int(args[1])}_{int(args[2])}"
            message = ' '.join(args[3:]) or "¡Un sticker de regalo!"
        elif first_arg in USER_FRIENDLY_ITEM_IDS:
            item_type = 'inventory_item'
            item_details = USER_FRIENDLY_ITEM_IDS[first_arg]
            message = ' '.join(args[1:]) or "¡Un regalo especial!"
        elif first_arg in ITEM_NAMES:
            item_type = 'inventory_item'
            item_details = first_arg
            message = ' '.join(args[1:]) or "¡Un regalo especial!"
        else:
            if first_arg == 'pack_shiny_kanto':
                item_type = 'inventory_item'
                item_details = first_arg
                message = ' '.join(args[1:]) or "¡Un regalo especial!"
            else:
                return await update.message.reply_text(f"Tipo no reconocido: '{first_arg}'.", disable_notification=True)

        notified_count = 0
        skipped_count = 0
        await update.message.reply_text(f"⏳ Enviando regalos a {len(all_users)} usuarios...", disable_notification=True)

        for uid in all_users:
            db.add_mail(uid, item_type, item_details, message)

            # --- CHECK: ¿QUIERE NOTIFICACIONES? ---
            if db.is_user_notification_enabled(uid):
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"📬 **¡Tienes correo! Ha llegado algo a tu /buzon**\n\n _Para dejar de recibir notificaciones del buzón, escribe:_ /notiboff",
                        parse_mode='Markdown'
                    )
                    notified_count += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
            else:
                skipped_count += 1

        await update.message.reply_text(
            f"✅ Regalo enviado a {len(all_users)} jugadores.\n📩 Avisados: {notified_count}\n🔕 Silenciados: {skipped_count}",
            disable_notification=True
        )

    except (IndexError, ValueError) as e:
        await update.message.reply_text(f"Uso incorrecto: {e}", disable_notification=True)


async def admin_force_delibird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return

    # 1. Borramos la programación persistente (Base de Datos)
    db.clear_delibird_schedule()

    # 2. BUSCAMOS Y ELIMINAMOS LA CUENTA ATRÁS EN RAM (El "Zombie")
    # Buscamos trabajos con los nombres que usamos al programarlos
    posibles_jobs = ["delibird_weekly_event", "delibird_restored_event", "delibird_recovered_event"]

    jobs_killed = 0
    for name in posibles_jobs:
        current_jobs = context.job_queue.get_jobs_by_name(name)
        for job in current_jobs:
            job.schedule_removal()
            jobs_killed += 1

    # 3. Lanzamos el evento manualmente
    await trigger_delibird_event(context)

    msg_extra = f" (Se cancelaron {jobs_killed} programaciones pendientes)" if jobs_killed > 0 else ""
    await update.message.reply_text(f"✅ Evento Delibird forzado manualmente.{msg_extra}", disable_notification=True)
    await update.message.delete()

async def send_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text(
            "Uso: Responde a un usuario, menciónalo o usa su ID.\n`/sendsticker [@usuario|ID] <poke_id> <shiny 0/1> [mensaje]`")
    try:
        poke_id, is_shiny = int(args[0]), int(args[1])
        message = ' '.join(args[2:]) or "¡Un regalo especial!"
        if not POKEMON_BY_ID.get(poke_id):
            return await update.message.reply_text(f"❌ Error: El Pokémon con ID {poke_id} no existe.")
        item_details = f"{poke_id}_{is_shiny}"
        db.get_or_create_user(target_user.id, target_user.first_name)
        db.add_mail(target_user.id, 'single_sticker', item_details, message)
        await update.message.reply_text(
            f"✅ Sticker de {POKEMON_BY_ID[poke_id]['name']} enviado al buzón de {target_user.first_name}.")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: `/sendsticker [@usuario|ID] <poke_id> <shiny 0/1> [mensaje]`")


async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text("Uso: `/addsticker [@usuario|ID] <poke_id> <shiny 0/1>`")
    try:
        poke_id, is_shiny = int(args[0]), bool(int(args[1]))
        poke_name = POKEMON_BY_ID.get(poke_id, {}).get('name')
        if not poke_name:
            return await update.message.reply_text(f"❌ Error: El Pokémon con ID {poke_id} no existe.")
        db.get_or_create_user(target_user.id, target_user.first_name)
        db.add_sticker_to_collection(target_user.id, poke_id, is_shiny)

        db.increment_monthly_stickers(target_user.id)

        shiny_text = " brillante" if is_shiny else ""
        await update.message.reply_text(
            f"✅ Añadido {poke_name}{shiny_text} a la colección de {target_user.first_name}.")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: `/addsticker [@usuario|ID] <poke_id> <shiny 0/1>`")


async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text("Uso: `/removesticker [@usuario|ID] <poke_id> <shiny 0/1>`")
    try:
        poke_id, is_shiny = int(args[0]), bool(int(args[1]))
        poke_name = POKEMON_BY_ID.get(poke_id, {}).get('name')
        if not poke_name:
            return await update.message.reply_text(f"❌ Error: El Pokémon con ID {poke_id} no existe.")
        if db.remove_sticker_from_collection(target_user.id, poke_id, is_shiny):
            shiny_text = " brillante" if is_shiny else ""
            await update.message.reply_text(
                f"✅ Eliminado {poke_name}{shiny_text} de la colección de {target_user.first_name}.")
        else:
            await update.message.reply_text(f"ℹ️ {target_user.first_name} no tenía ese sticker.")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: `/removesticker [@usuario|ID] <poke_id> <shiny 0/1>`")


async def dinero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return

    db.get_or_create_user(user.id, user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, update.effective_chat.id)

    money = db.get_user_money(user.id)
    # --- CORRECCIÓN: Usamos effective_message ---
    sent_message = await update.effective_message.reply_text(
        f"Tienes *{format_money(money)}₽* 💰.",
        parse_mode='Markdown',
        disable_notification=True
    )
    schedule_message_deletion(context, sent_message)
    if update.message:  # Solo borramos si hay comando de texto
        schedule_message_deletion(context, update.message)


async def regalar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    if not sender:
        return
    target_user, args = await _get_target_user_from_command(update, context)

    # Caso: Ayuda (no puso destinatario)
    if not target_user:
        msg = await update.message.reply_text(
            "Puedes regalarle a otro jugador parte de tu dinero. Así funciona el comando '/regalar':\n\n"
            "🔹 Responde a un mensaje de la persona y escribe:\n"
            "'/regalar <cantidad>'\n\n"
            "🔹 O bien, menciona a la persona; escribe:\n"
            "'/regalar @usuario <cantidad>'", disable_notification=True)
        # Borrar ayuda y comando en 60 segundos
        schedule_message_deletion(context, msg, 60)
        schedule_message_deletion(context, update.message, 5)
        return

    # Caso: Auto-regalo
    if sender.id == target_user.id:
        msg = await update.message.reply_text("😅 No puedes regalarte dinero a ti mismo.", disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        schedule_message_deletion(context, update.message, 10)
        return

    # Caso: Regalo a bot
    if target_user.is_bot:
        msg = await update.message.reply_text("🤖 No puedes enviarle dinero a un bot.", disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        schedule_message_deletion(context, update.message, 10)
        return

    # Caso: Cantidad inválida
    try:
        amount = int(args[0])
        if amount <= 0:
            msg = await update.message.reply_text("¿A quién intentas engañar? 🤨", disable_notification=True)
            schedule_message_deletion(context, msg, 10)
            schedule_message_deletion(context, update.message, 10)
            return
    except (IndexError, ValueError):
        msg = await update.message.reply_text(
            "Por favor, especifica una cantidad válida.\nUso: `/regalar [@usuario|ID] <cantidad>`",
            disable_notification=True)
        schedule_message_deletion(context, msg, 20)
        schedule_message_deletion(context, update.message, 5)
        return

    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(sender.id, update.effective_chat.id)

    sender_money = db.get_user_money(sender.id)

    # Caso: No tiene dinero
    if sender_money < amount:
        msg = await update.message.reply_text(f"No tienes suficiente dinero. Tienes *{format_money(sender_money)}₽*.",
                                              parse_mode='Markdown', disable_notification=True)
        schedule_message_deletion(context, update.message, 5)
        schedule_message_deletion(context, msg, 120)
        return

    # ÉXITO
    db.get_or_create_user(target_user.id, target_user.first_name)
    db.update_money(sender.id, -amount)
    db.update_money(target_user.id, amount)

    sender_mention = sender.mention_markdown()
    recipient_mention = target_user.mention_markdown()

    # Mensaje de éxito (este no se suele borrar rápido para que quede constancia, pero borramos el comando del usuario)
    await update.message.reply_text(
        f"💸 ¡Transacción completada!\n{sender_mention} le ha enviado a {recipient_mention}: *{format_money(amount)}₽*",
        parse_mode='Markdown', disable_notification=True
    )

    # Borramos SOLO el comando del usuario que inició todo
    schedule_message_deletion(context, update.message, 120)


async def ratio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_to_check: User | None = None
    issuer_user = update.effective_user
    if not issuer_user:
        return

    target_user, _ = await _get_target_user_from_command(update, context)

    if target_user:
        user_to_check = target_user
    else:
        user_to_check = issuer_user

    if not user_to_check:
        return

    db.get_or_create_user(user_to_check.id, user_to_check.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(issuer_user.id, update.effective_chat.id)

    capture_chance = db.get_user_capture_chance(user_to_check.id)
    user_mention = user_to_check.mention_markdown()

    if target_user and target_user.id != issuer_user.id:
        text = f"📊 El ratio de captura actual de {user_mention} es del *{capture_chance}%*."
    else:
        text = f"📊 Tu ratio de captura actual es del *{capture_chance}%*."

    # Enviamos el mensaje
    msg = await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)

    # --- PROGRAMAMOS EL BORRADO EN 60 SEGUNDOS ---
    schedule_message_deletion(context, msg, 60)
    if update.message:
        schedule_message_deletion(context, update.message, 60)


async def ranking_mensual_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el progreso actual del Ranking Mensual del Grupo."""
    # 1. Validar que se use en un grupo
    if update.effective_chat.type not in ['group', 'supergroup']:
        msg = await update.effective_message.reply_text("Este comando solo funciona en grupos.",
                                                        disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        schedule_message_deletion(context, update.message, 5)
        return

    chat_id = update.effective_chat.id
    ranking_data = db.get_group_monthly_ranking(chat_id)

    # 2. Si no hay datos (Nadie ha capturado nada)
    if not ranking_data:
        text = "🏆 **Ranking Mensual del Grupo** 🏆\n\n_Aún nadie ha capturado ningún sticker este mes._"
        msg = await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        schedule_message_deletion(context, update.message, 60)
        return

    # 3. Construir la lista visual
    text = "🏆 **Ranking Mensual (En curso)** 🏆\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(ranking_data):
        user_name = row['username'] if isinstance(row, dict) else row[1]
        count = row['stickers_this_month'] if isinstance(row, dict) else row[2]

        visual_rank = medals[i] if i < 3 else f"{i + 1}."
        text += f"{visual_rank} {user_name}: {count} stickers\n"


    # 4. Enviar el mensaje y programar el borrado de ambos en 60 segundos
    msg = await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)
    schedule_message_deletion(context, msg, 60)
    schedule_message_deletion(context, update.message, 60)


async def retos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    is_panel = (query and query.data == "panel_retos")

    if query and not is_panel:
        message = query.message
        chat_id = message.chat_id
    else:
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.effective_message.reply_text("Este comando solo funciona en grupos.",
                                                      disable_notification=True)
            return
        message = update.effective_message
        chat_id = update.effective_chat.id

    user = update.effective_user
    db.get_or_create_user(user.id, user.first_name)
    db.register_user_in_group(user.id, chat_id)

    # --- LÓGICA KANTO ---
    group_ids_kanto = db.get_group_unique_kanto_ids(chat_id)
    total_kanto = len(group_ids_kanto)
    target_kanto = 151

    text = "🤝 **Retos Grupales** 🤝\n\n"

    if total_kanto >= target_kanto:
        text += "🎯 Objetivo: Conseguir los 151 Pokémon de Kanto ✅ **¡Hecho!**\n"
    else:
        text += "🎯 Objetivo: Conseguir los 151 Pokémon de Kanto:\n"
        text += f"📊 Total: {total_kanto}/{target_kanto}\n"

    text += "\n" + "—" * 15 + "\n"

    # --- LÓGICA JOHTO (Desbloqueo al 75% de Kanto = 113) ---
    johto_unlocked = total_kanto >= 113

    if johto_unlocked:
        group_ids_johto = db.get_group_unique_johto_ids(chat_id)

        # --- FILTRO: EXCLUIR BEBÉS Y UNOWN DEL RECUENTO GRUPAL ---
        # IDs a excluir: 172, 173, 174, 175, 201, 236, 238, 239, 240
        excluded_ids = {172, 173, 174, 175, 201, 236, 238, 239, 240}
        valid_johto_ids = [pid for pid in group_ids_johto if pid not in excluded_ids]

        total_johto = len(valid_johto_ids)
        target_johto = 91  # 100 totales - 8 bebés - 1 unown

        if total_johto >= target_johto:
            text += f"🎯 Objetivo: Conseguir los {target_johto} Pokémon de Johto ✅ **¡Hecho!**\n"
        else:
            text += f"🎯 Objetivo: Conseguir los {target_johto} Pokémon de Johto:\n"
            text += f"📊 Total: {total_johto}/{target_johto}\n"
    else:
        text += "🔒 _Siguiente reto bloqueado (Requiere 75% de Kanto)_\n"

    is_unlocked_flag = 1 if johto_unlocked else 0
    keyboard = [[InlineKeyboardButton("📋 Stickers que faltan",
                                      callback_data=f"retos_missing_menu_{chat_id}_{is_unlocked_flag}")]]

    if query and not is_panel:
        refresh_deletion_timer(context, message, 30)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                       disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        if update.message:
            schedule_message_deletion(context, update.message, 5)


# --- SISTEMA DE CÓDIGOS DE AMIGO ---

async def codigos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    is_panel = (query and query.data == "panel_codigos")

    if query and not is_panel:
        message = query.message
        user_id = query.from_user.id
    else:
        message = update.effective_message
        user_id = update.effective_user.id
        if update.message:
            schedule_message_deletion(context, update.message, 900)

    db.delete_expired_codes()
    all_codes = db.get_all_friend_codes()

    regions = {'Europa': [], 'América': [], 'Asia': []}
    current_time = time.time()

    for row in all_codes:
        r = row['region']
        if r not in regions: r = 'Europa'
        days_left = int((row['expiry_timestamp'] - current_time) / 86400)

        # --- SOLUCIÓN: Limpiamos los nombres peligrosos para Markdown ---
        safe_nick = str(row['game_nick']).replace('_', '').replace('*', '').replace('`', '')

        line = f"🔹️ {safe_nick} - `{row['code']}` ({days_left} días)"
        regions[r].append(line)

    text = (
        "👥 *Códigos de amigo:*\n"
        "_Lista actualizada de códigos de amigo de Pokémon Shuffle (cada código se eliminará en 1 mes, si no se renueva antes):_\n\n"
    )
    text += "*Europa:*\n" + ("\n".join(regions['Europa']) if regions['Europa'] else "_Vacío_") + "\n\n"
    text += "*América:*\n" + ("\n".join(regions['América']) if regions['América'] else "_Vacío_") + "\n\n"
    text += "*Asia:*\n" + ("\n".join(regions['Asia']) if regions[
        'Asia'] else "_Vacío_") + "\n\n _Para eliminar un código de la lista, escribe /borrarcodigo seguido del código a eliminar, por ejemplo: /borrarcodigo 6T4A2944_"

    keyboard = [
        [InlineKeyboardButton("➕ Añadir código", callback_data="codes_menu_add")],
        [InlineKeyboardButton("🔄 Renovar", callback_data="codes_menu_renew")]
    ]

    try:
        if query and not is_panel:
            refresh_deletion_timer(context, message, 600)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                           disable_notification=True)
            schedule_message_deletion(context, msg, 600)
    except Exception as e:
        print(f"Error enviando menú de códigos: {e}")


async def delete_code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return

    # Verificamos si escribió el argumento
    if not context.args:
        msg = await update.message.reply_text(
            "❌ Debes especificar el código que quieres borrar.\nEjemplo: `/borrarcodigo AABB1122`",
            parse_mode='Markdown', disable_notification=True
        )
        schedule_message_deletion(context, msg, 30)
        schedule_message_deletion(context, update.message, 5)
        return

    code_to_delete = context.args[0].upper().strip()

    # Buscamos de quién es el código
    owner_id = db.get_code_owner(code_to_delete)

    if not owner_id:
        msg = await update.message.reply_text(
            f"❌ El código `{code_to_delete}` no existe en la lista.",
            parse_mode='Markdown', disable_notification=True
        )
    else:
        # VERIFICACIÓN DE PERMISOS
        # ¿Es el admin O es el dueño del código?
        if user.id == ADMIN_USER_ID or user.id == owner_id:
            db.delete_friend_code(code_to_delete)
            msg = await update.message.reply_text(
                f"🗑️ El código `{code_to_delete}` ha sido eliminado correctamente.",
                parse_mode='Markdown', disable_notification=True
            )
            await refresh_codes_board(context.bot, update.effective_chat.id)

        else:
            msg = await update.message.reply_text(
                "⛔ No puedes borrar un código que no es tuyo.",
                disable_notification=True
            )

    schedule_message_deletion(context, msg, 30)
    schedule_message_deletion(context, update.message, 5)


async def codigos_btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data
    chat_id = query.message.chat_id

    # Recuperamos la ID guardada en la base de datos
    fixed_board_id = db.get_codes_board_msg(chat_id)

    # --- COMPARACIÓN ROBUSTA (Convertimos a string para evitar errores de tipo) ---
    # Comparamos si la ID guardada es igual a la ID del mensaje que se ha tocado
    is_fixed_board = (str(fixed_board_id) == str(query.message.message_id))

    if is_fixed_board:
        # ¡ES EL FIJO! -> Red de seguridad: Cancelamos cualquier borrado pendiente
        cancel_scheduled_deletion(context, chat_id, query.message.message_id)
    else:
        # NO ES EL FIJO -> Ponemos cuenta atrás de 10 minutos
        refresh_deletion_timer(context, query.message, 600)

    if action == "codes_menu_add":
        text = (
            "📝 **Añadir Código**\n\n"
            "Para añadir tu código a la lista, escribe en este chat un mensaje con el siguiente formato:\n\n"
            "`Nick Región Código`\n\n"
            "• **Ejemplo:** `Sixtomaru Europa 6T4A2944`\n\n"
            "_Si quieres que el bot te avise cuando tu código esté a punto de caducar, inicia el bot en su chat: @PokeStickerCollectorBot_ \n\n _Para eliminar un código de la lista, escribe /borrarcodigo seguido del código a eliminar, por ejemplo: /borrarcodigo 6T4A2944_"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Atrás", callback_data="codes_menu_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await query.answer()

    elif action == "codes_menu_renew":
        if db.renew_friend_code(user_id):
            await query.answer("✅ ¡Código renovado por 30 días!", show_alert=True)

            # Si es el fijo, refrescamos el tablón visualmente.
            # Si es temporal, volvemos al menú principal (que regenera el mensaje).
            if is_fixed_board:
                await refresh_codes_board(context.bot, chat_id)
            else:
                await codigos_cmd(update, context)
                await refresh_codes_board(context.bot, chat_id)
        else:
            await query.answer("❌ No se ha encontrado tu código de amigo, por favor, añádelo de nuevo a la lista.",
                               show_alert=True)

    elif action == "codes_menu_back":
        await codigos_cmd(update, context)


async def process_friend_code_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analiza mensajes de texto para ver si son códigos de amigo."""

    # --- DEFENSA ANTI-ERRORES ---
    # Cogemos el mensaje normal o el mensaje editado. Si no hay ninguno, o no hay texto, abortamos.
    message = update.message or update.edited_message
    if not message or not message.text:
        return

    text = message.text
    user = update.effective_user

    # Patrón Regex: (Nick) (Region) (Codigo)
    pattern = r"^(.+)\s+(Europa|América|America|Asia)\s+([A-Z0-9\-]{8,9})$"

    match = re.match(pattern, text, re.IGNORECASE)

    if match:
        nick = match.group(1).strip()
        region_raw = match.group(2).lower()
        code = match.group(3).upper()

        region = "Europa"
        if "am" in region_raw:
            region = "América"
        elif "as" in region_raw:
            region = "Asia"

        clean_code = code.replace("-", "")
        if len(clean_code) != 8: return

        # --- VALIDACIONES ---
        # 1. Límite de 3 códigos (Excepto Admin)
        if user.id != ADMIN_USER_ID:
            count = db.check_user_has_code_count(user.id)
            if count >= 3:
                msg = await update.message.reply_text(
                    "❌ Ya tienes 3 códigos registrados (el máximo). Si quieres añadir otro, borra uno antiguo con /borrarcodigo.",
                    disable_notification=True
                )
                schedule_message_deletion(context, update.message, 5)
                schedule_message_deletion(context, msg, 60)
                return

        # 2. ¿El código existe ya?
        if db.check_code_exists(code):
            msg = await update.message.reply_text("❌ Este código ya está registrado en la lista.",
                                                  disable_notification=True)
            schedule_message_deletion(context, update.message, 5)
            schedule_message_deletion(context, msg, 60)
            return

        # --- AÑADIR ---
        db.add_friend_code(user.id, nick, region, code)

        msg = await update.message.reply_text("✅ Código agregado a la lista.", disable_notification=True)
        schedule_message_deletion(context, update.message, 5)
        schedule_message_deletion(context, msg, 60)

        await refresh_codes_board(context.bot, update.effective_chat.id)

# --- NUEVOS COMANDOS DE NOTIFICACIÓN DE CÓDIGOS ---

async def notic_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return

    db.set_code_notification(user.id, True)
    msg = await update.message.reply_text(
        "✅🗓 Recordatorio activado.\n\n_Para desactivarlo, escribe: /noticoff_.",
        parse_mode='Markdown', disable_notification=True
    )
    schedule_message_deletion(context, msg, 10)
    schedule_message_deletion(context, update.message, 10)


async def notic_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return

    db.set_code_notification(user.id, False)
    msg = await update.message.reply_text(
        "❌🗓 Recordatorio desactivado.\n\n_Si quieres volver a activarlo, escribe: /noticon_.",
        parse_mode='Markdown', disable_notification=True
    )
    schedule_message_deletion(context, msg, 10)
    schedule_message_deletion(context, update.message, 10)


# --- TAREA DIARIA DE REVISIÓN DE CADUCIDAD ---

async def check_code_expiration_job(context: ContextTypes.DEFAULT_TYPE):
    """Revisa si hay códigos que caducan en 3 días, avisa, y actualiza los tablones."""
    # 1. Limpieza de caducados de la base de datos
    db.delete_expired_codes()

    # 2. Comprobación de avisos (3 días)
    all_codes = db.get_all_friend_codes()
    current_time = time.time()

    for row in all_codes:
        expiry = row['expiry_timestamp']
        user_id = row['user_id']

        days_left = (expiry - current_time) / 86400

        if 2.0 < days_left <= 3.0:
            if db.is_code_notification_enabled(user_id):
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🗓 **Recordatorio:** Tu código de amigo de Shuffle se borrará de la lista de códigos del bot en **3 días**.\n"
                            "Si quieres que se mantenga, accede a /codigos y toca el botón **\"Renovar\"**.\n\n"
                            "_Recuerda que puedes borrar el código de la lista manualmente, escribiendo /borrarcodigo, seguido del código que quieres borrar._\n\n"
                            "_Si quieres dejar de recibir este recordatorio, escribe: /noticoff_"
                        ),
                        parse_mode='Markdown'
                    )
                    await asyncio.sleep(0.1)
                except Exception:
                    pass

    # --- NUEVO: ACTUALIZAR TODOS LOS TABLONES FIJOS ---
    active_groups = db.get_active_groups()
    for chat_id in active_groups:
        try:
            # Esto forzará que el mensaje anclado re-calcule los días restantes
            # y borre visualmente los que acaban de caducar hoy.
            await refresh_codes_board(context.bot, chat_id)
            await asyncio.sleep(0.1)  # Pausa anti-spam de Telegram
        except Exception as e:
            logger.error(f"Error actualizando tablón de códigos en {chat_id}: {e}")


# --- SISTEMA DE INTERCAMBIOS ---

async def intercambio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    is_panel = (query and query.data == "panel_intercambios")

    if is_panel:
        sender = query.from_user
        message = query.message
    else:
        sender = update.effective_user
        message = update.effective_message
        if update.message: schedule_message_deletion(context, update.message, 60)

    # 1. Validar límite diario del que ejecuta el comando
    if not db.check_trade_daily_limit(sender.id):
        text = "⛔ Has alcanzado tu límite de 2 intercambios diarios."
        if is_panel:
            await query.answer(text, show_alert=True)
        else:
            msg = await message.reply_text(text, disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return

    # 2. DEFINIR SIEMPRE EL OBJETIVO (Evita el UnboundLocalError)
    target_user = None
    if not is_panel:
        target_user, _ = await _get_target_user_from_command(update, context)

    # 3. Bloqueo de intercambio pendiente
    active_trades = context.chat_data.get('active_trades', {})
    if sender.id in active_trades:
        text = "⛔ Tienes un intercambio pendiente sin finalizar."
        keyboard = [[InlineKeyboardButton("🗑️ Cancelar intercambio anterior", callback_data="trade_force_cancel")]]

        if is_panel:
            await query.answer()
            msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                                 reply_markup=InlineKeyboardMarkup(keyboard), disable_notification=True)
            schedule_message_deletion(context, msg, 30)
        else:
            msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return

    # 4. Bloqueo de auto-intercambio (Avisa y detiene si eres tú mismo)
    if target_user and target_user.id == sender.id:
        msg = await message.reply_text("😅 No puedes intercambiar contigo mismo.", disable_notification=True)
        schedule_message_deletion(context, msg, 10)
        return

    # 5. Si NO hay objetivo -> Menú Principal (Ayuda + Buscador)
    if not target_user or target_user.is_bot:
        help_text = (
            "♻ **Intercambios**\n\n"
            "**¿Cómo funcionan?**\n"
            "Responde a un mensaje que haya escrito la persona con la que quieres intercambiar, y escribe `/intercambio` "
            "(también puedes mencionarla: `/intercambio @usuario`).\n\n"
            "Aparecerá un menú donde puedes ver sus repetidos y ofrecer uno de los tuyos."
        )
        cmd_msg_id = update.message.message_id if not is_panel and update.message else ""
        keyboard = [[InlineKeyboardButton("🔍 Buscar", callback_data=f"trade_search_start_{sender.id}_{cmd_msg_id}")]]

        if is_panel:
            msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text,
                                                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                                 disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        else:
            msg = await message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard),
                                           parse_mode='Markdown', disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return

    # 6. Si SÍ hay objetivo -> Validamos su límite diario y empezamos el intercambio con él
    if not db.check_trade_daily_limit(target_user.id):
        msg = await message.reply_text(f"⛔ {target_user.first_name} ha alcanzado su límite de intercambios hoy.",
                                       disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        return

    # 7. Llamamos al menú de Regiones (Kanto/Johto) dirigido al Target
    cmd_msg_id = update.message.message_id if not is_panel and update.message else ""
    await show_trade_region_menu(update, context, target_user.id, sender.id, cmd_msg_id=cmd_msg_id)


async def show_trade_region_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id, sender_id,
                                 cmd_msg_id=""):
    text = "♻️ Elige la región del Pokémon que quieres recibir:"

    keyboard = [
        [InlineKeyboardButton("🔍 Buscar", callback_data=f"trade_search_start_{sender_id}_{cmd_msg_id}")],
        [InlineKeyboardButton("🔸 Kanto", callback_data=f"trade_reg_{target_id}_{sender_id}_kanto_{cmd_msg_id}")],
        [InlineKeyboardButton("🔹 Johto", callback_data=f"trade_reg_{target_id}_{sender_id}_johto_{cmd_msg_id}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"trade_cancel_{sender_id}_{cmd_msg_id}")]
    ]

    if update.callback_query:
        refresh_deletion_timer(context, update.callback_query.message, 120)
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                                      parse_mode='Markdown')
    else:
        msg = await context.bot.send_message(update.effective_chat.id, text,
                                             reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                             disable_notification=True)
        schedule_message_deletion(context, msg, 120)


async def trade_reg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    # Formato: trade_reg_TGT_SND_REGION_MSGID
    target_id, sender_id, region = int(parts[2]), int(parts[3]), parts[4]
    cmd_msg_id = parts[5] if len(parts) > 5 else ""

    if query.from_user.id != sender_id:
        return await query.answer("No es tu menú.", show_alert=True)

    await show_trade_menu_target_duplicates(update, context, target_id, sender_id, region, 0, cmd_msg_id)


async def trade_back_reg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    target_id, sender_id = int(parts[3]), int(parts[4])
    cmd_msg_id = parts[5] if len(parts) > 5 else ""

    if query.from_user.id != sender_id:
        return await query.answer("No es tu menú.", show_alert=True)

    await show_trade_region_menu(update, context, target_id, sender_id, cmd_msg_id)


# ==========================================
# --- SISTEMA DE BÚSQUEDA DE INTERCAMBIOS ---
# ==========================================

async def trade_search_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pantalla 1: Selección de región para buscar."""
    query = update.callback_query
    parts = query.data.split('_')
    sender_id = int(parts[3])
    cmd_msg_id = parts[4] if len(parts) > 4 else ""

    if query.from_user.id != sender_id:
        return await query.answer("No es tu menú.", show_alert=True)

    if query.message.chat.type == 'private':
        return await query.answer("Este buscador solo funciona si usas el comando dentro de un grupo.", show_alert=True)

    text = "🔍 **Elige la región del sticker que quieres conseguir:**"
    keyboard = [
        [InlineKeyboardButton("🔸 Kanto", callback_data=f"trade_sreg_{sender_id}_kanto_0_num_{cmd_msg_id}")],
        [InlineKeyboardButton("🔹 Johto", callback_data=f"trade_sreg_{sender_id}_johto_0_num_{cmd_msg_id}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"trade_cancel_{sender_id}_{cmd_msg_id}")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_search_region_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pantalla 2: Lista de Pokémon que le faltan al jugador."""
    query = update.callback_query
    parts = query.data.split('_')
    sender_id = int(parts[2])
    region = parts[3]
    page = int(parts[4])
    sort_mode = parts[5]
    cmd_msg_id = parts[6] if len(parts) > 6 else ""

    if query.from_user.id != sender_id:
        return await query.answer("No es tu menú.", show_alert=True)

    user_stickers = db.get_all_user_stickers(sender_id)
    owned_species = {pid for pid, shiny in user_stickers}

    # 1. Filtramos la región (Y EXCLUIMOS EL UNOWN 201 BASE PARA QUE NO SALGA EN LA BÚSQUEDA)
    if region == 'kanto':
        pool = [p for p in ALL_POKEMON if p['id'] <= 151]
    elif region == 'johto':
        pool = [p for p in ALL_POKEMON if (152 <= p['id'] <= 251 and p['id'] != 201) or p['id'] > 20000]

    # 2. Filtramos SOLO las especies que no tiene en absoluto
    missing_species = [p for p in pool if p['id'] not in owned_species]

    # 3. MENSAJE SI NO LE FALTA NADA
    if not missing_species:
        await query.answer(f"¡No te falta ningún sticker de {region.capitalize()}!", show_alert=True)
        return

    # 4. Ordenación
    if sort_mode == 'az':
        missing_species.sort(key=lambda x: x['name'])
    else:
        missing_species.sort(key=lambda x: x['id'])

    ITEMS_PER_PAGE = 20
    total_pages = math.ceil(len(missing_species) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_list = missing_species[start:end]

    keyboard = []
    row = []
    for p in current_list:
        if p['id'] > 20000:
            btn_text = p['name']
        else:
            btn_text = f"#{p['id']:03} {p['name']}" if sort_mode == 'num' else p['name']

        cb_data = f"trade_sstick_{sender_id}_{p['id']}_{page}_{cmd_msg_id}"
        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    nav_row = []
    if page == 0:
        new_sort = 'num' if sort_mode == 'az' else 'az'
        btn_sort_text = "Orden 🔢" if sort_mode == 'az' else "Orden 🔤"
        nav_row.append(InlineKeyboardButton(btn_sort_text,
                                            callback_data=f"trade_sreg_{sender_id}_{region}_0_{new_sort}_{cmd_msg_id}"))

    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior",
                                            callback_data=f"trade_sreg_{sender_id}_{region}_{page - 1}_{sort_mode}_{cmd_msg_id}"))
    if end < len(missing_species):
        nav_row.append(InlineKeyboardButton("Siguiente ➡️",
                                            callback_data=f"trade_sreg_{sender_id}_{region}_{page + 1}_{sort_mode}_{cmd_msg_id}"))

    if nav_row: keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=f"trade_search_start_{sender_id}_{cmd_msg_id}")])

    text = f"🔍 **Elige el sticker que deseas conseguir ({region.capitalize()}):**"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_search_sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pantalla 3: Muestra usuarios del grupo con este Pokémon repetido."""
    query = update.callback_query
    parts = query.data.split('_')
    sender_id = int(parts[2])
    pokemon_id = int(parts[3])
    page = int(parts[4])
    cmd_msg_id = parts[5] if len(parts) > 5 else ""

    if query.from_user.id != sender_id:
        return await query.answer("No es tu menú.", show_alert=True)

    chat_id = query.message.chat.id
    group_users = db.get_users_in_group(chat_id)
    group_users = [u for u in group_users if u != sender_id]  # Excluir al propio buscador

    available_trades = []
    for uid in group_users:
        dupes = db.get_user_duplicates(uid)
        for d_pid, d_shiny in dupes:
            if d_pid == pokemon_id:
                available_trades.append((uid, d_shiny))

    if not available_trades:
        await query.answer("❌ Nadie del grupo tiene ese sticker repetido.", show_alert=True)
        # Volvemos a la pantalla de selección de región automáticamente
        text = "🔍 **Elige la región del sticker que deseas conseguir:**"
        keyboard = [
            [InlineKeyboardButton("🔸 Kanto", callback_data=f"trade_sreg_{sender_id}_kanto_0_num_{cmd_msg_id}")],
            [InlineKeyboardButton("🔹 Johto", callback_data=f"trade_sreg_{sender_id}_johto_0_num_{cmd_msg_id}")],
            [InlineKeyboardButton("❌ Cancelar", callback_data=f"trade_cancel_{sender_id}_{cmd_msg_id}")]
        ]
        return await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    trade_data = []
    for uid, is_shiny in available_trades:
        can_trade = db.check_trade_daily_limit(uid)
        # Intentar sacar nombre de BD rápido
        res = db.query_db("SELECT username FROM users WHERE user_id = %s", (uid,), one=True)
        uname = res[0] if res and res[0] else f"Entrenador"

        trade_data.append({
            'uid': uid,
            'name': uname,
            'is_shiny': is_shiny,
            'can_trade': can_trade
        })

    # Ordenar: Los que PUEDEN intercambiar van primero
    trade_data.sort(key=lambda x: not x['can_trade'])

    ITEMS_PER_PAGE = 10
    total_pages = math.ceil(len(trade_data) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_users = trade_data[start:end]

    keyboard = []
    for t in current_users:
        icon = "✅" if t['can_trade'] else "❌"
        shiny_str = " ✨" if t['is_shiny'] else ""
        btn_text = f"{icon} {t['name']}{shiny_str}"

        if t['can_trade']:
            # Mágico: Al pinchar, enviamos al usuario DIRECTO a la función 'trade_step2_handler' que ya tenemos programada
            cb_data = f"trade_step2_{t['uid']}_{sender_id}_{pokemon_id}_{int(t['is_shiny'])}_{cmd_msg_id}"
        else:
            cb_data = "trade_suser_err"

        keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

    # Navegación
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior",
                                            callback_data=f"trade_sstick_{sender_id}_{pokemon_id}_{page - 1}_{cmd_msg_id}"))
    if end < len(trade_data):
        nav_row.append(InlineKeyboardButton("Siguiente ➡️",
                                            callback_data=f"trade_sstick_{sender_id}_{pokemon_id}_{page + 1}_{cmd_msg_id}"))
    if nav_row: keyboard.append(nav_row)

    # Deducir región para volver correctamente
    region = 'kanto' if pokemon_id <= 151 else 'johto'
    keyboard.append(
        [InlineKeyboardButton("⬅️ Volver", callback_data=f"trade_sreg_{sender_id}_{region}_0_num_{cmd_msg_id}")])

    p_name = POKEMON_BY_ID[pokemon_id]['name']
    text = f"🔍 **Usuarios con {p_name} repetido:**\nSelecciona el usuario con el que quieres intercambiar:"

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_search_user_err_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pop-up para cuando se pincha en un usuario sin intercambios diarios."""
    await update.callback_query.answer("Este usuario no tiene intercambios disponibles.", show_alert=True)


# ==========================================


async def show_trade_menu_target_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id, sender_id,
                                            region, page=0, cmd_msg_id=""):
    duplicates = db.get_user_duplicates(target_id)

    # 1. Filtro por Región
    filtered_dupes = []
    for pid, shiny in duplicates:
        if region == 'kanto' and 1 <= pid <= 151:
            filtered_dupes.append((pid, shiny))
        elif region == 'johto' and (152 <= pid <= 251 or pid > 20000):
            filtered_dupes.append((pid, shiny))

    if not filtered_dupes:
        text = f"❌ El otro usuario no tiene stickers repetidos de {region.capitalize()} para cambiar."
        keyboard = [[InlineKeyboardButton("⬅️ Volver a regiones",
                                          callback_data=f"trade_back_reg_{target_id}_{sender_id}_{cmd_msg_id}")]]
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    sender_collection = db.get_all_user_stickers(sender_id)

    # 2. Función de Estado: 0 (No tiene especie), 1 (Tiene una variante), 2 (Ya tiene esa variante exacta)
    def get_status(p_id, s_shiny, collection):
        has_exact = (p_id, s_shiny) in collection
        has_normal = (p_id, 0) in collection
        has_shiny = (p_id, 1) in collection

        if not has_normal and not has_shiny: return 0  # Le falta la especie entera (🆕)
        if not has_exact: return 1  # Le falta esta variante, pero tiene la otra (✔️)
        return 2  # Ya tiene esta variante exacta (Nada)

    # 3. Ordenación Inteligente
    def sort_key(item):
        pid, shiny = item
        status = get_status(pid, shiny, sender_collection)
        name = POKEMON_BY_ID[pid]['name']
        # Prioridad 0 (Falta especie), 1 (Falta variante), 2 (Ya lo tiene)
        return (status, name)

    filtered_dupes.sort(key=sort_key)

    # 4. Paginación
    ITEMS_PER_PAGE = 20
    total_pages = math.ceil(len(filtered_dupes) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_list = filtered_dupes[start:end]

    keyboard = []
    row = []
    for poke_id, is_shiny in current_list:
        p_data = POKEMON_BY_ID[poke_id]
        rarity = get_rarity(p_data['category'], is_shiny)

        status = get_status(poke_id, is_shiny, sender_collection)

        if status == 0:
            mark = " 🆕"
        elif status == 1:
            mark = " ✔️"
        else:
            mark = ""

        shiny_mark = "✨" if is_shiny else ""
        btn_text = f"{p_data['name']}{shiny_mark} {RARITY_VISUALS.get(rarity, '')}{mark}"
        cb_data = f"trade_step2_{target_id}_{sender_id}_{poke_id}_{int(is_shiny)}_{cmd_msg_id}"

        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior",
                                            callback_data=f"trade_nav_target_{target_id}_{sender_id}_{region}_{page - 1}_{cmd_msg_id}"))
    if end < len(filtered_dupes):
        nav_row.append(InlineKeyboardButton("Siguiente ➡️",
                                            callback_data=f"trade_nav_target_{target_id}_{sender_id}_{region}_{page + 1}_{cmd_msg_id}"))
    if nav_row: keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("⬅️ Volver a regiones",
                                          callback_data=f"trade_back_reg_{target_id}_{sender_id}_{cmd_msg_id}")])

    target_name = (await context.bot.get_chat(target_id)).first_name
    text = f"♻ **Repetidos de {target_name} ({region.capitalize()}):**\nSelecciona qué quieres recibir."

    if update.callback_query:
        refresh_deletion_timer(context, update.callback_query.message, 120)
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                                      parse_mode='Markdown')
    else:
        msg = await context.bot.send_message(update.effective_chat.id, text,
                                             reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                             disable_notification=True)
        schedule_message_deletion(context, msg, 120)


async def trade_step2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    target_id, sender_id = int(parts[2]), int(parts[3])
    wanted_pid, wanted_shiny = int(parts[4]), bool(int(parts[5]))
    cmd_msg_id = parts[6] if len(parts) > 6 else ""

    if query.from_user.id != sender_id:
        return await query.answer("Solo la persona que inició el intercambio puede elegir.", show_alert=True)

    wanted_data = POKEMON_BY_ID[wanted_pid]
    wanted_rarity = get_rarity(wanted_data['category'], wanted_shiny)
    my_duplicates = db.get_user_duplicates(sender_id)

    valid_duplicates = []
    for pid, shiny in my_duplicates:
        p_data = POKEMON_BY_ID[pid]
        r = get_rarity(p_data['category'], shiny)
        if r == wanted_rarity:
            valid_duplicates.append((pid, shiny))

    target_collection = db.get_all_user_stickers(target_id)

    # 1. Función de Estado para el Destinatario
    def get_status(p_id, s_shiny, collection):
        has_exact = (p_id, s_shiny) in collection
        has_normal = (p_id, 0) in collection
        has_shiny = (p_id, 1) in collection

        if not has_normal and not has_shiny: return 0  # Le falta especie (🆕)
        if not has_exact: return 1  # Le falta variante (✔️)
        return 2  # Ya lo tiene (Nada)

    # 2. Ordenación Inteligente
    def sort_key_offer(item):
        pid, shiny = item
        status = get_status(pid, shiny, target_collection)
        name = POKEMON_BY_ID[pid]['name']
        return (status, name)

    valid_duplicates.sort(key=sort_key_offer)

    if not valid_duplicates:
        return await query.answer(f"❌ No tienes repetidos de rareza {wanted_rarity} para ofrecer.", show_alert=True)

    keyboard = []
    row = []
    for pid, shiny in valid_duplicates:
        p_data = POKEMON_BY_ID[pid]

        status = get_status(pid, shiny, target_collection)
        if status == 0:
            mark = " 🆕"
        elif status == 1:
            mark = " ✔️"
        else:
            mark = ""

        shiny_mark = "✨" if shiny else ""
        btn_text = f"{p_data['name']}{shiny_mark}{mark}"
        cb_data = f"trade_conf_{target_id}_{sender_id}_{wanted_pid}_{int(wanted_shiny)}_{pid}_{int(shiny)}"

        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    region_of_wanted = 'kanto' if wanted_pid <= 151 else 'johto'
    keyboard.append([InlineKeyboardButton("⬅️ Volver",
                                          callback_data=f"trade_nav_target_{target_id}_{sender_id}_{region_of_wanted}_0_{cmd_msg_id}")])

    text = (f"♻ **Tu Oferta ({wanted_rarity}):**\n"
            f"Elegiste: {wanted_data['name']}\n"
            f"Selecciona qué repetido ofreces a cambio:")

    refresh_deletion_timer(context, query.message, 120)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    target_id, sender_id = int(parts[2]), int(parts[3])

    if query.from_user.id != sender_id:
        await query.answer("Solo la persona que inició el intercambio puede elegir.", show_alert=True)
        return

    want_p, want_s = int(parts[4]), bool(int(parts[5]))
    offer_p, offer_s = int(parts[6]), bool(int(parts[7]))

    sender = await context.bot.get_chat(sender_id)
    target = await context.bot.get_chat(target_id)

    w_data = POKEMON_BY_ID[want_p]
    o_data = POKEMON_BY_ID[offer_p]

    w_name = f"{w_data['name']}{'✨' if want_s else ''}"
    o_name = f"{o_data['name']}{'✨' if offer_s else ''}"

    s_coll = db.get_all_user_stickers(sender_id)
    t_coll = db.get_all_user_stickers(target_id)

    s_new = "🆕" if (want_p, want_s) not in s_coll else ""
    t_new = "🆕" if (offer_p, offer_s) not in t_coll else ""

    text = (
        f"♻ **Petición de Intercambio**\n\n"
        f"👤 {sender.mention_markdown()} ofrece: {o_name} {t_new}\n"
        f"👤 Para {target.mention_markdown()} por: {w_name} {s_new}\n\n"
        f"Esperando confirmación de {target.mention_markdown()}..."
    )

    data_payload = f"{target_id}_{sender_id}_{want_p}_{int(want_s)}_{offer_p}_{int(offer_s)}"

    keyboard = [
        [InlineKeyboardButton("✅ Aceptar", callback_data=f"trade_exec_{data_payload}")],
        [InlineKeyboardButton("❌ Rechazar", callback_data=f"trade_reject_{data_payload}")]
    ]

    # --- CAMBIO IMPORTANTE: GESTIÓN DE TIEMPO ---
    # 1. Cancelamos borrado anterior del menú
    cancel_scheduled_deletion(context, query.message.chat_id, query.message.message_id)

    # 2. Registramos al usuario como ocupado
    context.chat_data.setdefault('active_trades', {})
    context.chat_data['active_trades'][sender_id] = query.message.message_id

    # 3. Programamos la tarea de LIMPIEZA TOTAL en 24 horas (86400s)
    context.job_queue.run_once(
        trade_timeout_job,
        86400,
        data={'chat_id': query.message.chat_id, 'user_id': sender_id, 'message_id': query.message.message_id},
        name=f"trade_timeout_{sender_id}"
    )
    # ---------------------------------------------

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_final_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    action = parts[1]  # exec o reject

    target_id, sender_id = int(parts[2]), int(parts[3])
    user_id = query.from_user.id

    # 1. Validaciones de permisos (Quién pulsa el botón)
    if action == "exec":
        if user_id != target_id:
            await query.answer("Solo el destinatario puede aceptar.", show_alert=True)
            return
    else:
        if user_id != target_id and user_id != sender_id:
            await query.answer("No puedes cancelar este intercambio.", show_alert=True)
            return

    # Liberar usuario del estado "ocupado"
    if sender_id in context.chat_data.get('active_trades', {}):
        del context.chat_data['active_trades'][sender_id]

    if action == "reject":
        await query.edit_message_text("❌ Intercambio cancelado.")
        # Programar borrado del aviso en 5 segundos (para que lo lea)
        schedule_message_deletion(context, query.message, 5)
        return

    # 2. Validar límites diarios
    if not db.check_trade_daily_limit(sender_id) or not db.check_trade_daily_limit(target_id):
        await query.answer("⛔ Error: Alguno de los dos alcanzó el límite diario.", show_alert=True)
        await query.delete_message()
        return

    # Datos de los Pokémon
    want_p, want_s = int(parts[4]), bool(int(parts[5]))  # Lo que da el TARGET (Destinatario)
    offer_p, offer_s = int(parts[6]), bool(int(parts[7]))  # Lo que da el SENDER (Solicitante)

    # 3. VALIDACIÓN CRÍTICA DE STOCK
    # Comprobamos si el Solicitante aún tiene el repetido que ofreció
    if not db.has_duplicate(sender_id, offer_p, offer_s):
        await query.answer("❌ Error: El usuario que envió la oferta ya no tiene ese Pokémon repetido.", show_alert=True)
        await query.delete_message()
        return

    # Comprobamos si el Destinatario aún tiene el repetido que se le pidió
    if not db.has_duplicate(target_id, want_p, want_s):
        await query.answer("❌ Error: Ya no tienes ese Pokémon repetido para intercambiar.", show_alert=True)
        await query.delete_message()
        return
    # ----------------------------------------

    # 4. Ejecución en Base de Datos
    status_sender, status_target = db.execute_trade(sender_id, offer_p, offer_s, target_id, want_p, want_s)

    # Obtener nombres e información
    sender = await context.bot.get_chat(sender_id)
    target = await context.bot.get_chat(target_id)

    s_name = sender.first_name
    t_name = target.first_name

    w_data = POKEMON_BY_ID[want_p]
    o_data = POKEMON_BY_ID[offer_p]

    w_txt = f"{w_data['name']}{'✨' if want_s else ''}"
    o_txt = f"{o_data['name']}{'✨' if offer_s else ''}"

    # Gestión de dinero si ya tenían 2
    if status_sender == 'MAX':
        rarity = get_rarity(w_data['category'], want_s)
        price = DUPLICATE_MONEY_VALUES.get(rarity, 100)
        db.update_money(sender_id, price)
        w_txt += f" (+{format_money(price)}₽)"

    if status_target == 'MAX':
        rarity = get_rarity(o_data['category'], offer_s)
        price = DUPLICATE_MONEY_VALUES.get(rarity, 100)
        db.update_money(target_id, price)
        o_txt += f" (+{format_money(price)}₽)"

    # --- DETECTOR DE ÁLBUM COMPLETO (Para ambos jugadores) ---
    premios_extra = ""

    # Comprobamos al Sender (El que inició el intercambio)
    if not db.is_kanto_completed_by_user(sender_id):
        if db.get_user_unique_kanto_count(sender_id) >= 151:
            db.set_kanto_completed_by_user(sender_id)
            db.update_money(sender_id, 3000)
            db.add_item_to_inventory(sender_id, 'pack_shiny_kanto', 1)
            premios_extra += f"\n\n🎊 ¡Felicidades {sender.mention_markdown()}, has completado *Kanto*! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

    if not db.is_johto_completed_by_user(sender_id):
        if db.get_user_unique_johto_count(sender_id) >= 100:
            db.set_johto_completed_by_user(sender_id)
            db.update_money(sender_id, 3000)
            db.add_item_to_inventory(sender_id, 'pack_shiny_johto', 1)
            premios_extra += f"\n\n🎊 ¡Felicidades {sender.mention_markdown()}, has completado *Johto*! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"

    if not db.is_unown_completed_by_user(sender_id):
        if db.get_user_unique_unown_count(sender_id) >= 28:
            db.set_unown_completed_by_user(sender_id)
            db.update_money(sender_id, 2000)
            db.add_item_to_inventory(sender_id, 'pack_shiny_unown', 1)
            premios_extra += f"\n\n🎊 ¡Felicidades {sender.mention_markdown()}, has completado el *Álbum Unown*! 🎊\n¡Recibes 2000₽ y un Sobre Brillante Unown!"

    # Comprobamos al Target (El que aceptó el intercambio)
    if not db.is_kanto_completed_by_user(target_id):
        if db.get_user_unique_kanto_count(target_id) >= 151:
            db.set_kanto_completed_by_user(target_id)
            db.update_money(target_id, 3000)
            db.add_item_to_inventory(target_id, 'pack_shiny_kanto', 1)
            premios_extra += f"\n\n🎊 ¡Felicidades {target.mention_markdown()}, has completado *Kanto*! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Kanto!"

    if not db.is_johto_completed_by_user(target_id):
        if db.get_user_unique_johto_count(target_id) >= 100:
            db.set_johto_completed_by_user(target_id)
            db.update_money(target_id, 3000)
            db.add_item_to_inventory(target_id, 'pack_shiny_johto', 1)
            premios_extra += f"\n\n🎊 ¡Felicidades {target.mention_markdown()}, has completado *Johto*! 🎊\n¡Recibes 3000₽ y un Sobre Brillante Johto!"

    if not db.is_unown_completed_by_user(target_id):
        if db.get_user_unique_unown_count(target_id) >= 28:
            db.set_unown_completed_by_user(target_id)
            db.update_money(target_id, 2000)
            db.add_item_to_inventory(target_id, 'pack_shiny_unown', 1)
            premios_extra += f"\n\n🎊 ¡Felicidades {target.mention_markdown()}, has completado el *Álbum Unown*! 🎊\n¡Recibes 2000₽ y un Sobre Brillante Unown!"
    # ---------------------------------------------------------

    final_text = (
        f"♻✅ **¡Intercambio aceptado!**\n\n"
        f"👤 {s_name} recibió: {w_txt}\n"
        f"👤 {t_name} recibió: {o_txt}"
        f"{premios_extra}"
    )

    await query.edit_message_text(final_text, parse_mode='Markdown')


async def trade_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    """Tarea que se ejecuta a las 24h para limpiar datos y mensaje."""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    user_id = job_data['user_id']
    message_id = job_data['message_id']

    # 1. Limpiar memoria (Liberar al usuario)
    if user_id in context.chat_data.get('active_trades', {}):
        del context.chat_data['active_trades'][user_id]

    # 2. Borrar mensaje visual
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        pass  # Si ya no existe, no pasa nada


async def regional_event_announcement_job(context: ContextTypes.DEFAULT_TYPE):
    """Avisa a las 10:00 si hay un evento regional activo."""
    today_str = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d')

    # Limpiar BD de días pasados
    db.clean_old_scheduled_events(today_str)

    active_regional_event = db.get_scheduled_event(today_str)

    if active_regional_event:
        text = f"📜 <b>Evento activo. Durante el día de hoy solo aparecerán Pokémon y Eventos de {active_regional_event}.</b>"
        active_groups = db.get_active_groups()
        for chat_id in active_groups:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
                await asyncio.sleep(0.1)
            except:
                pass

async def trade_cancel_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el botón de Cancelar en el menú de selección de intercambio."""
    query = update.callback_query
    # Formato: trade_cancel_SENDER_MSGID
    parts = query.data.split('_')
    sender_id = int(parts[2])

    if query.from_user.id != sender_id:
        await query.answer("Solo quien inició puede cancelar.", show_alert=True)
        return

    await query.delete_message()

    # Si hay un msg_id del comando, lo borramos en 1 segundo
    if len(parts) > 3 and parts[3].isdigit():
        cmd_msg_id = int(parts[3])
        context.job_queue.run_once(delete_message_job, 1,
                                   data={'chat_id': query.message.chat_id, 'message_id': cmd_msg_id},
                                   name=f"del_{cmd_msg_id}")

async def trade_force_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botón de emergencia para desbloquearse."""
    query = update.callback_query
    user_id = query.from_user.id

    # Limpiar memoria
    if user_id in context.chat_data.get('active_trades', {}):
        # Intentamos borrar el mensaje viejo si aun existe
        old_msg_id = context.chat_data['active_trades'][user_id]
        try:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=old_msg_id)
        except:
            pass

        del context.chat_data['active_trades'][user_id]
        await query.answer("✅ Intercambio anterior cancelado. Ya puedes iniciar uno nuevo.", show_alert=True)
        # Borramos el mensaje de error que contenía este botón
        await query.delete_message()
    else:
        await query.answer("Ya no tienes intercambios pendientes.", show_alert=True)
        await query.delete_message()


async def retos_missing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    refresh_deletion_timer(context, query.message, 30)

    try:
        parts = query.data.split('_')
        chat_id = int(parts[-2])  # El penúltimo es el ID
        # El último es el flag de desbloqueo (si existe, si no asumimos 0 por compatibilidad vieja)
        is_johto_unlocked = int(parts[-1]) if len(parts) > 4 else 0
    except:
        return

    text = "📂 **Selecciona una región para ver los faltantes:**"

    keyboard = []
    # Botón Kanto (Siempre)
    keyboard.append([InlineKeyboardButton("🔸 Kanto", callback_data=f"retos_view_kanto_{chat_id}")])

    # Botón Johto (Solo si desbloqueado)
    if is_johto_unlocked:
        keyboard.append([InlineKeyboardButton("🔹 Johto", callback_data=f"retos_view_johto_{chat_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=f"retos_back_{chat_id}")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def retos_view_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    refresh_deletion_timer(context, query.message, 30)

    data = query.data.split('_')
    region = data[2]
    chat_id = int(data[3])

    k_ids = db.get_group_unique_kanto_ids(chat_id)
    is_unlocked = 1 if len(k_ids) >= 113 else 0

    rarity_counts = {'C': 0, 'B': 0, 'A': 0, 'S': 0}
    rarity_totals = {'C': 0, 'B': 0, 'A': 0, 'S': 0}
    missing_names = []
    text = ""

    if region == 'kanto':
        group_ids = k_ids
        for p in ALL_POKEMON:
            if p['id'] > 151: continue
            rarity_totals[p['category']] += 1
            if p['id'] in group_ids:
                rarity_counts[p['category']] += 1
            else:
                missing_names.append(p['name'])

        text = "🔸 **Kanto:**\n\n"

    elif region == 'johto':
        raw_group_ids = db.get_group_unique_johto_ids(chat_id)
        # Excluir bebés y Unown del conteo (Los Legendarios SÍ entran)
        excluded_ids = {172, 173, 174, 175, 201, 236, 238, 239, 240}
        group_ids = {pid for pid in raw_group_ids if pid not in excluded_ids}

        # --- CORRECCIÓN: USAR ALL_POKEMON PARA INCLUIR LEGENDARIOS ---
        for p in ALL_POKEMON:
            if p['id'] < 152 or p['id'] > 251: continue
            if p['id'] in excluded_ids: continue  # Saltamos los bebés aquí también

            rarity_totals[p['category']] += 1
            if p['id'] in group_ids:
                rarity_counts[p['category']] += 1
            else:
                missing_names.append(p['name'])
        # --------------------------------------------------------------

        text = "🔹 **Johto:**\n\n"

    text += "_Rarezas:_\n"
    r_text = []
    for cat in ['C', 'B', 'A', 'S']:
        emoji = RARITY_VISUALS[cat]
        tot = rarity_totals[cat] if rarity_totals[cat] > 0 else 1
        r_text.append(f"{emoji} {rarity_counts[cat]}/{rarity_totals[cat]}")
    text += ", ".join(r_text) + "\n\n"

    if not missing_names:
        text += f"✅ _¡Álbumdex completo de {region.capitalize()}!_\n\n"
    else:
        text += "Faltan:\n"
        for name in missing_names[:50]: text += f"- {name}\n"
        if len(missing_names) > 50: text += f"... y {len(missing_names) - 50} más.\n"
        text += "\n"

    total_valid = sum(rarity_totals.values())
    text += f"📊 **Total: {len(group_ids)}/{total_valid}**"

    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data=f"retos_missing_menu_{chat_id}_{is_unlocked}")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_nav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    # Formato: trade_nav_target_TGT_SND_REGION_PAGE_MSGID
    target_id, sender_id, region, page = int(parts[3]), int(parts[4]), parts[5], int(parts[6])
    cmd_msg_id = parts[7] if len(parts) > 7 else ""

    if query.from_user.id != sender_id:
        return await query.answer("No es tu menú.", show_alert=True)

    await show_trade_menu_target_duplicates(update, context, target_id, sender_id, region, page, cmd_msg_id)

async def clemailbox_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if target_user:
        changes = db.clear_user_mailbox(target_user.id)
        await update.message.reply_text(
            f"✅ Buzón de {target_user.first_name} limpiado. Se eliminaron {changes} regalos.", disable_notification=True)
    elif args and args[0].lower() == 'all':
        changes = db.clear_all_mailboxes()
        await update.message.reply_text(
            f"✅ Todos los buzones han sido limpiados. Se eliminaron {changes} regalos en total.", disable_notification=True)
    else:
        await update.message.reply_text("Uso: `/clemailbox [@usuario|ID]` o `/clemailbox all`")


async def removemail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    try:
        mail_id = int(context.args[0])
        if db.remove_mail_item_by_id(mail_id):
            await update.message.reply_text(f"✅ Regalo con ID `{mail_id}` eliminado correctamente.", disable_notification=True)
        else:
            await update.message.reply_text(f"ℹ️No se encontró ningún regalo con el ID `{mail_id}`.", disable_notification=True)
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Uso: `/removemail <mail_id>`\nPuedes ver la ID del regalo en el comando /buzon.", disable_notification=True)


async def clearalbum_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)
    if not target_user:
        await update.message.reply_text(
            "Uso: `/clearalbum [@usuario|ID]`\nDebes especificar a quién quieres borrarle el álbum.", disable_notification=True)
        return
    changes = db.clear_user_collection(target_user.id)
    await update.message.reply_text(
        f"🗑️ ¡Álbumdex de {target_user.first_name} vaciado!\nSe eliminaron {changes} stickers de su colección.", disable_notification=True)


async def schedule_delibird_week(context: ContextTypes.DEFAULT_TYPE):
    """Calcula una nueva fecha aleatoria y la guarda en BD."""
    # 1. Calcular momento aleatorio en la semana (7 días)
    seconds_in_week = 7 * 24 * 3600
    random_delay = random.randint(3600, seconds_in_week - 3600)
    target_timestamp = time.time() + random_delay

    # 2. Guardar en Base de Datos (Persistencia)
    db.set_delibird_schedule(target_timestamp)

    # 3. Programar la ejecución en memoria
    context.job_queue.run_once(trigger_delibird_event, random_delay, name="delibird_weekly_event")

    trigger_date = datetime.fromtimestamp(target_timestamp)
    logger.info(f"🐧 Delibird PROGRAMADO y GUARDADO para: {trigger_date}")


async def check_delibird_startup(application):
    """Se ejecuta al encender el bot: recupera o reprograma Delibird asegurando 1 solo por semana."""
    last_check = application.bot_data.get('last_startup_check')
    now_min = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d %H:%M')
    if last_check == now_min:
        return
    application.bot_data['last_startup_check'] = now_min

    saved_timestamp = db.get_delibird_schedule()
    current_time = time.time()

    # 1. Si hay fecha guardada y es válida, la respetamos
    if saved_timestamp:
        delay = saved_timestamp - current_time

        if delay <= 0:
            logger.warning("🐧 Delibird detectado en startup. Lanzando...")
            db.clear_delibird_schedule()
            application.job_queue.run_once(trigger_delibird_event, 1, name="delibird_recovered_event")
        else:
            trigger_date = datetime.fromtimestamp(saved_timestamp, TZ_SPAIN)
            logger.info(f"🐧 Restaurando evento Delibird para: {trigger_date.strftime('%d/%m/%Y %H:%M:%S')}")
            application.job_queue.run_once(trigger_delibird_event, delay, name="delibird_restored_event")

    # 2. Si NO hay fecha, comprobamos si YA SALIÓ esta semana
    else:
        # Obtenemos la semana actual (ej: '2026-W42')
        current_week = datetime.now(TZ_SPAIN).strftime('%Y-W%V')

        # Le preguntamos a la BD si alguien tiene esa semana registrada como reclamada
        # (Usamos una consulta rápida para ver si existe al menos 1 registro esta semana)
        ya_salio = db.query_db("SELECT 1 FROM users WHERE last_delibird_claim = %s LIMIT 1", (current_week,), one=True)

        if ya_salio:
            logger.info("🐧 Startup: Delibird ya hizo su reparto esta semana. A dormir hasta el lunes.")
            return  # ¡Cortamos aquí! No programamos nada nuevo.

        # 3. Si NO hay fecha y NO ha salido esta semana, lo reprogramamos de emergencia
        seconds_left = get_seconds_until_end_of_week()

        if seconds_left < 7200:  # Quedan menos de 2 horas
            random_delay = random.randint(60, max(120, int(seconds_left) - 60))
        else:
            random_delay = random.randint(3600, int(seconds_left) - 3600)

        target_timestamp = current_time + random_delay
        db.set_delibird_schedule(target_timestamp)

        trigger_date = datetime.fromtimestamp(target_timestamp, TZ_SPAIN)
        logger.info(
            f"🐧 Delibird REPROGRAMADO de emergencia para esta semana: {trigger_date.strftime('%d/%m/%Y %H:%M:%S')}")
        application.job_queue.run_once(trigger_delibird_event, random_delay, name="delibird_emergency_event")


async def trigger_delibird_event(context: ContextTypes.DEFAULT_TYPE):
    """Lanza el evento."""
    # 1. Limpiamos la programación de la BD
    db.clear_delibird_schedule()

    active_groups = db.get_active_groups()
    current_time = time.time()

    # Log para saber qué está pasando
    logger.info(f"🐧 Lanzando Delibird a {len(active_groups)} grupos activos.")

    text = (
        "🐧🎁 **¡DELIBIRD HA LLEGADO!**\n\n"
        "Trae un saco lleno de sobres elementales de Kanto.\n"
        "¡Reclama el tuyo antes de que se vaya!\n\n"
    )

    keyboard = [
        [InlineKeyboardButton("🎁 ¡RECLAMAR SOBRE!", callback_data="delibird_claim")],
        [InlineKeyboardButton("ℹ", callback_data="delibird_info")]
    ]

    count_sent = 0
    for chat_id in active_groups:
        try:
            # Añadimos debug para ver a qué chat intenta enviar
            logger.info(f"🐧 Enviando a chat: {chat_id}")

            msg = await context.bot.send_message(chat_id=chat_id, text=text,
                                                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

            DELIBIRD_STATE[chat_id] = {
                'msg_id': msg.message_id,
                'winners': [],
                'timestamp': current_time
            }
            # Cierre en 24h
            context.job_queue.run_once(close_delibird_event, 86400, chat_id=chat_id, data=chat_id)
            count_sent += 1

        except Exception as e:
            # AQUÍ VERÁS EL ERROR EN RENDER SI FALLA
            logger.error(f"❌ Error enviando Delibird a {chat_id}: {e}")

    logger.info(f"🐧 Delibird enviado con éxito a {count_sent}/{len(active_groups)} grupos.")

async def close_delibird_event(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    state = DELIBIRD_STATE.get(chat_id)

    if state:
        try:
            # Editar mensaje final
            final_text = "🐧💤 **Delibird se fue a descansar**\n\nResultados del reparto:\n" + "\n".join(
                state['winners'])
            await context.bot.edit_message_text(chat_id=chat_id, message_id=state['msg_id'], text=final_text,
                                                parse_mode='Markdown')
        except:
            pass

        # Limpiar memoria
        del DELIBIRD_STATE[chat_id]


async def delibird_claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    message = query.message

    if query.data == "delibird_info":
        await query.answer(
            "🎒 Contiene sobres de tipos (Fuego, Agua, etc...) y Sobres Especiales con más probabilidad de Shiny.",
            show_alert=True)
        return

    # --- 1. DEFENSA CONTRA MENSAJES ZOMBIES ---
    # Comprobamos la edad real del mensaje en Telegram
    msg_timestamp = message.date.timestamp()
    current_timestamp = time.time()

    if (current_timestamp - msg_timestamp) > 86400:  # 86400s = 24 horas
        await query.answer("Delibird ya se fue a descansar...", show_alert=True)

        # Rescatamos la lista de ganadores para cerrar el mensaje de forma bonita
        winners_list = []
        current_text = message.text_markdown if message.text_markdown else message.text
        if "Resultados:" in current_text:
            parts = current_text.split("Resultados:\n")
            if len(parts) > 1:
                raw_lines = parts[1].split("\n")
                winners_list = [line for line in raw_lines if line.strip()]

        final_text = "🐧💤 **Delibird se fue a descansar**\n\nResultados del reparto:\n" + "\n".join(winners_list)
        try:
            await query.edit_message_text(text=final_text, parse_mode='Markdown')
        except:
            pass
        return
    # ------------------------------------------

    # --- 2. RECUPERACIÓN DE ESTADO EN RAM (SI SE REINICIÓ RECIENTEMENTE) ---
    state = DELIBIRD_STATE.get(chat_id)

    if not state:
        current_text = message.text_markdown if message.text_markdown else message.text
        if "DELIBIRD HA LLEGADO" in current_text:
            winners_list = []
            if "Resultados:" in current_text:
                parts = current_text.split("Resultados:\n")
                if len(parts) > 1:
                    raw_lines = parts[1].split("\n")
                    winners_list = [line for line in raw_lines if line.strip()]

            DELIBIRD_STATE[chat_id] = {
                'msg_id': message.message_id,
                'winners': winners_list,
                'timestamp': time.time()
            }
            state = DELIBIRD_STATE[chat_id]
        else:
            await query.answer("Delibird ya se ha ido...", show_alert=True)
            return

    # --- 3. VERIFICACIÓN SEGURA EN BASE DE DATOS ---
    if db.check_delibird_claimed_this_week(user.id):
        await query.answer("¡Ya has cogido un sobre esta semana!", show_alert=True)
        return
    # -----------------------------------------------

    # Seleccionar premio
    possible_packs = [k for k in SHOP_CONFIG.keys() if k.startswith('pack_elem_')]
    prize_id = random.choice(possible_packs)
    prize_info = SHOP_CONFIG[prize_id]

    # Dar premio (A LA MOCHILA)
    db.get_or_create_user(user.id, user.first_name)
    db.add_item_to_inventory(user.id, prize_id, 1)

    # MARCAR EN BASE DE DATOS
    db.set_delibird_claimed(user.id)

    # Actualizar lista visual
    safe_name = user.first_name.replace('*', '').replace('_', '')
    pack_display_name = f"🎴{prize_info['emoji']} Sobre {prize_info.get('type_filter', 'Especial')} de Kanto"
    list_line = f"- {safe_name} recibió {pack_display_name}."
    state['winners'].append(list_line)

    new_text = (
            "🐧🎁 **¡DELIBIRD HA LLEGADO!**\n\n"
            "Trae un saco lleno de sobres elementales de Kanto.\n"
            "¡Reclama el tuyo antes de que se vaya!\n\n"
            "Resultados:\n" + "\n".join(state['winners'])
    )

    try:
        await query.edit_message_text(text=new_text, reply_markup=query.message.reply_markup, parse_mode='Markdown')
    except:
        pass

    await query.answer(f"¡Has conseguido un {prize_info['name']}!\nLo guardas en tu mochila.", show_alert=True)

# COMANDO DE TEST
async def admin_test_delibird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return

    chat_id = update.effective_chat.id
    # Borrar mensaje del comando
    await update.message.delete()

    # --- CORRECCIÓN AQUÍ: Añadido 'db.' delante de query_db ---
    # Limpiar mi estado en la base de datos para poder probar
    db.query_db("UPDATE users SET last_delibird_claim = NULL WHERE user_id = ?", (update.effective_user.id,))
    # ----------------------------------------------------------

    text = (
        "🐧🎁 **¡DELIBIRD HA LLEGADO!** (Test)\n\n"
        "Trae un saco lleno de sobres elementales de Kanto.\n"
        "¡Reclama el tuyo antes de que se vaya!\n\n"
        "_La bolsa contiene sobres de cada tipo de Pokémon o un Sobre Especial de 7 stickers._"
    )

    keyboard = [
        [InlineKeyboardButton("🎁 ¡RECLAMAR PREMIO!", callback_data="delibird_claim")],
        [InlineKeyboardButton("ℹ️ ¿Qué hay en el saco?", callback_data="delibird_info")]
    ]

    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard),
                                             parse_mode='Markdown')

        # Guardar estado SOLO para este chat
        DELIBIRD_STATE[chat_id] = {
            'msg_id': msg.message_id,
            'winners': [],
            'timestamp': time.time()
        }

        # Programar cierre
        context.job_queue.run_once(close_delibird_event, 86400, chat_id=chat_id, data=chat_id)

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Error test: {e}")


async def admin_force_unlock_johto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fuerza el desbloqueo de Johto en el grupo actual."""
    if update.effective_user.id != ADMIN_USER_ID: return

    chat_id = update.effective_chat.id

    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Este comando solo funciona en grupos.", disable_notification=True)
        return

    # Comprobamos si ya estaba desbloqueado
    if db.is_event_completed(chat_id, 'amelia_johto_unlock'):
        msg = await update.message.reply_text("ℹ️ Johto ya estaba desbloqueado en este grupo.",
                                              disable_notification=True)
    else:
        # Marcamos el evento como completado
        db.mark_event_completed(chat_id, 'amelia_johto_unlock')
        msg = await update.message.reply_text("✅ ¡Región de Johto desbloqueada manualmente para este grupo!",
                                              disable_notification=True)

    # Borrar mensajes
    schedule_message_deletion(context, update.message, 5)
    schedule_message_deletion(context, msg, 10)

# --- COMANDOS ADMIN EXTRA ---

async def admin_reset_group_kanto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("Este comando debe usarse dentro del grupo que quieres limpiar.")

    chat_id = update.effective_chat.id
    db.reset_group_pokedex(chat_id)
    await update.message.reply_text("🗑️ Se ha eliminado todo el progreso del reto grupal en este chat.", disable_notification=True)


async def admin_check_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text("Uso: Responde a un mensaje del usuario.", disable_notification=True)

    money = db.get_user_money(target_user.id)
    await update.message.reply_text(f"💰 {target_user.first_name} tiene: *{format_money(money)}₽*",
                                    parse_mode='Markdown', disable_notification=True)


async def admin_set_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)

    if not target_user or not args:
        return await update.message.reply_text("Uso: Responde al usuario y pon `/setmoney <cantidad>`", disable_notification=True)

    try:
        amount = int(args[0])
        db.set_money(target_user.id, amount)
        await update.message.reply_text(
            f"✅ El dinero de {target_user.first_name} se ha fijado en *{format_money(amount)}₽*.",
            parse_mode='Markdown', disable_notification=True)
    except ValueError:
        await update.message.reply_text("❌ Cantidad inválida.", disable_notification=True)


async def admin_list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return

    groups = db.get_active_groups()

    text = "📂 **Grupos con Spawn Activo:**\n"
    if not groups:
        text += "_No hay grupos activos en este momento._"
    else:
        for gid in groups:
            try:
                chat = await context.bot.get_chat(gid)
                text += f"- {chat.title} (ID: `{gid}`)\n"
            except BadRequest:
                text += f"- Desconocido/Expulsado (ID: `{gid}`)\n"

    await update.message.reply_text(text, parse_mode='Markdown')


async def admin_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)

    if not target_user:
        return await update.message.reply_text("Responde a un mensaje o menciona al usuario.", disable_notification=True)

    await update.message.reply_text(f"👤 **Usuario:** {target_user.full_name}\n🆔 **ID:** `{target_user.id}`",
                                    parse_mode='Markdown', disable_notification=True)


async def admin_view_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return

    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("Uso: `/vermochila <user_id>`", disable_notification=True)

    items = db.get_user_inventory(target_id)
    if not items:
        return await update.message.reply_text(f"🎒 La mochila del usuario `{target_id}` está vacía.",
                                               parse_mode='Markdown', disable_notification=True)

    text = f"🎒 **Mochila de {target_id}:**\n\n"
    for item in items:
        name = ITEM_NAMES.get(item['item_id'], item['item_id'])
        text += f"🔸️{name} (ID: `{item['item_id']}`) x{item['quantity']}\n"

    await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)


async def admin_remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)

    if not target_user or not args:
        return await update.message.reply_text("Uso: `/quitarobjeto <usuario> <item_id> [cantidad]`", disable_notification=True)

    item_id = args[0]
    qty = 1
    if len(args) > 1 and args[1].isdigit():
        qty = int(args[1])

    db.remove_item_from_inventory(target_user.id, item_id, qty)
    await update.message.reply_text(
        f"🗑️ Eliminados {qty}x `{item_id}` de la mochila de {target_user.mention_markdown()}.", parse_mode='Markdown', disable_notification=True)


async def admin_add_bulk_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)

    if not target_user or not args:
        return await update.message.reply_text(
            "Uso: `/addbulk @usuario ID [ID_s] ...`\nEj: `/addbulk @Pepe 1 4s 7` (4s = Charmander Shiny)", disable_notification=True)

    added = []

    for arg in args:
        try:
            is_shiny = 0
            if 's' in arg.lower():
                p_id = int(arg.lower().replace('s', ''))
                is_shiny = 1
            elif '_' in arg:
                parts = arg.split('_')
                p_id = int(parts[0])
                is_shiny = int(parts[1])
            else:
                p_id = int(arg)

            p_data = POKEMON_BY_ID.get(p_id)
            if p_data:
                db.add_sticker_to_collection(target_user.id, p_id, is_shiny)
                added.append(f"{p_data['name']}{'✨' if is_shiny else ''}")
        except ValueError:
            continue

    if added:
        await update.message.reply_text(f"✅ Añadidos a {target_user.first_name}:\n" + ", ".join(added), disable_notification=True)
    else:
        await update.message.reply_text("❌ No se pudo añadir ningún Pokémon.", disable_notification=True)


async def admin_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca usuarios en la BD por nombre parcial."""
    if update.effective_user.id != ADMIN_USER_ID: return

    try:
        if not context.args:
            await update.message.reply_text("Uso: `/buscaruser <nombre>`", disable_notification=True)
            return

        search_term = context.args[0]

        # Buscamos en la base de datos (el % sirve para buscar coincidencias parciales)
        # Nota: Usamos LOWER para ignorar mayúsculas/minúsculas
        sql = "SELECT user_id, username FROM users WHERE LOWER(username) LIKE ?"
        # En Postgres LIKE es sensitive, pero al bajar a lower comparamos igual.
        # El helper query_db convierte ? a %s si es Postgres.

        results = db.query_db(sql, (f'%{search_term.lower()}%',))

        if not results:
            await update.message.reply_text("❌ No encontré a nadie con ese nombre.", disable_notification=True)
            return

        text = f"🔍 **Resultados para '{search_term}':**\n\n"
        for row in results:
            # row[0] es ID, row[1] es Username
            text += f"👤 {row[1]} \n🆔 ID: `{row[0]}`\n\n"

        await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}", disable_notification=True)


async def admin_force_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fuerza el reparto de premios y el ranking del mes actual manualmente."""
    if update.effective_user.id != ADMIN_USER_ID: return

    try:
        await update.message.reply_text("🚀 Iniciando proceso de Ranking Mensual forzado...", disable_notification=True)

        # Llamamos a la función del trabajo mensual forzando la ejecución
        await check_monthly_job(context, force=True)

        await update.message.reply_text("✅ Ranking calculado, premios enviados y contadores reseteados.",
                                        disable_notification=True)

    except Exception as e:
        logger.error(f"Error forzando ranking: {e}")
        await update.message.reply_text(f"❌ Error al forzar ranking: {e}", disable_notification=True)


async def admin_force_stop_remote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return

    if not context.args:
        # Aquí SÍ va el disable_notification (en el reply_text)
        return await update.message.reply_text("Uso: `/forcestop <chat_id>`", disable_notification=True)

    try:
        target_chat_id = int(context.args[0])

        # --- CORRECCIÓN AQUÍ: Quitar disable_notification de get_jobs_by_name ---
        jobs = context.job_queue.get_jobs_by_name(f"spawn_{target_chat_id}")
        # ------------------------------------------------------------------------

        for job in jobs:
            job.schedule_removal()

        db.set_group_active(target_chat_id, False)

        await update.message.reply_text(f"🛑 Juego detenido forzosamente en el grupo `{target_chat_id}`.",
                                        disable_notification=True)

    except ValueError:
        await update.message.reply_text("❌ ID de chat inválida.", disable_notification=True)
    except Exception as e:
        logger.error(f"Error en forcestop: {e}")
        await update.message.reply_text("❌ Error al detener el juego.", disable_notification=True)


async def post_init(application: Application):
    bot = cast(Bot, getattr(application, "bot"))
    user_commands = [
        BotCommand("albumdex", "📖 Revisa tu progreso."),
        BotCommand("tienda", "🏪 Compra sobres de stickers."),
        BotCommand("mochila", "🎒 Revisa tus objetos."),
        BotCommand("intercambio", "♻ Intercambia stickers."),
        BotCommand("guarderia", "🏡 Guardería Pokémon."),
        BotCommand("tombola", "🎟️ Tómbola diaria."),
        BotCommand("buzon", "💌 Revisa tu buzón."),
        BotCommand("retos", "🤝 Retos Grupales."),
        BotCommand("dinero", "💰 Consulta tu dinero."),
        BotCommand("regalar", "💸 Envía dinero a otro jugador."),
        BotCommand("codigos", "👥 Lista de Códigos de Amigo."),
        BotCommand("start", "▶️ Inicia el juego (solo admins)."),
        BotCommand("stopgame", "⏸️ Detiene el juego (solo admins).")
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllGroupChats())

    logger.info("Comandos del bot configurados exitosamente.")

    # --- RECUPERACIÓN DE EVENTOS (DELIBIRD) ---
    # Comprobamos si había un evento pendiente al encender el bot
    await check_delibird_startup(application)


async def daily_tombola_job(context: ContextTypes.DEFAULT_TYPE):
    # --- LOG DE CONTROL ---
    logger.info("🕒 EJECUTANDO TÓMBOLA DIARIA (SISTEMA GLOBAL)...")
    # ----------------------

    text = (
        "🎟️ *Tómbola Diaria* 🎟️\n\n"
        "¡Prueba suerte una vez al día!\nEstos son los premios, dependiendo de la bola que saques:\n"
        "🟤 100₽ | 🟢 200₽ | 🔵 400₽ | 🟡 ¡Sobre Mágico!"
    )
    keyboard = [[InlineKeyboardButton("Probar Suerte ✨", callback_data="tombola_claim_public")]]
    markup = InlineKeyboardMarkup(keyboard)

    active_groups = db.get_active_groups()
    for chat_id in active_groups:
        try:
            # Enviamos el mensaje
            msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode='Markdown')

            # GUARDAMOS EN LA VARIABLE GLOBAL (INFALIBLE)
            TOMBOLA_STATE[chat_id] = {
                'msg_id': msg.message_id,
                'winners': []
            }

        except Exception as e:
            logger.error(f"No se pudo enviar la tómbola al chat {chat_id}: {e}")


def main():
    keep_alive()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # --- ZONA DE TAREAS PROGRAMADAS (LIMPIA) ---

    # 1. Ranking Mensual (Día 1 a las 12:00)
    old_ranking = application.job_queue.get_jobs_by_name("monthly_ranking_check")
    for job in old_ranking: job.schedule_removal()

    application.job_queue.run_daily(
        check_monthly_job,
        time=dt_time(12, 0, tzinfo=TZ_SPAIN),
        name="monthly_ranking_check"
    )

    # 2. Tómbola Diaria (00:01)
    old_tombola = application.job_queue.get_jobs_by_name("daily_tombola_broadcast")
    for job in old_tombola: job.schedule_removal()

    application.job_queue.run_daily(
        daily_tombola_job,
        time=dt_time(0, 1, tzinfo=TZ_SPAIN),
        name="daily_tombola_broadcast"
    )

    # 3. Recordatorio de Códigos (12:00)
    old_codes = application.job_queue.get_jobs_by_name("code_expiration_check")
    for job in old_codes: job.schedule_removal()

    application.job_queue.run_daily(
        check_code_expiration_job,
        time=dt_time(12, 0, tzinfo=TZ_SPAIN),
        name="code_expiration_check"
    )

    # 4. Planificador Semanal de Delibird (Lunes 00:05)
    old_delibird = application.job_queue.get_jobs_by_name("delibird_scheduler")
    for job in old_delibird: job.schedule_removal()

    application.job_queue.run_daily(
        schedule_delibird_week,
        time=dt_time(0, 5, tzinfo=TZ_SPAIN),
        days=(0,),  # 0 = Lunes (Corregido)
        name="delibird_scheduler"
    )

    # 5. Incubadora de Huevos (Cada 5 minutos)
    application.job_queue.run_repeating(
        egg_hatch_job,
        interval=300,
        first=10,
        name="egg_hatching_check"
    )

    # Aviso de Evento Regional (10:00 AM)
    old_regev = application.job_queue.get_jobs_by_name("regional_event_announcement")
    for job in old_regev: job.schedule_removal()

    application.job_queue.run_daily(
        regional_event_announcement_job,
        time=dt_time(10, 0, tzinfo=TZ_SPAIN),
        name="regional_event_announcement"
    )

    # Limpiador de minijuegos caducados (03:00 AM)
    application.job_queue.run_daily(
        clean_expired_minigames_job,
        time=dt_time(3, 0, tzinfo=TZ_SPAIN),
        name="clean_expired_minigames"
    )


    async def admin_setup_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Crea el mensaje fijo de códigos."""
        if update.effective_user.id != ADMIN_USER_ID: return
        chat_id = update.effective_chat.id

        # Creamos un mensaje "dummy" que luego la función de refresh rellenará
        msg = await update.message.reply_text("⏳ Generando tablón de códigos...", disable_notification=True)

        # Guardamos la ID y lo rellenamos
        db.set_codes_board_msg(chat_id, msg.message_id)
        await refresh_codes_board(context.bot, chat_id)

        await update.message.delete()


    async def menu_grupo_shuffle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = "ℹ️ Menú:"

        # Creamos la lista de botones URL (cada uno en su propia fila)
        keyboard = [
            [InlineKeyboardButton("🗓 Calendario de Eventos Especiales", url="https://t.me/pokemon_shuffle/136468")],
            [InlineKeyboardButton("👥 Lista de Códigos Shuffle", url="https://t.me/pokemon_shuffle/376680")],
            [InlineKeyboardButton("🏆 Retos de Grupo", url="https://t.me/pokemon_shuffle/172831")],
            [InlineKeyboardButton("🗣 Off-Topic", url="https://t.me/joinchat/BJ0pDg7ntNfIFuVonHSTiQ")],
            [InlineKeyboardButton("🔴 Pokémon Go", url="https://t.me/joinchat/Y4wR9kZnCX0zZTVk")],
            [InlineKeyboardButton("🎴 Pokémon TCGP", url="https://t.me/+4iaXq14CXIsyOWM0")]
        ]

        # Enviamos el mensaje con el teclado
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_notification=True
        )
    # ---------------------------------------------------------------

    all_handlers: list[BaseHandler] = [
        ChatMemberHandler(welcome_message, ChatMemberHandler.MY_CHAT_MEMBER),

        CommandHandler("start", start),
        CommandHandler("stopgame", stop_game),
        CommandHandler("buzon", buzon),
        CommandHandler("tombola", tombola_start),
        CommandHandler("mochila", inventory_cmd),
        CommandHandler("albumdex", albumdex_cmd),
        CommandHandler("retos", retos_cmd),
        CommandHandler("dinero", dinero),
        CommandHandler("regalar", regalar_cmd),
        CommandHandler("tienda", tienda_cmd),
        CommandHandler("ratio", ratio_cmd),
        CommandHandler("moddinero", moddinero_cmd),
        CommandHandler("sendtoall", send_to_all),
        CommandHandler("sendsticker", send_sticker_cmd),
        CommandHandler("addsticker", add_sticker_cmd),
        CommandHandler("removesticker", remove_sticker_cmd),
        CommandHandler("clemailbox", clemailbox_cmd),
        CommandHandler("removemail", removemail_cmd),
        CommandHandler("clearalbum", clearalbum_cmd),
        CommandHandler("resetmoney", resetmoney_cmd),
        CommandHandler("darobjeto", darobjeto_cmd),
        CommandHandler("forcespawn", force_spawn_command),
        CommandHandler("regalarobjeto", regalar_objeto_cmd),


        CommandHandler("resetgroup", admin_reset_group_kanto),
        CommandHandler("checkmoney", admin_check_money),
        CommandHandler("setmoney", admin_set_money),
        CommandHandler("listgroups", admin_list_groups),

        CommandHandler("getid", admin_get_id),
        CommandHandler("vermochila", admin_view_inventory),
        CommandHandler("quitarobjeto", admin_remove_item),
        CommandHandler("addbulk", admin_add_bulk_stickers),
        CommandHandler("forcestop", admin_force_stop_remote),
        CommandHandler("setup", setup_panel),
        CommandHandler("bangroup", admin_ban_group),
        CommandHandler("unbangroup", admin_unban_group),
        CommandHandler("listbanned", admin_list_banned),
        CommandHandler("notibon", notib_on_cmd),
        CommandHandler("notiboff", notib_off_cmd),
        CommandHandler("noticon", notic_on_cmd),
        CommandHandler("noticoff", notic_off_cmd),
        CommandHandler("codigos", codigos_cmd),
        CommandHandler("sendtogroup", admin_send_to_group),
        CommandHandler("buscaruser", admin_search_user),
        CommandHandler("borrarcodigo", delete_code_cmd),
        CommandHandler("intercambio", intercambio_cmd),
        CommandHandler("testdelibird", admin_test_delibird),
        CommandHandler("forceevent", admin_force_delibird),
        CommandHandler("unlockjohto", admin_force_unlock_johto),
        CommandHandler("fixdb", admin_fix_johto_db),
        CommandHandler("guarderia", guarderia_cmd),
        CommandHandler("forceranking", admin_force_ranking),
        CommandHandler("eventoregion", admin_regional_event),
        CommandHandler("setupcodigos", admin_setup_codes),
        CommandHandler("regalodelibird", admin_regalo_delibird),
        CommandHandler("forceevento", force_event_command),
        CommandHandler("menugruposhuffle", menu_grupo_shuffle_cmd),
        CommandHandler("testminijuego", test_minijuego_cmd),
        CommandHandler("cuandodelibird", admin_check_delibird),
        CommandHandler("rankingmensual", ranking_mensual_cmd),
        CommandHandler("multisobre", multisobre_cmd),
        CommandHandler("multicompra", multicompra_cmd),

        CallbackQueryHandler(claim_event_handler, pattern="^event_claim_"),
        CallbackQueryHandler(event_step_handler, pattern=r"^ev\|"),

        CallbackQueryHandler(albumdex_cmd, pattern="^album_main_"),
        CallbackQueryHandler(album_close_handler, pattern="^album_close_"),
        CallbackQueryHandler(album_dupe_menu, pattern="^album_dupe_menu_"),
        CallbackQueryHandler(album_dupe_show, pattern="^album_dupe_show_"),
        CallbackQueryHandler(album_region_handler, pattern="^album_"),
        CallbackQueryHandler(choose_sticker_version_handler, pattern="^showsticker_"),
        CallbackQueryHandler(send_sticker_handler, pattern="^sendsticker_"),
        CallbackQueryHandler(claim_button_handler, pattern="^claim_"),
        CallbackQueryHandler(claim_mail_handler, pattern="^claimmail_"),
        CallbackQueryHandler(claim_all_mail_handler, pattern="^claimall_"),
        CallbackQueryHandler(buzon_refresh_handler, pattern="^buzon_refresh_"),
        CallbackQueryHandler(tombola_claim, pattern="^tombola_claim_"),
        CallbackQueryHandler(open_pack_handler, pattern="^openpack_"),
        CallbackQueryHandler(prebuy_pack_handler, pattern="^prebuy_"),
        CallbackQueryHandler(confirm_buy_pack_handler, pattern="^confirmbuy_"),
        CallbackQueryHandler(tienda_close_handler, pattern="^shop_close_"),
        CallbackQueryHandler(tienda_cmd, pattern="^shop_refresh_"),
        CallbackQueryHandler(missing_sticker_handler, pattern="^missing_sticker$"),
        CallbackQueryHandler(view_ticket_handler, pattern="^viewticket_"),
        CallbackQueryHandler(view_special_item_handler, pattern="^viewspecial_"),
        CallbackQueryHandler(show_special_item_handler, pattern="^showspecial_"),
        CallbackQueryHandler(panel_handler, pattern="^panel_"),
        CallbackQueryHandler(codigos_btn_handler, pattern="^codes_menu_"),
        CallbackQueryHandler(retos_missing_menu, pattern="^retos_missing_menu_"),
        CallbackQueryHandler(retos_view_region, pattern="^retos_view_"),
        CallbackQueryHandler(retos_cmd, pattern="^retos_back_"),
        CallbackQueryHandler(trade_step2_handler, pattern="^trade_step2_"),
        CallbackQueryHandler(trade_confirm_handler, pattern="^trade_conf_"),
        CallbackQueryHandler(trade_final_handler, pattern="^trade_(exec|reject)_"),
        CallbackQueryHandler(trade_nav_handler, pattern="^trade_nav_target_"),
        CallbackQueryHandler(trade_cancel_menu_handler, pattern="^trade_cancel_"),
        CallbackQueryHandler(trade_reg_handler, pattern="^trade_reg_"),
        CallbackQueryHandler(trade_back_reg_handler, pattern="^trade_back_reg_"),
        CallbackQueryHandler(ranking_navigation_handler, pattern="^rank_nav_"),
        CallbackQueryHandler(inventory_cmd, pattern="^inv_mode_"),
        CallbackQueryHandler(delibird_claim_handler, pattern="^delibird_"),
        CallbackQueryHandler(trade_force_cancel_handler, pattern="^trade_force_cancel$"),
        CallbackQueryHandler(tienda_category_handler, pattern="^shop_cat_"),
        CallbackQueryHandler(egg_claim_handler, pattern="^egg_claim_"),
        CallbackQueryHandler(egg_check_handler, pattern="^egg_check_"),
        CallbackQueryHandler(trade_search_start_handler, pattern="^trade_search_start_"),
        CallbackQueryHandler(trade_search_region_handler, pattern="^trade_sreg_"),
        CallbackQueryHandler(trade_search_sticker_handler, pattern="^trade_sstick_"),
        CallbackQueryHandler(trade_search_user_err_handler, pattern="^trade_suser_err$"),
        CallbackQueryHandler(inv_close_handler, pattern="^inv_close_"),
        CallbackQueryHandler(safari_hunt_btn_handler, pattern="^safari_hunt_"),

        MessageHandler(filters.TEXT & ~filters.COMMAND, process_friend_code_msg),
    ]
    application.add_handlers(all_handlers)
    for chat_id in db.get_active_groups():
        initial_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
        application.job_queue.run_once(spawn_pokemon, initial_delay, chat_id=chat_id, name=f"spawn_{chat_id}")
        logger.info(f"Trabajo de spawn reanudado para el chat activo {chat_id}")
    application.run_polling()


if __name__ == '__main__':
    main()
