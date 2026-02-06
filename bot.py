# bot.py
import logging
import random
import time  # <--- Este es el módulo time original (necesario para time.time)
import asyncio
import re
# --- CORRECCIÓN IMPORTS: Renombramos time a dt_time para evitar conflicto ---
from datetime import datetime, time as dt_time
import pytz
import math
from typing import cast
import os
from threading import Thread

# --- Importamos Flask y Waitress ---
from flask import Flask
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
from pokemon_data import POKEMON_REGIONS, ALL_POKEMON, POKEMON_BY_ID
from bot_utils import format_money, get_rarity, RARITY_VISUALS, DUPLICATE_MONEY_VALUES
from events import EVENTS

# --- CONFIGURACIÓN DEL SERVIDOR WEB ---
app = Flask('')


@app.route('/')
def home():
    return "¡El bot está vivo y coleando!"


def run():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run)
    t.start()


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
DELIBIRD_GLOBAL_CLAIMED = set() # Nueva variable: IDs de usuarios que ya reclamaron esta semana# --- CONFIGURACIÓN DE TIEMPOS DE APARICIÓN (En segundos) ---
MIN_SPAWN_TIME = 7200  # 2 horas
MAX_SPAWN_TIME = 14400  # 4 horas

# --- CONFIGURACIÓN DE OBJETOS Y SOBRES ---
# --- CONFIGURACIÓN DE OBJETOS Y SOBRES ---
# --- CONFIGURACIÓN DE OBJETOS Y SOBRES ---
# --- CONFIGURACIÓN DE OBJETOS Y SOBRES ---
SHOP_CONFIG = {
    'pack_small_national': {'name': 'Sobre Pequeño Nacional', 'price': 1000, 'size': 3, 'is_magic': False,
                            'desc': 'Contiene 3 stickers al azar.'},
    'pack_medium_national': {'name': 'Sobre Mediano Nacional', 'price': 1500, 'size': 5, 'is_magic': False,
                             'desc': 'Contiene 5 stickers al azar.'},
    'pack_large_national': {'name': 'Sobre Grande Nacional', 'price': 1900, 'size': 7, 'is_magic': False,
                            'desc': 'Contiene 7 stickers al azar.'},
    'pack_magic_small_national': {'name': 'Sobre Mágico Pequeño', 'price': 1600, 'size': 1, 'is_magic': True,
                                  'desc': 'Contiene 1 sticker que no tienes.'},
    'pack_magic_medium_national': {'name': 'Sobre Mágico Mediano', 'price': 2100, 'size': 3, 'is_magic': True,
                                   'desc': 'Contiene 3 stickers que no tienes.'},
    'pack_magic_large_national': {'name': 'Sobre Mágico Grande', 'price': 2500, 'size': 5, 'is_magic': True,
                                  'desc': 'Contiene 5 stickers que no tienes.'},

    # --- SOBRES DE EVENTO (OCULTOS) ---
    'pack_shiny_kanto': {'name': 'Sobre Brillante Kanto', 'price': 0, 'size': 1, 'is_magic': False,
                         'desc': 'Garantiza 1 Shiny.', 'hidden': True},

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
                           'hidden': True, 'emoji': '✨🔺'}
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

DAILY_WEIGHTS = [50, 32, 16, 2]
USER_FRIENDLY_ITEM_IDS = {'sobremagicomedianonacional': 'pack_magic_medium_national'}
POKEMON_BY_CATEGORY = {cat: [] for cat in PROBABILITIES.keys()}
for pokemon_item in ALL_POKEMON:
    POKEMON_BY_CATEGORY[pokemon_item['category']].append(pokemon_item)
POKEMON_PER_PAGE = 52
PACK_OPEN_COOLDOWN = 15


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


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.delete_message(chat_id=context.job.data['chat_id'], message_id=context.job.data['message_id'])
    except BadRequest:
        logger.info(f"El mensaje a borrar ({context.job.data['message_id']}) ya no existía.")
    except Exception as e:
        logger.error(f"Error al borrar mensaje programado: {e}")


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
async def check_monthly_job(context: ContextTypes.DEFAULT_TYPE):
    """Tarea mensual: Ranking por grupo y reseteo."""
    now = datetime.now(TZ_SPAIN)

    if now.day == 1:
        active_groups = db.get_active_groups()

        # Filtro Global de ganadores (para no repetir premio gordo)
        global_pack_winners = set()

        # Diccionario para guardar el ranking calculado antes de borrar la BD
        final_rankings_cache = {}

        # FASE 1: CALCULAR GANADORES Y PREMIOS (Igual que antes)
        # ------------------------------------------------------

        # Pre-calculamos todo para poder dar los premios y vaciar la BD
        # pero guardamos la lista visual para enviarla paginada después.

        groups_data = {}

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

        # Procesamiento Horizontal (Niveles 1 al 10 reciben premio/mención especial)
        # El resto (11+) solo sale en la lista sin premio.

        # Calculamos premios para todos (aunque sean 100)
        max_rank = 0
        for data in groups_data.values():
            if len(data['ranking']) > max_rank: max_rank = len(data['ranking'])

        for i in range(max_rank):
            for chat_id, data in groups_data.items():
                ranking = data['ranking']
                if i < len(ranking):
                    user_row = ranking[i]
                    uid, uname, count = user_row[0], user_row[1], user_row[2]

                    prize_text = ""

                    # Solo damos premios hasta el Top 10 (configurable)
                    if i < 10:
                        if uid in global_pack_winners:
                            prize_text = "_(👑 Ya premiado)_"
                            # No damos dinero si ya ganó
                        else:
                            pool = data['prizes_pool']
                            if len(pool) > 0:
                                prize_item = pool.pop(0)
                                p_name = "Sobre Grande" if 'large' in prize_item else "Sobre Mediano" if 'medium' in prize_item else "Sobre Pequeño"
                                db.add_mail(uid, 'inventory_item', prize_item, f"🥇 Premio Ranking Grupo {chat_id}")
                                global_pack_winners.add(uid)
                                prize_text = f"(+ {p_name} 🎴)"
                            else:
                                db.add_mail(uid, 'money', '500', f"Premio Ranking Grupo {chat_id}")
                                prize_text = "(+500₽)"

                    medals = ["🥇", "🥈", "🥉"]
                    visual_rank = medals[i] if i < 3 else f"{i + 1}."
                    line = f"{visual_rank} {uname}: {count} stickers {prize_text}"
                    data['lines'].append(line)

        # FASE 2: ENVIAR MENSAJES Y GUARDAR PARA PAGINACIÓN
        # -------------------------------------------------

        for chat_id, data in groups_data.items():
            lines = data['lines']
            if not lines: continue

            # Guardamos la lista completa en la memoria del chat para poder paginarla
            # Usamos una clave especial 'monthly_ranking_archive'
            context.application.chat_data.setdefault(chat_id, {})
            context.application.chat_data[chat_id]['monthly_ranking_archive'] = lines

            # Enviamos la página 0
            await send_ranking_page(context.bot, chat_id, lines, 0)

        # FASE 3: RESETEO FINAL
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

    # Recuperamos la lista de la memoria
    lines = context.chat_data.get('monthly_ranking_archive')

    if not lines:
        await query.answer("Este ranking ha caducado.", show_alert=True)
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
    total_pokemon_count = len(ALL_POKEMON)
    owned_normal = len({s[0] for s in user_collection if s[1] == 0})
    owned_shiny = len({s[0] for s in user_collection if s[1] == 1})

    rarity_counts = {rarity: 0 for rarity in RARITY_VISUALS.keys()}
    for pokemon_id, is_shiny in user_collection:
        pokemon_data = POKEMON_BY_ID.get(pokemon_id)
        if pokemon_data:
            final_rarity = get_rarity(pokemon_data['category'], is_shiny)
            if final_rarity in rarity_counts: rarity_counts[final_rarity] += 1

    rarity_lines = [f"{rarity_counts[code]} {emoji}" for code, emoji in RARITY_VISUALS.items()]

    text = (f"📖 *Álbumdex Nacional de {owner_user.first_name}*\n\n"
            f"Stickers: *{owned_normal}/{total_pokemon_count}*\n"
            f"Brillantes: *{owned_shiny}/{total_pokemon_count}*\n\n"
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
            schedule_message_deletion(context, update.message, 60)


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
        region = parts[3]  # kanto
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
            name_display = f"{p_data['name']}{'✨' if is_shiny else ''}"
            names_list.append(name_display)

    # Ordenar alfabéticamente
    names_list.sort()

    text = f"♻ **Repetidos de {region.capitalize()}:**\n\n"
    if not names_list:
        text += "_No tienes repetidos en esta región._"
    else:
        text += ", ".join(names_list)

    cb_back = f"album_dupe_menu_{owner_id}"
    if cmd_msg_id: cb_back += f"_{cmd_msg_id}"
    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data=cb_back)]]

    refresh_deletion_timer(context, query.message, 60)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


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
        text += f"▪️ {group['group_name']} (ID: `{group['chat_id']}`)\n"

    await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)


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
        # Formato: album_REGION_PAGE_OWNERID_MSGID_SORTMODE
        # Ejemplo: album_Kanto_0_123456_999_num

        region_name = parts[1]
        page = int(parts[2])
        owner_id = int(parts[3])

        if len(parts) > 4 and parts[4].isdigit():
            cmd_msg_id = int(parts[4])

        # Detectar modo de ordenación (por defecto numérico 'num')
        # Buscamos si el último parámetro es 'az' o 'num'
        sort_mode = 'num'
        if parts[-1] in ['num', 'az']:
            sort_mode = parts[-1]

        if interactor_user.id != owner_id:
            await query.answer("Este álbum no es tuyo.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en los datos del álbum.", show_alert=True)
        return

    # Obtener lista base
    raw_list = POKEMON_REGIONS.get(region_name)
    if not raw_list:
        await query.answer("Región no encontrada.", show_alert=True)
        return

    # --- LÓGICA DE ORDENACIÓN ---
    # Hacemos una copia para no alterar la lista global original
    pokemon_list_region = raw_list[:]

    if sort_mode == 'az':
        # Ordenar alfabéticamente por nombre
        pokemon_list_region.sort(key=lambda x: x['name'])
    else:
        # Ordenar por ID (numérico) - Ya suelen estar así, pero aseguramos
        pokemon_list_region.sort(key=lambda x: x['id'])
    # ----------------------------

    await query.answer()
    refresh_deletion_timer(context, query.message, 60)

    user_collection = db.get_all_user_stickers(owner_id)
    total_region = len(pokemon_list_region)
    total_pages = math.ceil(total_region / POKEMON_PER_PAGE)

    start_index = page * POKEMON_PER_PAGE
    end_index = (page + 1) * POKEMON_PER_PAGE
    pokemon_on_page = pokemon_list_region[start_index:end_index]

    # Título con indicación de orden
    order_icon = "🔤" if sort_mode == 'az' else "🔢"
    text = f"📖 *Álbumdex de {region_name}* ({order_icon})\n(Pág. {page + 1}/{total_pages})"

    keyboard, row = [], []
    for pokemon in pokemon_on_page:
        has_normal = (pokemon['id'], 0) in user_collection
        has_shiny = (pokemon['id'], 1) in user_collection

        if has_normal or has_shiny:
            button_text = f"#{pokemon['id']:03} {pokemon['name']}"
            if has_shiny:
                button_text += f" ✨{RARITY_VISUALS.get(get_rarity(pokemon['category'], True), '')}"
            elif has_normal:
                button_text += f" {RARITY_VISUALS.get(get_rarity(pokemon['category'], False), '')}"

            # Al ver detalle, mantenemos contexto básico
            cb_data = f"showsticker_{region_name}_{page}_{pokemon['id']}_{owner_id}"
            if cmd_msg_id: cb_data += f"_{cmd_msg_id}"
            # Nota: Al volver de ver el sticker, volverá al orden por defecto (num) salvo que pasemos sort_mode también.
            # Para simplificar, showsticker no guarda el sort_mode, así que al volver reseteará a numérico.
            # Si quieres persistencia total es más complejo.

            callback_data = cb_data
        else:
            button_text = f"#{pokemon['id']:03} ---"
            callback_data = "missing_sticker"

        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    # --- BARRA DE NAVEGACIÓN ---
    pagination_row = []

    # Botón Orden (Izquierda)
    new_sort = 'num' if sort_mode == 'az' else 'az'
    btn_sort_text = "Orden 🔢" if sort_mode == 'az' else "Orden 🔤"

    # Construimos el callback conservando todo
    cb_sort = f"album_{region_name}_0_{owner_id}"  # Reseteamos a pág 0 al cambiar orden
    if cmd_msg_id: cb_sort += f"_{cmd_msg_id}"
    cb_sort += f"_{new_sort}"

    pagination_row.append(InlineKeyboardButton(btn_sort_text, callback_data=cb_sort))

    # Botones Paginación
    if page > 0:
        prev_cb = f"album_{region_name}_{page - 1}_{owner_id}"
        if cmd_msg_id: prev_cb += f"_{cmd_msg_id}"
        prev_cb += f"_{sort_mode}"  # Mantenemos orden actual
        pagination_row.append(InlineKeyboardButton("⬅️", callback_data=prev_cb))

    if end_index < total_region:
        next_cb = f"album_{region_name}_{page + 1}_{owner_id}"
        if cmd_msg_id: next_cb += f"_{cmd_msg_id}"
        next_cb += f"_{sort_mode}"  # Mantenemos orden actual
        pagination_row.append(InlineKeyboardButton("➡️", callback_data=next_cb))

    if pagination_row: keyboard.append(pagination_row)

    # Botones inferiores
    back_cb = f"album_main_{owner_id}"
    if cmd_msg_id: back_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver al Álbum Nacional", callback_data=back_cb)])

    close_cb = f"album_close_{owner_id}"
    if cmd_msg_id: close_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Cerrar Álbumdex", callback_data=close_cb)])  # Texto cambiado

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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

    # --- NUEVO: LÓGICA DE COOLDOWN (2 veces cada 30 min) ---
    # Usamos context.user_data para guardar el historial del usuario
    now = time.time()
    COOLDOWN_SECONDS = 1800  # 30 minutos
    MAX_SHOWS = 2

    # Inicializamos la lista si no existe
    if 'show_history' not in context.user_data:
        context.user_data['show_history'] = []

    # Limpiamos marcas de tiempo antiguas (mayores a 30 min)
    context.user_data['show_history'] = [
        t for t in context.user_data['show_history']
        if now - t < COOLDOWN_SECONDS
    ]

    # Comprobamos si ha superado el límite
    if len(context.user_data['show_history']) >= MAX_SHOWS:
        # Calculamos cuánto falta para que expire el más antiguo
        oldest_time = context.user_data['show_history'][0]
        wait_time = int(COOLDOWN_SECONDS - (now - oldest_time))
        minutes = wait_time // 60
        seconds = wait_time % 60

        await query.answer(
            f"⛔ Para evitar spam, solo puedes mostrar 2 Pokémon cada 30 minutos.\n\n"
            f"Podrás mostrar otro en: {minutes}m {seconds}s.",
            show_alert=True
        )
        return
    # -------------------------------------------------------

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

        # --- REGISTRAMOS EL USO ---
        context.user_data['show_history'].append(now)
        # --------------------------

        shiny_text = " Brillante" if is_shiny else ""
        final_rarity = get_rarity(pokemon_data['category'], is_shiny)
        rarity_emoji = RARITY_VISUALS.get(final_rarity, "")

        message_text = f"{interactor_user.first_name} mostró su *{pokemon_data['name']}{shiny_text}* {rarity_emoji}"

        # --- ENVIAMOS EN SILENCIO (disable_notification=True) ---
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=message_text,
            parse_mode='Markdown',
            disable_notification=True  # <--- SILENCIO
        )

        image_path = f"Stickers/Kanto/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"
        with open(image_path, 'rb') as sticker_file:
            await context.bot.send_sticker(
                chat_id=message.chat_id,
                sticker=sticker_file,
                disable_notification=True  # <--- SILENCIO
            )

        await query.answer()

    except (ValueError, IndexError):
        await query.answer("Error al procesar la solicitud.", show_alert=True)
    except FileNotFoundError:
        logger.error(f"Sticker no encontrado: {image_path}")
        await query.answer("¡Uy! No encuentro ese sticker.", show_alert=True)


def choose_random_pokemon():
    chosen_category = random.choices(list(PROBABILITIES.keys()), weights=list(PROBABILITIES.values()), k=1)[0]
    chosen_pokemon = random.choice(POKEMON_BY_CATEGORY[chosen_category])
    is_shiny = random.random() < SHINY_CHANCE
    return chosen_pokemon, is_shiny, get_rarity(chosen_pokemon['category'], is_shiny)


async def spawn_event(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    context.chat_data.setdefault('active_events', {})

    # --- CAMBIO: LIMPIEZA CADA 3 DÍAS ---
    current_time = time.time()
    # 3 días = 259200 segundos
    TIMEOUT_SECONDS = 259200

    for msg_id, data in list(context.chat_data['active_events'].items()):
        if current_time - data.get('timestamp', 0) > TIMEOUT_SECONDS:
            del context.chat_data['active_events'][msg_id]
            # Opcional: Intentar borrar el mensaje viejo de Telegram para limpiar el chat
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except BadRequest:
                pass
    # ------------------------------------

    is_qualified = await is_group_qualified(chat_id, context)

    available_events = []
    legendary_missions = ['mision_moltres', 'mision_zapdos', 'mision_articuno', 'mision_mewtwo']

    for ev_id in EVENTS.keys():
        if not is_qualified and ev_id in legendary_missions:
            continue

        if ev_id in legendary_missions:
            if db.is_event_completed(chat_id, ev_id):
                continue
        available_events.append(ev_id)

    if not available_events:
        return

    event_id = random.choice(available_events)

    text = "¡Un evento especial ha aparecido!"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔍 Aceptar evento", callback_data=f"event_claim_{event_id}")]])
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='Markdown')

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

    try:
        # 1. Evento
        if random.random() < EVENT_CHANCE:
            await spawn_event(context)
            spawned_something = True

        # 2. Pokémon (si no hubo evento)
        if not spawned_something:
            context.chat_data.setdefault('active_spawns', {})
            current_time = time.time()

            #3 DÍAS (259200 segundos) ---
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
            # ---------------------------------------------------------

            pokemon_data, is_shiny, rarity = choose_random_pokemon()

            if pokemon_data['id'] == 144 and not db.is_event_completed(chat_id, 'mision_articuno'):
                pokemon_data = random.choice(POKEMON_BY_CATEGORY['C'])
                rarity = get_rarity('C', is_shiny)

            if pokemon_data['id'] == 145 and not db.is_event_completed(chat_id, 'mision_zapdos'):
                pokemon_data = random.choice(POKEMON_BY_CATEGORY['C'])
                rarity = get_rarity('C', is_shiny)

            if pokemon_data['id'] == 146 and not db.is_event_completed(chat_id, 'mision_moltres'):
                pokemon_data = random.choice(POKEMON_BY_CATEGORY['C'])
                rarity = get_rarity('C', is_shiny)

            if pokemon_data['id'] == 150 and not db.is_event_completed(chat_id, 'mision_mewtwo'):
                pokemon_data = random.choice(POKEMON_BY_CATEGORY['C'])
                rarity = get_rarity('C', is_shiny)

            pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
            text_message = f"¡Un *{pokemon_name} {RARITY_VISUALS.get(rarity, '')}* salvaje apareció!"
            image_path = f"Stickers/Kanto/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"

            try:
                with open(image_path, 'rb') as sticker_file:
                    sticker_msg = await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file)

                callback_data = f"claim_0_{pokemon_data['id']}_{int(is_shiny)}_{rarity}"
                button_text = "¡Capturar! 📷"
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=callback_data)]])

                text_msg = await context.bot.send_message(chat_id=chat_id, text=text_message, parse_mode='Markdown',
                                                          reply_markup=reply_markup)

                context.chat_data['active_spawns'][text_msg.message_id] = {
                    'sticker_id': sticker_msg.message_id,
                    'text_id': text_msg.message_id,
                    'timestamp': current_time
                }
            except FileNotFoundError:
                logger.error(f"No se encontró la imagen: {image_path}")

    except Exception as e:
        logger.error(f"⚠️ Error en el ciclo de spawn para el chat {chat_id}: {e}")

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
    pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
    text_message = f"¡Un *{pokemon_name} {RARITY_VISUALS.get(rarity, '')}* salvaje apareció!"
    image_path = f"Stickers/Kanto/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"

    try:
        with open(image_path, 'rb') as sticker_file:
            sticker_msg = await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file)

        callback_data = f"claim_0_{pokemon_data['id']}_{int(is_shiny)}_{rarity}"
        button_text = "¡Capturar! 📷"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=callback_data)]])

        text_msg = await context.bot.send_message(chat_id=chat_id, text=text_message, parse_mode='Markdown',
                                                  reply_markup=reply_markup)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user: return

    # --- CAMBIO: Registramos al usuario SIEMPRE, sea grupo o privado ---
    db.get_or_create_user(user.id, user.first_name)
    # -----------------------------------------------------------------

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

        schedule_message_deletion(context, update.message, 30)
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
        schedule_message_deletion(context, update.message, 30)
        schedule_message_deletion(context, msg, 30)
        return
    for job in jobs:
        job.schedule_removal()

    db.set_group_active(chat.id, False)
    msg = await update.message.reply_text("❌ La aparición de Pokémon salvajes se ha desactivado.", disable_notification=True)
    schedule_message_deletion(context, update.message, 30)
    schedule_message_deletion(context, msg, 30)


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
        if current_time - last_attempt_time < 30:
            time_left = math.ceil(30 - (current_time - last_attempt_time))
            await query.answer(f"Espera unos {time_left} segundos...", show_alert=True)
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

        if message.chat.type in ['group', 'supergroup']:
            db.increment_group_monthly_stickers(user.id, message.chat.id)

        for key in ['sticker_id', 'text_id']:
            try:
                await context.bot.delete_message(chat_id=message.chat_id, message_id=claimed_spawn[key])
            except BadRequest:
                pass

        pokemon_data = POKEMON_BY_ID.get(pokemon_id)
        pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
        rarity_emoji = RARITY_VISUALS.get(rarity, '')

        # --- NUEVA LÓGICA DE CAPTURA (1º, 2º, 3º+) ---
        status = db.add_sticker_smart(user.id, pokemon_id, is_shiny)
        message_text = ""

        if status == 'NEW':
            # 1ª Vez
            message_text = f"🎉 ¡Felicidades, {user.mention_markdown()}! Has conseguido un sticker de *{pokemon_name} {rarity_emoji}*. Lo has registrado en tu Álbumdex."
        elif status == 'DUPLICATE':
            # 2ª Vez
            message_text = f"♻ ¡Genial, {user.mention_markdown()}! Conseguiste un sticker de *{pokemon_name} {rarity_emoji}*. Como solo tenías 1, te lo guardas para intercambiarlo."
        else:
            # 3ª Vez o más (MAX) -> Dinero
            money_earned = DUPLICATE_MONEY_VALUES.get(rarity, 100)
            db.update_money(user.id, money_earned)
            message_text = f"✔️ ¡Genial, {user.mention_markdown()}! Conseguiste un sticker de *{pokemon_name} {rarity_emoji}*. Como ya lo tienes repetido, se convierte en *{format_money(money_earned)}₽* 💰."

        # ---------------------------------------------

        # Reto Grupal
        if message.chat.type in ['group', 'supergroup']:
            db.add_pokemon_to_group_pokedex(message.chat.id, pokemon_id)

        # Premio Individual (Kanto)
        if not db.is_kanto_completed_by_user(user.id):
            unique_count = db.get_user_unique_kanto_count(user.id)
            if unique_count >= 151:
                db.set_kanto_completed_by_user(user.id)
                db.update_money(user.id, 3000)
                message_text += f"\n\n🎊 ¡Felicidades {user.mention_markdown()}, has conseguido los 151 Pokémon de Kanto! 🎊\n¡Recibes 3000₽ de recompensa!"

        # Premio Reto Grupal
        is_qualified = await is_group_qualified(message.chat.id, context)
        if message.chat.type in ['group', 'supergroup']:
            if not db.is_event_completed(message.chat.id, 'kanto_group_challenge'):
                group_unique = db.get_group_unique_kanto_ids(message.chat.id)
                if len(group_unique) >= 151:
                    db.mark_event_completed(message.chat.id, 'kanto_group_challenge')
                    if is_qualified:
                        for uid in db.get_users_in_group(message.chat.id):
                            db.add_mail(uid, 'money', '2000', "Premio Reto Grupal: Kanto Completado")
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! Habéis completado Kanto y recibido 2000₽."
                    else:
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! Habéis completado Kanto."

        await context.bot.send_message(chat_id=message.chat_id, text=message_text, parse_mode='Markdown')

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
            text=f"❌ La foto de {user.mention_markdown()} salió movida y no escaneó al pokémon.",
            parse_mode='Markdown',
            reply_to_message_id=msg_id
        )
        schedule_message_deletion(context, fail_message, 120)


async def claim_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    message = cast(Message, query.message)
    if not message:
        await query.answer()
        return

    message_id = message.message_id
    context.chat_data.setdefault('active_events', {})
    event_info = context.chat_data['active_events'].get(message_id)

    if not event_info or event_info.get('claimed_by'):
        await query.answer("Este evento ya ha sido aceptado por otra persona.", show_alert=True)
        return

    event_info['claimed_by'] = user.id
    event_id = event_info['event_id']
    await query.answer("¡Has aceptado el evento!")

    if message.chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, message.chat.id)

    await message.delete()

    event_data = EVENTS[event_id]
    step_data = event_data['steps']['start']

    result = step_data['get_text_and_keyboard'](user)
    text = result['text']

    keyboard_rows = []
    if 'keyboard' in result and result['keyboard']:
        for row in result['keyboard']:
            keyboard_rows.append([
                InlineKeyboardButton(button['text'], callback_data=f"{button['callback_data']}_{user.id}")
                for button in row
            ])

    reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None

    await context.bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def event_step_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    message = cast(Message, query.message)
    if not message:
        await query.answer()
        return

    try:
        main_data, owner_id_str = query.data.rsplit('_', 1)
        owner_id = int(owner_id_str)

        if user.id != owner_id:
            await query.answer("Solo la persona que inició el evento puede continuar.", show_alert=True)
            return

        parts = main_data.split('|')
        event_id = parts[1]
        step_id = parts[2]
        decision_parts = parts[3:]

    except (IndexError, ValueError):
        logger.warning(f"Error al procesar el callback_data del evento: {query.data}")
        await query.answer("Error en los datos del evento.", show_alert=True)
        return

    event_data = EVENTS.get(event_id)
    if not event_data: return

    step_data = event_data['steps'].get(step_id)
    if not step_data: return

    if 'action' in step_data:
        # --- AQUÍ PASAMOS EL CHAT_ID ---
        result = step_data['action'](user, decision_parts, original_text=message.text, chat_id=message.chat_id)
        # -------------------------------

        if result.get('event_completed') and result.get('event_id'):
            db.mark_event_completed(message.chat.id, result['event_id'])
            logger.info(f"Evento {result['event_id']} marcado como completado para el chat {message.chat.id}")

        final_text = result.get('text', '...')
        reply_markup = None

        if 'keyboard' in result and result['keyboard']:
            keyboard_rows = []
            for row in result['keyboard']:
                keyboard_rows.append([
                    InlineKeyboardButton(button['text'], callback_data=f"{button['callback_data']}_{user.id}")
                    for button in row
                ])
            reply_markup = InlineKeyboardMarkup(keyboard_rows)

        await query.edit_message_text(
            text=final_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        await query.answer()


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
            pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
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
        schedule_message_deletion(context, msg, 5)
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
    schedule_message_deletion(context, update.message, 60)
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
        "Prueba suerte una vez al día para ganar premios. Dependiendo de la bola que saques, esto es lo que te puede tocar:\n"
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
                # shop_refresh_OWNERID o shop_refresh_OWNERID_MSGID
                if len(parts) > 3 and parts[-1].isdigit() and parts[-2].isdigit():
                    owner_id = int(parts[-2])
                    cmd_msg_id = int(parts[-1])
                else:
                    owner_id = int(parts[-1])

                if interactor_user.id != owner_id:
                    await query.answer("Esta tienda no es tuya.", show_alert=True)
                    return
                owner_user = interactor_user
            except (ValueError, IndexError):
                await query.answer("Error al cargar la tienda.", show_alert=True)
                return
    else:
        owner_user = interactor_user
        if update.message: cmd_msg_id = update.message.message_id

    db.get_or_create_user(owner_user.id, owner_user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(owner_user.id, update.effective_chat.id)

    user_money = db.get_user_money(owner_user.id)

    # IMPORTANTE: Filtramos los ocultos
    descriptions = [f"· *{details['name']}:* {details['desc']}" for key, details in SHOP_CONFIG.items() if
                    not details.get('hidden')]
    desc_text = "\n".join(descriptions)

    text = (f"🏪 *Tienda de Sobres* 🏪\n\n"
            f"¡Bienvenido, {owner_user.first_name}!\n"
            f"Tu dinero actual: *{format_money(user_money)}₽*\n\n"
            f"*¿Qué contiene cada sobre?*\n{desc_text}\n\n"
            "Elige un sobre para comprar:")

    keyboard = []
    for item_id, details in SHOP_CONFIG.items():
        if details.get('hidden'): continue  # NO MOSTRAR SI ES OCULTO

        cb_data = f"prebuy_{item_id}_{owner_user.id}"
        if cmd_msg_id: cb_data += f"_{cmd_msg_id}"
        button_text = f"{details['name']} - {format_money(details['price'])}₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=cb_data)])

    refresh_cb = f"shop_refresh_{owner_user.id}"
    if cmd_msg_id: refresh_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("🔄 Actualizar Saldo", callback_data=refresh_cb)])

    close_cb = f"shop_close_{owner_user.id}"
    if cmd_msg_id: close_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Salir de la tienda", callback_data=close_cb)])

    if query and not is_panel:
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            if query.data.startswith("shop_refresh_"): await query.answer()
        except BadRequest:
            await query.answer("Tu saldo no ha cambiado.")
    else:
        msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                             reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                             disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        if update.message: schedule_message_deletion(context, update.message, 60)


async def prebuy_pack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    try:
        parts = query.data.split('_')
        # Formatos: prebuy_itemid_OWNERID o prebuy_itemid_OWNERID_MSGID

        if parts[-1].isdigit() and parts[-2].isdigit():
            # Caso con MSG_ID
            cmd_msg_id = parts[-1]
            owner_id = int(parts[-2])
            item_id = '_'.join(parts[1:-2])
        else:
            # Caso sin MSG_ID (ej: desde panel)
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

    text = (f"🛒 **Confirmar Compra**\n\n"
            f"¿Estás seguro de que quieres comprar:\n"
            f"*{pack_details['name']}* por *{format_money(pack_details['price'])}₽*?")

    confirm_data = f"confirmbuy_{item_id}_{owner_id}"
    if cmd_msg_id: confirm_data += f"_{cmd_msg_id}"

    cancel_data = f"shop_refresh_{owner_id}"
    if cmd_msg_id: cancel_data += f"_{cmd_msg_id}"

    keyboard = [
        [InlineKeyboardButton("✅ Confirmar", callback_data=confirm_data)],
        [InlineKeyboardButton("❌ Cancelar", callback_data=cancel_data)]
    ]

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
        await query.answer(f"✅ ¡Comprado! Tienes un {pack_details['name']} en tu mochila.", show_alert=True)
        # Volvemos a la tienda automáticamente para que vea su saldo actualizado
        # Importante: tienda_cmd sabrá leer el ID desde el callback 'confirmbuy...'
        await tienda_cmd(update, context)
    else:
        needed = pack_price - user_money
        await query.answer(f"❌ No tienes suficiente dinero. Te faltan {format_money(needed)}₽.", show_alert=True)
        # Volvemos a la tienda
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
        user = query.from_user
        # Si pulsó el botón de cambio, leemos el modo deseado
        if query.data.startswith("inv_mode_"):
            mode = query.data.split("_")[-1]  # packs o special
    else:
        user = update.effective_user

    if not user: return

    db.get_or_create_user(user.id, user.first_name)
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, update.effective_chat.id)

    items = db.get_user_inventory(user.id)
    text = ""
    keyboard_buttons = []

    # --- BOTÓN DE CAMBIO DE MODO (SIEMPRE ARRIBA) ---
    if mode == "packs":
        # Estamos en sobres, mostramos botón para ir a especiales
        keyboard_buttons.append([InlineKeyboardButton("🪶 Otros Objetos", callback_data="inv_mode_special")])
        text = "🎒 **Mochila - Sobres**\n\n"
    else:
        # Estamos en especiales, mostramos botón para ir a sobres
        keyboard_buttons.append([InlineKeyboardButton("🎴 Sobres", callback_data="inv_mode_packs")])
        text = "🎒 **Mochila - Objetos Especiales**\n\n"

    has_items = False

    # --- FILTRADO Y VISUALIZACIÓN ---
    for item in items:
        item_id = item['item_id']
        qty = item['quantity']

        # MODO SOBRES
        if mode == "packs":
            if item_id in PACK_CONFIG:
                raw_name = ITEM_NAMES.get(item_id, 'Objeto')
                item_name = f"{raw_name} 🎴"
                # Añadir botón de abrir
                keyboard_buttons.append(
                    [InlineKeyboardButton(f"Abrir {raw_name}", callback_data=f"openpack_{item_id}_{user.id}")])
                text += f"🔸️ {item_name} x{qty}\n"
                has_items = True

        # MODO ESPECIALES
        else:
            if item_id.startswith('lottery_ticket_') or item_id in SPECIAL_ITEMS_DATA:
                if item_id.startswith('lottery_ticket_'):
                    item_name = "Ticket de lotería ganador"
                else:
                    data = SPECIAL_ITEMS_DATA[item_id]
                    item_name = f"{data['name']} {data['emoji']}"

                # Botones de acción (Ver/Mostrar) en la misma línea
                row = [
                    InlineKeyboardButton("🔍 Ver",
                                         callback_data=f"view{'ticket' if 'ticket' in item_id else 'special'}_{item_id}_{user.id}"),
                    InlineKeyboardButton("📢 Mostrar", callback_data=f"showspecial_{item_id}_{user.id}")
                ]
                keyboard_buttons.append(row)
                text += f"🔸️ {item_name} x{qty}\n"
                has_items = True

    if not has_items:
        text += "_Bolsillo vacío._"

    markup = InlineKeyboardMarkup(keyboard_buttons)

    # ENVÍO O EDICIÓN
    if query and query.data.startswith("inv_mode_"):
        # Navegación interna (cambio de pestaña) -> EDITAR
        await query.answer()
        await query.edit_message_text(text, reply_markup=markup, parse_mode='Markdown')
    else:
        # Comando nuevo -> ENVIAR NUEVO
        if query: await query.answer()  # Si viene del panel

        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=markup,
            parse_mode='Markdown',
            disable_notification=True
        )
        schedule_message_deletion(context, sent_message)
        if update.message:
            schedule_message_deletion(context, update.message)


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
        await query.answer(f"Abriendo {ITEM_NAMES.get(item_id)}...")

        if message.chat.type in ['group', 'supergroup']:
            db.register_user_in_group(user.id, message.chat.id)

        await message.delete()
        db.remove_item_from_inventory(user.id, item_id, 1)

        opening_message = await context.bot.send_message(
            message.chat_id,
            f"🎴 ¡{user.mention_markdown()} ha abierto un *{ITEM_NAMES.get(item_id)}*! ",
            parse_mode='Markdown',
            disable_notification=True
        )

        pack_config = SHOP_CONFIG.get(item_id, {})  # Usamos SHOP_CONFIG para tener info completa
        pack_size = pack_config.get('size', 1)
        pack_results = []
        message_ids_to_delete = [opening_message.message_id]

        # --- LÓGICA DE GENERACIÓN ---

        # 1. Sobre Brillante (100% Shiny)
        if item_id == 'pack_shiny_kanto':
            p_data, _, _ = choose_random_pokemon()
            pack_results.append({'data': p_data, 'is_shiny': True})

        # 2. Sobre Especial Kanto (Doble probabilidad shiny)
        elif item_id == 'pack_elem_especial':
            for _ in range(pack_size):
                is_shiny = random.random() < (SHINY_CHANCE * 2)
                p_data, _, _ = choose_random_pokemon()
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})

        # 3. Sobres Elementales (Filtrados por tipo) - ¡ESTO FALTABA!
        elif 'type_filter' in pack_config:
            target_type = pack_config['type_filter']
            # Filtramos la lista global
            type_pool = [p for p in ALL_POKEMON if target_type in p.get('types', [])]
            if not type_pool: type_pool = ALL_POKEMON  # Fallback

            for _ in range(pack_size):
                p_data = random.choice(type_pool)
                is_shiny = random.random() < SHINY_CHANCE
                pack_results.append({'data': p_data, 'is_shiny': is_shiny})

        # 4. Sobres Mágicos
        elif pack_config.get('is_magic'):
            user_stickers = db.get_all_user_stickers(user.id)
            all_normal_stickers = {(p['id'], 0) for p in ALL_POKEMON}
            all_shiny_stickers = {(p['id'], 1) for p in ALL_POKEMON}
            unowned_normal = list(all_normal_stickers - user_stickers)
            unowned_shinies = list(all_shiny_stickers - user_stickers)
            random.shuffle(unowned_normal)
            random.shuffle(unowned_shinies)
            for _ in range(pack_size):
                is_shiny_roll = random.random() < SHINY_CHANCE
                if is_shiny_roll and unowned_shinies:
                    poke_id, is_shiny_flag = unowned_shinies.pop(0)
                    pack_results.append({'data': POKEMON_BY_ID[poke_id], 'is_shiny': bool(is_shiny_flag)})
                elif unowned_normal:
                    poke_id, is_shiny_flag = unowned_normal.pop(0)
                    pack_results.append({'data': POKEMON_BY_ID[poke_id], 'is_shiny': bool(is_shiny_flag)})
                else:
                    pokemon_data, is_shiny_status, _ = choose_random_pokemon()
                    pack_results.append({'data': pokemon_data, 'is_shiny': is_shiny_status})

        # 5. Sobres Normales
        else:
            for _ in range(pack_size):
                p_data, s, _ = choose_random_pokemon()
                pack_results.append({'data': p_data, 'is_shiny': s})

        summary_parts = []

        for result in pack_results:
            p, s = result['data'], result['is_shiny']
            rarity = get_rarity(p['category'], s)
            try:
                with open(f"Stickers/Kanto/{'Shiny/' if s else ''}{p['id']}{'s' if s else ''}.png",
                          'rb') as sticker_file:
                    msg = await context.bot.send_sticker(
                        chat_id=message.chat_id, sticker=sticker_file, disable_notification=True
                    )
                    message_ids_to_delete.append(msg.message_id)
                await asyncio.sleep(1.2)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                logger.error(f"Error enviando sticker {p['id']}: {e}")

            p_name, r_emoji = f"{p['name']}{' brillante ✨' if s else ''}", RARITY_VISUALS.get(rarity, '')

            if message.chat.type in ['group', 'supergroup']:
                db.add_pokemon_to_group_pokedex(message.chat.id, p['id'])  # Pokedex grupal

            # --- NUEVA LÓGICA SMART (1º, 2º, 3º+) ---
            status = db.add_sticker_smart(user.id, p['id'], s)

            if status == 'NEW':
                summary_parts.append(f"🔸🆕 {p_name} {r_emoji}")
            elif status == 'DUPLICATE':
                summary_parts.append(f"🔸♻️ {p_name} {r_emoji} (Repetido)")
            else:  # MAX
                money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                db.update_money(user.id, money)
                summary_parts.append(f"🔸✔️ {p_name} {r_emoji} (*{format_money(money)}₽*💰)")
            # --------------------------

        pack_name = ITEM_NAMES.get(item_id, "Sobre")
        vertical_summary = "\n".join(summary_parts)
        final_text = f"📜 Resultado del {pack_name} de {user.mention_markdown()}:\n\n{vertical_summary}"

        # --- SECCIÓN DEL PREMIO POR COMPLETAR KANTO ---
        if not db.is_kanto_completed_by_user(user.id):
            unique_count = db.get_user_unique_kanto_count(user.id)
            if unique_count >= 151:
                db.set_kanto_completed_by_user(user.id)
                db.update_money(user.id, 3000)
                final_text += f"\n\n🎊 ¡Felicidades {user.mention_markdown()}, has conseguido los 151 Pokémon de Kanto! 🎊\n¡Recibes 3000₽ de recompensa!"
        # ----------------------------------------------

        await context.bot.send_message(message.chat_id, text=final_text, parse_mode='Markdown',
                                       disable_notification=True)

        if message_ids_to_delete and context.job_queue:
            context.job_queue.run_once(delete_pack_stickers, 60,
                                       data={'chat_id': message.chat_id, 'sticker_ids': message_ids_to_delete})
        context.chat_data['last_pack_open_time'] = time.time()
    finally:
        context.chat_data['is_opening_pack'] = False


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

    VALID_ITEMS = [
        'pack_small_national', 'pack_medium_national', 'pack_large_national',
        'pack_magic_small_national', 'pack_magic_medium_national', 'pack_magic_large_national',
        'pluma_naranja', 'pluma_amarilla', 'pluma_azul', 'foto_psiquica', 'lottery_ticket'
    ]

    for arg in args:
        if arg.lower() in VALID_ITEMS:
            item_id = arg.lower()
            break

    if not item_id:
        return await message.reply_text(
            "❌ No has especificado un objeto válido.\n"
            "Uso: `/regalarobjeto @usuario1 @usuario2 item_id`\n"
            "Ejemplo: `/regalarobjeto @Pepe pack_medium_national`"
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
        msg = "¡Un regalo especial de la administración!"
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
                text=f"📬 **¡TIENES CORREO!**\n\nEl admin te ha enviado: *{item_name}*\nNota: _{msg}_",
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
        schedule_message_deletion(context, update.message, 60)
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
        schedule_message_deletion(context, update.message, 20)
        return

    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(sender.id, update.effective_chat.id)

    sender_money = db.get_user_money(sender.id)

    # Caso: No tiene dinero
    if sender_money < amount:
        msg = await update.message.reply_text(f"No tienes suficiente dinero. Tienes *{format_money(sender_money)}₽*.",
                                              parse_mode='Markdown', disable_notification=True)
        schedule_message_deletion(context, update.message, 120)
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

    await update.message.reply_text(text, parse_mode='Markdown', disable_notification=True)


async def retos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Detectamos si viene del botón del Panel
    is_panel = (query and query.data == "panel_retos")

    if query and not is_panel:
        # Navegación interna (ej: botón "Volver" desde la lista de faltantes)
        message = query.message
        chat_id = message.chat_id
    else:
        # Viene de comando de texto /retos O del botón del Panel
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.effective_message.reply_text("Este comando solo funciona en grupos.",
                                                      disable_notification=True)
            return
        message = update.effective_message
        chat_id = update.effective_chat.id

    # Aseguramos registro usuario
    user = update.effective_user
    db.get_or_create_user(user.id, user.first_name)
    db.register_user_in_group(user.id, chat_id)

    # --- LÓGICA KANTO ---
    group_ids_kanto = db.get_group_unique_kanto_ids(chat_id)
    total_kanto = len(group_ids_kanto)
    target_kanto = 151

    # Construcción del Mensaje Principal
    text = "🤝 **Retos Grupales** 🤝\n\n"

    # Bloque Kanto
    if total_kanto >= target_kanto:
        text += "🎯 Objetivo: Conseguir los 151 Pokémon de Kanto ✅ **¡Hecho!**\n"
    else:
        text += "🎯 Objetivo: Conseguir los 151 Pokémon de Kanto:\n"
        text += f"📊 Total: {total_kanto}/{target_kanto}\n"

    text += "\n" + "—" * 15 + "\n"  # Separador visual

    # Botón para ver detalles
    keyboard = [[InlineKeyboardButton("📋 Stickers que faltan", callback_data=f"retos_missing_menu_{chat_id}")]]

    # --- BLOQUE DE ENVÍO ---
    if query and not is_panel:
        # Si estamos navegando dentro del menú (botón volver), EDITAMOS
        refresh_deletion_timer(context, message, 30)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        # Si venimos del Panel o del comando, ENVIAMOS MENSAJE NUEVO
        msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                       disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        if update.message:
            schedule_message_deletion(context, update.message, 60)


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
        # --- CAMBIO: 900 segundos (15 min) ---
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

        line = f"🔹️ {row['game_nick']} - `{row['code']}` ({days_left} días)"
        regions[r].append(line)

    text = (
        "👥 *Códigos de amigo:*\n"
        "_Lista actualizada de códigos de amigo de Pokémon Shuffle (cada código se eliminará en 1 mes, si no se renueva antes):_\n\n"
    )
    text += "*Europa:*\n" + ("\n".join(regions['Europa']) if regions['Europa'] else "_Vacío_") + "\n\n"
    text += "*América:*\n" + ("\n".join(regions['América']) if regions['América'] else "_Vacío_") + "\n\n"
    text += "*Asia:*\n" + ("\n".join(regions['Asia']) if regions['Asia'] else "_Vacío_") + "\n\n _Para eliminar un código de la lista, escribe /borrarcodigo seguido del código a eliminar, por ejemplo: /borrarcodigo 6T4A2944_"


    keyboard = [
        [InlineKeyboardButton("➕ Añadir código", callback_data="codes_menu_add")],
        [InlineKeyboardButton("🔄 Renovar", callback_data="codes_menu_renew")]
    ]

    if query and not is_panel:
        # --- CAMBIO: 600 segundos ---
        refresh_deletion_timer(context, message, 600)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown',
                                       disable_notification=True)
        # --- CAMBIO: 600 segundos ---
        schedule_message_deletion(context, msg, 600)


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
        schedule_message_deletion(context, update.message, 30)
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
        else:
            msg = await update.message.reply_text(
                "⛔ No puedes borrar un código que no es tuyo.",
                disable_notification=True
            )

    schedule_message_deletion(context, msg, 30)
    schedule_message_deletion(context, update.message, 30)


async def codigos_btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data

    # --- CAMBIO: Reiniciar a 600 segundos en cualquier interacción ---
    refresh_deletion_timer(context, query.message, 600)

    if action == "codes_menu_add":
        text = (
            "📝 **Añadir Código**\n\n"
            "Para añadir tu código a la lista, escribe en este chat un mensaje con el siguiente formato:\n\n"
            "`Nick Región Código`\n\n"
            "• **Ejemplo:** `Sixtomaru Europa 6T4A2944`\n\n"
            "_Para eliminar un código de la lista, escribe /borrarcodigo seguido del código a eliminar, por ejemplo: /borrarcodigo 6T4A2944_"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Atrás", callback_data="codes_menu_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await query.answer()

    elif action == "codes_menu_renew":
        if db.renew_friend_code(user_id):
            await query.answer("✅ ¡Código renovado por 30 días!", show_alert=True)
            await codigos_cmd(update, context)
        else:
            await query.answer("❌ No se ha encontrado tu código de amigo, por favor, añádelo de nuevo a la lista.",
                               show_alert=True)

    elif action == "codes_menu_back":
        await codigos_cmd(update, context)


async def process_friend_code_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analiza mensajes de texto para ver si son códigos de amigo."""
    text = update.message.text
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
                schedule_message_deletion(context, update.message, 60)
                schedule_message_deletion(context, msg, 60)
                return

        # 2. ¿El código existe ya?
        if db.check_code_exists(code):
            msg = await update.message.reply_text("❌ Este código ya está registrado en la lista.",
                                                  disable_notification=True)
            schedule_message_deletion(context, update.message, 60)
            schedule_message_deletion(context, msg, 60)
            return

        # --- AÑADIR ---
        db.add_friend_code(user.id, nick, region, code)

        msg = await update.message.reply_text("✅ Código agregado a la lista.", disable_notification=True)
        schedule_message_deletion(context, update.message, 60)
        schedule_message_deletion(context, msg, 60)


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
    """Revisa si hay códigos que caducan en 3 días y avisa."""
    all_codes = db.get_all_friend_codes()
    current_time = time.time()

    for row in all_codes:
        expiry = row['expiry_timestamp']
        user_id = row['user_id']

        # Calcular días restantes
        days_left = (expiry - current_time) / 86400

        # Si le quedan entre 2.5 y 3.5 días, consideramos que son "3 días"
        # (Esto evita que se envíe varias veces o que se salte por horas)
        if 2.0 < days_left <= 3.0:

            # Verificar si el usuario quiere recibir la alerta
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
                    # Pequeña pausa anti-spam
                    await asyncio.sleep(0.1)
                except Exception as e:
                    # Si el usuario bloqueó al bot, fallará.
                    pass


# --- SISTEMA DE INTERCAMBIOS ---

async def intercambio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detectar si viene del Panel
    query = update.callback_query
    is_panel = (query and query.data == "panel_intercambios")

    if is_panel:
        sender = query.from_user
        message = query.message  # El panel (no lo usamos para reply)
    else:
        sender = update.effective_user
        message = update.effective_message
        if update.message: schedule_message_deletion(context, update.message, 60)

    # 1. Validar límite diario
    if not db.check_trade_daily_limit(sender.id):
        # Si es panel, usamos answer, si es texto, reply
        text = "⛔ Has alcanzado tu límite de 2 intercambios diarios."
        if is_panel:
            await query.answer(text, show_alert=True)
        else:
            msg = await message.reply_text(text, disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return

    # 2. Obtener objetivo (Solo si es comando de texto con mención)
    target_user = None
    if not is_panel:
        target_user, _ = await _get_target_user_from_command(update, context)

    # --- NUEVO: Validar si ya tiene intercambio activo ---
    active_trades = context.chat_data.get('active_trades', {})
    if sender.id in active_trades:
        text = "⛔ Ya tienes una petición de intercambio pendiente. Espéra a que la acepten o rechacen."
        if is_panel:
            await query.answer(text, show_alert=True)
        else:
            msg = await message.reply_text(text, disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return
    # ----------------------------------------------------

    # Si no hay objetivo o es el mismo usuario -> Mostrar Ayuda
    if not target_user or target_user.id == sender.id or target_user.is_bot:
        help_text = (
            "♻ **Intercambios**\n\n"
            "**¿Cómo funcionan?**\n"
            "Responde a un mensaje que haya escrito la persona con la que quieres intercambiar, y escribe `/intercambio` "
            "(también puedes mencionarla: `/intercambio @usuario`).\n\n"
            "Aparecerá un menú donde puedes ver sus repetidos y ofrecer uno de los tuyos."
        )
        if is_panel:
            # Enviamos mensaje nuevo temporal
            msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text,
                                                 parse_mode='Markdown', disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        else:
            msg = await message.reply_text(help_text, parse_mode='Markdown', disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return

    # 3. Validar límite diario del objetivo
    if not db.check_trade_daily_limit(target_user.id):
        msg = await message.reply_text(f"⛔ {target_user.first_name} ha alcanzado su límite de intercambios hoy.",
                                       disable_notification=True)
        schedule_message_deletion(context, msg, 60)
        return

    # 4. Iniciar flujo
    await show_trade_menu_target_duplicates(update, context, target_user.id, sender.id, page=0)


async def show_trade_menu_target_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id, sender_id,
                                            page=0):
    # Obtener repetidos del TARGET
    duplicates = db.get_user_duplicates(target_id)

    if not duplicates:
        text = "❌ El otro usuario no tiene stickers repetidos para cambiar."
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        else:
            msg = await context.bot.send_message(update.effective_chat.id, text, disable_notification=True)
            schedule_message_deletion(context, msg, 60)
        return

    # Paginación
    ITEMS_PER_PAGE = 20
    total_pages = math.ceil(len(duplicates) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_list = duplicates[start:end]

    # Obtener colección del SENDER para marcar los NEW
    sender_collection = db.get_all_user_stickers(sender_id)

    keyboard = []
    row = []
    for poke_id, is_shiny in current_list:
        p_data = POKEMON_BY_ID[poke_id]
        rarity = get_rarity(p_data['category'], is_shiny)

        # Marca NEW si sender no lo tiene
        is_new = (poke_id, is_shiny) not in sender_collection
        new_mark = "🆕" if is_new else ""
        shiny_mark = "✨" if is_shiny else ""

        btn_text = f"{p_data['name']}{shiny_mark} {RARITY_VISUALS.get(rarity, '')} {new_mark}"
        # trade_select_target_TGT_SND_POKE_SHINY
        cb_data = f"trade_step2_{target_id}_{sender_id}_{poke_id}_{int(is_shiny)}"

        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    # Botones navegación
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"trade_nav_target_{target_id}_{sender_id}_{page - 1}"))
    if end < len(duplicates):
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"trade_nav_target_{target_id}_{sender_id}_{page + 1}"))
    if nav_row: keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data=f"trade_cancel_{sender_id}")])

    target_name = (await context.bot.get_chat(target_id)).first_name
    text = f"♻ **Repetidos de {target_name}:**\nSelecciona qué quieres recibir."

    if update.callback_query:
        refresh_deletion_timer(context, update.callback_query.message, 120)  # 2 min
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

    # --- CORRECCIÓN: SOLO EL SENDER PUEDE ELEGIR ---
    if query.from_user.id != sender_id:
        await query.answer("Solo la persona que inició el intercambio puede elegir.", show_alert=True)
        return
    # -----------------------------------------------

    wanted_data = POKEMON_BY_ID[wanted_pid]
    wanted_rarity = get_rarity(wanted_data['category'], wanted_shiny)

    my_duplicates = db.get_user_duplicates(sender_id)

    valid_duplicates = []
    for pid, shiny in my_duplicates:
        p_data = POKEMON_BY_ID[pid]
        r = get_rarity(p_data['category'], shiny)
        if r == wanted_rarity:
            valid_duplicates.append((pid, shiny))

    if not valid_duplicates:
        await query.answer(f"❌ No tienes repetidos de rareza {wanted_rarity} para ofrecer.", show_alert=True)
        return

    target_collection = db.get_all_user_stickers(target_id)

    keyboard = []
    row = []
    for pid, shiny in valid_duplicates:
        p_data = POKEMON_BY_ID[pid]

        is_useful = (pid, shiny) not in target_collection
        useful_mark = "🤝" if is_useful else ""
        shiny_mark = "✨" if shiny else ""

        btn_text = f"{p_data['name']}{shiny_mark} {useful_mark}"
        cb_data = f"trade_conf_{target_id}_{sender_id}_{wanted_pid}_{int(wanted_shiny)}_{pid}_{int(shiny)}"

        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=f"trade_nav_target_{target_id}_{sender_id}_0")])

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

    # Obtenemos los objetos de chat completos para poder mencionar
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

    # --- CAMBIO: MENCIONES REALES ---
    text = (
        f"♻ **Petición de Intercambio**\n\n"
        f"👤 {sender.mention_markdown()} ofrece: {o_name} {t_new}\n"
        f"👤 Para {target.mention_markdown()} por: {w_name} {s_new}\n\n"
        f"Esperando confirmación de {target.mention_markdown()}..."
    )
    # --------------------------------

    data_payload = f"{target_id}_{sender_id}_{want_p}_{int(want_s)}_{offer_p}_{int(offer_s)}"

    keyboard = [
        [InlineKeyboardButton("✅ Aceptar", callback_data=f"trade_exec_{data_payload}")],
        [InlineKeyboardButton("❌ Rechazar", callback_data=f"trade_reject_{data_payload}")]
    ]

    cancel_scheduled_deletion(context, query.message.chat_id, query.message.message_id)
    context.chat_data.setdefault('active_trades', {})
    context.chat_data['active_trades'][sender_id] = query.message.message_id
    schedule_message_deletion(context, query.message, 86400)

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
        return

    # 2. Validar límites diarios
    if not db.check_trade_daily_limit(sender_id) or not db.check_trade_daily_limit(target_id):
        await query.answer("⛔ Error: Alguno de los dos alcanzó el límite diario.", show_alert=True)
        await query.delete_message()
        return

    # Datos de los Pokémon
    want_p, want_s = int(parts[4]), bool(int(parts[5]))  # Lo que da el TARGET (Destinatario)
    offer_p, offer_s = int(parts[6]), bool(int(parts[7]))  # Lo que da el SENDER (Solicitante)

    # 3. VALIDACIÓN CRÍTICA DE STOCK (¡NUEVO!)
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

    # Obtener nombres
    s_name = (await context.bot.get_chat(sender_id)).first_name
    t_name = (await context.bot.get_chat(target_id)).first_name

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

    final_text = (
        f"♻✅ **¡Intercambio aceptado!**\n\n"
        f"👤 {s_name} recibió: {w_txt}\n"
        f"👤 {t_name} recibió: {o_txt}"
    )

    await query.edit_message_text(final_text, parse_mode='Markdown')

async def retos_missing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    refresh_deletion_timer(context, query.message, 30)

    try:
        chat_id = int(query.data.split('_')[-1])
    except:
        return

    text = "📂 **Selecciona una región para ver los faltantes:**"

    # Por ahora solo Kanto, pero preparado para más
    keyboard = [
        [InlineKeyboardButton("🔸 Kanto", callback_data=f"retos_view_kanto_{chat_id}")],
        # [InlineKeyboardButton("🔹 Johto", callback_data=f"retos_view_johto_{chat_id}")], # Futuro
        [InlineKeyboardButton("⬅️ Volver", callback_data=f"retos_back_{chat_id}")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def retos_view_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    refresh_deletion_timer(context, query.message, 30)

    data = query.data.split('_')
    region = data[2]  # 'kanto'
    chat_id = int(data[3])

    if region == 'kanto':
        # Calcular estadísticas
        group_ids = db.get_group_unique_kanto_ids(chat_id)

        # Contadores de rareza
        rarity_counts = {'C': 0, 'B': 0, 'A': 0, 'S': 0}
        rarity_totals = {'C': 0, 'B': 0, 'A': 0, 'S': 0}
        missing_names = []

        # Recorremos SOLO Kanto (1-151)
        for p in ALL_POKEMON:
            if p['id'] > 151: continue

            rarity_totals[p['category']] += 1

            if p['id'] in group_ids:
                rarity_counts[p['category']] += 1
            else:
                missing_names.append(p['name'])

        # Construir texto
        text = "🔸 **Kanto:**\n\n"

        text += "_Rarezas:_\n"
        r_text = []
        for cat in ['C', 'B', 'A', 'S']:
            emoji = RARITY_VISUALS[cat]
            r_text.append(f"{emoji} {rarity_counts[cat]}/{rarity_totals[cat]}")
        text += ", ".join(r_text) + "\n\n"

        if not missing_names:
            text += "✅ _¡Álbumdex completo de Kanto!_\n\n"
        else:
            text += "Faltan:\n"
            # Limitamos a mostrar 50 para no romper el límite de Telegram si faltan todos
            # Si quieres todos, quita el [:50]
            for name in missing_names[:50]:
                text += f"- {name}\n"
            if len(missing_names) > 50:
                text += f"... y {len(missing_names) - 50} más.\n"
            text += "\n"

        text += f"📊 **Total: {len(group_ids)}/151**"

        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data=f"retos_missing_menu_{chat_id}")]]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def trade_nav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    # trade_nav_target_TGT_SND_PAGE
    target_id, sender_id, page = int(parts[3]), int(parts[4]), int(parts[5])

    if query.from_user.id != sender_id:
        await query.answer("No es tu menú.", show_alert=True)
        return

    await show_trade_menu_target_duplicates(update, context, target_id, sender_id, page)

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
            await update.message.reply_text(f"ℹ️ No se encontró ningún regalo con el ID `{mail_id}`.", disable_notification=True)
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
    """Planifica el evento de Delibird para un momento aleatorio de la semana."""
    # Se ejecuta los lunes a las 00:05

    # 1. Calcular segundos aleatorios en la semana (7 días)
    # Dejamos un margen de 1 hora al principio y al final
    seconds_in_week = 7 * 24 * 3600
    random_delay = random.randint(3600, seconds_in_week - 3600)

    # 2. Programar el trabajo único
    context.job_queue.run_once(trigger_delibird_event, random_delay, name="delibird_weekly_event")

    # Calcular fecha para el log
    trigger_date = datetime.fromtimestamp(time.time() + random_delay)
    logger.info(f"🐧 Delibird programado para: {trigger_date}")


async def trigger_delibird_event(context: ContextTypes.DEFAULT_TYPE):
    """Lanza el evento."""
    # 1. Limpiamos la lista global de reclamados (Empieza nueva semana)
    DELIBIRD_GLOBAL_CLAIMED.clear()

    active_groups = db.get_active_groups()
    current_time = time.time()

    text = (
        "🐧🎁 **¡DELIBIRD HA LLEGADO!**\n\n"
        "Trae un saco lleno de sobres elementales de Kanto.\n"
        "¡Reclama el tuyo antes de que se vaya!\n\n"
        "_La bolsa contiene sobres de cada tipo de Pokémon o un Sobre Especial de 7 stickers._"
    )

    keyboard = [
        [InlineKeyboardButton("¡RECLAMAR PREMIO!🎁", callback_data="delibird_claim")],
        [InlineKeyboardButton("ℹ", callback_data="delibird_info")]
    ]

    for chat_id in active_groups:
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text,
                                                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

            DELIBIRD_STATE[chat_id] = {
                'msg_id': msg.message_id,
                'winners': [],
                'timestamp': current_time
            }
            # Cierre en 24h
            context.job_queue.run_once(close_delibird_event, 86400, chat_id=chat_id, data=chat_id)
        except:
            pass


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

    if query.data == "delibird_info":
        await query.answer(
            "🎒 Contiene sobres de tipos (Fuego, Agua, etc...) y Sobres Especiales con más probabilidad de Shiny.",
            show_alert=True)
        return

    # Verificar estado local
    state = DELIBIRD_STATE.get(chat_id)
    if not state:
        await query.answer("Delibird ya se ha ido...", show_alert=True)
        return

    # --- VERIFICACIÓN GLOBAL ---
    if user.id in DELIBIRD_GLOBAL_CLAIMED:
        await query.answer("¡Ya has cogido un sobre en algún grupo! Solo 1 por semana.", show_alert=True)
        return
    # ---------------------------

    # Seleccionar premio
    # Creamos lista de IDs posibles (todos los elem_ y el especial)
    possible_packs = [k for k in SHOP_CONFIG.keys() if k.startswith('pack_elem_')]
    prize_id = random.choice(possible_packs)
    prize_info = SHOP_CONFIG[prize_id]

    # Dar premio (A LA MOCHILA)
    db.get_or_create_user(user.id, user.first_name)
    db.add_item_to_inventory(user.id, prize_id, 1)

    # Marcar como reclamado globalmente
    DELIBIRD_GLOBAL_CLAIMED.add(user.id)

    # Actualizar lista mensaje
    safe_name = user.first_name.replace('*', '').replace('_', '')
    list_line = f"- {safe_name} recibió {prize_info['name']} {prize_info['emoji']}"
    state['winners'].append(list_line)

    new_text = (
            "🐧🎁 **¡DELIBIRD HA LLEGADO!**\n"
            "Trae un saco lleno de sobres elementales de Kanto.\n"
            "¡Reclama el tuyo antes de que se vaya!\n\n"
            "Resultados:\n" + "\n".join(state['winners'])
    )

    try:
        await query.edit_message_text(text=new_text, reply_markup=query.message.reply_markup, parse_mode='Markdown')
    except:
        pass

    # Alerta Pop-up
    await query.answer(f"¡Has conseguido un {prize_info['name']}!\nGuárdalo en tu mochila.", show_alert=True)


# COMANDO DE TEST
async def admin_test_delibird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    await trigger_delibird_event(context)
    await update.message.delete()


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
        text += f"▪️ {name} (ID: `{item['item_id']}`) x{item['quantity']}\n"

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


async def daily_tombola_job(context: ContextTypes.DEFAULT_TYPE):
    # --- LOG DE CONTROL ---
    logger.info("🕒 EJECUTANDO TÓMBOLA DIARIA (SISTEMA GLOBAL)...")
    # ----------------------

    text = (
        "🎟️ *Tómbola Diaria* 🎟️\n\n"
        "Prueba suerte una vez al día para ganar premios. Dependiendo de la bola que saques, esto es lo que te puede tocar:\n"
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

    # --- ZONA DE TAREAS PROGRAMADAS (CON LIMPIEZA ANTI-DUPLICADOS) ---

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
    application.job_queue.run_daily(
        schedule_delibird_week,
        time=dt_time(0, 5, tzinfo=TZ_SPAIN),
        days=(1,),
        # 0=Lunes (en python-telegram-bot suele ser 0-6 L-D o 1-7, verificar librería. Usually Monday=1 in datetime but check APScheduler. En PTB days=(1,) es Martes? No, days=(0,) es Lunes. Probamos (0,).)
        name="delibird_scheduler"
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
        CallbackQueryHandler(lambda u, c: u.callback_query.delete_message(), pattern="^trade_cancel_"),
        CallbackQueryHandler(ranking_navigation_handler, pattern="^rank_nav_"),
        CallbackQueryHandler(inventory_cmd, pattern="^inv_mode_"),
        CallbackQueryHandler(delibird_claim_handler, pattern="^delibird_"),

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
