"""
champions.py
============
Lista de campeones de LoL y resolución fuzzy de nombres.

Uso:
    from champions import resolve_champion
    champ = resolve_champion("cali")   # → ("Akali", 103)
    champ = resolve_champion("fresh")  # → ("Thresh", 412)
    champ = resolve_champion("xyz")    # → None
"""

from rapidfuzz import fuzz

# ─── Lista completa de campeones (nombre display, id) ────────────────────────
# Champion IDs oficiales de Riot (Data Dragon)
CHAMPIONS: dict[str, int] = {
    "Aatrox": 266, "Ahri": 103, "Akali": 84, "Akshan": 166, "Alistar": 12,
    "Amumu": 32, "Anivia": 34, "Annie": 1, "Aphelios": 523, "Ashe": 22,
    "Aurelion Sol": 136, "Aurora": 893, "Azir": 268, "Bard": 432,
    "Bel'Veth": 200, "Blitzcrank": 53, "Brand": 63, "Braum": 201,
    "Briar": 233, "Caitlyn": 51, "Camille": 164, "Cassiopeia": 69,
    "Cho'Gath": 31, "Corki": 42, "Darius": 122, "Diana": 131,
    "Dr. Mundo": 36, "Draven": 119, "Ekko": 245, "Elise": 60,
    "Evelynn": 28, "Ezreal": 81, "Fiddlesticks": 9, "Fiora": 114,
    "Fizz": 105, "Galio": 3, "Gangplank": 41, "Garen": 86, "Gnar": 150,
    "Gragas": 79, "Graves": 104, "Gwen": 887, "Hecarim": 120,
    "Heimerdinger": 74, "Hwei": 910, "Illaoi": 420, "Irelia": 39,
    "Ivern": 427, "Janna": 40, "Jarvan IV": 59, "Jax": 24, "Jayce": 126,
    "Jhin": 202, "Jinx": 222, "K'Sante": 897, "Kai'Sa": 145,
    "Kalista": 429, "Karma": 43, "Karthus": 30, "Kassadin": 38,
    "Katarina": 55, "Kayle": 10, "Kayn": 141, "Kennen": 85,
    "Kha'Zix": 121, "Kindred": 203, "Kled": 240, "Kog'Maw": 96,
    "LeBlanc": 7, "Lee Sin": 64, "Leona": 89, "Lillia": 876, "Lissandra": 127,
    "Lucian": 236, "Lulu": 117, "Lux": 99, "Malphite": 54, "Malzahar": 90,
    "Maokai": 57, "Master Yi": 11, "Milio": 902, "Miss Fortune": 21,
    "Mordekaiser": 82, "Morgana": 25, "Naafiri": 950, "Nami": 267,
    "Nasus": 75, "Nautilus": 111, "Neeko": 518, "Nidalee": 76,
    "Nilah": 895, "Nocturne": 56, "Nunu & Willump": 20, "Olaf": 2,
    "Orianna": 61, "Ornn": 516, "Pantheon": 80, "Poppy": 78,
    "Pyke": 555, "Qiyana": 246, "Quinn": 133, "Rakan": 497,
    "Rammus": 33, "Rek'Sai": 421, "Rell": 526, "Renata Glasc": 888,
    "Renekton": 58, "Rengar": 107, "Riven": 92, "Rumble": 68,
    "Ryze": 13, "Samira": 360, "Sejuani": 113, "Senna": 235,
    "Seraphine": 147, "Sett": 875, "Shaco": 35, "Shen": 98,
    "Shyvana": 102, "Singed": 27, "Sion": 14, "Sivir": 15,
    "Skarner": 72, "Smolder": 901, "Sona": 37, "Soraka": 16,
    "Swain": 50, "Sylas": 517, "Syndra": 134, "Tahm Kench": 223,
    "Taliyah": 163, "Talon": 91, "Taric": 44, "Teemo": 17,
    "Thresh": 412, "Tristana": 18, "Trundle": 48, "Tryndamere": 23,
    "Twisted Fate": 4, "Twitch": 29, "Udyr": 77, "Urgot": 6,
    "Varus": 110, "Vayne": 67, "Veigar": 45, "Vel'Koz": 161,
    "Vex": 711, "Vi": 254, "Viego": 234, "Viktor": 112,
    "Vladimir": 8, "Volibear": 106, "Warwick": 19, "Wukong": 62,
    "Xayah": 498, "Xerath": 101, "Xin Zhao": 5, "Yasuo": 157,
    "Yone": 777, "Yorick": 83, "Yuumi": 350, "Zac": 154, "Zed": 238,
    "Zeri": 221, "Ziggs": 115, "Zilean": 26, "Zoe": 142, "Zyra": 143,
}

# Umbral mínimo de similitud para aceptar un match (0-100)
FUZZY_THRESHOLD = 55

# ─── Aliases de voz ──────────────────────────────────────────────────────────
# Palabras que Google Speech suele devolver en vez del nombre real del campeón.
# Agrega aquí cualquier pronunciación problemática que encuentres.
VOICE_ALIASES: dict[str, str] = {
    # Reconocimientos frecuentes en español
    "cali": "Akali",
    "a cali": "Akali",
    "acali": "Akali",
    "fresh": "Thresh",
    "tres": "Thresh",
    "master": "Master Yi",
    "yi": "Master Yi",
    "kai sa": "Kai'Sa",
    "kaisa": "Kai'Sa",
    "kha zix": "Kha'Zix",
    "khazix": "Kha'Zix",
    "bel vet": "Bel'Veth",
    "belveth": "Bel'Veth",
    "kog maw": "Kog'Maw",
    "rek sai": "Rek'Sai",
    "vel koz": "Vel'Koz",
    "cho gath": "Cho'Gath",
    "k sante": "K'Sante",
    "mundo": "Dr. Mundo",
    "twisted": "Twisted Fate",
    "tf": "Twisted Fate",
    "miss fortune": "Miss Fortune",
    "mf": "Miss Fortune",
    "jarvan": "Jarvan IV",
    "xin": "Xin Zhao",
    "lee": "Lee Sin",
    "tahm": "Tahm Kench",
    "aurelion": "Aurelion Sol",
    "auri": "Aurelion Sol",
    "asol": "Aurelion Sol",
    "nunu": "Nunu & Willump",
    "renata": "Renata Glasc",
    "leblanc": "LeBlanc",
}


def resolve_champion(raw: str) -> tuple[str, int] | None:
    """
    Mapea un string (posiblemente mal reconocido por voz) al campeón más
    parecido usando aliases exactos primero y luego fuzzy matching.

    Retorna (nombre, id) o None si no hay match confiable.

    Ejemplos:
        "a cali"    → ("Akali", 84)
        "fresh"     → ("Thresh", 412)
        "master yi" → ("Master Yi", 11)
        "xyz123"    → None
    """
    if not raw:
        return None

    query = raw.strip().lower()

    # ── 1. Alias exacto ───────────────────────────────────────────────────────
    if query in VOICE_ALIASES:
        name = VOICE_ALIASES[query]
        return name, CHAMPIONS[name]

    # ── 2. Alias parcial (el query contiene o está contenido en un alias) ─────
    for alias, name in VOICE_ALIASES.items():
        if alias in query or query in alias:
            return name, CHAMPIONS[name]

    # ── 3. Match exacto contra nombre oficial (case-insensitive) ─────────────
    for name in CHAMPIONS:
        if query == name.lower():
            return name, CHAMPIONS[name]

    # ── 4. Fuzzy multi-scorer ─────────────────────────────────────────────────
    # Probamos tres métricas distintas y nos quedamos con el mejor resultado:
    # - partial_ratio:     qué tan bien encaja el query DENTRO del nombre
    # - token_set_ratio:   ignora orden y palabras extra
    # - ratio:             similitud global carácter a carácter
    names = list(CHAMPIONS.keys())
    best_name, best_score = None, 0

    for name in names:
        target = name.lower()
        score = max(
            fuzz.partial_ratio(query, target),
            fuzz.token_set_ratio(query, target),
            fuzz.ratio(query, target),
        )
        if score > best_score:
            best_score, best_name = score, name

    if best_score >= FUZZY_THRESHOLD and best_name:
        return best_name, CHAMPIONS[best_name]

    return None