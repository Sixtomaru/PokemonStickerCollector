# -*- coding: utf-8 -*-
# events.py
import random
from telegram import User
import database as db
from pokemon_data import POKEMON_BY_ID
from bot_utils import format_money, get_rarity, RARITY_VISUALS, DUPLICATE_MONEY_VALUES

# --- Listas de Pokémon ---
PESCA_RUTA_12_PEQUEÑOS = [7, 54, 60, 61, 72, 90, 98, 99, 116, 117, 118, 119, 120, 121, 129, 138, 139]
PESCA_RUTA_12_GRANDES = [7, 8, 54, 55, 60, 61, 62, 72, 90, 98, 99, 116, 117, 86, 118, 119, 120, 121, 129, 134, 138, 139]
CASINO_TIER_1_POKEMON = [63, 35, 37, 147]
CASINO_TIER_2_POKEMON = [30, 33, 127, 123, 137, 40]
BOSQUE_VERDE_POKEMON = [10, 11, 12, 13, 14, 15, 16, 17, 25]
TUNEL_ROCA_WILD_POKEMON = [41, 42, 74, 104, 66, 67, 95]
TUNEL_ROCA_DOMINGUERAS = {"Neli": 52, "Ariana": 35, "Dora": 36, "Leah": 39, "Marta": 40, "Sofía": 96, "Alma": 97}
TUNEL_ROCA_ITEMS = [{'name': 'Super Ball', 'value': 200, 'weight': 60},
                    {'name': 'Velocidad X', 'value': 300, 'weight': 30},
                    {'name': 'Cura Total', 'value': 400, 'weight': 10}]
TORRE_LAVANDA_GHOSTS = [92, 93]
TORRE_LAVANDA_SPECIAL_GHOST = 105
TORRE_LAVANDA_FLEE_POKEMON = 104
AZULONA_RESTAURANTE_POKEMON_IDS = [123, 68, 122]
AZULONA_HELADO_PREMIOS_VALUES = [100, 200, 400]
ERIKA_GUARD_POKEMON = [71, 114, 45]
KANTO_GRASS_TYPES = [1, 2, 3, 43, 44, 45, 46, 47, 69, 70, 71, 102, 103, 114]
ERIKA_DROPPED_ITEMS = [{'name': 'Antídoto', 'value': 100}, {'name': 'Antiparalizar', 'value': 100},
                       {'name': 'Antiquemar', 'value': 200}, {'name': 'Antihielo', 'value': 200},
                       {'name': 'Despertar', 'value': 200}, {'name': 'Cura Total', 'value': 400}]
DOJO_POKEMON = [107, 106]
GYM_MEDIUM_POKEMON = [79, 80, 122, 64]
GYM_EXORCIST_POKEMON = [92, 93]
GYM_SABRINA_POKEMON = [64, 65, 122, 49]


def _handle_sticker_reward(user_id, user_mention, pokemon_id, is_shiny=False, chat_id=None):
    pokemon_data = POKEMON_BY_ID.get(pokemon_id)
    if not pokemon_data:
        return "Error: No se encontró el Pokémon."

    rarity = get_rarity(pokemon_data['category'], is_shiny)
    pokemon_name = f"{pokemon_data['name']}{' brillante ✨' if is_shiny else ''}"
    rarity_emoji = RARITY_VISUALS.get(rarity, '')

    # --- 1. ACTUALIZAR PROGRESO GRUPAL (Si es en grupo) ---
    if chat_id:
        db.increment_group_monthly_stickers(user_id, chat_id)  # Ranking
        db.add_pokemon_to_group_pokedex(chat_id, pokemon_id)  # Reto 151
    # ------------------------------------------------------

    # --- 2. LÓGICA SMART (1º, 2º, 3º+) ---
    status = db.add_sticker_smart(user_id, pokemon_id, is_shiny)

    if status == 'NEW':
        # Primera vez que lo consigue
        return (f"🎉 ¡Felicidades, {user_mention}! Has conseguido un sticker de "
                f"*{pokemon_name} {rarity_emoji}*. Lo has registrado en tu Álbumdex.")

    elif status == 'DUPLICATE':
        # Segunda vez (se guarda copia para intercambio)
        return (f"♻ ¡Genial, {user_mention}! Conseguiste un sticker de "
                f"*{pokemon_name} {rarity_emoji}*. Como solo tenías 1, te lo guardas para intercambiarlo.")

    else:  # status == 'MAX'
        # Tercera vez o más (se vende)
        money_earned = DUPLICATE_MONEY_VALUES.get(rarity, 100)
        db.update_money(user_id, money_earned)
        return (f"✔️ ¡Genial, {user_mention}! Conseguiste un sticker de "
                f"*{pokemon_name} {rarity_emoji}*. Como ya lo tienes repetido, se convierte en *{format_money(money_earned)}₽* 💰.")

# --- LÓGICA DE EVENTOS (DEFINICIONES DE FUNCIONES) ---

# 1. PESCA
def evento_pesca_ruta_12(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    variant = decision_parts[0]
    choice = decision_parts[1]

    choice_made_text = {
        'vale': 'ℹ️ Decidiste vigilar la caña.',
        'no_puedo': 'ℹ️ Decidiste no hacerlo.',
        'lo_hare': 'ℹ️ Decidiste alquilar la caña.',
        'nah_para_que': 'ℹ️ Decidiste no alquilarla.'
    }.get(choice, "Tomaste una decisión.")

    result_text = ""

    if variant == 'vigilar_caña':
        if choice == 'vale':
            pokemon_id = random.choice(PESCA_RUTA_12_PEQUEÑOS)
            reward_message = _handle_sticker_reward(user_id, user_mention, pokemon_id, False, chat_id)
            result_text = (
                f"🔸{user.first_name} ve cómo el pescador se aleja rápidamente. "
                "Mientras, la caña se mueve; algo está tirando de ella. "
                "Instintivamente, la sujeta con fuerza y tira, mientras gira la manivela.\n\n"
                f"🔸¡{user.first_name} ha pescado un *{POKEMON_BY_ID[pokemon_id]['name']}*!\n\n"
                "Mientras sujeta la caña, coge el Álbumdex y hace una foto con escáner.\n\n"
                "El pescador llega rápidamente y agradece el favor.\n\n"
                f"{reward_message}"
            )
        else:
            pokemon_id = random.choice(PESCA_RUTA_12_GRANDES)
            reward_message = _handle_sticker_reward(user_id, user_mention, pokemon_id, False, chat_id)
            result_text = (
                f"🔸{user.first_name} sigue su camino, no sin antes fijar su mirada sobre el "
                f"*{POKEMON_BY_ID[pokemon_id]['name']}* ayudante del pescador. "
                "Coge su Álbumdex y lo registra con el modo escáner.\n\n"
                f"{reward_message}"
            )
    elif variant == 'alquilar_caña':
        if choice == 'lo_hare':
            costo_caña = 200
            if db.get_user_money(user_id) < costo_caña:
                result_text = ("🔸¡Oh, no! El pescadero te mira el bolsillo y ve que no tienes "
                               "suficiente dinero.\n\n"
                               f"🔸*Necesitas {format_money(costo_caña)}₽* y no quieres quedar mal. "
                               "Mejor seguir tu camino...")
            else:
                db.update_money(user_id, -costo_caña)
                pokemon_id = random.choice(PESCA_RUTA_12_PEQUEÑOS)
                reward_message = _handle_sticker_reward(user_id, user_mention, pokemon_id, False, chat_id)
                result_text = (f"🔸{user.first_name} va con la caña a la zona de pescadores, "
                               "coloca el cebo, "
                               "lanza lejos el anzuelo, y... ... ... \n ¡oh, un "
                               f"*{POKEMON_BY_ID[pokemon_id]['name']}* ha picado!\n\n"
                               f"🔸{user.first_name} le hace una foto con escáner y lo devuelve al agua.\n\n"
                               f"{reward_message}")
        else:
            result_text = (f"🔸{user.first_name} pensó que sería una pérdida de tiempo y dinero, "
                           "por lo que siguió disfrutando del camino y la brisa fluvial.")

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# 2. CASINO
def _get_casino_sale_variant(user):
    all_pokemon_for_sale = CASINO_TIER_1_POKEMON + CASINO_TIER_2_POKEMON
    selected_ids = random.sample(all_pokemon_for_sale, 3)
    offer_texts = []
    buttons = []
    for poke_id in selected_ids:
        price = random.choice([100, 200, 300]) if poke_id in CASINO_TIER_1_POKEMON else random.choice(
            [300, 400, 500, 600])
        name = POKEMON_BY_ID[poke_id]['name']
        offer_texts.append(f"🔴 {name} ({price}₽)")
        buttons.append({'text': name, 'callback_data': f'ev|casino_rocket|decision|buy_pokemon|{poke_id}|{price}'})
    text = (
            f"_Evento aceptado por {user.first_name}_\n\n"
            f"🔸{user.first_name} se encuentra en Ciudad Azulona, caminando cerca del Casino Rocket... A la entrada, un empleado con traje negro y gafas de sol le sonríe:\n\n"
            "💬 *Eh, tú. Tengo algo que podría interesarte… pokémon bastante raros, ¿Quieres echar un vistazo?*\n\n"
            "🔸El hombre abre un maletín, y dentro hay tres Poké Balls junto a los nombres de tres pokémon:\n"
            + ", ".join(offer_texts))
    keyboard = [buttons,
                [{'text': 'No comprar nada', 'callback_data': 'ev|casino_rocket|decision|buy_pokemon|no_buy|0'}]]
    return {'text': text, 'keyboard': keyboard}


def evento_casino_rocket(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    variant = decision_parts[0]
    choice = decision_parts[1]
    text = ""
    keyboard = []
    separator = "\n\n" + "—" * 20 + "\n\n"

    if variant == 'buy_pokemon':
        poke_id_str = choice
        price_str = decision_parts[2] if len(decision_parts) > 2 else '0'
        if poke_id_str == 'no_buy':
            choice_made_text = "ℹ️ Decidiste no comprar nada."
            text = (f"_{choice_made_text}_\n\n"
                    "🔸El hombre suspira con un gesto de decepción.\n"
                    "💬 *Tú te lo pierdes, amigo. Si te arrepientes, estaré por aquí.*")
            return {'text': original_text + separator + text}
        try:
            poke_id = int(poke_id_str)
            price = int(price_str)
            poke_name = POKEMON_BY_ID[poke_id]['name']
        except (ValueError, KeyError):
            return {'text': original_text + separator + "Error: Opción no válida."}
        choice_made_text = f"ℹ️ Decidiste comprar a {poke_name} por {price}₽."
        if db.get_user_money(user_id) < price:
            text = (f"🔸Intentas comprar el Pokémon, pero al buscar en tus bolsillos te das cuenta de que no tienes "
                    f"suficiente dinero. Necesitas *{format_money(price)}₽*.\n\n"
                    "🔸El hombre del traje te mira con desdén y cierra el maletín.")
            return {'text': original_text + separator + text}
        db.update_money(user_id, -price)
        reward_message = _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)
        text = (f"_{choice_made_text}_\n\n"
                "🔸El empleado se despide con una amplia sonrisa: 💬 *Gracias por tu compra, si te pasas otro día, tendremos especímenes diferentes.*\n\n"
                f"{reward_message}")
        return {'text': original_text + separator + text}

    elif variant == 'claw_machine':
        current_attempts = int(decision_parts[2])
        base_text = original_text.split(separator)[0]
        if choice == 'no_play':
            choice_made_text = "ℹ️ Decidiste no jugar."
            db.update_money(user_id, 200)
            text = (f"_{choice_made_text}_\n\n"
                    f"🔸{user.first_name} procede a continuar su camino, pero, al mirar en el suelo, junto a la máquina…\n"
                    "💰 ¡Encuentra *200₽*!")
            return {'text': base_text + separator + text}
        if choice == 'stop':
            text = f"🔸Decides que ya has tenido suficiente por hoy y te alejas de la máquina."
            return {'text': base_text + separator + text}
        if choice == 'play':
            cost = 200
            if db.get_user_money(user_id) < cost:
                text = (
                    f"🔸Buscas en tus bolsillos y te das cuenta de que no tienes los *{format_money(cost)}₽* necesarios para jugar, por lo que te quedas con las ganas...\n\n"
                    )
                return {'text': base_text + separator + text}
            db.update_money(user_id, -cost)
            current_attempts += 1
            initial_text = f"_Decidiste jugar (Intento {current_attempts}/3)._\n\n"
            if random.random() < 0.02:
                win_msg = "🔸El gancho baja y... agarra con fuerza el sobre y lo lleva hasta la caja de premios, pero, al soltarlo, notas que ha caído algo más: ¡han caído dos sobres en lugar de uno! 💬 *¡¡Premio doble!!*"
                db.add_item_to_inventory(user_id, 'pack_small_national', 2)
                text = initial_text + win_msg + f"\n\n🎉 ¡{user_mention} ha conseguido dos Sobres Pequeños de Kanto!"
            elif random.random() < 0.25:
                win_msgs = [
                    "🔸El gancho baja y... agarra fuertemente el sobre, y lo deposita sobre el cajón de premios 💬 *¡Toma ya!*",
                    "🔸El gancho baja y... agarra fuertemente el sobre, pero de camino lo deja caer, sin embargo, rebota y cae en el cajón de premios 💬 *¡Toma, vaya potra!*",
                    "🔸El gancho baja y... agarra el sobre. Mientras está subiendo, el gancho se tambalea tanto, que el sobre comienza a dar saltos de un lado a otro. Sin embargo logra aguantar hasta el cajón de premios. 💬 *¡Sííííí!*"
                ]
                db.add_item_to_inventory(user_id, 'pack_small_national', 1)
                text = initial_text + random.choice(
                    win_msgs) + f"\n\n🎉 ¡{user_mention} ha conseguido un Sobre Pequeño de Kanto!"
            else:
                if current_attempts == 3:
                    fail_msg = (
                        "🔸Pulsas el botón y el gancho baja. Por unos segundos, sientes cómo todo va, como a cámara lenta. Quedas mirando el gancho fijamente, aguantando la respiración, sientes que si bajas la atención un segundo, todo estará perdido. Notas una presión alrededor, tu cerebro te hace pensar que hay miradas de personas que llegan de todas direcciones, todas puestas sobre ti. No puedes fallar. La garra metálica se cierra, y mientras sube, los sobres se deslizan entre sus dedos, como el agua escapa cuando alguien intenta atraparla con las manos. Al subir, lo único que queda entre sus protuberancias ferrosas, es aire y tu frustración, que es casi palpable. Cansado por la estresante situación, lo único que alcanzas a decir es:\n 💬 *Si lo sé, ni vengo.*")
                    text = initial_text + fail_msg
                else:
                    fail_msgs = [
                        "🔸El gancho baja y... vuelve a subir sin ejercer la mínima presión. 💬 *¡Menuda estafa!*",
                        "🔸El gancho baja y... agarra el sobre con fuerza, pero lo ha dejado caer en cuanto ha subido 💬 *La máquina está calentita, debo estar cerca de conseguir el premio... creo.*",
                        "🔸El gancho baja y... agarra el sobre con fuerza y lo desplaza hacia el cajón de premios, pero cae por el camino 💬 *¡Aaaah, casi!*",
                        "🔸El gancho baja y... vuelve a subir sin ejercer la mínima presión. 💬 *Ahí van 200₽ a la basura...*",
                        "🔸El gancho baja y... vuelve a subir sin ejercer la mínima presión. 💬 *Espero que la próxima vaya mejor...*"
                    ]
                    text = initial_text + random.choice(fail_msgs)
                    keyboard = [[{'text': 'Volver a jugar',
                                  'callback_data': f'ev|casino_rocket|decision|claw_machine|play|{current_attempts}'},
                                 {'text': 'Dejar de jugar',
                                  'callback_data': f'ev|casino_rocket|decision|claw_machine|stop|{current_attempts}'}]]
            return {'text': base_text + separator + text, 'keyboard': keyboard}
    return {'text': "Error en el evento del casino."}


# 3. BOSQUE VERDE
def _get_bosque_verde_variant(user: User):
    if random.random() < 0.5:
        text = f"_Evento aceptado por {user.first_name}_\n\n🔸{user.first_name} pasea por el Bosque Verde, cuando un destello en el suelo llama su atención. Parece que alguien ha perdido algo...\n\n"
        if random.random() < 0.05:
            db.add_item_to_inventory(user.id, 'pack_small_national')
            text += "¡Anda, es un Sobre Pequeño Nacional! ¡Lo guardas en la mochila!"
        else:
            money_found = random.choice([100, 200, 300])
            db.update_money(user.id, money_found)
            text += f"¡Anda, son *{format_money(money_found)}₽* 💰!"
    else:
        text = f"_Evento aceptado por {user.first_name}_\n\n🔸Mientras {user.first_name} se distrae con el canto y revoloteo de los Pidgey en las copas de los árboles del Bosque Verde, sin darse cuenta, se topa con algo en el camino...\n\n"
        poke_id = random.choice(BOSQUE_VERDE_POKEMON)
        poke_name = POKEMON_BY_ID[poke_id]['name']
        text += f"¡Es un *{poke_name}*!\n\n"
        text += "Rápidamente, saca su Álbumdex y escanea al Pokémon antes de que huya.\n\n"
        # OJO: Los eventos de inicio directo no pasan por 'action', así que no tienen chat_id
        # Para que sume, habría que cambiar la estructura del bot.py para pasar chat_id a 'get_text_and_keyboard'
        # Por ahora, usamos una solución parcial:
        text += _handle_sticker_reward(user.id, user.mention_markdown(), poke_id, False, None)
    return {'text': text}


# 4. TUNEL ROCA
def _get_tunel_roca_variant(user: User):
    if random.random() < 0.5:
        dominguera_name, poke_id = random.choice(list(TUNEL_ROCA_DOMINGUERAS.items()))
        poke_name = POKEMON_BY_ID[poke_id]['name']
        text = (
            f"_Evento aceptado por {user.first_name}_\n\n"
            f"🔸{user.first_name} se adentra en la completa oscuridad del Túnel Roca. El aire es frío y húmedo.\n"
            "🔸De repente, el Álbumdex vibra con una llamada entrante. ¡Es Amelia!\n\n"
            f"💬 *¡{user.first_name}!, tu Álbumdex me indica que estás cerca del Túnel Roca, ¿es correcto?\n Estoy recibiendo la señal de auxilio de una entrenadora perdida dentro del túnel. Es la Dominguera {dominguera_name}. Al parecer, a su {poke_name} se le han agotado los PP de Destello y no puede salir. Te mando las coordenadas.*\n\n"
            f"🔸Siguiendo las instrucciones de Amelia, {user.first_name} utiliza su Álbumdex en modo linterna, encuentra a la asustada entrenadora y la acompaña a la salida.\n\n"
            f"💬 *¡Oh, muchas gracias! Veo que tienes un Álbumdex; como agradecimiento, dejaré que escanees y registres a {poke_name}*."
        )
        keyboard = [[
            {'text': '¡Vale!', 'callback_data': f'ev|tunel_roca|decision|vale|{poke_id}'},
            {'text': 'No hace falta', 'callback_data': f'ev|tunel_roca|decision|no_hace_falta|{poke_id}'}
        ]]
        return {'text': text, 'keyboard': keyboard}
    else:
        poke_id = random.choice(TUNEL_ROCA_WILD_POKEMON)
        poke_name = POKEMON_BY_ID[poke_id]['name']
        text = (
            f"_Evento aceptado por {user.first_name}_\n\n"
            f"🔸{user.first_name} se adentra en la completa oscuridad del Túnel Roca. A duras penas, avanza con el modo linterna de su Álbumdex.\n\n"
            "En un descuido, choca contra algo, haciéndole perder el equilibrio.\n\n"
            f"Un gruñido resuena en la oscuridad... Rápidamente, {user.first_name} apunta en dirección al sonido con la luz del Álbumdex.\n ¡Es un *{poke_name}* salvaje!\n\n"
            "Pone el modo escáner antes de que el Pokémon se vaya.\n\n"
        )
        text += _handle_sticker_reward(user.id, user.mention_markdown(), poke_id, False, None)
        return {'text': text}


def evento_tunel_roca(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    poke_id = int(decision_parts[1])
    choice_made_text = ""
    dominguera_name = "la Dominguera"
    for name, p_id in TUNEL_ROCA_DOMINGUERAS.items():
        if p_id == poke_id:
            dominguera_name = name
            break
    result_text = ""

    if choice == 'vale':
        choice_made_text = "ℹ️ Elegiste escanearlo."
        result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)
    else:
        choice_made_text = "ℹ️ Elegiste no hacerlo."
        chosen_item = random.choices(TUNEL_ROCA_ITEMS, weights=[item['weight'] for item in TUNEL_ROCA_ITEMS], k=1)[0]
        item_name = chosen_item['name']
        item_value = chosen_item['value']
        db.update_money(user_id, item_value)
        result_text += "💬 *Al menos deja que te dé algo.*\n\n"
        result_text += f"🔸 Antes de poder reaccionar, tienes en las manos un *{item_name}* que te ha dado {dominguera_name} antes de irse.\n\n"
        result_text += f"{user.first_name} no sabe muy bien qué hacer con el objeto, así que lo vende, pensando que le será más útil el dinero.\n\n"
        result_text += f"🔸️ Recibes *{format_money(item_value)}₽* 💰."

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# 5. TORRE LAVANDA
def _get_torre_lavanda_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔸{user.first_name} se adentra en la espeluznante Torre Pokémon de Pueblo Lavanda. "
        "Mientras sube las escaleras, la niebla y un aire helado le hace tener escalofríos.\n\n"
        "De repente, una figura espectral aparece flotando justo enfrente...")
    if random.random() < 0.80:
        pokemon_id = random.choice(TORRE_LAVANDA_GHOSTS)
    else:
        pokemon_id = TORRE_LAVANDA_SPECIAL_GHOST
    keyboard = [[
        {'text': 'Escanear', 'callback_data': f'ev|torre_lavanda|decision|scan|{pokemon_id}'},
        {'text': 'Huir', 'callback_data': f'ev|torre_lavanda|decision|flee|{pokemon_id}'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_torre_lavanda(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    pokemon_id = int(decision_parts[1])
    choice_made_text = ""
    result_text = ""

    if choice == 'scan':
        choice_made_text = "ℹ️ Decidiste escanearlo."
        if pokemon_id == TORRE_LAVANDA_SPECIAL_GHOST:
            result_text += "🔸 Apuntas con el Álbumdex y, después de un rato, logras escanear al fantasma antes de que se desvanezca en la niebla. ¡Has registrado un *Marowak*! ¿Qué?, ¿habrá escaneado mal?...\n\n"
            result_text += _handle_sticker_reward(user_id, user_mention, TORRE_LAVANDA_SPECIAL_GHOST, False, chat_id)
        else:
            result_text += f"🔸 Apuntas con el Álbumdex y, después de un rato, logras escanear al fantasma antes de que se desvanezca en la niebla. ¡Has registrado un *{POKEMON_BY_ID[pokemon_id]['name']}*!\n\n"
            result_text += _handle_sticker_reward(user_id, user_mention, pokemon_id, False, chat_id)
    else:
        choice_made_text = "ℹ️ Decidiste huir de allí."
        money_reward = 100
        result_text += "🔸 Baja rápidamente las escaleras y ve que hay algo en el primer peldaño.\n\n"
        result_text += f"Al enfocar con la linterna del Álbumdex, ve a un pequeño y triste *Cubone*. Se pregunta qué hace solo en un sitio como ese. Se agacha y lo agarra entre tus brazos; pero en ese momento ve entre la niebla una silueta humana, diciendo cosas ininteligibles.\nDe repente desaparece y {user.first_name} siente un escalofrío por la espalda, por lo que decide salir de allí inmediatamente.\nLleva al Cubone al Centro Pokémon, y las enfermeras le cuentan que no está perdido, que vive allí en la Torre Pokémon, que ellas se encargan de cuidarlo.\n\n"
        result_text += "Antes de irte, escaneas al pequeño Pokémon.\n\n"
        result_text += "Cuando vas a salir, notas algo en la espalda; es una enfermera quitándote un Amuleto que tenías pegado. 💬 *Ten cuidado con los exorcistas* - te dice con una sonrisa.\n\n"
        result_text += _handle_sticker_reward(user_id, user_mention, TORRE_LAVANDA_FLEE_POKEMON, False, chat_id)
        db.update_money(user_id, money_reward)
        result_text += f"\n🔸 Además, ¡recibes *{format_money(money_reward)}₽* 💰 al vender el Amuleto!"

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# 6. CIUDAD AZULONA
def _get_ciudad_azulona_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔸 {user.first_name} va paseando por Ciudad Azulona. Puede notar el aroma de la comida de varios establecimientos cercanos.\nJusto enfrente, tiene dos opciones que le llaman la atención: un restaurante con una pinta increíble o un puesto de helados artesanales.\nPiensa que es muy pronto para comer, pero quizá tarde para el helado, por lo que, tarda un poco en elegir:")
    keyboard = [[
        {'text': 'Restaurante', 'callback_data': 'ev|ciudad_azulona|decision|restaurante'},
        {'text': 'Helado', 'callback_data': 'ev|ciudad_azulona|decision|helado'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_ciudad_azulona(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    if choice == 'helado':
        choice_made_text = "ℹ️ Decidiste tomar un helado."
        premio = random.choice(AZULONA_HELADO_PREMIOS_VALUES)
        db.update_money(user_id, premio)

        if premio == 100:
            result_text = "🔸 Se decide por un clásico. Elige un helado de dos bolas: una de fresas silvestres y otra de moras. La mezcla de los trozos de fruta con la leche congelada, le parece simplemente deliciosa.\nCuando está a punto de sentarse en un banco, ve algo brillar entre unos arbustos. Se acerca y encuentra una Poké Ball. Piensa que no es algo que vaya a necesitar, así que decide venderla más tarde en el Centro Comercial.\n\n¡Obtienes *100₽* 💰!"
        elif premio == 200:
            result_text = "🔸 Se decide por un Milk shake de durazno. El sabor de la leche mezclado con el dulzor del durazno maduro, le parece una combinación cremosa y frutal increíble. Mientras lo disfruta, nota que algo brilla en el suelo. Se acerca y encuentra una Super Ball. No es algo que necesite, así que decide venderla en el Centro Comercial.\n\n¡Obtienes *200₽* 💰!"
        else:
            result_text = "🔸Se decide por un Melonpan helado. El pan, cuidadosamente calentado, hace contraste con el delicioso helado de vainilla de su interior. El azúcar glaseado por encima invita a seguir comiendo con el crujido de cada bocado.\nDe pronto, algo frena su instinto voraz: ve que algo reluce entre unos arbustos.\nSe acerca y encuentra una Ultra Ball. Decide que no es algo que vaya a utilizar, por lo que, al terminar el helado, la vende en el Centro Comercial.\n\n¡Obtienes *400₽* 💰!"

    elif choice == 'restaurante':
        choice_made_text = "ℹ️ Decidiste entrar en el restaurante."
        pokemon_id = random.choice(AZULONA_RESTAURANTE_POKEMON_IDS)
        if pokemon_id == 123:
            result_text = "🔸 Entra en el restaurante. Se sienta y pide la comida. Un camarero le sirve un plato de yakisoba recién hecho. Mientras come, se fija en la cocina y ve a un Scyther moviendo sus guadañas a una velocidad increíble, ¡está ayudando a cortar los ingredientes!\nDisimuladamente, saca su Álbumdex y lo escanea."
        elif pokemon_id == 68:
            result_text = "🔸Entra en el restaurante. Se sienta y pide la comida: una pizza de champiñones, queso vegano y tofu. Mientras espera, ve a un imponente Machamp en la cocina usando sus cuatro brazos para fregar, secar y colocar los platos a la vez, con una eficiencia asombrosa.\nDisimuladamente, saca su Álbumdex y lo escanea."
        else:
            result_text = "🔸 Entra en el restaurante y pide un entrante: unas croquetas Pikachu; pequeñas bolitas crujientes de queso y patata decoradas estilo Pikachu.\nEscucha algo a su lado, es un Mr. Mime agarrando algo invisible y zarandeándolo de un lado para el otro. Parece que hace como que barre el restaurante, pero realmente lo está haciendo. 💭 ¿Será por sus poderes psíquicos?\nDisimuladamente, saca su Álbumdex y lo escanea."
        result_text += "\n\n" + _handle_sticker_reward(user_id, user_mention, pokemon_id, False, chat_id)

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# 7. ERIKA
def _get_erika_nap_variant(user: User):
    if random.random() < 0.5:
        guard_poke_id = random.choice(ERIKA_GUARD_POKEMON)
        guard_poke_name = POKEMON_BY_ID[guard_poke_id]['name']
        text = (
            f"_Evento aceptado por {user.first_name}_\n\n"
            f"🔸{user.first_name} camina por los jardines cercanos al Gimnasio de Ciudad Azulona y le vienen olores de todo tipo de flores.\n\n"
            f"A lo lejos, en un banco, ve a la líder Erika aparentemente durmiendo plácidamente mientras toma el sol. A su lado, inmóvil, hay un imponente *{guard_poke_name}* haciendo lo mismo.\n\n"
            f"{user.first_name} aprovecha que están distraídos para sacar el Álbumdex y escanearlo.\n\n"
        )
        text += _handle_sticker_reward(user.id, user.mention_markdown(), guard_poke_id, False, None)
        return {'text': text}
    else:
        text = (
            f"_Evento aceptado por {user.first_name}_\n\n"
            f"🔸{user.first_name} camina por los jardines cercanos al Gimnasio de Ciudad Azulona y le vienen olores de todo tipo de flores.\n\n"
            f"A lo lejos, en un banco, ve a la líder Erika aparentemente durmiendo plácidamente mientras toma el sol. {user.first_name} nota que hay un objeto cerca del banco, en el suelo. Lo recoge y piensa qué hacer con él:\n\n"
            f"-¿La despierto y le pregunto si es suyo?\n"
            f"-¿Lo dejo en el banco para cuando despierte?\n"
            f"-¿Me lo llevo? probablemente no sea suyo..."
        )
        keyboard = [[
            {'text': 'Despertarla', 'callback_data': 'ev|erika_nap|decision|wake_up'},
            {'text': 'Dejarlo', 'callback_data': 'ev|erika_nap|decision|leave_it'},
            {'text': 'Llevártelo', 'callback_data': 'ev|erika_nap|decision|take_it'}
        ]]
        return {'text': text, 'keyboard': keyboard}


def evento_erika_nap(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    if choice == 'wake_up':
        choice_made_text = "ℹ️ Decidiste despertarla."
        poke_id = random.choice(KANTO_GRASS_TYPES)
        result_text = (
            "🔸💬 *Disculpa... creo que esto es tuyo.*\n\n"
            "Erika abre los ojos lentamente, aún adormilada.\n\n"
            "💬 *Ah... sí. Me habré quedado dormida... Muchas gracias.*\n\n"
            "Después de un rato mirándote, todavía adormecida, se fija en algo que llevas.\n\n"
            "💬 *Anda, llevas un Álbumdex. Yo también adoro coleccionar stickers, sobre todo los de tipo Planta. Por favor, acepta esto como agradecimiento.*\n\n"
            "¡Erika te entrega una pegatina de su colección personal!\n\n"
        )
        result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)

    elif choice == 'leave_it':
        choice_made_text = "ℹ️ Decidiste dejarlo en el banco."
        base_text = (
            f"🔸{user.first_name} decide no molestarla. Cuidadosamente, coloca el objeto a su lado, para que lo vea en cuanto despierte.\n\n"
        )
        if random.random() < 0.5:
            better_grass_types = [pid for pid in KANTO_GRASS_TYPES if POKEMON_BY_ID[pid]['category'] != 'C']
            if not better_grass_types: better_grass_types = KANTO_GRASS_TYPES
            poke_id = random.choice(better_grass_types)
            result_text = base_text + (
                "En ese momento, Erika despierta y mira adormilada cómo le estás dejando el objeto a su lado.\n\n"
                "💬 *¿Esto es para mí? —dijo Erika mirando el objeto fijamente— ¡Ah, si es mío!, debe habérseme caído mientras descansaba, ¡Muchas gracias por tu generosidad!*\n\n"
                "De pronto se fija en un objeto que llevas.\n\n"
                "💬 *Anda, llevas un Álbumdex. Yo también adoro coleccionar stickers, sobre todo los de tipo Planta. Por favor, acepta esto como agradecimiento.*\n\n"
                "¡Erika te entrega una pegatina de su colección personal!\n\n"
            )
            result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)
        else:
            result_text = base_text + (
                f"🔸{user.first_name} se va satisfecho, pensando que ha hecho una buena acción."
            )

    elif choice == 'take_it':
        choice_made_text = "ℹ️ Decidiste llevártelo."
        item = random.choice(ERIKA_DROPPED_ITEMS)
        db.update_money(user_id, item['value'])
        result_text = (
            f"¡Es un *{item['name']}*!\n\n"
            f"🔸{user.first_name} pensó que el objeto no era de Erika, y lo llevó a vender en el centro comercial.\n\n"
            f"¡Obtienes *{format_money(item['value'])}₽* 💰!"
        )

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# 8. LOTERÍA
def _get_loteria_azafran_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔸{user.first_name} llega a la bulliciosa estación del Magnetotrén, en Ciudad Azafrán. Entre la multitud, ve un mostrador muy colorido con un cartel que indica: 'LOTERÍA'.\n\n"
        "Un amable lotero exclama:\n"
        "💬 *¡Compre su billete de lotería aquí, sabrá si ha ganado al instante!*"
    )
    keyboard = [[
        {'text': 'Comprar (100₽)', 'callback_data': 'ev|lottery_azafran|decision|play'},
        {'text': 'Mejor no', 'callback_data': 'ev|lottery_azafran|decision|no_play'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_loteria_azafran(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]

    if choice == 'no_play':
        choice_made_text = "ℹ️ Decidiste no jugar."
        text = f"🔸{user.first_name} decide que es mejor guardar el dinero y se aleja del mostrador."
        separator = "\n\n" + "—" * 20 + "\n\n"
        return {'text': original_text + separator + f"_{choice_made_text}_\n\n{text}"}

    # Lógica de jugar
    cost = 100
    if db.get_user_money(user_id) < cost:
        choice_made_text = "ℹ️ Intentaste comprar un billete."
        text = f"🔸Buscas en tus bolsillos pero no tienes suficientes monedas. Necesitas *{format_money(cost)}₽*."
        separator = "\n\n" + "—" * 20 + "\n\n"
        return {'text': original_text + separator + f"_{choice_made_text}_\n\n{text}"}

    db.update_money(user_id, -cost)
    user_num_int = random.randint(0, 9999)
    win_num_int = random.randint(0, 9999)
    user_num_str = f"{user_num_int:04}"
    win_num_str = f"{win_num_int:04}"

    base_text = (
        f"ℹ️ Decidiste probar suerte.\n\n"
        f"🔸{user.first_name} paga *100₽* y recibe su billete impreso al instante.\n"
        f"🎫 **Tu Número:** `{user_num_str}`\n\n"
        f"En una pantalla del establecimiento, los números comienzan a aparecer uno a uno...\n"
        f"🖥 **Número Ganador:** `{win_num_str}`\n\n"
        f"{user.first_name} compara los números...\n\n"
    )
    result_text = ""
    if user_num_str == win_num_str:
        prize = 50000
        db.update_money(user_id, prize)
        ticket_item_id = f"lottery_ticket_{user_num_str}"
        db.add_item_to_inventory(user_id, ticket_item_id, 1)
        result_text = (
            "🔸🚨 *¡¡ALARMA DE GANADOR!!* 🚨\n"
            "¡¡Los números son idénticos!! ¡¡Has ganado el premio gordo!!\n"
            "Toda la estación aplaude mientras el vendedor te entrega el gran premio.\n\n"
            f"¡Recibes *{format_money(prize)}₽* 💰!\n"
            "🏆 *Has guardado el Ticket de lotería ganador en tu mochila.*"
        )
    elif user_num_str[-3:] == win_num_str[-3:]:
        prize = 15000
        db.update_money(user_id, prize)
        result_text = (
            "🔸¡¡Enhorabuena!! ¡Las tres últimas cifras coinciden!\n"
            "💬 *¡Eso sí que es suerte!*\n\n"
            f"¡Recibes *{format_money(prize)}₽* 💰!"
        )
    elif user_num_str[-2:] == win_num_str[-2:]:
        prize = 4000
        db.update_money(user_id, prize)
        result_text = (
            "🔸¡Las dos últimas cifras coinciden!\n"
            "💬 *¡No está mal! Aquí tienes un pequeño premio.*\n\n"
            f"¡Obtienes *{format_money(prize)}₽* 💰!"
        )
    elif user_num_str[-1] == win_num_str[-1]:
        prize = 500
        db.update_money(user_id, prize)
        result_text = (
            "🔸¡La última cifra coincide!\n"
            "💬 *¡Bien!, al menos recuperas tu dinero y te llevas un extra.*\n\n"
            f"¡Obtienes *{format_money(prize)}₽* 💰!"
        )
    else:
        result_text = (
            "🔸Los números no coinciden ni en la terminación.\n"
            "💬 *¡Vaya, la próxima vez habrá más suerte! —dice el vendedor.*"
        )

    separator = "\n\n" + "—" * 20 + "\n\n"
    return {'text': original_text + separator + base_text + result_text}


# 9. DOJO
def _get_dojo_azafran_variant(user: User):
    poke_id = random.choice(DOJO_POKEMON)
    poke_name = POKEMON_BY_ID[poke_id]['name']

    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔸{user.first_name} camina por las calles de Ciudad Azafrán y pasa por delante del antiguo Dojo Karate.\n\n"
        f"A través de una ventana, puede ver al Maestro Karateka entrenando intensamente, lanzando patadas y puñetazos al aire en perfecta sincronía con su *{poke_name}*.\n\n"
        f"{user.first_name} duda si sacar el Álbumdex para intentar registrar al Pokémon a escondidas..."
    )

    keyboard = [[
        {'text': 'Escanear', 'callback_data': f'ev|dojo_azafran|decision|scan|{poke_id}'},
        {'text': 'Seguir caminando', 'callback_data': 'ev|dojo_azafran|decision|walk'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_dojo_azafran(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    if choice == 'scan':
        choice_made_text = "ℹ️ Decidiste escanearlo."
        poke_id = int(decision_parts[1])
        result_text = (
            f"🔸{user.first_name} saca rápidamente el Álbumdex, aprovecha el descanso del Pokémon para escanearlo y huye de allí antes de ser visto.\n\n"
        )
        result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)

    elif choice == 'walk':
        choice_made_text = "ℹ️ Decidiste seguir caminando."

        base_text = (
            f"🔸{user.first_name} prefiere no interrumpir el entrenamiento y continúa caminando hasta llegar a la puerta del Gimnasio de Ciudad Azafrán.\n"
            "Justo cuando va a pasar de largo, las puertas automáticas se abren y "
        )

        variant = random.choice(['medium', 'exorcist', 'sabrina'])

        if variant == 'medium':
            poke_id = random.choice(GYM_MEDIUM_POKEMON)
            poke_name = POKEMON_BY_ID[poke_id]['name']
            result_text = base_text + (
                f"sale una Médium seguida fielmente de su *{poke_name}*.\n\n"
                f"{user.first_name} escanea al pokémon disimuladamente.\n\n"
            )
            result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)

        elif variant == 'exorcist':
            poke_id = random.choice(GYM_EXORCIST_POKEMON)
            poke_name = POKEMON_BY_ID[poke_id]['name']
            result_text = base_text + (
                f"sale un Exorcista murmurando oraciones, seguido de su *{poke_name}*, que va flotando alrededor suya.\n"
                f"{user.first_name} aprovecha y apunta con el Álbumdex al pokémon y lo registra.\n\n"
            )
            result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)

        elif variant == 'sabrina':
            poke_id = random.choice(GYM_SABRINA_POKEMON)
            poke_name = POKEMON_BY_ID[poke_id]['name']
            result_text = base_text + (
                f"sale la líder Sabrina rodeada de gente. Su presencia impone respeto, pero parece muy popular entre la multitud.\n\n"
                f"Su *{poke_name}* hace de guardaespaldas y la protege con sus poderes psíquicos. {user.first_name} se mimetiza entre la gente, consigue escanear al pokémon con su Álbumdex, y de paso hace algunas fotos a Sabrina.\n\n"
            )
            result_text += _handle_sticker_reward(user_id, user_mention, poke_id, False, chat_id)

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# --- NUEVO EVENTO: MISIÓN RESCATE MEOWTH ---
def _get_mision_meowth_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔸{user.first_name} está caminando tranquilamente cuando su Álbumdex empieza a vibrar. ¡Es una llamada de Amelia!\n"
        f"💬 *¡Hola! ¿{user.first_name}? Tengo una misión. Hay una anciana cerca del lugar que necesita ayuda; su Meowth se ha subido a un árbol muy alto y no sabe bajar. He enviado un Pidgeotto de la reserva al Centro Pokémon más cercano para que te sirva de apoyo. ¡Cuento contigo!*\n\n"
        f"🔸{user.first_name} recoge al Pidgeotto y llega al lugar. El árbol es grande, y el Meowth maúlla asustado mientras se aferra a una rama.\n\n"
        f"{user.first_name} piensa detenidamente cómo intervenir:\n"
        "-¿Intento subir yo?, el Pidgeotto podría ayudarme de alguna manera...\n"
        "-Mejor envío al Pidgeotto y que lo baje él... ¿no?\n"
        "-¿Y si monto en Pidgeotto y lo bajamos entre los dos? tiene Vuelo..."
    )
    keyboard = [[
        {'text': 'Subir yo', 'callback_data': 'ev|mision_meowth|decision|climb'},
        {'text': 'Enviarlo', 'callback_data': 'ev|mision_meowth|decision|send'},
        {'text': 'Montar en él', 'callback_data': 'ev|mision_meowth|decision|ride'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_mision_meowth(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    if choice == 'climb':
        choice_made_text = "ℹ️ Decidiste subir al árbol."
        prize = 400
        db.update_money(user_id, prize)
        result_text = (
            f"🔸{user.first_name} comienza a trepar por el tronco. Le hace una señal al Pidgeotto, quien usa *Viento Afín* para crear una corriente de aire que empuja suavemente a {user.first_name} contra el árbol, mejorando su agarre y escalando el árbol fácilmente.\n\n"
            f"Al llegar a la rama, {user.first_name} le habla con suavidad al Pokémon. El Meowth va lentamente, se agarra en sus hombros y bajan juntos sin problemas.\n"
            "La anciana está encantada y te agradece el servicio.\n\n"
            f"¡Recibes *{format_money(prize)}₽* 💰 como pago por el trabajo!"
        )

    elif choice == 'send':
        choice_made_text = "ℹ️ Decidiste enviar al Pidgeotto."
        prize = 300
        db.update_money(user_id, prize)
        result_text = (
            f"🔸{user.first_name} prefiere no arriesgarse y manda al Pidgeotto a por él. El pájaro vuela rápidamente hacia la rama, pero el batir de sus alas pone muy nervioso al Meowth, el cual lanza un arañazo al aire, pierde el equilibrio, resbala y... ¡cae directamente sobre la cara de {user.first_name}!\n\n"
            "A pesar del golpe, el Meowth está a salvo. La dueña te da las gracias.\n\n"
            f"¡Recibes *{format_money(prize)}₽* 💰 como pago por el trabajo!"
        )

    elif choice == 'ride':
        choice_made_text = "ℹ️ Decidiste montar en Pidgeotto."
        prize = 100
        db.update_money(user_id, prize)
        result_text = (
            f"🔸{user.first_name} piensa que lo más rápido es volar hasta la rama. Se sube a lomos de Pidgeotto, pero el pobre Pokémon apenas puede con el peso.\n\n"
            f"Aleteando con gran esfuerzo y volando a trompicones, logran llegar a la altura del Meowth. {user.first_name} lo agarra como puede, pero un movimiento brusco desestabiliza al pájaro y se precipitan los tres hacia el suelo.\n\n"
            "Todos están bien, aunque un poco magullados. La anciana te agradece sin mucho entusiasmo.\n\n"
            f"¡Recibes *{format_money(prize)}₽* 💰 como pago por el trabajo!"
        )

    separator = "\n\n" + "—" * 20 + "\n\n"
    final_text = original_text + separator + f"_{choice_made_text}_\n\n{result_text}"
    return {'text': final_text}


# --- NUEVO EVENTO: MISIÓN MOLTRES ---
def _get_mision_moltres_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔹*_Misión especial_*\n\n"
        f"🔸El Álbumdex de {user.first_name} suena y vibra. ¡Amelia está llamando!\n"
        f"💬 *¡{user.first_name}, te necesito urgentemente! Se han alertado gritos desgarradores de lo que parece ser un Pokémon atrapado en el Monte Ascuas, en las Islas Sete.*\n"
        f"💬 *Es una zona peligrosa con muchos desprendimientos. Te he mandado una Poké Ball con un Machamp al Centro Pokémon que tienes cerca; puede ser muy útil ¡Por favor, ve allí y averigua qué está pasando!*\n\n"
        f"🔸{user.first_name} llega al monte y ve la entrada de una cueva, pero un derrumbe reciente ha bloqueado completamente el paso con rocas enormes. Escucha el grito de un Pokémon; piensa que, sin lugar a dudas, viene de dentro.\n"
        f"Saca al Machamp y este se prepara para recibir órdenes.\n\n"
        f"{user.first_name} recuerda la nota que le dejó Amelia con los ataques que tiene Machamp, y elige uno de ellos:"
    )
    keyboard = [[
        {'text': 'Usar Hiperrayo', 'callback_data': 'ev|mision_moltres|decision|hyperbeam'},
        {'text': 'Usar Fuerza', 'callback_data': 'ev|mision_moltres|decision|strength'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_mision_moltres(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    MACHAMP_ID = 68
    EVENT_ID = 'mision_moltres'

    if choice == 'strength':
        choice_made_text = "ℹ️ Ordenaste a Machamp usar Fuerza."
        prize_money = 600

        db.update_money(user_id, prize_money)
        inventory = db.get_user_inventory(user_id)
        has_feather = any(item['item_id'] == 'pluma_naranja' for item in inventory)
        feather_text = ""
        if not has_feather:
            db.add_item_to_inventory(user_id, 'pluma_naranja', 1)
            feather_text = "-Pluma Naranja (Guardada en mochila)"
        else:
            feather_text = "-Pluma Naranja (Ya la tenías)"

        sticker_msg = _handle_sticker_reward(user_id, user_mention, MACHAMP_ID, False, chat_id)

        result_text = (
            f"🔸Machamp se acerca a las rocas y, con una concentración y fuerza notables, comienza a empujar y apartar los bloques más grandes, hasta que logra abrir un hueco considerable.\n"
            f"De repente, del interior de la cueva surge una llamarada cegadora. Un ave envuelta en fuego sale disparada hacia el cielo a una velocidad vertiginosa.\n\n"
            f"Casi instintivamente agarras el Álbumdex y apuntas al cielo, pero ya no está. Notas algo caer, es una pluma brillante.\n\n"
            f"💬 *¡Impecable trabajo! Siéntete libre de registrar a Machamp* —te dice Amelia por el aparato—.\n\n"
            f" Obtienes:\n"
            f"-*{format_money(prize_money)}₽* 💰\n"
            f"{feather_text}\n\n"
            f"{sticker_msg}\n\n"
            f"🔓 _A partir de ahora, Moltres podrá aparecer salvaje en el grupo._"
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': True, 'event_id': EVENT_ID}

    elif choice == 'hyperbeam':
        choice_made_text = "ℹ️ Ordenaste a Machamp usar Hiperrayo."
        result_text = (
            f"🔸Machamp carga una energía inmensa y la suelta toda de golpe en un Hiperrayo devastador apuntando hacia las rocas. La explosión pulveriza la entrada, pero la onda expansiva es tan fuerte que provoca un derrumbe aún mayor.\n"
            f"Se sigue escuchando al Pokémon en el interior, pero Machamp está agotado por el esfuerzo y el techo de la entrada empieza a ceder. {user.first_name} tiene que meter al Machamp a su Poké Ball y regresar para ponerse a salvo.\n"
            f"💬 *Misión fallida...* —dice Amelia por el Álbumdex—. *La zona es inestable. Tendremos que intentarlo en otro momento.*"
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': False}


# --- NUEVO EVENTO: MISIÓN ZAPDOS ---
def _get_mision_zapdos_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔹*_Misión especial_*\n\n"
        f"🔸El Álbumdex de {user.first_name} recibe una llamada. ¡Es de Amelia!\n\n"
        f"💬 *¡{user.first_name}, tenemos un problema grave! La red eléctrica se ha vuelto loca. ¡Hay tanto apagones como picos de tensión en muchas zonas de Kanto! Estás cerca de la Central Eléctrica, ¿verdad?, ¿podrías echar un vistazo?\n"
        f"Te he enviado al PC más cercano una Poké Ball con un Rhydon, intenta ir por él antes de ir a la central, te será de ayuda.*\n\n"
        f"🔸*{user.first_name}* se adentra en la central. Se escucha un chisporroteo constante. Al mirar hacia los generadores, ve el problema, un enorme pájaro brillante está absorbiendo electricidad. \n"
        f"*{user.first_name}*, precavido, saca a Rhydon antes de avanzar. El ave nota su presencia y lanza un rayo en su dirección; afortunadamente, Rhydon tiene la habilidad Pararrayos, por lo que absorbe el ataque sin sufrir ni un rasguño. En ese momento, da gracias a Amelia y piensa qué movimiento debe ordenar a Rhydon:"
    )
    keyboard = [[
        {'text': 'Usar Cara Susto', 'callback_data': 'ev|mision_zapdos|decision|scaryface'},
        {'text': 'Usar Terratemblor', 'callback_data': 'ev|mision_zapdos|decision|bulldoze'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_mision_zapdos(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    RHYDON_ID = 112
    EVENT_ID = 'mision_zapdos'

    if choice == 'scaryface':
        choice_made_text = "ℹ️ Ordenaste usar Cara Susto."
        prize_money = 600

        db.update_money(user_id, prize_money)
        inventory = db.get_user_inventory(user_id)
        has_feather = any(item['item_id'] == 'pluma_amarilla' for item in inventory)
        feather_text = ""
        if not has_feather:
            db.add_item_to_inventory(user_id, 'pluma_amarilla', 1)
            feather_text = "-Pluma Amarilla (Guardada en mochila)"
        else:
            feather_text = "-Pluma Amarilla (Ya la tenías)"

        sticker_msg = _handle_sticker_reward(user_id, user_mention, RHYDON_ID, False, chat_id)

        result_text = (
            f"🔸Rhydon da un paso al frente y, con un rugido, pone una mueca terrorífica mirando fijamente al Pokémon centelleante.\n\n"
            f"El ave, que ya estaba confundido al ver que sus rayos no surtían efecto, entra en pánico ante la intimidación de Rhydon. Con un chirrido agudo, bate sus alas violentamente y sale volando del lugar, dejando un rastro de chispas tras de sí.\n\n"
            f"Entre las chispas que caen al suelo, ves descender lentamente un objeto brillante, una especie de pluma amarilla.\n\n"
            f"💬 *¡Lo has conseguido!* —se escucha a Amelia a través del Álbumdex—. *Esperemos que todo vuelva a la normalidad. Buen trabajo con ese Rhydon, puedes escanearlo para tu colección, si quieres.*\n\n"
            f"Obtienes:\n"
            f"-💰 *{format_money(prize_money)}₽*\n"
            f"{feather_text}\n\n"
            f"{sticker_msg}\n\n"
            f"🔓 _A partir de ahora, Zapdos podrá aparecer salvaje en el grupo._"
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': True, 'event_id': EVENT_ID}

    elif choice == 'bulldoze':
        choice_made_text = "ℹ️ Ordenaste usar Terratemblor."
        result_text = (
            f"🔸Rhydon golpea el suelo con fuerza bruta y hace temblar toda la zona, pero... el Pokémon pájaro está flotando en el aire, ¡el ataque no le afecta en absoluto!\n"
            f"El ave, furiosa por el intento de ataque, emite un chillido ensordecedor y comienza a usar Danza Lluvia. \n"
            f"Nubes negras se forman de repente y empieza a llover. Rhydon se siente incómodo con la lluvia y deja de prestar atención al objetivo. La electricidad del ambiente comienza a intensificarse, están cayendo rayos por todas partes, convirtiendo la central en una trampa mortal.\n"
            f"💬 *¡Es demasiado peligroso!* —grita Amelia, quien aún está en la llamada—. *¡Sal de ahí ahora mismo!*\n"
            f"{user.first_name} regresa a Rhydon a su Poké Ball y huye de la central antes de que sea demasiado tarde.\n\n"
            f"❌ Misión fallida."
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': False}


# --- NUEVO EVENTO: MISIÓN ARTICUNO ---
def _get_mision_articuno_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔹*_Misión especial_*\n\n"
        f"🔸El Álbumdex de {user.first_name} recibe una llamada. ¡Es de Amelia!\n\n"
        f"💬 *¡{user.first_name}, necesito tu ayuda! Los termómetros de Isla Canela están marcando temperaturas muy bajas, parece ser que corrientes de aire gélido llegan desde las Islas Espuma.*\n"
        f"*Te he enviado un Slowbro al PC. ¡Por favor, ve e investiga qué ocurre!*\n\n"
        f"🔸*{user.first_name}* recoge a Slowbro y navega sobre su lomo haciendo Surf hasta llegar a las Islas Espuma. El frío es cortante. Al llegar a la entrada de la cueva, se encuentran con un obstáculo: un bloque de hielo colosal ha sellado la entrada casi por completo.\n"
        f"Desde el interior, se escucha algo, pero lo único que puede ver es una silueta azul, parece que un Pokémon quedó atrapado dentro. Hay que intentar despejar la entrada. {user.first_name} mira a Slowbro, que bosteza despreocupado, y le ordena un ataque:"
    )
    keyboard = [[
        {'text': 'Psíquico', 'callback_data': 'ev|mision_articuno|decision|psychic'},
        {'text': 'Cabezazo Zen', 'callback_data': 'ev|mision_articuno|decision|zenheadbutt'},
        {'text': 'Llamarada', 'callback_data': 'ev|mision_articuno|decision|flamethrower'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_mision_articuno(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    SLOWBRO_ID = 80
    EVENT_ID = 'mision_articuno'

    if choice == 'flamethrower':
        choice_made_text = "ℹ️ Ordenaste usar Llamarada."
        prize_money = 600

        db.update_money(user_id, prize_money)
        inventory = db.get_user_inventory(user_id)
        has_feather = any(item['item_id'] == 'pluma_azul' for item in inventory)
        feather_text = ""
        if not has_feather:
            db.add_item_to_inventory(user_id, 'pluma_azul', 1)
            feather_text = "-Pluma Azul (Guardada en mochila)"
        else:
            feather_text = "-Pluma Azul (Ya la tenías)"

        sticker_msg = _handle_sticker_reward(user_id, user_mention, SLOWBRO_ID, False, chat_id)

        result_text = (
            f"🔸Slowbro abre la boca y empieza a acumular fuego; para luego expulsarlo violentamente. {user.first_name} se aparta rápidamente y queda boquiabierto. Una llama enorme, con una forma estrellada, colisiona contra el bloque de hielo y llena todo con intensas flamas. En cuestión de segundos, todo el hielo de la entrada queda derretido.\n"
            f"Un chillido agudo resuena desde el interior. Un ave, envuelta en una bruma helada, sale disparada hacia el cielo a una velocidad increíble, dejando tras de sí una estela brillante.\n"
            f"Ves caer del cielo algo parecido a una pluma azul y se posa en la cabeza de Slowbro, que ni se inmuta. {user.first_name} lo mira sonriendo, pensando en lo increíble que ha sido que un Pokémon de agua pueda lanzar tanto fuego.\n\n"
            f"Escanea a Slowbro y cuenta a Amelia lo ocurrido, y esta le recompensa por ello.\n\n"
            f"Obtienes:\n"
            f"-💰 *{format_money(prize_money)}₽*\n"
            f"{feather_text}\n\n"
            f"{sticker_msg}\n\n"
            f"🔓 _A partir de ahora, Articuno podrá aparecer salvaje en el grupo._"
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': True, 'event_id': EVENT_ID}

    elif choice == 'psychic':
        choice_made_text = "ℹ️ Ordenaste usar Psíquico."
        result_text = (
            f"🔸Slowbro intenta retirar el bloque de hielo con sus poderes psicoquinéticos, pero está firmemente unido a la entrada de la cueva. Mira a {user.first_name} con confusión, pero de pronto, se pone serio, dirige su mirada hacia el bloque de hielo, y usa de nuevo Psíquico. Sigue intentándolo una y otra vez, cada vez con mayor intensidad. De repente, para de hacerlo y... cae al suelo fuera de combate.\n\n"
            f"{user.first_name} suspira y lo lleva al Centro Pokémon más cercano.\n\n"
            f"❌ Misión fallida."
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': False}

    elif choice == 'zenheadbutt':
        choice_made_text = "ℹ️ Ordenaste usar Cabezazo Zen."
        result_text = (
            f"Slowbro dirige su mirada hacia el enorme bloque de hielo, y con todas sus fuerzas, le da un gran cabezazo que resuena en todo el lugar. \n"
            f"El bloque congelado apenas tiene un rasguño; Slowbro lo mira desafiante, y segundos después cae al suelo debilitado.\n\n"
            f"{user.first_name} suspira y siente que no fue la opción más acertada. Rápidamente lo lleva al Centro Pokémon más cercano.\n\n"
            f"❌ Misión fallida."
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': False}


# --- NUEVO EVENTO: MISIÓN MEWTWO ---
def _get_mision_mewtwo_variant(user: User):
    text = (
        f"_Evento aceptado por {user.first_name}_\n\n"
        f"🔹*_Misión especial_*\n\n"
        f"🔸Hace un espléndido día por Isla Canela, {user.first_name} va paseando, disfrutando de la brisa marina. \n"
        f"De repente, se oye una explosión proveniente de una mansión cercana. \n"
        f"Rápidamente, llama a Amelia y le cuenta la situación.\n\n"
        f"💬 *Vale {user.first_name}, te he mandado un Poliwrath al Centro Pokémon de Isla Canela, ¿podrías acercarte a investigar por si hubiera alguien herido? ten mucho cuidado, si la cosa se complica, ya sabes, para fuera...*\n\n"
        f"🔸{user.first_name} entra en la mansión en ruinas y ve a gente que sale huyendo del lugar, algunos con magulladuras. No hay llamas, por lo que usa a Poliwrath para apartar escombros que ha dejado la explosión. Decide asomarse al sótano, para ver si hay alguien más.\n"
        f"Al entrar, activa la linterna de su Álbumdex, ya que todo está en la más absoluta oscuridad, pero no ve a nadie. \n"
        f"De pronto, una voz dice: \"Ayúdame...\".\n"
        f"{user.first_name} se adentra más; fuerza la vista, y lo ve: una figura humanoide enganchada a una serie de máquinas, y recubierta de una pesada armadura metálica, que la inmoviliza. Le mira atentamente.\n"
        f"\"Ayúdame a salir...\" —le dice sin mover la boca, la voz resuena directamente en su cabeza.\n\n"
        f"{user.first_name} siente una sensación extraña y piensa: ¿debería ayudar?"
    )
    keyboard = [[
        {'text': 'Ayudar', 'callback_data': 'ev|mision_mewtwo|decision|help'},
        {'text': 'Huir', 'callback_data': 'ev|mision_mewtwo|decision|flee'}
    ]]
    return {'text': text, 'keyboard': keyboard}


def evento_mision_mewtwo(user, decision_parts, original_text, chat_id):
    user_id = user.id
    user_mention = user.mention_markdown()
    choice = decision_parts[0]
    result_text = ""
    choice_made_text = ""

    POLIWRATH_ID = 62
    EVENT_ID = 'mision_mewtwo'

    if choice == 'help':
        choice_made_text = "ℹ️ Decidiste ayudar."
        prize_money = 1200

        db.update_money(user_id, prize_money)
        inventory = db.get_user_inventory(user_id)
        has_photo = any(item['item_id'] == 'foto_psiquica' for item in inventory)
        photo_text = ""
        if not has_photo:
            db.add_item_to_inventory(user_id, 'foto_psiquica', 1)
            photo_text = "-Foto Psíquica(?) (Guardada en mochila)"
        else:
            photo_text = "-Foto Psíquica(?) (Ya la tenías)"

        sticker_msg = _handle_sticker_reward(user_id, user_mention, POLIWRATH_ID, False, chat_id)

        result_text = (
            f"🔸Antes de poder decir nada, la figura proyecta en su mente las instrucciones para desactivar los cierres de la armadura. Siguiendo sus indicaciones telepáticas, {user.first_name} consigue liberar al ser.\n"
            f"Los pesados metales de la armadura, caen uno tras otro con gran estruendo.\n\n"
            f"La extraña criatura se acerca levitando lentamente, {user.first_name} quiere mantener las distancias, pero sus piernas no se mueven, es como si una extraña fuerza le obligara a estar quieto. De reojo mira a Poliwrath, al cual le ocurre lo mismo. \n"
            f"\"Sé lo que quieres...\" —dice la voz en tu mente— deja que te dé las gracias.\n\n"
            f"De repente, siente un tirón en las manos; ¡el Álbumdex sale volando por sí solo! Se eleva por encima de su cabeza y se coloca detrás de él. {user.first_name} deja de sentir la presión en las piernas, se gira instintivamente a mirar el objeto levitando y un fogonazo que dura unos instantes alumbra toda la sala. \n"
            f"El Álbumdex comienza a caer por la gravedad y {user.first_name} lo atrapa al vuelo.\n\n"
            f"De pronto, una onda expansiva de aire le empuja: el ser ha salido disparado a una velocidad supersónica, atravesando el techo de las diferentes plantas de la mansión.\n"
            f"{user.first_name} no entiende nada, pero sabe que es hora de actuar, ya que hay pequeños desprendimientos. Aprovechando la luz proveniente del agujero del techo, guarda a Poliwrath en su Poké Ball y sale del lugar.\n\n"
            f"Le cuenta todo a Amelia.\n\n"
            f"💬 *¿Una armadura? ¿Telepatía? —Amelia intenta asimilarlo todo— Nunca oí nada parecido, ¿te imaginas que fuera un Pokémon legendario?* \n"
            f"*Fuera lo que fuese, al final escapó; por lo que, \"Misión cumplida\", supongo.*\n"
            f"*Aquí tienes una recompensa extra, por el riesgo corrido. Gracias por tu ayuda, {user.first_name}.*\n\n"
            f"Obtienes:\n"
            f"💰 *{format_money(prize_money)}₽*\n\n"
            f"Mientras {user.first_name} escanea a Poliwrath, ve que hay una foto que no había visto antes en el Modo Cámara del Álbumdex, y suspira: el Pokémon humanoide pensó que quería una foto suya, en lugar de escanearle.\n\n"
            f"{sticker_msg}\n\n"
            f"{photo_text}\n\n"
            f"🔓 _A partir de ahora, Mewtwo podrá aparecer salvaje en el grupo._"
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': True, 'event_id': EVENT_ID}

    elif choice == 'flee':
        choice_made_text = "ℹ️ Decidiste huir de allí."
        result_text = (
            f"🔸La presión psíquica es demasiado fuerte. {user.first_name} siente un mareo intenso que no le deja pensar con claridad.\n\n"
            f"El edificio comienza a temblar de nuevo. Temiendo un derrumbe inminente, {user.first_name} regresa a Poliwrath a su Poké Ball y sale corriendo del lugar.\n\n"
            f"💬 *¿No había nadie? —pregunta Amelia—. Mejor, gracias por acercarte a echar un vistazo.*\n\n"
            f"❌ Misión fallida."
        )
        return {'text': original_text + "\n\n" + "—" * 20 + "\n\n" + f"_{choice_made_text}_\n\n{result_text}",
                'event_completed': False}


# --- DICCIONARIO PRINCIPAL DE EVENTOS ---
EVENTS = {
    'pesca_ruta_12': {
        'name': "Aventura de Pesca en Ruta 12",
        'steps': {
            'start': {'get_text_and_keyboard': lambda user: random.choice([{'text': (
                f"_Evento aceptado por {user.first_name}_\n\n🔸{user.first_name} va paseando por la Ruta 12, cuando de pronto escucha la voz de alguien:\n💬 *Oye, perdona, ¿puedes venir un momento?*\n\n🔸{user.first_name} dirige su mirada a un pescador, que le está indicando con la mano que se acerque:\n💬 *¿Podría pedirte un favor? ¿Puedes vigilar la caña? Voy a comprar cebo, solo será un momento.*"),
                                                                            'keyboard': [[{'text': 'Vale',
                                                                                           'callback_data': 'ev|pesca_ruta_12|decision|vigilar_caña|vale'},
                                                                                          {'text': 'No puedo',
                                                                                           'callback_data': 'ev|pesca_ruta_12|decision|vigilar_caña|no_puedo'}]]},
                                                                           {'text': (
                                                                               f"_Evento aceptado por {user.first_name}_\n\n🔸{user.first_name} va a entrar en la Ruta 12 y ve un puesto con cañas de pescar, con un cartel que anuncia:\n\"¡Alquila una caña de pescar por solo 200₽!\""),
                                                                            'keyboard': [[{'text': 'Lo haré',
                                                                                           'callback_data': 'ev|pesca_ruta_12|decision|alquilar_caña|lo_hare'},
                                                                                          {'text': 'Nah, para qué',
                                                                                           'callback_data': 'ev|pesca_ruta_12|decision|alquilar_caña|nah_para_que'}]]}])},
            'decision': {'action': evento_pesca_ruta_12}
        }
    },
    'casino_rocket': {
        'name': "Negocios en el Casino Rocket",
        'steps': {
            'start': {'get_text_and_keyboard': lambda user: random.choice([_get_casino_sale_variant(user), {'text': (
                f"_Evento aceptado por {user.first_name}_\n\n🔸{user.first_name} se encuentra en Ciudad Azulona, caminando cerca del Casino Rocket, un edificio de lo más llamativo. Fuera del casino, junto a la entrada, hay una máquina de gancho con sobres pequeños de Kanto decorados con Poké Balls.\n\nUn cartel dice:\n🪧 1 intento por solo 200₽ 💰 (máximo 3 intentos por persona)."),
                                                                                                            'keyboard': [
                                                                                                                [{
                                                                                                                     'text': 'Jugar',
                                                                                                                     'callback_data': 'ev|casino_rocket|decision|claw_machine|play|0'},
                                                                                                                 {
                                                                                                                     'text': 'No jugar',
                                                                                                                     'callback_data': 'ev|casino_rocket|decision|claw_machine|no_play|0'}]]}])},
            'decision': {'action': evento_casino_rocket}
        }
    },
    'bosque_verde': {
        'name': "Paseo por el Bosque Verde",
        'steps': {'start': {'get_text_and_keyboard': _get_bosque_verde_variant}}
    },
    'tunel_roca': {
        'name': "Aventura en el Túnel Roca",
        'steps': {'start': {'get_text_and_keyboard': _get_tunel_roca_variant},
                  'decision': {'action': evento_tunel_roca}}
    },
    'torre_lavanda': {
        'name': "Misterio en la Torre Pokémon",
        'steps': {'start': {'get_text_and_keyboard': _get_torre_lavanda_variant},
                  'decision': {'action': evento_torre_lavanda}}
    },
    'ciudad_azulona': {
        'name': "Un bocado en Ciudad Azulona",
        'steps': {'start': {'get_text_and_keyboard': _get_ciudad_azulona_variant},
                  'decision': {'action': evento_ciudad_azulona}}
    },
    'erika_nap': {
        'name': "Siesta en el Jardín",
        'steps': {'start': {'get_text_and_keyboard': _get_erika_nap_variant}, 'decision': {'action': evento_erika_nap}}
    },
    'lottery_azafran': {
        'name': "Lotería de Ciudad Azafrán",
        'steps': {'start': {'get_text_and_keyboard': _get_loteria_azafran_variant},
                  'decision': {'action': evento_loteria_azafran}}
    },
    'dojo_azafran': {
        'name': "Entrenamiento en Azafrán",
        'steps': {'start': {'get_text_and_keyboard': _get_dojo_azafran_variant},
                  'decision': {'action': evento_dojo_azafran}}
    },
    'mision_meowth': {
        'name': "Misión de Rescate Aéreo",
        'steps': {
            'start': {'get_text_and_keyboard': _get_mision_meowth_variant},
            'decision': {'action': evento_mision_meowth}
        }
    },
    'mision_moltres': {
        'name': "Misión Especial: Fuego en la Montaña",
        'steps': {
            'start': {'get_text_and_keyboard': _get_mision_moltres_variant},
            'decision': {'action': evento_mision_moltres}
        }
    },
    'mision_zapdos': {
        'name': "Misión Especial: Tormenta en la Central",
        'steps': {
            'start': {'get_text_and_keyboard': _get_mision_zapdos_variant},
            'decision': {
                'action': evento_mision_zapdos
            }
        }
    },
    'mision_articuno': {
        'name': "Misión Especial: Viento Helado en las Islas",
        'steps': {
            'start': {'get_text_and_keyboard': _get_mision_articuno_variant},
            'decision': {
                'action': evento_mision_articuno
            }
        }
    },
    'mision_mewtwo': {
        'name': "Misión Especial: El Secreto de la Mansión",
        'steps': {
            'start': {'get_text_and_keyboard': _get_mision_mewtwo_variant},
            'decision': {
                'action': evento_mision_mewtwo
            }
        }
    }
}

