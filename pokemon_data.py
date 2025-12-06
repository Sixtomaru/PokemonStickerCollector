# pokemon_data.py

# Categorías:
# 'C': 1ª evo (45%)
# 'B': 2ª evo o sin evo (30%)
# 'A': 3ª evo, especiales, megas (20%)
# 'S': Legendarios (5%)

# El bot calculará la rareza final (S, SS, SSS) si es shiny.

POKEMON_KANTO = [
    {"id": 1, "name": "Bulbasaur", "category": "C"},
    {"id": 2, "name": "Ivysaur", "category": "B"},
    {"id": 3, "name": "Venusaur", "category": "A"},
    {"id": 4, "name": "Charmander", "category": "C"},
    {"id": 5, "name": "Charmeleon", "category": "B"},
    {"id": 6, "name": "Charizard", "category": "A"},
    {"id": 7, "name": "Squirtle", "category": "C"},
    {"id": 8, "name": "Wartortle", "category": "B"},
    {"id": 9, "name": "Blastoise", "category": "A"},
    {"id": 10, "name": "Caterpie", "category": "C"},
    {"id": 11, "name": "Metapod", "category": "B"},
    {"id": 12, "name": "Butterfree", "category": "A"},
    {"id": 13, "name": "Weedle", "category": "C"},
    {"id": 14, "name": "Kakuna", "category": "B"},
    {"id": 15, "name": "Beedrill", "category": "A"},
    {"id": 16, "name": "Pidgey", "category": "C"},
    {"id": 17, "name": "Pidgeotto", "category": "B"},
    {"id": 18, "name": "Pidgeot", "category": "A"},
    {"id": 19, "name": "Rattata", "category": "C"},
    {"id": 20, "name": "Raticate", "category": "B"},
    {"id": 21, "name": "Spearow", "category": "C"},
    {"id": 22, "name": "Fearow", "category": "B"},
    {"id": 23, "name": "Ekans", "category": "C"},
    {"id": 24, "name": "Arbok", "category": "B"},
    {"id": 25, "name": "Pikachu", "category": "A"}, # Considerado especial
    {"id": 26, "name": "Raichu", "category": "A"},
    {"id": 27, "name": "Sandshrew", "category": "C"},
    {"id": 28, "name": "Sandslash", "category": "B"},
    {"id": 29, "name": "Nidoran♀", "category": "C"},
    {"id": 30, "name": "Nidorina", "category": "B"},
    {"id": 31, "name": "Nidoqueen", "category": "A"},
    {"id": 32, "name": "Nidoran♂", "category": "C"},
    {"id": 33, "name": "Nidorino", "category": "B"},
    {"id": 34, "name": "Nidoking", "category": "A"},
    {"id": 35, "name": "Clefairy", "category": "C"},
    {"id": 36, "name": "Clefable", "category": "B"},
    {"id": 37, "name": "Vulpix", "category": "C"},
    {"id": 38, "name": "Ninetales", "category": "B"},
    {"id": 39, "name": "Jigglypuff", "category": "C"},
    {"id": 40, "name": "Wigglytuff", "category": "B"},
    {"id": 41, "name": "Zubat", "category": "C"},
    {"id": 42, "name": "Golbat", "category": "B"},
    {"id": 43, "name": "Oddish", "category": "C"},
    {"id": 44, "name": "Gloom", "category": "B"},
    {"id": 45, "name": "Vileplume", "category": "A"},
    {"id": 46, "name": "Paras", "category": "C"},
    {"id": 47, "name": "Parasect", "category": "B"},
    {"id": 48, "name": "Venonat", "category": "C"},
    {"id": 49, "name": "Venomoth", "category": "B"},
    {"id": 50, "name": "Diglett", "category": "C"},
    {"id": 51, "name": "Dugtrio", "category": "B"},
    {"id": 52, "name": "Meowth", "category": "C"},
    {"id": 53, "name": "Persian", "category": "B"},
    {"id": 54, "name": "Psyduck", "category": "C"},
    {"id": 55, "name": "Golduck", "category": "B"},
    {"id": 56, "name": "Mankey", "category": "C"},
    {"id": 57, "name": "Primeape", "category": "B"},
    {"id": 58, "name": "Growlithe", "category": "C"},
    {"id": 59, "name": "Arcanine", "category": "A"},
    {"id": 60, "name": "Poliwag", "category": "C"},
    {"id": 61, "name": "Poliwhirl", "category": "B"},
    {"id": 62, "name": "Poliwrath", "category": "A"},
    {"id": 63, "name": "Abra", "category": "C"},
    {"id": 64, "name": "Kadabra", "category": "B"},
    {"id": 65, "name": "Alakazam", "category": "A"},
    {"id": 66, "name": "Machop", "category": "C"},
    {"id": 67, "name": "Machoke", "category": "B"},
    {"id": 68, "name": "Machamp", "category": "A"},
    {"id": 69, "name": "Bellsprout", "category": "C"},
    {"id": 70, "name": "Weepinbell", "category": "B"},
    {"id": 71, "name": "Victreebel", "category": "A"},
    {"id": 72, "name": "Tentacool", "category": "C"},
    {"id": 73, "name": "Tentacruel", "category": "B"},
    {"id": 74, "name": "Geodude", "category": "C"},
    {"id": 75, "name": "Graveler", "category": "B"},
    {"id": 76, "name": "Golem", "category": "A"},
    {"id": 77, "name": "Ponyta", "category": "C"},
    {"id": 78, "name": "Rapidash", "category": "B"},
    {"id": 79, "name": "Slowpoke", "category": "C"},
    {"id": 80, "name": "Slowbro", "category": "B"},
    {"id": 81, "name": "Magnemite", "category": "C"},
    {"id": 82, "name": "Magneton", "category": "B"},
    {"id": 83, "name": "Farfetch'd", "category": "B"}, # Sin evolución
    {"id": 84, "name": "Doduo", "category": "C"},
    {"id": 85, "name": "Dodrio", "category": "B"},
    {"id": 86, "name": "Seel", "category": "C"},
    {"id": 87, "name": "Dewgong", "category": "B"},
    {"id": 88, "name": "Grimer", "category": "C"},
    {"id": 89, "name": "Muk", "category": "B"},
    {"id": 90, "name": "Shellder", "category": "C"},
    {"id": 91, "name": "Cloyster", "category": "B"},
    {"id": 92, "name": "Gastly", "category": "C"},
    {"id": 93, "name": "Haunter", "category": "B"},
    {"id": 94, "name": "Gengar", "category": "A"},
    {"id": 95, "name": "Onix", "category": "B"}, # Sin evolución
    {"id": 96, "name": "Drowzee", "category": "C"},
    {"id": 97, "name": "Hypno", "category": "B"},
    {"id": 98, "name": "Krabby", "category": "C"},
    {"id": 99, "name": "Kingler", "category": "B"},
    {"id": 100, "name": "Voltorb", "category": "C"},
    {"id": 101, "name": "Electrode", "category": "B"},
    {"id": 102, "name": "Exeggcute", "category": "C"},
    {"id": 103, "name": "Exeggutor", "category": "B"},
    {"id": 104, "name": "Cubone", "category": "C"},
    {"id": 105, "name": "Marowak", "category": "B"},
    {"id": 106, "name": "Hitmonlee", "category": "B"}, # Sin evolución
    {"id": 107, "name": "Hitmonchan", "category": "B"}, # Sin evolución
    {"id": 108, "name": "Lickitung", "category": "B"}, # Sin evolución
    {"id": 109, "name": "Koffing", "category": "C"},
    {"id": 110, "name": "Weezing", "category": "B"},
    {"id": 111, "name": "Rhyhorn", "category": "C"},
    {"id": 112, "name": "Rhydon", "category": "B"},
    {"id": 113, "name": "Chansey", "category": "B"}, # Sin evolución
    {"id": 114, "name": "Tangela", "category": "B"}, # Sin evolución
    {"id": 115, "name": "Kangaskhan", "category": "B"}, # Sin evolución
    {"id": 116, "name": "Horsea", "category": "C"},
    {"id": 117, "name": "Seadra", "category": "B"},
    {"id": 118, "name": "Goldeen", "category": "C"},
    {"id": 119, "name": "Seaking", "category": "B"},
    {"id": 120, "name": "Staryu", "category": "C"},
    {"id": 121, "name": "Starmie", "category": "B"},
    {"id": 122, "name": "Mr. Mime", "category": "B"}, # Sin evolución
    {"id": 123, "name": "Scyther", "category": "B"}, # Sin evolución
    {"id": 124, "name": "Jynx", "category": "B"}, # Sin evolución
    {"id": 125, "name": "Electabuzz", "category": "B"}, # Sin evolución
    {"id": 126, "name": "Magmar", "category": "B"}, # Sin evolución
    {"id": 127, "name": "Pinsir", "category": "B"}, # Sin evolución
    {"id": 128, "name": "Tauros", "category": "B"}, # Sin evolución
    {"id": 129, "name": "Magikarp", "category": "C"},
    {"id": 130, "name": "Gyarados", "category": "A"},
    {"id": 131, "name": "Lapras", "category": "A"}, # Especial
    {"id": 132, "name": "Ditto", "category": "A"}, # Especial
    {"id": 133, "name": "Eevee", "category": "C"},
    {"id": 134, "name": "Vaporeon", "category": "A"},
    {"id": 135, "name": "Jolteon", "category": "A"},
    {"id": 136, "name": "Flareon", "category": "A"},
    {"id": 137, "name": "Porygon", "category": "B"}, # Sin evolución
    {"id": 138, "name": "Omanyte", "category": "C"},
    {"id": 139, "name": "Omastar", "category": "B"},
    {"id": 140, "name": "Kabuto", "category": "C"},
    {"id": 141, "name": "Kabutops", "category": "B"},
    {"id": 142, "name": "Aerodactyl", "category": "A"}, # Especial
    {"id": 143, "name": "Snorlax", "category": "A"}, # Especial
    {"id": 144, "name": "Articuno", "category": "S"}, # Legendario
    {"id": 145, "name": "Zapdos", "category": "S"}, # Legendario
    {"id": 146, "name": "Moltres", "category": "S"}, # Legendario
    {"id": 147, "name": "Dratini", "category": "C"},
    {"id": 148, "name": "Dragonair", "category": "B"},
    {"id": 149, "name": "Dragonite", "category": "A"},
    {"id": 150, "name": "Mewtwo", "category": "S"}, # Legendario
    {"id": 151, "name": "Mew", "category": "S"}, # Legendario
]

# --- NUEVA ESTRUCTURA ---
POKEMON_REGIONS = {
    "Kanto": POKEMON_KANTO,
    # Cuando añadas Johto, crearías POKEMON_JOHTO y lo añadirías aquí:
    # "Johto": POKEMON_JOHTO,
}

# Creamos una lista con todos los Pokémon para cálculos nacionales
ALL_POKEMON = [p for region_list in POKEMON_REGIONS.values() for p in region_list]

# --- AÑADE ESTA LÍNEA AL FINAL ---
POKEMON_BY_ID = {p['id']: p for p in ALL_POKEMON}