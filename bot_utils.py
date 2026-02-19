# bot_utils.py

# Constantes de rareza compartidas
RARITY_VISUALS = {'C': '🟤', 'B': '🟢', 'A': '🔵', 'S': '🟡', 'SS': '⭐', 'SSS': '🌟'}
DUPLICATE_MONEY_VALUES = {'C': 100, 'B': 200, 'A': 400, 'S': 800, 'SS': 1600, 'SSS': 3200}


def format_money(amount: int) -> str:
    """Formatea un número como una cadena de dinero."""
    return f"{amount:,}".replace(",", ".")


def get_rarity(category, is_shiny):
    """Calcula la rareza final de un Pokémon."""
    if not is_shiny: return category
    return 'S' if category in ['C', 'B'] else 'SS' if category == 'A' else 'SSS'


# --- ESTA ES LA FUNCIÓN QUE TE FALTABA ---
def get_formatted_name(pokemon_data, is_shiny=False):
    """Devuelve el nombre formateado. Intenta mostrar el emoji custom mediante enlace Markdown."""
    shiny_text = " ✨" if is_shiny else ""

    # Truco para Markdown V1: Enlace invisible con el ID del emoji
    # El emoji aparecerá antes del nombre si el cliente de Telegram lo soporta en este modo
    emoji_display = ""
    if 'emoji_id' in pokemon_data:
        emoji_id = pokemon_data['emoji_id']
        # Usamos el carácter invisible \u2060 para anclar el enlace del emoji
        emoji_display = f"[\u2060](tg://emoji?id={emoji_id})"

    return f"{emoji_display}{pokemon_data['name']}{shiny_text}"
