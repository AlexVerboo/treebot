# ==============================
# IMPORTS
# ==============================
import os
import sys
import random
import time
import difflib
from urllib.request import urlopen

import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request

# ==============================
# CONFIGURACIÓN DEL BOT
# ==============================
app = Flask(__name__)

GROUPME_API_URL = 'https://api.groupme.com/v3/bots/post'
GROUPME_BOT_ID = os.getenv("GROUPME_BOT_ID")

# ==============================
# FUNCIONES DE ENVÍO DE MENSAJES
# ==============================
def log(msg):
    print(str(msg))
    sys.stdout.flush()

def _post_to_groupme(data):
    """Función interna para enviar cualquier payload al bot."""
    try:
        response = requests.post(GROUPME_API_URL, json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log(f"Error enviando mensaje a GroupMe: {e}")
        return None

def send_message(msg):
    data = {'bot_id': GROUPME_BOT_ID, 'text': msg}
    return _post_to_groupme(data)

def send_image(msg, imageurl):
    data = {
        "bot_id": GROUPME_BOT_ID,
        "text": msg,
        "attachments": [{"type": "image", "url": imageurl}]
    }
    return _post_to_groupme(data)

def tagall(msg, ids):
    data = {
        "bot_id": GROUPME_BOT_ID,
        "text": msg,
        "attachments": [{"type": "mentions", "user_ids": ids, "loci": []}]
    }
    return _post_to_groupme(data)

# ==============================
# FUNCIONES DE GOOGLE SHEETS
# ==============================
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('client_secret.json', scope)
    client = gspread.authorize(creds)
    return client

def GetRandomImage():
    client = get_gspread_client()
    sheet = client.open("Trees in space game Records").worksheet('Images')
    imagepick = str(random.randrange(0, 9260))
    imageurl = sheet.acell('A' + imagepick).value
    send_image(f"Picking Random Image No{imagepick} from Trees in Spaces Archive", imageurl)

def PersonalRecords(id):
    client = get_gspread_client()
    output = ""
    gamertags = client.open("Trees in space game Records").worksheet('Trees in Space Members').get("AB:AD")
    usergamertag = next((x[0] for x in gamertags if x[2] == id), "")
    if usergamertag:
        stats = client.open("Trees in space game Records").worksheet('Trees in Space Members').get("C2:I30")
        for x in stats:
            if x[0] == usergamertag:
                output += f"These are the stats for {usergamertag}\n"
                for y in range(len(x)):
                    output += f"{stats[0][y]} ➡️ {x[y]}\n"
    else:
        output = "I dont see your name on the Stats list. Tell my boss to update his shit.... NEXT!!!"
    return output

# ==============================
# UTILIDADES AUXILIARES
# ==============================
def listToString(s):
    return "".join(s)

def CloseMatch(str, posibilities):
    posibilities = [p.lower() for p in posibilities]
    matches = difflib.get_close_matches(str, posibilities, n=1, cutoff=0.8)
    return matches[0] if matches else None

def lastWord(string):
    return string.split()[-1]

def FlatList(List):
    return [item for sublist in List for item in sublist]

# ==============================
# RUTAS FLASK
# ==============================
@app.route("/", methods=['GET'])
def hello():
    return "Trees in Space!", 200

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    originaldata = data['text']
    text = data['text'].lower()
    name = data['name']
    sender_id = data.get('sender_id', '')

    log(f"Recieved {data}")
    time.sleep(1)

    # ===== Respuestas predefinidas =====
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

    # ===== Ignorar respuestas del propio bot =====
    if name == 'Wild Palm Tree':
        return "ok", 200

    # ===== Diccionario de comandos =====
    comandos = {
        "bot?": lambda: send_message(random.choice(hihi)),
        "back out": lambda: send_message("Bowls Time!"),
        "backout": lambda: send_message("Bowls Time!"),
        "good bot": lambda: send_message("🐶"),
        "do you speak spanish?": lambda: send_message(random.choice(spanish)),
        "rules!": lambda: send_message(rules_text if random.randint(1,10)<8 else f"You know, I like you {name}, have this:\n https://www.youtube.com/watch?v=GaAUS0GsG_M"),
        "fuck me": lambda: send_message("If you gave a chance I would take it 🎵🎵") if name == "Man Of War" else None,
        "thats it for me boys": lambda: send_message(random.choice(byebye)),
        "that’s it for me boys": lambda: send_message(random.choice(byebye)),
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
        "heavyrecords!": lambda: send_message(listToString(GetHeavyRecord(text[14:]))),
        "squadrecords!": lambda: send_message(listToString(GetSquadRecord(text[14:]))),
        "records!": lambda: send_message(listToString(GetRecord(text[9:]))),
        "random!": lambda: GetRandomImage(),
        "mystats!": lambda: send_message(PersonalRecords(sender_id)),
        "changed name": lambda: send_message(updatename(originaldata)) if name == "GroupMe" else None,
        "daysoff!": lambda: send_message(DaysOff()),
        "butthole!": lambda: send_message("you have reached the butthole limit of the month"),
    }

    # ===== Ejecutar comandos que coincidan =====
    for cmd, action in comandos.items():
        if cmd in text or (cmd == "changed name" and cmd in originaldata):
            result = action()
            if result is not None:
                break

    return "ok", 200

# ==============================
# FIN DEL ARCHIVO
# ==============================
if __name__ == '__main__':
    app.run(debug=True)
