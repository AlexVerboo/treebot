# ==============================
# IMPORTS
# ==============================
import os
import re
import sys
import hmac
import json
import random
import time
import platform
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import requests
from flask import Flask, request, jsonify, render_template

import alerts
import db
import player_page
import sheets
import roles
import scheduler
import snakemagic

# ==============================
# CONFIGURACIÓN DEL BOT
# ==============================
app = Flask(__name__)

GROUPME_API_URL = 'https://api.groupme.com/v3/bots/post'
GROUPME_BOT_ID = os.getenv("GROUPME_BOT_ID")
BOT_NAME = os.getenv("BOT_NAME", "Wild Palm Tree")
VERSION = "2.0.0-dev"
STARTED_AT = time.time()

# Secret in the GroupMe callback URL (https://.../?token=...). GroupMe does not
# sign its callbacks, so without this anyone who knows the URL could make the bot post.
# If WEBHOOK_TOKEN is not set, every POST is accepted (same as v1.0).
WEBHOOK_TOKEN = (os.getenv("WEBHOOK_TOKEN") or "").strip()

# Messages are processed in the background: GroupMe gets its "200 OK" right away
# and the bot answers a moment later. Two threads are enough for the group.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cmd")
_side_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="side")

# ==============================
# FUNCIONES DE ENVÍO DE MENSAJES
# ==============================
def log(msg):
    print(str(msg))
    sys.stdout.flush()

def _post_to_groupme(data, attempts=3):
    """Sends any payload to the bot. Retries on network errors, 429 and 5xx."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(GROUPME_API_URL, json=data, timeout=10)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.exceptions.HTTPError(f"GroupMe answered {response.status_code}")
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            log(f"Error sending to GroupMe (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(attempt)
    alerts.send("GroupMe rejected a bot message 3 times in a row.", key="groupme-post")
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
        "📖 Available commands:\n"
        "- bot? → Says hi\n"
        "- rules! → Shows the group rules\n"
        "- back out → Exit message\n"
        "- settings! → Controller settings\n"
        "- that's it for me boys / bye bye → Says goodbye\n"
        "- who is the best at halo? → Picks a name (at random)\n"
        "- do you speak spanish? → Find out if the bot speaks Spanish\n"
        "- records! <map or mode> → Big Team records\n"
        "- squadrecords! <map or mode> → Squad Battle records\n"
        "- heavyrecords! <map or mode> → Heavies records\n"
        "- random! → Random image from the archive\n"
        "- snakemagic! → Random video from snakemagic.com\n"
        "- mystats! → Your stats\n"
        "- daysoff! → Days off\n"
        "- ggs → Tonight's recap (wins, losses, top players)\n"
        "- menu! / help → This list"
    )

def safe(fn):
    """Si Google Sheets falla, el bot avisa en vez de tronar."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log(f"Error en {fn.__name__}: {e!r}")
            alerts.send(f"`{fn.__name__}` failed reading Google Sheets: {type(e).__name__}: {str(e)[:200]}",
                        key=f"sheets-{fn.__name__}")
            return send_message("My spreadsheet brain is not working right now 🌴🔥 try later")
    return wrapper

# ===== ggs: resumen de la noche =====
# El resumen necesita la API de Halo (SPNKr, Python 3.11+), que no corre en Render,
# así que el bot arranca el workflow "GGs summary" de GitHub y ese manda el resumen.
GH_DISPATCH_TOKEN = (os.getenv("GH_DISPATCH_TOKEN") or "").strip()
GH_REPO = os.getenv("GH_REPO", "AlexVerboo/treebot")
GGS_COOLDOWN = 300  # segundos entre resúmenes, para que no lo spameen
_last_ggs = [0.0]

def cmd_ggs():
    if not GH_DISPATCH_TOKEN:
        log("ggs: falta GH_DISPATCH_TOKEN en Render")
        return send_message("GGs! 🌴 (my boss still has to plug in the recap thing)")
    if time.time() - _last_ggs[0] < GGS_COOLDOWN:
        return send_message("Hold on, I'm already counting tonight's games 🌴🧮")
    try:
        r = requests.post(
            f"https://api.github.com/repos/{GH_REPO}/actions/workflows/ggs.yml/dispatches",
            headers={"Authorization": f"Bearer {GH_DISPATCH_TOKEN}",
                     "Accept": "application/vnd.github+json"},
            json={"ref": "master"}, timeout=10)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        log(f"ggs: no pude arrancar el workflow: {e!r}")
        return send_message("GGs! 🌴 (I couldn't get tonight's recap, try later)")
    _last_ggs[0] = time.time()
    return send_message("GGs! 🌴 Counting tonight's games, give me a minute or two...")

@safe
def cmd_records(kind, query):
    return send_message(sheets.format_records(kind, query))

@safe
def cmd_random_image():
    n, url = sheets.random_image()
    return send_image(f"Picking Random Image No{n} from Trees in Spaces Archive", url)

def cmd_snakemagic():
    msg = snakemagic.random_video()
    if not msg:
        return send_message("The snake is sleeping right now 🐍💤 try later (snakemagic.com)")
    return send_message(msg)

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

def roles_data():
    role_names, tags = sheets.get_roles()
    stats, updated = sheets.get_player_stats()
    key = lambda gt: gt.lower().replace(" ", "")
    tags_by_key = {key(gt): t for gt, t in tags.items()}
    profiles = {key(m["gamertag"]): m["profile"] for m in sheets.get_members()}
    players, seen = [], set()
    for gt in list(stats) + list(tags):
        k = key(gt)
        if k in seen:
            continue
        seen.add(k)
        players.append({
            "gamertag": gt,
            "roles": tags_by_key.get(k, []),
            "stats": stats.get(gt, {}),
            "profile": profiles.get(k, ""),
        })
    cfg = roles.page_config(role_names)
    cfg.update({"players": players, "updated": updated or "never"})
    return cfg

@app.route("/roles", methods=['GET'])
def roles_page():
    try:
        data = roles_data()
    except Exception as e:
        log(f"Error leyendo roles: {e!r}")
        return "Trees in Space! (roles unavailable right now)", 503
    return render_template("roles.html", data_json=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))

@app.route("/api/roles", methods=['GET'])
def api_roles():
    return jsonify(roles_data())

def _gt_key(gt):
    return "".join((gt or "").lower().split())


def _roles_for(gamertag):
    _, tags = sheets.get_roles()
    return next((t for gt, t in tags.items() if _gt_key(gt) == _gt_key(gamertag)), [])


def _profile_for(gamertag):
    return next((m["profile"] for m in sheets.get_members()
                 if _gt_key(m["gamertag"]) == _gt_key(gamertag)), "")


def player_data(gamertag):
    """(data, http status). data is None when there is nothing to show."""
    if not db.enabled():
        return None, 503
    try:
        return player_page.load(gamertag, roles_for=_roles_for, profile_for=_profile_for), 200
    except player_page.NotFound:
        return None, 404
    except Exception as e:
        log(f"Error building the player page for {gamertag!r}: {e!r}")
        alerts.send(f"Player page failed for `{gamertag[:40]}`: {type(e).__name__}: "
                    f"{str(e)[:200]}", key="player-page")
        return None, 503


_PLAYER_ERRORS = {404: "I don't know that Tree 🌴 (check the gamertag, or ask to be added)",
                  503: "Player stats are unavailable right now 🌴🔥 try later"}


@app.route("/player/<path:gamertag>", methods=['GET'])
def player_view(gamertag):
    data, status = player_data(gamertag)
    if data is None:
        return render_template("player.html", data_json="null", gamertag=gamertag,
                               error=_PLAYER_ERRORS[status]), status
    return render_template("player.html", gamertag=data["gamertag"], error="",
                           data_json=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


@app.route("/api/player/<path:gamertag>", methods=['GET'])
def api_player(gamertag):
    data, status = player_data(gamertag)
    if data is None:
        return jsonify({"error": _PLAYER_ERRORS[status]}), status
    return jsonify(data)


def _check_sheets():
    sheets._values(sheets.MEMBERS_SHEET)  # uses the 5-minute cache
    return "ok"


DB_HEALTH_TIMEOUT = float(os.getenv("DB_HEALTH_TIMEOUT", "4"))


def _check_database():
    return db.health(timeout=DB_HEALTH_TIMEOUT)


@app.route("/health", methods=['GET'])
def health():
    """Light check for the uptime monitor and Render. /health?deep=1 also checks Google Sheets
    and the database (keep the uptime monitor on the light one: the deep one wakes Neon up).
    Always answers 200 while the bot process is alive; a failing check shows as "degraded"."""
    body = {
        "status": "ok",
        "version": VERSION,
        "python": platform.python_version(),
        "uptime_s": int(time.time() - STARTED_AT),
        "checks": {
            "groupme_bot_id": "ok" if GROUPME_BOT_ID else "missing",
            "webhook_token": "on" if WEBHOOK_TOKEN else "off",
            "alerts": "on" if os.getenv("DISCORD_ALERT_WEBHOOK") else "off",
            "daily_scheduler": "on" if os.getenv("GH_DISPATCH_TOKEN") else "off",
        },
    }
    if request.args.get("deep"):
        # both checks run at the same time, each with its own short timeout
        sheets_job = _side_executor.submit(_check_sheets)
        db_job = _side_executor.submit(_check_database) if db.enabled() else None
        try:
            body["checks"]["sheets"] = sheets_job.result(timeout=8)
        except FutureTimeout:
            body["checks"]["sheets"] = "timeout"
        except Exception as e:
            body["checks"]["sheets"] = f"error: {type(e).__name__}"
        if db_job is None:
            body["checks"]["database"] = "off"
        else:
            try:
                info = db_job.result(timeout=DB_HEALTH_TIMEOUT + 1)
                body["checks"]["database"] = info["status"]
                body["last_ingest"] = info["last_ingest"]
            except FutureTimeout:
                body["checks"]["database"] = "timeout"
            except Exception as e:
                body["checks"]["database"] = f"error: {type(e).__name__}"
    if any(v not in ("ok", "on", "off") for v in body["checks"].values()):
        body["status"] = "degraded"
    return jsonify(body), 200


@app.before_request
def _daily_job_check():
    """On every request (the uptime monitor pings every 5 min), check in the
    background whether today's records job or the night ingestion still has to be started."""
    _side_executor.submit(scheduler.maybe_run_all)

# ==============================
# WEBHOOK DE GROUPME
# ==============================
@app.route('/', methods=['POST'])
def webhook():
    if WEBHOOK_TOKEN and not hmac.compare_digest(request.args.get("token", ""), WEBHOOK_TOKEN):
        log("Webhook rejected: wrong or missing token")
        return "forbidden", 403

    data = request.get_json(silent=True) or {}
    log(f"Recieved {data}")

    # ===== Ignorar respuestas del propio bot =====
    if data.get('sender_type') == 'bot' or data.get('name', '') == BOT_NAME:
        return "ok", 200

    # Answer GroupMe right away; the command runs in the background.
    _executor.submit(_handle_safely, data)
    return "ok", 200


def _handle_safely(data):
    try:
        handle_message(data)
    except Exception as e:
        log(f"Error handling message: {e!r}")
        alerts.send(f"The bot failed handling `{(data.get('text') or '')[:80]}`: "
                    f"{type(e).__name__}: {str(e)[:200]}", key="handle-message")


def handle_message(data):
    """Everything the bot does with a GroupMe message (same behavior as v1.0)."""
    originaldata = data.get('text') or ''
    text = normalize(originaldata)
    name = data.get('name', '')
    sender_id = data.get('sender_id', '')

    # Small pause so the answer shows up after the member's message
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
        "snakemagic!": lambda: cmd_snakemagic(),
        "snake!": lambda: cmd_snakemagic(),
        "mystats!": lambda: cmd_mystats(sender_id),
        "daysoff!": lambda: cmd_daysoff(),
        "ggs": lambda: cmd_ggs(),
        "ggs!": lambda: cmd_ggs(),
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

# ==============================
# FIN DEL ARCHIVO
# ==============================
if __name__ == '__main__':
    app.run(debug=True)
