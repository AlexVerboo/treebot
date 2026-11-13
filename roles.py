"""
Roles de Trees in Space y qué estadísticas muestra cada uno en la página /roles.

Los tags de cada persona viven en la hoja "Roles" (una columna por rol, con casillas).
Para agregar un rol nuevo:
  1. Agrega una columna en la hoja "Roles" con el nombre del rol (ej. "Sniper").
  2. (Opcional) Agrégalo aquí en ROLES con sus columnas. Si no está aquí, la página
     lo muestra igual con las columnas de DEFAULT_COLUMNS.

Las claves de las columnas son las que escribe player_stats_updater.py en la hoja "Player Stats".
Compatible con Python 3.7 (Render).
"""

# key: (etiqueta, formato, más bajo es mejor)
#   formato: "n" número con 2 decimales, "i" entero, "pct" porcentaje, "time" mm:ss
STATS = {
    "matches":              ("Matches", "i", False),
    "win_pct":              ("Win %", "pct", False),
    "kills_pg":             ("Kills / game", "n", False),
    "deaths_pg":            ("Deaths / game", "n", True),
    "assists_pg":           ("Assists / game", "n", False),
    "kd":                   ("K/D", "n", False),
    "kda":                  ("KDA", "n", False),
    "dmg_pg":               ("Damage / game", "i", False),
    "dmg_diff_pg":          ("Dmg diff / game", "i", False),
    "accuracy":             ("Accuracy", "pct", False),
    "headshot_pct":         ("Headshot %", "pct", False),
    "power_kills_pg":       ("Power wpn kills / game", "n", False),
    "melee_kills_pg":       ("Melee kills / game", "n", False),
    "max_spree":            ("Best spree", "i", False),
    "callouts_pg":          ("Callout assists / game", "n", False),
    "obj_pg":               ("Objectives / game", "n", False),
    # Vehículos
    "driver_assists_pg":    ("Driver assists / game", "n", False),
    "vehicle_destroys_pg":  ("Vehicles destroyed / game", "n", False),
    "hijacks_pg":           ("Hijacks / game", "n", False),
    "emp_assists_pg":       ("EMP assists / game", "n", False),
    # Capture the Flag (por partida de CTF)
    "ctf_matches":          ("CTF games", "i", False),
    "caps_pg":              ("Flag caps / CTF game", "n", False),
    "grabs_pg":             ("Flag grabs / CTF game", "n", False),
    "returns_pg":           ("Flag returns / CTF game", "n", False),
    "carrier_kills_pg":     ("Carrier kills / CTF game", "n", False),
    "carry_time_pg":        ("Flag carry time / CTF game", "time", False),
    # Zonas (KOTH, Strongholds, Total Control)
    "zone_matches":         ("Zone games", "i", False),
    "zone_caps_pg":         ("Zone caps / zone game", "n", False),
    "zone_def_kills_pg":    ("Zone defense kills / zone game", "n", False),
    "zone_off_kills_pg":    ("Zone offense kills / zone game", "n", False),
    "zone_time_pg":         ("Zone time / zone game", "time", False),
    # Oddball
    "ball_matches":         ("Oddball games", "i", False),
    "ball_time_pg":         ("Skull time / oddball game", "time", False),
    "ball_carrier_kills_pg": ("Skull carrier kills / oddball game", "n", False),
    # Stockpile
    "seed_matches":         ("Stockpile games", "i", False),
    "seeds_dep_pg":         ("Seeds deposited / stockpile game", "n", False),
    "seed_carrier_kills_pg": ("Seed carrier kills / stockpile game", "n", False),
}

# Orden de las pestañas y qué columnas muestra cada rol. La primera columna es la que
# ordena la tabla al abrir la pestaña.
ROLES = [
    {
        "name": "Roamer",
        "icon": "🗡️",
        "blurb": "Denial by killing: hunts the enemy team and keeps them off the map.",
        "columns": ["kills_pg", "kd", "kda", "dmg_pg", "dmg_diff_pg", "power_kills_pg",
                    "headshot_pct", "accuracy", "max_spree"],
    },
    {
        "name": "Anchor",
        "icon": "🛡️",
        "blurb": "Holds the line: defends the base, the flag and the zones, and stays alive.",
        "columns": ["deaths_pg", "kd", "returns_pg", "carrier_kills_pg", "zone_def_kills_pg",
                    "ball_carrier_kills_pg", "seed_carrier_kills_pg", "callouts_pg"],
    },
    {
        "name": "Objective",
        "icon": "🚩",
        "blurb": "Plays the objective: caps flags, takes zones, carries the skull.",
        "columns": ["obj_pg", "win_pct", "caps_pg", "grabs_pg", "carry_time_pg",
                    "zone_caps_pg", "zone_time_pg", "ball_time_pg", "seeds_dep_pg"],
    },
    {
        "name": "Driver",
        "icon": "🚙",
        "blurb": "Wheelman: gets the team around and turns vehicles into kills.",
        "columns": ["driver_assists_pg", "hijacks_pg", "vehicle_destroys_pg",
                    "emp_assists_pg", "kills_pg", "kd"],
    },
]

DEFAULT_COLUMNS = ["kills_pg", "deaths_pg", "assists_pg", "kd", "kda", "dmg_pg",
                   "accuracy", "obj_pg", "win_pct"]

# Columnas de la pestaña "All Trees"
OVERVIEW_COLUMNS = ["matches", "win_pct", "kd", "kda", "kills_pg", "assists_pg",
                    "dmg_pg", "obj_pg", "accuracy"]


def role_names():
    return [r["name"] for r in ROLES]


def page_config(extra_roles=()):
    """Lo que necesita la página: roles (incluidos los que solo existen en la hoja) y stats."""
    known = {r["name"].lower() for r in ROLES}
    roles = [dict(r) for r in ROLES]
    for name in extra_roles:
        if name.lower() not in known:
            known.add(name.lower())
            roles.append({"name": name, "icon": "🌲", "blurb": "", "columns": DEFAULT_COLUMNS})
    stats = {k: {"label": v[0], "fmt": v[1], "low": v[2]} for k, v in STATS.items()}
    return {"roles": roles, "stats": stats, "overview": OVERVIEW_COLUMNS}
