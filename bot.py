# bot.py
import logging
import random
import time
import asyncio
from datetime import datetime
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
PROBABILITIES = {'C': 0.45, 'B': 0.30, 'A': 0.20, 'S': 0.05}
SHINY_CHANCE = 0.02
TZ_SPAIN = pytz.timezone('Europe/Madrid')

# --- Probabilidad del 15% ---
EVENT_CHANCE = 0.15

# --- CONFIGURACIÓN DE TIEMPOS DE APARICIÓN (En segundos) ---
MIN_SPAWN_TIME = 3600  # 1 hora
MAX_SPAWN_TIME = 14400  # 4 horas

# --- CONFIGURACIÓN DE OBJETOS Y SOBRES ---
SHOP_CONFIG = {
    'pack_small_national': {'name': 'Sobre Pequeño Nacional', 'price': 1000, 'size': 3, 'is_magic': False,
                            'desc': 'Contiene 3 stickers al azar.'},
    'pack_medium_national': {'name': 'Sobre Mediano Nacional', 'price': 1500, 'size': 5, 'is_magic': False,
                             'desc': 'Contiene 5 stickers al azar.'},
    'pack_large_national': {'name': 'Sobre Grande Nacional', 'price': 1900, 'size': 7, 'is_magic': False,
                            'desc': 'Contiene 7 stickers al azar.'},
    'pack_magic_small_national': {'name': 'Sobre Mágico Pequeño Nacional', 'price': 1600, 'size': 1, 'is_magic': True,
                                  'desc': 'Contiene 1 sticker que no tienes.'},
    'pack_magic_medium_national': {'name': 'Sobre Mágico Mediano Nacional', 'price': 2100, 'size': 3, 'is_magic': True,
                                   'desc': 'Contiene 3 stickers que no tienes.'},
    'pack_magic_large_national': {'name': 'Sobre Mágico Grande Nacional', 'price': 2500, 'size': 5, 'is_magic': True,
                                  'desc': 'Contiene 5 stickers que no tienes.'},
}
ITEM_NAMES = {item_id: details['name'] for item_id, details in SHOP_CONFIG.items()}
PACK_CONFIG = {item_id: {'size': details['size'], 'is_magic': details['is_magic']} for item_id, details in
               SHOP_CONFIG.items()}

# --- Emojis de dinero ---
DAILY_PRIZES = [
    {'type': 'money', 'value': 100, 'emoji': '🟤',
     'msg': '¡{usuario} sacó la bola 🟤!\n\n¡Obtuvo *100₽* 💰! ¡Menos es nada!'},
    {'type': 'money', 'value': 200, 'emoji': '🟢',
     'msg': '¡{usuario} sacó la bola 🟢!\n\n¡Genial, *200₽* 💰 que se llevó!'},
    {'type': 'money', 'value': 400, 'emoji': '🔵',
     'msg': '¡{usuario} sacó la bola 🔵!\n\n¡Fantástico! ¡Ha ganado *400₽* 💰!'},
    {'type': 'item', 'value': 'pack_magic_medium_national', 'emoji': '🟡',
     'msg': '¡Sacaste la bola 🟡!\n\n¡¡PREMIO GORDO!! ¡{usuario} ha conseguido un *Sobre Mágico Mediano Nacional*! 🎴'}
]

ITEM_NAMES['pack_magic_medium_national'] = SHOP_CONFIG['pack_magic_medium_national']['name']
ITEM_NAMES['pluma_naranja'] = 'Pluma Naranja'
ITEM_NAMES['pluma_amarilla'] = 'Pluma Amarilla'
ITEM_NAMES['pluma_azul'] = 'Pluma Azul'
ITEM_NAMES['foto_psiquica'] = 'Foto Psíquica(?)'

DAILY_WEIGHTS = [50, 30, 15, 5]
USER_FRIENDLY_ITEM_IDS = {'sobremagicomedianonacional': 'pack_magic_medium_national'}
POKEMON_BY_CATEGORY = {cat: [] for cat in PROBABILITIES.keys()}
for pokemon_item in ALL_POKEMON:
    POKEMON_BY_CATEGORY[pokemon_item['category']].append(pokemon_item)
POKEMON_PER_PAGE = 52
PACK_OPEN_COOLDOWN = 15


# --- FUNCIONES AUXILIARES ---

async def is_group_qualified(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Verifica si el grupo cumple los requisitos de actividad.
    Devuelve True si:
    1. El ADMIN_USER_ID está en el grupo.
    2. O hay al menos 3 usuarios registrados en la base de datos para este chat.
    """
    # 1. Chequeo de Admin (Llave Maestra)
    try:
        member = await context.bot.get_chat_member(chat_id, ADMIN_USER_ID)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
    except BadRequest:
        pass # El admin no está o no se puede leer

    # 2. Chequeo de Usuarios Activos
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
    """Tarea diaria que verifica si es día 1 para enviar premios."""
    now = datetime.now(TZ_SPAIN)
    if now.day == 1:
        ranking = db.get_monthly_ranking()
        if not ranking:
            db.reset_monthly_stickers()
            return
        message_lines = ["🏆 Ranking de mayor número de stickers conseguidos este mes:\n"]
        medals = ["🥇", "🥈", "🥉"]
        for index, (uid, uname, count) in enumerate(ranking):
            medal = medals[index] if index < 3 else "-"
            prize = 300
            if index == 0: prize = 1000
            elif index == 1: prize = 800
            elif index == 2: prize = 500
            line = f"{medal} {uname}: {count} stickers - (Premio: {format_money(prize)}₽)"
            message_lines.append(line)
            db.add_mail(uid, 'money', str(prize), "Premio mensual")
        message_lines.append("\n_Los premios han sido enviados_")
        final_text = "\n".join(message_lines)
        active_groups = db.get_active_groups()
        for chat_id in active_groups:
            try:
                await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Error enviando ranking mensual al chat {chat_id}: {e}")
        db.reset_monthly_stickers()


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

    if query:
        try:
            parts = query.data.split('_')
            owner_id_str = parts[-2] if len(parts) > 2 and parts[-1].isdigit() else parts[-1]
            owner_id = int(owner_id_str)
            if len(parts) > 2 and parts[-1].isdigit():
                cmd_msg_id = int(parts[-1])
            if interactor_user.id != owner_id:
                await query.answer("Este álbumdex no es tuyo.", show_alert=True)
                return
            owner_user = interactor_user
        except (ValueError, IndexError):
            await query.answer("Error en el botón.", show_alert=True)
            return
    else:
        owner_user = interactor_user
        if update.message:
            cmd_msg_id = update.message.message_id

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
            if final_rarity in rarity_counts:
                rarity_counts[final_rarity] += 1
    rarity_lines = [f"{rarity_counts[code]} {emoji}" for code, emoji in RARITY_VISUALS.items()]
    text = (f"📖 *Álbumdex Nacional de {owner_user.first_name}*\n\n"
            f"Stickers: *{owned_normal}/{total_pokemon_count}*\n"
            f"Brillantes: *{owned_shiny}/{total_pokemon_count}*\n\n"
            f"Rarezas: {', '.join(rarity_lines)}\n\n"
            "Selecciona una región para ver detalles:")

    keyboard = []
    for name in POKEMON_REGIONS.keys():
        cb_data = f"album_{name}_0_{owner_user.id}"
        if cmd_msg_id:
            cb_data += f"_{cmd_msg_id}"
        keyboard.append([InlineKeyboardButton(f"Ver Álbum de {name}", callback_data=cb_data)])

    close_cb_data = f"album_close_{owner_user.id}"
    if cmd_msg_id:
        close_cb_data += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Cerrar Álbum", callback_data=close_cb_data)])

    if query:
        await query.answer()
        refresh_deletion_timer(context, query.message, 60)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        schedule_message_deletion(context, update.message, 60)
        schedule_message_deletion(context, msg, 60)


async def album_region_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    cmd_msg_id = None
    try:
        parts = query.data.split('_')
        region_name = parts[1]
        page = int(parts[2])
        owner_id = int(parts[3])
        if len(parts) > 4:
            cmd_msg_id = int(parts[4])
        if interactor_user.id != owner_id:
            await query.answer("Este álbum no es tuyo.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en los datos del álbum.", show_alert=True)
        return
    pokemon_list_region = POKEMON_REGIONS.get(region_name)
    if not pokemon_list_region:
        await query.answer("Región no encontrada.", show_alert=True)
        return
    await query.answer()
    refresh_deletion_timer(context, query.message, 60)

    user_collection = db.get_all_user_stickers(owner_id)
    total_region, total_pages = len(pokemon_list_region), math.ceil(len(pokemon_list_region) / POKEMON_PER_PAGE)
    start_index, end_index = page * POKEMON_PER_PAGE, (page + 1) * POKEMON_PER_PAGE
    pokemon_on_page = pokemon_list_region[start_index:end_index]
    text = f"📖 *Álbumdex de {region_name} (Pág. {page + 1}/{total_pages})*"
    keyboard, row = [], []
    for pokemon in pokemon_on_page:
        has_normal, has_shiny = (pokemon['id'], 0) in user_collection, (pokemon['id'], 1) in user_collection
        if has_normal or has_shiny:
            button_text = f"#{pokemon['id']:03} {pokemon['name']}"
            if has_shiny:
                button_text += f" ✨{RARITY_VISUALS.get(get_rarity(pokemon['category'], True), '')}"
            elif has_normal:
                button_text += f" {RARITY_VISUALS.get(get_rarity(pokemon['category'], False), '')}"
            cb_data = f"showsticker_{region_name}_{page}_{pokemon['id']}_{owner_id}"
            if cmd_msg_id:
                cb_data += f"_{cmd_msg_id}"
            callback_data = cb_data
        else:
            button_text = f"#{pokemon['id']:03} ---"
            callback_data = "missing_sticker"
        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    pagination_row = []
    if page > 0:
        prev_cb = f"album_{region_name}_{page - 1}_{owner_id}"
        if cmd_msg_id: prev_cb += f"_{cmd_msg_id}"
        pagination_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=prev_cb))
    if end_index < total_region:
        next_cb = f"album_{region_name}_{page + 1}_{owner_id}"
        if cmd_msg_id: next_cb += f"_{cmd_msg_id}"
        pagination_row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=next_cb))
    if pagination_row:
        keyboard.append(pagination_row)
    back_cb = f"album_main_{owner_id}"
    if cmd_msg_id: back_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver al Álbum Nacional", callback_data=back_cb)])
    close_cb = f"album_close_{owner_id}"
    if cmd_msg_id: close_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Cerrar Álbum", callback_data=close_cb)])
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
    back_cb_data = f"album_{region_name}_{page_str}_{owner_id}"
    if cmd_msg_id_str:
        back_cb_data += f"_{cmd_msg_id_str}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data=back_cb_data)])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def send_sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user
    message = cast(Message, query.message)
    if not message:
        await query.answer("El mensaje original no está disponible.", show_alert=True)
        return
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
        shiny_text = " Brillante" if is_shiny else ""
        final_rarity = get_rarity(pokemon_data['category'], is_shiny)
        rarity_emoji = RARITY_VISUALS.get(final_rarity, "")
        message_text = f"{interactor_user.first_name} mostró su *{pokemon_data['name']}{shiny_text}* {rarity_emoji}"
        await context.bot.send_message(chat_id=message.chat_id, text=message_text, parse_mode='Markdown')
        image_path = f"Stickers/Kanto/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"
        with open(image_path, 'rb') as sticker_file:
            await context.bot.send_sticker(chat_id=message.chat_id, sticker=sticker_file)
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
    if context.chat_data['active_events']:
        logger.info(f"Limpiando evento activo anterior en el chat {chat_id}")
        context.chat_data['active_events'] = {}

    # --- NUEVA LÓGICA DE FILTRADO (Llave Maestra) ---
    is_qualified = await is_group_qualified(chat_id, context)

    available_events = []
    legendary_missions = ['mision_moltres', 'mision_zapdos', 'mision_articuno', 'mision_mewtwo']

    for ev_id in EVENTS.keys():
        # Si el grupo NO es cualificado, bloqueamos los legendarios
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
    context.chat_data['active_events'][msg.message_id] = {'event_id': event_id, 'claimed_by': None}


async def spawn_pokemon(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id  # Recuperamos el chat_id del job

    if random.random() < EVENT_CHANCE:
        await spawn_event(context)
        # Importante: aunque sea evento, reprogramamos el siguiente spawn
        if chat_id in db.get_active_groups():
            next_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
            context.job_queue.run_once(spawn_pokemon, next_delay, chat_id=chat_id, name=f"spawn_{chat_id}")
            logger.info(f"Próximo spawn en chat {chat_id} en {next_delay} segundos.")
        return

    context.chat_data.setdefault('active_spawns', {})
    current_time = time.time()
    for msg_id in list(context.chat_data.get('active_spawns', {}).keys()):
        if current_time - context.chat_data['active_spawns'][msg_id].get('timestamp', 0) > 7200:
            spawn_data = context.chat_data['active_spawns'].pop(msg_id, None)
            if spawn_data:
                for key in ['sticker_id', 'text_id']:
                    try:
                        await context.bot.delete_message(chat_id, spawn_data[key])
                    except BadRequest:
                        pass

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
        # --- ATOMIC SPAWN (BOTÓN INCLUIDO) ---

        # 1. Enviamos Sticker
        with open(image_path, 'rb') as sticker_file:
            sticker_msg = await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file)

        # 2. Preparamos el botón CON ID 0 (Comodín)
        callback_data = f"claim_0_{pokemon_data['id']}_{int(is_shiny)}_{rarity}"
        button_text = "¡Capturar! 📷"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=callback_data)]])

        # 3. Enviamos Texto YA CON EL BOTÓN
        text_msg = await context.bot.send_message(chat_id=chat_id, text=text_message, parse_mode='Markdown',
                                                  reply_markup=reply_markup)

        # 4. Guardamos los datos USANDO LA ID REAL DEL MENSAJE ENVIADO
        context.chat_data['active_spawns'][text_msg.message_id] = {
            'sticker_id': sticker_msg.message_id,
            'text_id': text_msg.message_id,
            'timestamp': current_time
        }
        # FIN. Ahora el botón se ve siempre porque sale junto con el mensaje.

    except FileNotFoundError:
        logger.error(f"No se encontró la imagen: {image_path}")

    # --- REPROGRAMAR EL SIGUIENTE SPAWN ---
    # Verificamos si el grupo sigue activo en BD antes de programar
    if chat_id in db.get_active_groups():
        next_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
        context.job_queue.run_once(spawn_pokemon, next_delay, chat_id=chat_id, name=f"spawn_{chat_id}")
        logger.info(f"Próximo spawn en chat {chat_id} en {next_delay} segundos.")


# --- COMANDO SECRETO PARA EL ADMIN: FORZAR APARICIÓN ---
async def force_spawn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Comprobación de seguridad: SOLO TU ID
    if update.effective_user.id != ADMIN_USER_ID:
        return  # Ignorar si no es el admin

    chat_id = update.effective_chat.id

    # 2. Lógica de spawn (copiada y adaptada de spawn_pokemon, pero SIN re-programar ni eventos)
    pokemon_data, is_shiny, rarity = choose_random_pokemon()

    # Mensajes y nombres
    pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
    text_message = f"¡Un *{pokemon_name} {RARITY_VISUALS.get(rarity, '')}* salvaje apareció!"
    image_path = f"Stickers/Kanto/{'Shiny/' if is_shiny else ''}{pokemon_data['id']}{'s' if is_shiny else ''}.png"

    try:
        # Enviar Sticker
        with open(image_path, 'rb') as sticker_file:
            sticker_msg = await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file)

        # Botón con ID 0
        callback_data = f"claim_0_{pokemon_data['id']}_{int(is_shiny)}_{rarity}"
        button_text = "¡Capturar! 📷"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=callback_data)]])

        # Texto con botón
        text_msg = await context.bot.send_message(chat_id=chat_id, text=text_message, parse_mode='Markdown',
                                                  reply_markup=reply_markup)

        # Guardar datos con ID real
        context.chat_data.setdefault('active_spawns', {})
        context.chat_data['active_spawns'][text_msg.message_id] = {
            'sticker_id': sticker_msg.message_id,
            'text_id': text_msg.message_id,
            'timestamp': time.time()
        }

        # Borrar el mensaje del comando "/forcespawn" para que quede limpio
        await update.message.delete()

    except FileNotFoundError:
        logger.error(f"No se encontró la imagen: {image_path}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    if chat.type in ['group', 'supergroup']:
        # Verificar permisos de administrador
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator'] and user.id != ADMIN_USER_ID:
            await update.message.reply_text("⛔ Este comando solo puede ser usado por administradores.")
            return

        # Verificar cantidad de miembros (>= 10)
        member_count = await context.bot.get_chat_member_count(chat.id)
        if member_count < 10 and user.id != ADMIN_USER_ID:
            await update.message.reply_text("⚠️ El bot solo funciona en grupos con al menos 10 miembros.")
            return

        db.add_group(chat.id, chat.title)
        db.set_group_active(chat.id, True)

        # Comprobar si ya existe un job programado
        current_jobs = context.job_queue.get_jobs_by_name(f"spawn_{chat.id}")
        if not current_jobs:
            # --- MODIFICADO: Primer spawn aleatorio (entre 1h y 4h), no 10s ---
            initial_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
            context.job_queue.run_once(spawn_pokemon, initial_delay, chat_id=chat.id, name=f"spawn_{chat.id}")
            msg = await update.message.reply_text("✅ Aparición de Pokémon salvajes activada.")
            logger.info(f"Juego iniciado en {chat.id}. Spawn inicial en {initial_delay}s.")
        else:
            msg = await update.message.reply_text("El bot ya está en funcionamiento.")

        # Borrar comando y respuesta
        schedule_message_deletion(context, update.message, 30)
        schedule_message_deletion(context, msg, 30)

    else:
        await update.message.reply_text("¡Hola! Añádeme a un grupo para empezar.")


async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or not update.effective_user:
        return
    if chat.type == 'private':
        await update.message.reply_text("Este comando solo funciona en grupos.")
        return
    member = await context.bot.get_chat_member(chat.id, update.effective_user.id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("⛔ Este comando solo puede ser usado por administradores.")
        return

    # Detener el job programado (rompe la cadena de run_once)
    jobs = context.job_queue.get_jobs_by_name(f"spawn_{chat.id}")
    if not jobs:
        msg = await update.message.reply_text("El juego ya está detenido.")
        schedule_message_deletion(context, update.message, 30)
        schedule_message_deletion(context, msg, 30)
        return
    for job in jobs:
        job.schedule_removal()

    db.set_group_active(chat.id, False)
    msg = await update.message.reply_text("❌ La aparición de Pokémon salvajes se ha desactivado.")
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

    # --- REGISTRO DEL USUARIO EN EL GRUPO ACTUAL ---
    if message.chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, message.chat.id)

    try:
        # AHORA IGNORAMOS EL msg_id QUE VIENE EN EL STRING (PORQUE ES 0)
        _, _, pokemon_id_str, is_shiny_str, rarity = query.data.split('_')
        # Y USAMOS LA ID REAL DEL MENSAJE DONDE SE PULSÓ EL BOTÓN
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

        # Incrementar contador mensual
        db.increment_monthly_stickers(user.id)

        for key in ['sticker_id', 'text_id']:
            try:
                await context.bot.delete_message(chat_id=message.chat_id, message_id=claimed_spawn[key])
            except BadRequest:
                pass

        pokemon_data = POKEMON_BY_ID.get(pokemon_id)
        pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"

        message_text = ""

        if db.check_sticker_owned(user.id, pokemon_id, is_shiny):
            money_earned = DUPLICATE_MONEY_VALUES.get(rarity, 100)
            db.update_money(user.id, money_earned)
            message_text = f"✔️ ¡Genial, {user.mention_markdown()}! Conseguiste un sticker de *{pokemon_name} {RARITY_VISUALS.get(rarity, '')}*. Como ya lo tenías, se convierte en *{format_money(money_earned)}₽* 💰."
        else:
            db.add_sticker_to_collection(user.id, pokemon_id, is_shiny)
            message_text = f"🎉 ¡Felicidades, {user.mention_markdown()}! Has conseguido un sticker de *{pokemon_name} {RARITY_VISUALS.get(rarity, '')}*. Lo has registrado en tu Álbumdex."

        # --- NUEVO: Añadir a Pokédex Grupal ---
        if message.chat.type in ['group', 'supergroup']:
            db.add_pokemon_to_group_pokedex(message.chat.id, pokemon_id)

        # --- LÓGICA DE VALIDACIÓN (JUEZ SILENCIOSO) ---
        is_qualified = await is_group_qualified(message.chat.id, context)

        # --- VERIFICAR KANTO COMPLETADO (INDIVIDUAL) ---
        if not db.is_kanto_completed_by_user(user.id):
            unique_count = db.get_user_unique_kanto_count(user.id)
            if unique_count >= 151:
                db.set_kanto_completed_by_user(user.id)
                if is_qualified:
                    db.update_money(user.id, 3000)
                    message_text += f"\n\n🎊 ¡Felicidades {user.mention_markdown()}, has conseguido los 151 Pokémon de Kanto! 🎊\n¡Recibes 3000₽ de recompensa!"
                else:
                    # Mensaje normal SIN premio
                    message_text += f"\n\n🎊 ¡Felicidades {user.mention_markdown()}, has conseguido los 151 Pokémon de Kanto! 🎊"

        # --- VERIFICAR RETO GRUPAL (LOCAL PARA ESTE GRUPO) ---
        chat_id = message.chat.id
        if message.chat.type in ['group', 'supergroup']:
            # Usamos el sistema de eventos para marcar si ESTE grupo ya completó el reto Kanto
            if not db.is_event_completed(chat_id, 'kanto_group_challenge'):
                # Contamos pokémon únicos capturados EN ESTE GRUPO
                group_unique_ids = db.get_group_unique_kanto_ids(chat_id)

                if len(group_unique_ids) >= 151:
                    db.mark_event_completed(chat_id, 'kanto_group_challenge')

                    if is_qualified:
                        # Premiar solo a los miembros de este grupo
                        group_users = db.get_users_in_group(chat_id)
                        for uid in group_users:
                            db.add_mail(uid, 'money', '2000', "Premio Reto Grupal: Kanto Completado")
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! ¡Habéis completado el reto de conseguir los 151 Pokémon de Kanto capturándolos aquí! Cada jugador ha recibido 2000₽ en su buzón."
                    else:
                        message_text += f"\n\n🌍🎉 ¡FELICIDADES AL GRUPO! ¡Habéis completado el reto de conseguir los 151 Pokémon de Kanto capturándolos aquí!"

        await context.bot.send_message(chat_id=message.chat_id, text=message_text, parse_mode='Markdown')

    else:
        await query.answer()
        new_chance = min(100, current_chance + 5)
        db.update_user_capture_chance(user.id, new_chance)

        spawn_data = context.chat_data['active_spawns'].get(msg_id)
        if spawn_data:
            if 'cooldowns' not in spawn_data:
                spawn_data['cooldowns'] = {}
            spawn_data['cooldowns'][user.id] = time.time()

        fail_message = await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"❌ La foto de {user.mention_markdown()} salió movida y no escaneó al pokémon.",
            parse_mode='Markdown',
            reply_to_message_id=msg_id
        )
        schedule_message_deletion(context, fail_message, delay_seconds=120)


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

    # --- REGISTRO DEL USUARIO EN EL GRUPO ACTUAL (Al aceptar evento) ---
    # Importante para que sus Pokémon de evento cuenten para el reto grupal
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
    if not event_data:
        return

    step_data = event_data['steps'].get(step_id)
    if not step_data:
        return

    if 'action' in step_data:
        result = step_data['action'](user, decision_parts, original_text=message.text)

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
    # --- REGISTRO POR ACTIVIDAD ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(owner_user.id, update.effective_chat.id)

    mails = db.get_user_mail(owner_user.id)
    text_empty = "📭 Tu buzón está vacío."
    if not mails:
        if query:
            try:
                if getattr(query.message, 'text', '') != text_empty:
                    await query.edit_message_text(text_empty)
            except BadRequest:
                pass
        else:
            sent_message = await update.message.reply_text(text_empty)
            schedule_message_deletion(context, sent_message)
            if update.message:
                schedule_message_deletion(context, update.message)
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

    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        sent_message = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                                       parse_mode='Markdown')
        schedule_message_deletion(context, sent_message)
        if update.message:
            schedule_message_deletion(context, update.message)


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
            if db.check_sticker_owned(user.id, poke_id, is_shiny):
                money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                db.update_money(user.id, money)
                message_text = f"📬 {user_mention} reclamó *{pokemon_name} {rarity_emoji}*. Ya lo tenía, ¡así que recibe *{format_money(money)}₽*!"
            else:
                db.add_sticker_to_collection(user.id, poke_id, is_shiny)
                message_text = f"📬 ¡Felicidades, {user_mention}! Has reclamado un *{pokemon_name} {rarity_emoji}*."
    if message_text:
        await context.bot.send_message(chat_id=message.chat_id, text=message_text, parse_mode='Markdown')
    await buzon(update, context)


async def buzon_refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await buzon(update, context)


async def tombola_start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    db.get_or_create_user(user.id, user.first_name)
    # --- REGISTRO POR ACTIVIDAD ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, update.effective_chat.id)

    if db.get_last_daily_claim(user.id) == datetime.now(TZ_SPAIN).strftime('%Y-%m-%d'):
        await update.message.reply_text("⏳ Ya has probado suerte hoy. ¡Vuelve mañana!")
        return
    text = ("🎟️ *Tómbola Diaria* 🎟️\n\n"
            "Prueba suerte una vez al día para ganar premios. Dependiendo de la bola que saques, esto es lo que te puede tocar:\n"
            "🟤 100₽ | 🟢 200₽ | 🔵 400₽ | 🟡 ¡Sobre Mágico!")
    keyboard = [[InlineKeyboardButton("Probar Suerte ✨", callback_data=f"tombola_claim_{user.id}")]]
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # Auto-borrado de la pregunta y el comando
    schedule_message_deletion(_context, update.message, 40)
    schedule_message_deletion(_context, msg, 40)


async def tombola_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    try:
        owner_id = int(query.data.split('_')[-1])
        if interactor_user.id != owner_id:
            await query.answer("No puedes reclamar la tómbola de otra persona.", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("Error en el botón.", show_alert=True)
        return

    today_str = datetime.now(TZ_SPAIN).strftime('%Y-%m-%d')
    if db.get_last_daily_claim(owner_id) == today_str:
        await query.answer("¡Ya has reclamado tu premio de hoy!", show_alert=True)
        await query.edit_message_text("⏳ Este premio ya fue reclamado.")
        return

    db.update_last_daily_claim(owner_id, today_str)
    prize = random.choices(DAILY_PRIZES, weights=DAILY_WEIGHTS, k=1)[0]
    if prize['type'] == 'money':
        db.update_money(owner_id, prize['value'])
    else:
        db.add_item_to_inventory(owner_id, prize['value'])

    # IMPORTANTE: Cancelar el borrado del mensaje porque ahora es el resultado y queremos que se quede
    if query.message:
        cancel_scheduled_deletion(context, query.message.chat_id, query.message.message_id)

    # MODIFICADO: Formatear el mensaje con el nombre del usuario
    msg_text = prize['msg'].format(usuario=interactor_user.mention_markdown())
    await query.edit_message_text(msg_text, parse_mode='Markdown')
    await query.answer()


async def tienda_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = update.effective_user
    cmd_msg_id = None
    owner_user = None

    if query:
        parts = query.data.split('_')
        owner_id = int(parts[-2])
        if len(parts) > 2:
            cmd_msg_id = int(parts[-1])
        if interactor_user.id != owner_id:
            await query.answer("Esta tienda no es tuya.", show_alert=True)
            return
        owner_user = interactor_user
    else:
        owner_user = interactor_user
        if update.message:
            cmd_msg_id = update.message.message_id

    db.get_or_create_user(owner_user.id, owner_user.first_name)
    # --- REGISTRO POR ACTIVIDAD ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(owner_user.id, update.effective_chat.id)

    user_money = db.get_user_money(owner_user.id)

    descriptions = [f"· *{details['name']}:* {details['desc']}" for details in SHOP_CONFIG.values()]
    desc_text = "\n".join(descriptions)

    text = (f"🏪 *Tienda de Sobres* 🏪\n\n"
            f"¡Bienvenido, {owner_user.first_name}!\n"
            f"Tu dinero actual: *{format_money(user_money)}₽*\n\n"
            f"*¿Qué contiene cada sobre?*\n{desc_text}\n\n"
            "Elige un sobre para comprar:")

    keyboard = []
    for item_id, details in SHOP_CONFIG.items():
        cb_data = f"buy_{item_id}_{owner_user.id}"
        if cmd_msg_id: cb_data += f"_{cmd_msg_id}"
        button_text = f"{details['name']} - {format_money(details['price'])}₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=cb_data)])

    refresh_cb = f"shop_refresh_{owner_user.id}"
    if cmd_msg_id: refresh_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("🔄 Actualizar Saldo", callback_data=refresh_cb)])

    close_cb = f"shop_close_{owner_user.id}"
    if cmd_msg_id: close_cb += f"_{cmd_msg_id}"
    keyboard.append([InlineKeyboardButton("❌ Salir de la tienda", callback_data=close_cb)])

    if query:
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            if query.data.startswith("buy_"):
                await query.answer()
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Tu saldo no ha cambiado.")
            else:
                logger.error(f"Error al actualizar tienda: {e}")
                await query.answer("Ocurrió un error al actualizar.", show_alert=True)
    else:
        msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        # Auto-borrado tienda
        schedule_message_deletion(context, update.message, 60)
        schedule_message_deletion(context, msg, 60)


async def buy_pack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    interactor_user = query.from_user

    try:
        parts = query.data.split('_')
        owner_id_str = parts[-2]
        item_id = '_'.join(parts[1:-2])
        owner_id = int(owner_id_str)

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
        await query.answer(f"✅ ¡Has comprado un {pack_details['name']}! Lo encontrarás en tu /mochila.",
                           show_alert=True)
        await tienda_cmd(update, context)
    else:
        needed = pack_price - user_money
        await query.answer(f"❌ No tienes suficiente dinero. Te faltan {format_money(needed)}₽.", show_alert=True)


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
    user = update.effective_user
    if not user:
        return

    db.get_or_create_user(user.id, user.first_name)
    # --- REGISTRO POR ACTIVIDAD ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, update.effective_chat.id)

    items = db.get_user_inventory(user.id)

    text = "🎒 Tu mochila está vacía."
    keyboard = None
    if items:
        text = "🎒 *Tu Mochila:*\n\n"
        keyboard_buttons = []
        for item in items:
            if item['item_id'].startswith('lottery_ticket_'):
                item_name = "Ticket de lotería ganador"
                keyboard_buttons.append([InlineKeyboardButton("👀 Ver Ticket",
                                                              callback_data=f"viewticket_{item['item_id']}_{user.id}")])
            elif item['item_id'] == 'pluma_naranja':
                item_name = "Pluma Naranja 🪶"
                keyboard_buttons.append([InlineKeyboardButton("Ver Pluma naranja",
                                                              callback_data=f"viewspecial_{item['item_id']}_{user.id}")])
            elif item['item_id'] == 'pluma_amarilla':
                item_name = "Pluma Amarilla 🪶"
                keyboard_buttons.append([InlineKeyboardButton("Ver Pluma amarilla",
                                                              callback_data=f"viewspecial_{item['item_id']}_{user.id}")])
            elif item['item_id'] == 'pluma_azul':
                item_name = "Pluma Azul 🪶"
                keyboard_buttons.append([InlineKeyboardButton("Ver Pluma azul",
                                                              callback_data=f"viewspecial_{item['item_id']}_{user.id}")])
            elif item['item_id'] == 'foto_psiquica':
                item_name = "Foto Psíquica(?) 🖼"
                keyboard_buttons.append([InlineKeyboardButton("Ver Foto Psíquica(?)",
                                                              callback_data=f"viewspecial_{item['item_id']}_{user.id}")])
            else:
                item_name = ITEM_NAMES.get(item['item_id'], 'Objeto')

                if item['item_id'] in PACK_CONFIG:
                    item_name += " 🎴"
                    keyboard_buttons.append([InlineKeyboardButton(f"Abrir {item_name.replace(' 🎴', '')}",
                                                                  callback_data=f"openpack_{item['item_id']}_{user.id}")])

            text += f"🔸️ {item_name} x{item['quantity']}\n"

        if keyboard_buttons:
            keyboard = InlineKeyboardMarkup(keyboard_buttons)

    sent_message = await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
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

        # --- REGISTRO DEL USUARIO EN EL GRUPO ACTUAL (Al abrir sobre) ---
        if message.chat.type in ['group', 'supergroup']:
            db.register_user_in_group(user.id, message.chat.id)

        await message.delete()

        db.remove_item_from_inventory(user.id, item_id, 1)
        opening_message = await context.bot.send_message(
            message.chat_id,
            f"🍀 ¡{user.mention_markdown()} ha abierto un *{ITEM_NAMES.get(item_id)}*! 🍀",
            parse_mode='Markdown'
        )
        pack_config = PACK_CONFIG.get(item_id, {})
        pack_size, is_magic = pack_config.get('size', 3), pack_config.get('is_magic', False)
        pack_results, summary_parts = [], []
        message_ids_to_delete = [opening_message.message_id]

        if is_magic:
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
        else:
            pack_results = [{'data': p, 'is_shiny': s} for p, s, _ in
                            [choose_random_pokemon() for _ in range(pack_size)]]

        for result in pack_results:
            p, s = result['data'], result['is_shiny']
            rarity = get_rarity(p['category'], s)
            try:
                with open(f"Stickers/Kanto/{'Shiny/' if s else ''}{p['id']}{'s' if s else ''}.png",
                          'rb') as sticker_file:
                    msg = await context.bot.send_sticker(chat_id=message.chat_id, sticker=sticker_file)
                    message_ids_to_delete.append(msg.message_id)
                await asyncio.sleep(1.2)
            except RetryAfter as e:
                logger.warning(f"Flood control excedido. Esperando {e.retry_after} segundos.")
                await asyncio.sleep(e.retry_after)
                with open(f"Stickers/Kanto/{'Shiny/' if s else ''}{p['id']}{'s' if s else ''}.png",
                          'rb') as sticker_file:
                    msg = await context.bot.send_sticker(chat_id=message.chat_id, sticker=sticker_file)
                    message_ids_to_delete.append(msg.message_id)
            except Exception as e:
                logger.error(f"Error enviando sticker {p['id']}: {e}")
            p_name, r_emoji = f"{p['name']}{' brillante ✨' if s else ''}", RARITY_VISUALS.get(rarity, '')

            # --- MODIFICADO: NO INCREMENTAMOS EL RANKING MENSUAL AQUÍ ---
            # Solo se incrementa con capturas salvajes y eventos.

            if db.check_sticker_owned(user.id, p['id'], s):
                money = DUPLICATE_MONEY_VALUES.get(rarity, 100)
                db.update_money(user.id, money)
                summary_parts.append(f"🔸 {p_name} {r_emoji} (*{format_money(money)}₽*💰)")
            else:
                db.add_sticker_to_collection(user.id, p['id'], s)
                summary_parts.append(f"🔸🆕 {p_name} {r_emoji}")

        pack_name = ITEM_NAMES.get(item_id, "Sobre")
        vertical_summary = "\n".join(summary_parts)

        final_text = f"📜 Resultado del {pack_name} de {user.mention_markdown()}:\n\n{vertical_summary}"

        await context.bot.send_message(message.chat_id, text=final_text, parse_mode='Markdown')
        if message_ids_to_delete and context.job_queue:
            context.job_queue.run_once(delete_pack_stickers, when=60,
                                       data={'chat_id': message.chat_id, 'sticker_ids': message_ids_to_delete})
        context.chat_data['last_pack_open_time'] = time.time()
    finally:
        context.chat_data['is_opening_pack'] = False
        logger.info(f"Desbloqueo de apertura de sobres para el chat {message.chat_id}.")


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


async def view_special_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts = query.data.split('_')
        owner_id = int(parts[-1])
        item_id = "_".join(parts[1:-1])

        if query.from_user.id != owner_id:
            await query.answer("No puedes ver los objetos de otro usuario.", show_alert=True)
            return

        if item_id == 'pluma_naranja':
            await query.answer(
                "Es una especie de pluma que se calienta rápidamente al exponerla al sol, caída de un ave legendaria de Kanto.",
                show_alert=True)
        elif item_id == 'pluma_amarilla':
            await query.answer(
                "Es una pluma erizada que se carga fácilmente de electricidad estática con solo agitarla, caída de un ave legendaria de Kanto.",
                show_alert=True)
        elif item_id == 'pluma_azul':
            await query.answer("Es una pluma de tacto frío y cristalino, caída de un ave legendaria de Kanto.",
                               show_alert=True)
        elif item_id == 'foto_psiquica':
            await query.answer(
                "Una fotografía hecha con el Álbumdex. Sales tú con cara de asombro y un Pokémon legendario humanoide levitando tras de ti.",
                show_alert=True)
        else:
            await query.answer("Objeto desconocido.", show_alert=True)

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


# --- COMANDO PARA DAR OBJETO A UN USUARIO (ADMIN) ---
async def darobjeto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text("Uso: `/darobjeto [@usuario|ID] <item_id>`")

    try:
        item_id = args[0]
        # Mapeo simple para facilitar nombres largos si fuera necesario, o usar directo
        # Si el admin escribe el nombre exacto del config

        # Verificamos si existe en la tienda o es un objeto especial conocido
        valid_items = list(SHOP_CONFIG.keys()) + ['pluma_naranja', 'pluma_amarilla', 'pluma_azul', 'foto_psiquica',
                                                  'lottery_ticket']

        # Nota: No validamos estrictamente para permitir flexibilidad si añades cosas nuevas,
        # pero avisamos si parece raro.

        msg = " ".join(args[1:])  # Mensaje opcional
        if not msg: msg = "¡Un regalo de la administración!"

        db.add_mail(target_user.id, 'inventory_item', item_id, msg)

        item_name = ITEM_NAMES.get(item_id, item_id)
        await update.message.reply_text(f"✅ Enviado *{item_name}* al buzón de {target_user.mention_markdown()}.",
                                        parse_mode='Markdown')

    except (IndexError, ValueError):
        await update.message.reply_text(
            "Uso: `/darobjeto [@usuario|ID] <item_id> [mensaje opcional]`\nEj: `/darobjeto @pepe pack_small_national`")


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
        if not args: return await update.message.reply_text("Uso: /sendtoall <tipo/id> [args] [mensaje]")

        all_users = db.get_all_user_ids()
        first_arg = args[0].lower()

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
            return await update.message.reply_text(f"Tipo no reconocido: '{first_arg}'.")

        for uid in all_users: db.add_mail(uid, item_type, item_details, message)
        await update.message.reply_text(f"✅ Regalo enviado a los {len(all_users)} jugadores.")
    except (IndexError, ValueError) as e:
        await update.message.reply_text(f"Uso incorrecto: {e}")


async def send_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text(
            "Uso: Responde a un usuario, menciónalo o usa su ID.\n`/sendsticker [@usuario|ID] <poke_id> <shiny 0/1> [mensaje]`")
    try:
        poke_id, is_shiny = int(args[0]), int(args[1])
        message = ' '.join(args[2:]) or "¡Un regalo especial del admin!"
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

        # Incrementar mensual también si el admin lo añade
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
    if not user:
        return
    db.get_or_create_user(user.id, user.first_name)
    # --- REGISTRO POR ACTIVIDAD ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(user.id, update.effective_chat.id)

    money = db.get_user_money(user.id)
    sent_message = await update.message.reply_text(f"Tienes *{format_money(money)}₽* 💰.", parse_mode='Markdown')
    schedule_message_deletion(context, sent_message)
    if update.message:
        schedule_message_deletion(context, update.message)


async def regalar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    if not sender:
        return
    target_user, args = await _get_target_user_from_command(update, context)

    if not target_user:
        await update.message.reply_text(
            "Puedes regalarle a otro jugador parte de tu dinero. Así funciona el comando '/regalar':\n\n"
            "🔹 Responde a un mensaje de la persona y escribe:\n"
            "'/regalar <cantidad>'\n\n"
            "🔹 O bien, menciona a la persona; escribe:\n"
            "'/regalar @usuario <cantidad>'")
        return
    if sender.id == target_user.id:
        await update.message.reply_text("😅 No puedes regalarte dinero a ti mismo.")
        return
    if target_user.is_bot:
        await update.message.reply_text("🤖 No puedes enviarle dinero a un bot.")
        return

    try:
        amount = int(args[0])
        if amount <= 0:
            await update.message.reply_text("¿A quién intentas engañar? 🤨")
            return
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Por favor, especifica una cantidad válida.\nUso: `/regalar [@usuario|ID] <cantidad>`")
        return

    # --- REGISTRO POR ACTIVIDAD (Remitente) ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(sender.id, update.effective_chat.id)

    sender_money = db.get_user_money(sender.id)
    if sender_money < amount:
        msg = await update.message.reply_text(f"No tienes suficiente dinero. Tienes *{format_money(sender_money)}₽*.",
                                              parse_mode='Markdown')
        schedule_message_deletion(context, update.message, 40)
        schedule_message_deletion(context, msg, 40)
        return

    db.get_or_create_user(target_user.id, target_user.first_name)
    db.update_money(sender.id, -amount)
    db.update_money(target_user.id, amount)

    sender_mention = sender.mention_markdown()
    recipient_mention = target_user.mention_markdown()
    msg = await update.message.reply_text(
        f"💸 ¡Transacción completada!\n{sender_mention} le ha enviado a {recipient_mention}: *{format_money(amount)}₽*",
        parse_mode='Markdown'
    )

    # Auto-borrado regalar
    schedule_message_deletion(context, update.message, 40)
    schedule_message_deletion(context, msg, 40)


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
    # --- REGISTRO POR ACTIVIDAD (Quien pregunta) ---
    if update.effective_chat.type in ['group', 'supergroup']:
        db.register_user_in_group(issuer_user.id, update.effective_chat.id)

    capture_chance = db.get_user_capture_chance(user_to_check.id)
    user_mention = user_to_check.mention_markdown()

    if target_user and target_user.id != issuer_user.id:
        text = f"📊 El ratio de captura actual de {user_mention} es del *{capture_chance}%*."
    else:
        text = f"📊 Tu ratio de captura actual es del *{capture_chance}%*."

    await update.message.reply_text(text, parse_mode='Markdown')


async def retos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el progreso de los retos grupales del GRUPO ACTUAL."""
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Este comando solo funciona en grupos.")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # REGISTRAMOS AL USUARIO POR SI ACASO NO LO ESTABA
    db.get_or_create_user(user_id, update.effective_user.first_name)
    db.register_user_in_group(user_id, chat_id)

    # Obtenemos los IDs únicos que tienen los MIEMBROS DE ESTE GRUPO
    # (Usamos la nueva función Anti-Exploit que consulta group_pokedex)
    group_ids = db.get_group_unique_kanto_ids(chat_id)
    total_group = len(group_ids)

    # Calculamos totales por rareza en Kanto (1-151)
    kanto_rarity_totals = {'C': 0, 'B': 0, 'A': 0, 'S': 0}
    for p in ALL_POKEMON:
        if p['id'] <= 151:
            kanto_rarity_totals[p['category']] += 1

    # Calculamos conseguidos por rareza (en este grupo)
    group_rarity_counts = {'C': 0, 'B': 0, 'A': 0, 'S': 0}
    for pid in group_ids:
        p_data = POKEMON_BY_ID.get(pid)
        if p_data:
            group_rarity_counts[p_data['category']] += 1

    text = "🤝 **Retos Grupales** 🤝\n\n"
    text += "🎯 **Objetivo: Conseguir los 151 Pokémon de Kanto AQUÍ**\n"
    text += "_El progreso solo cuenta los Pokémon capturados dentro de este grupo._\n\n"

    rarity_texts = []
    for cat in ['C', 'B', 'A', 'S']:
        emoji = RARITY_VISUALS[cat]
        rarity_texts.append(f"{emoji} {group_rarity_counts[cat]}/{kanto_rarity_totals[cat]}")

    text += ", ".join(rarity_texts) + "\n\n"
    text += f"📊 **Total: {total_group}/151**"

    if total_group >= 151:
        text += "\n\n✅ **¡COMPLETADO!**"

    msg = await update.message.reply_text(text, parse_mode='Markdown')

    # Auto-borrado retos
    schedule_message_deletion(context, update.message, 30)
    schedule_message_deletion(context, msg, 30)


async def clemailbox_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    if target_user:
        changes = db.clear_user_mailbox(target_user.id)
        await update.message.reply_text(
            f"✅ Buzón de {target_user.first_name} limpiado. Se eliminaron {changes} regalos.")
    elif args and args[0].lower() == 'all':
        changes = db.clear_all_mailboxes()
        await update.message.reply_text(
            f"✅ Todos los buzones han sido limpiados. Se eliminaron {changes} regalos en total.")
    else:
        await update.message.reply_text("Uso: `/clemailbox [@usuario|ID]` o `/clemailbox all`")


async def removemail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    try:
        mail_id = int(context.args[0])
        if db.remove_mail_item_by_id(mail_id):
            await update.message.reply_text(f"✅ Regalo con ID `{mail_id}` eliminado correctamente.")
        else:
            await update.message.reply_text(f"ℹ️ No se encontró ningún regalo con el ID `{mail_id}`.")
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Uso: `/removemail <mail_id>`\nPuedes ver la ID del regalo en el comando /buzon.")


async def clearalbum_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)
    if not target_user:
        await update.message.reply_text(
            "Uso: `/clearalbum [@usuario|ID]`\nDebes especificar a quién quieres borrarle el álbum.")
        return
    changes = db.clear_user_collection(target_user.id)
    await update.message.reply_text(
        f"🗑️ ¡Álbumdex de {target_user.first_name} vaciado!\nSe eliminaron {changes} stickers de su colección.")

# --- COMANDOS ADMIN EXTRA ---

async def admin_reset_group_kanto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina todos los Pokémon del reto grupal del grupo actual."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("Este comando debe usarse dentro del grupo que quieres limpiar.")
    
    chat_id = update.effective_chat.id
    db.reset_group_pokedex(chat_id)
    await update.message.reply_text("🗑️ Se ha eliminado todo el progreso del reto grupal en este chat.")

async def admin_check_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saber el dinero de un usuario mencionando un mensaje suyo."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)
    if not target_user:
        return await update.message.reply_text("Uso: Responde a un mensaje del usuario.")
    
    money = db.get_user_money(target_user.id)
    await update.message.reply_text(f"💰 {target_user.first_name} tiene: *{format_money(money)}₽*", parse_mode='Markdown')

async def admin_set_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Establecer una cantidad de monedas fija a un usuario."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    
    if not target_user or not args:
        return await update.message.reply_text("Uso: Responde al usuario y pon `/setmoney <cantidad>`")
    
    try:
        amount = int(args[0])
        db.set_money(target_user.id, amount)
        await update.message.reply_text(f"✅ El dinero de {target_user.first_name} se ha fijado en *{format_money(amount)}₽*.", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Cantidad inválida.")

async def admin_list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver en qué grupos se ha añadido el bot."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    
    groups = db.get_all_groups_info() 
    
    if not groups:
        return await update.message.reply_text("El bot no está registrado en ningún grupo activo.")
    
    text = "📂 **Grupos Activos:**\n\n"
    for g in groups:
        name = g.get('group_name') or "Desconocido"
        text += f"🔹 {name} (ID: `{g['chat_id']}`)\n"
        
    await update.message.reply_text(text, parse_mode='Markdown')

# --- COMANDOS OCULTOS NUEVOS ---

async def admin_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obtiene ID y nombre del usuario respondiendo a su mensaje o mencionándolo."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, _ = await _get_target_user_from_command(update, context)
    
    if not target_user:
        return await update.message.reply_text("Responde a un mensaje o menciona al usuario.")
        
    await update.message.reply_text(f"👤 **Usuario:** {target_user.full_name}\n🆔 **ID:** `{target_user.id}`", parse_mode='Markdown')

async def admin_view_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ve la mochila de un usuario por su ID."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("Uso: `/vermochila <user_id>`")
        
    items = db.get_user_inventory(target_id)
    if not items:
        return await update.message.reply_text(f"🎒 La mochila del usuario `{target_id}` está vacía.", parse_mode='Markdown')
        
    text = f"🎒 **Mochila de {target_id}:**\n\n"
    for item in items:
        name = ITEM_NAMES.get(item['item_id'], item['item_id'])
        text += f"▪️ {name} (ID: `{item['item_id']}`) x{item['quantity']}\n"
        
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quita un objeto de la mochila de un usuario."""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    
    if not target_user or not args:
        return await update.message.reply_text("Uso: `/quitarobjeto <usuario> <item_id> [cantidad]`")
    
    item_id = args[0]
    qty = 1
    if len(args) > 1 and args[1].isdigit():
        qty = int(args[1])
        
    db.remove_item_from_inventory(target_user.id, item_id, qty)
    await update.message.reply_text(f"🗑️ Eliminados {qty}x `{item_id}` de la mochila de {target_user.mention_markdown()}.", parse_mode='Markdown')

async def admin_add_bulk_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Añade múltiples stickers a un usuario. Ejemplo: /addbulk @user 1 4s 7"""
    if not update.effective_user or update.effective_user.id != ADMIN_USER_ID: return
    target_user, args = await _get_target_user_from_command(update, context)
    
    if not target_user or not args:
        return await update.message.reply_text("Uso: `/addbulk @usuario ID [ID_s] ...`\nEj: `/addbulk @Pepe 1 4s 7` (4s = Charmander Shiny)")
    
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
                # NO incrementamos ranking mensual aquí para no romper el competitivo
                added.append(f"{p_data['name']}{'✨' if is_shiny else ''}")
        except ValueError:
            continue
            
    if added:
        await update.message.reply_text(f"✅ Añadidos a {target_user.first_name}:\n" + ", ".join(added))
    else:
        await update.message.reply_text("❌ No se pudo añadir ningún Pokémon.")

# ----------------------------------------------------

async def post_init(application: Application):
    bot = cast(Bot, getattr(application, "bot"))
    user_commands = [
        BotCommand("albumdex", "📖 Revisa tu progreso."),
        BotCommand("tienda", "🏪 Compra sobres de stickers."),
        BotCommand("mochila", "🎒 Revisa tus objetos."),
        BotCommand("tombola", "🎟️ Tómbola diaria"),
        BotCommand("buzon", "💌 Revisa tu buzón."),
        BotCommand("retos", "🤝 Retos Grupales."),
        BotCommand("dinero", "💰 Consulta tu dinero."),
        BotCommand("regalar", "💸 Envía dinero a otro jugador."),
        BotCommand("start", "▶️ Inicia el juego (solo admins)."),
        BotCommand("stopgame", "⏸️ Detiene el juego (solo admins).")
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllGroupChats())
    logger.info("Comandos del bot configurados exitosamente.")


def main():
    # --- NUEVO: Iniciamos el servidor web en un hilo aparte ---
    keep_alive()
    # ---------------------------------------------------------

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Tarea diaria para verificar ranking mensual (se ejecuta cada 24h)
    application.job_queue.run_repeating(check_monthly_job, interval=86400, first=10, name="monthly_ranking_check")

    all_handlers: list[BaseHandler] = [
        # Handler para bienvenida
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
        
        # Nuevos Comandos Admin (Visibles si sabes que existen)
        CommandHandler("resetgroup", admin_reset_group_kanto),
        CommandHandler("checkmoney", admin_check_money),
        CommandHandler("setmoney", admin_set_money),
        CommandHandler("listgroups", admin_list_groups),
        
        # Nuevos Comandos Ocultos (No listados en post_init)
        CommandHandler("getid", admin_get_id),
        CommandHandler("vermochila", admin_view_inventory),
        CommandHandler("quitarobjeto", admin_remove_item),
        CommandHandler("addbulk", admin_add_bulk_stickers),

        CallbackQueryHandler(claim_event_handler, pattern="^event_claim_"),
        CallbackQueryHandler(event_step_handler, pattern=r"^ev\|"),

        CallbackQueryHandler(albumdex_cmd, pattern="^album_main_"),
        CallbackQueryHandler(album_close_handler, pattern="^album_close_"),
        CallbackQueryHandler(album_region_handler, pattern="^album_"),
        CallbackQueryHandler(choose_sticker_version_handler, pattern="^showsticker_"),
        CallbackQueryHandler(send_sticker_handler, pattern="^sendsticker_"),
        CallbackQueryHandler(claim_button_handler, pattern="^claim_"),
        CallbackQueryHandler(claim_mail_handler, pattern="^claimmail_"),
        CallbackQueryHandler(buzon_refresh_handler, pattern="^buzon_refresh_"),
        CallbackQueryHandler(tombola_claim, pattern="^tombola_claim_"),
        CallbackQueryHandler(open_pack_handler, pattern="^openpack_"),
        CallbackQueryHandler(buy_pack_handler, pattern="^buy_"),
        CallbackQueryHandler(tienda_close_handler, pattern="^shop_close_"),
        CallbackQueryHandler(tienda_cmd, pattern="^shop_refresh_"),
        CallbackQueryHandler(missing_sticker_handler, pattern="^missing_sticker$"),
        CallbackQueryHandler(view_ticket_handler, pattern="^viewticket_"),
        CallbackQueryHandler(view_special_item_handler, pattern="^viewspecial_"),
    ]
    application.add_handlers(all_handlers)
    for chat_id in db.get_active_groups():
        # Inicializar el spawn aleatorio en el reinicio
        initial_delay = random.randint(MIN_SPAWN_TIME, MAX_SPAWN_TIME)
        application.job_queue.run_once(spawn_pokemon, initial_delay, chat_id=chat_id, name=f"spawn_{chat_id}")
        logger.info(f"Trabajo de spawn reanudado para el chat activo {chat_id}")
    application.run_polling()


if __name__ == '__main__':
    main()
