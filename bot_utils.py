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


def get_formatted_name(pokemon_data, is_shiny=False):
    """
    Versión restaurada y limpia.
    Devuelve solo el nombre en negrita (HTML) sin intentar cargar emojis personalizados.
    """
    shiny_text = " ✨" if is_shiny else ""

    # Devolvemos el nombre limpio en negrita.
    # Usamos <b> porque tu bot.py ahora funciona en modo HTML.
    return f"<b>{pokemon_data['name']}</b>{shiny_text}"
