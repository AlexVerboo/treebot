# ==============================
# IMPORTS
# ==============================
import os
import re
import sys
import json
import random
import time

import requests
from flask import Flask, request, jsonify, render_template

import sheets

# ==============================
# CONFIGURACIÓN DEL BOT
# ==============================
app = Flask(__name__)

GROUPME_API_URL = 'https://api.groupme.com/v3/bots/post'
GROUPME_BOT_ID = os.getenv("GROUPME_BOT_ID")
BOT_NAME = os.getenv("BOT_NAME", "Wild Palm Tree")

# ==============================
# FUNCIONES DE ENVÍO DE MENSAJES
# ==============================
def log(msg):
    print(str(msg))
    sys.stdout.flush()

def _post_to_groupme(data):
    """Función interna para enviar cualquier payload al bot."""
    try:
        response = requests.post(GROUPME_API_URL, json=data, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        log(f"Error enviando mensaje a GroupMe: {e}")
        return False

def send_message(msg):
    # GroupMe corta los mensajes de más de 1000 caracteres
    for i in range(0, max(len(msg), 1), 990):
        _post_to_groupme({'bot_id': GROUPME_BOT_ID, 'text': msg[i:i + 990]})
    return True

def send_image(msg, imageurl):
    data = {
        "bot_id": GROUPME_BOT_ID,
        "text": msg,
        "attachments": [{"type": "image", "url": imageurl}]
    }
    return _post_to_groupme(data)

def show_help():
    return (
        "📖 Comandos disponibles:\n"
        "- bot? → Saluda\n"
        "- rules! → Muestra las reglas\n"
        "- back out → Mensaje de salida\n"
        "- settings! → Ajustes del control\n"
        "- that's it for me boys / bye bye → Despedida\n"
        "- who is the best at halo? → Da un nombre (al azar)\n"
        "- do you speak spanish? → Responde si habla español\n"
        "- records! <mapa o modo> → Records de Big Team\n"
        "- squadrecords! <mapa o modo> → Records de Squad Battle\n"
        "- heavyrecords! <mapa o modo> → Records de Heavies\n"
        "- random! → Imagen al azar del archivo\n"
        "- mystats! → Tus estadísticas\n"
        "- daysoff! → Días libres\n"
        "- menu! / help → Esta lista"
    )

def safe(fn):
    """Si Google Sheets falla, el bot avisa en vez de tronar."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log(f"Error en {fn.__name__}: {e!r}")
            return send_message("My spreadsheet brain is not working right now 🌴🔥 try later")
    return wrapper

@safe
def cmd_records(kind, query):
    return send_message(sheets.format_records(kind, query))

@safe
def cmd_random_image():
    n, url = sheets.random_image()
    return send_image(f"Picking Random Image No{n} from Trees in Spaces Archive", url)

@safe
def cmd_mystats(sender_id):
    return send_message(sheets.personal_stats(sender_id))

@safe
def cmd_daysoff():
    return send_message(sheets.days_off())

@safe
def cmd_changed_name(text):
    m = re.match(r"^(.*) changed name to (.*)$", text.strip())
    if m:
        return send_message(sheets.update_name(m.group(1), m.group(2)))
    return None

def normalize(text):
    return (text or "").lower().replace("’", "'").replace("‘", "'").strip()

# ==============================
# PÁGINA WEB PÚBLICA
# ==============================
def site_data():
    return {
        "records": {kind: sheets.get_records(kind) for kind in sheets.RECORD_SHEETS},
        "members": sheets.get_members(),
        "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
    }

@app.route("/", methods=['GET'])
def home():
    try:
        data = site_data()
    except Exception as e:
        log(f"Error leyendo la hoja para la web: {e!r}")
        return "Trees in Space! (records unavailable right now)", 503
    return render_template("index.html", data_json=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))

@app.route("/api/records", methods=['GET'])
def api_records():
    return jsonify(site_data())

@app.route("/health", methods=['GET'])
def health():
    return "Trees in Space!", 200

# ==============================
# WEBHOOK DE GROUPME
# ==============================
@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json(silent=True) or {}
    originaldata = data.get('text') or ''
    text = normalize(originaldata)
    name = data.get('name', '')
    sender_id = data.get('sender_id', '')

    log(f"Recieved {data}")

    # ===== Ignorar respuestas del propio bot =====
    if data.get('sender_type') == 'bot' or name == BOT_NAME:
        return "ok", 200

    time.sleep(1)

    byebye = [
        f"night-night {name}", f"sweet dreams, I love you {name}", 
        "Bye Fucker", f"Adiós {name}", 
        f"Yeah, go away already. Everyone!, {name} is gone, lets play!"
    ]
    hihi = ["Hello", "Mande", "Yes?", "Hola", "uh?", f"{name}?"]
    rules_text = (
        "These are the Group rules (They also apply for the parties and any communication channels as a group)\n"
        "-) No discrimination\n-) No religion\n-) No politics (including other countries)\n-) No spamming"
    )
    rude = [
        f"Say that one more time and I wont sell you my bath water again.", f"Fuck you {name}", 
        "Yeah right, says the halo 4 lover", "Watch Out, this one learned from Drawn Together...🤪🤪",
        "Oh no, what do I do now? 💥💥 ", "No, tu chinga tu madre. pinche perro aguado", 
        "Nice . . . ", "I guess I'll cry now. or not, maybe ill find you and eat your waffles",
        "Is this the kind of language we're expected to use? I could have been cursing all this time. "
    ]
    ftbb = [
        "Fuck that bottom bitch", "hahaha Are you the new guy?", 
        "Well, lets say you might need to be central time","Tunisia Basketball Federation",
        "You have to ask burrito about it", "You have to ask Man of War about it, fr",
        "Dont be noosy", f"What is {name}?"
    ]
    spanish = [
        "Si", "Sometimes", "Yeah, turns out my father is Mexican, Can You belive it? I guess not everyone is going up the border after all", 
        "Yes but please dont tell ICE", "Yes sir, I can order TexMex the right way", "👍 🤠"
    ]
    trees = [
        "IntangibleFancy, He is 50% Intangible and 50% Fancy", "Andrew Says Ni, and some times says, hell no!! 🔫🔫",
        "S O Tyrik", "BattlebornValor", "Dark Samurai112", "TheDuDEwithAGuN if we ever see him playing",
        "Hmmvvee98, S7 sniper here ❎", "Hidan while cursing on spanish", "K00PA00, just like the one on mario bros",
        "Burrito, whenever he is not a simp with Kama", 
        "JRush77, you know how they say men are killers but gay people slay! ",
        "Nut but after bowls time", 
        "snakemagic, driving us to the victory, but please dont get out of the turrret, He's got the reptile yuyu 🐍🧙",
        "Man Of War, Set the defense, with a Hammer please 💢🔨", "Kama At Me Bro, or Sister", "Sinoooooooova, it's a Sinova"
    ]

    # ===== Comandos exactos =====
    comandos = {
        "bot?": lambda: send_message(random.choice(hihi)),
        "back out": lambda: send_message("Bowls Time!"),
        "backout": lambda: send_message("Bowls Time!"),
        "good bot": lambda: send_message("🐶"),
        "do you speak spanish?": lambda: send_message(random.choice(spanish)),
        "bot do you speak spanish?": lambda: send_message(random.choice(spanish)),
        "rules!": lambda: send_message(rules_text if random.randint(1,10)<8 else f"You know, I like you {name}, have this:\n https://www.youtube.com/watch?v=GaAUS0GsG_M"),
        "fuck me": lambda: send_message("If you gave a chance I would take it 🎵🎵") if name == "Man Of War" else None,
        "thats it for me boys": lambda: send_message(random.choice(byebye)),
        "that's it for me boys": lambda: send_message(random.choice(byebye)),
        "bye bye": lambda: send_message(random.choice(byebye)),
        "settings!": lambda: send_message(
            '***SENSITIVITY AND ACCELERATION \nlook acceleration 3.5\nlook sensitivity horizontal 3.5\nlook sensitivity vertical 3.5\n'
            '***TRIGGER DEADZONE\nLeft Inner DeadZone 0%\nLeft outer DeadZone 55%\nRight inner DeadZone 0%\nRight outer DeadZone 55%\n'
            '***MOVE THUMSTICK\ncenter Dedzone 1\nMax Input threshold 0.0\nAxial deadzone 0.0\n'
            '***LOOK THUMSTICK\nCenter deadzone 0\nMax Input threshold 0\nAxial deadzone 0.0'
        ),
        "fuck you bot": lambda: send_message(random.choice(rude)),
        "who is the best at halo?": lambda: send_message(random.choice(trees)),
        "what does ftbb mean?": lambda: send_message(random.choice(ftbb)),
        "random!": lambda: cmd_random_image(),
        "mystats!": lambda: cmd_mystats(sender_id),
        "daysoff!": lambda: cmd_daysoff(),
        "butthole!": lambda: send_message("you have reached the butthole limit of the month"),
        "menu!": lambda: send_message(show_help()),
        "menu": lambda: send_message(show_help()),
        "help": lambda: send_message(show_help()),
    }

    # ===== Comandos con argumento (ej. "records! breaker") =====
    con_argumento = {
        "heavyrecords!": "heavies",
        "squadrecords!": "squad",
        "records!": "btb",
    }

    # Mensaje del sistema de GroupMe cuando alguien cambia su nombre
    if name == "GroupMe" and "changed name to" in originaldata:
        cmd_changed_name(originaldata)
    elif text in comandos:
        comandos[text]()
    else:
        for prefix, kind in con_argumento.items():
            if text.startswith(prefix):
                cmd_records(kind, text[len(prefix):])
                break

    return "ok", 200

# ==============================
# FIN DEL ARCHIVO
# ==============================
if __name__ == '__main__':
    app.run(debug=True)
