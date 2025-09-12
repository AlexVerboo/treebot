# ==============================
# IMPORTS
# ==============================
import os
import sys
import requests
import random
import time
import gspread
import difflib
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import Flask, request
from selenium import webdriver
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# FLASK APP SETUP
# ==============================
app = Flask(__name__)

# Ruta GET para verificar que el bot corre
@app.route("/", methods=['GET'])
def hello():
    return "Trees in Space!", 200

# ==============================
# MAIN WEBHOOK
# ==============================
@app.route('/', methods=['POST'])
def webhook():
  data = request.get_json()
  originaldata = data['text']
  data['text'] = data['text'].lower()
  log('Recieved {}'.format(data))
  time.sleep(1)

  # Respuestas predefinidas
  byebye = ["night-night "+data['name'], "sweet dreams, I love you "+data['name'], "Bye Fucker","Adiós "+data['name'],"Yeah, go away already. Everyone!, "+data['name']+" is gone, lets play!"]
  hihi = ["Hello", "Mande","Yes?", "Hola","uh?",data['name']+"?"]
  rules = "These are the Group rules (They also apply for the parties and any communication channels as a group)\n-) No discrimination\n-) No religion\n-) No politics (including other countries)\n-) No spamming"
  rude = ["Say that one more time and I wont sell you my bath water again.", "Fuck you "+data['name'], "Yeah right, says the halo 4 lover","Watch Out, this one learned from Drawn Together...🤪🤪","Oh no, what do I do now? 💥💥 ","No, tu chinga tu madre. pinche perro aguado","Nice . . . ","I guess I'll cry now. or not, maybe ill find you and eat your waffles","Is this the kind of language we're expected to use? I could have been cursing all this time. "]
  ftbb = ["Fuck that bottom bitch","hahaha Are you the new guy?", "Well, lets say you might need to be central time","Tunisia Basketball Federation","You have to ask burrito about it", "You have to ask Man of War about it, fr","Dont be noosy", "What is "+data['name']+"?"]
  spanish = ["Si", "Sometimes","Yeah, turns out my father is Mexican, Can You belive it? I guess not everyone is going up the border after all", "Yes but please dont tell ICE","Yes sir, I can order TexMex the right way","👍 🤠"]
  trees =  ["IntangibleFancy, He is 50% Intangible and 50% Fancy","Andrew Says Ni, and some times says, hell no!! 🔫🔫","S O Tyrik","BattlebornValor","Dark Samurai112","TheDuDEwithAGuN if we ever see him playing","Hmmvvee98, S7 sniper here ❎","Hidan while cursing on spanish","K00PA00, just like the one on mario bros","Burrito, whenever he is not a simp with Kama","JRush77, you know how they say men are killers but gay people slay! ","Nut but after bowls time","snakemagic, driving us to the victory, but please dont get out of the turrret, He's got the reptile yuyu 🐍🧙","Man Of War, Set the defense, with a Hammer please 💢🔨","Kama At Me Bro, or Sister","Sinoooooooova, it's a Sinova"]

  # No queremos que el bot se responda a sí mismo
  # GetID(data['name'],data['user_id'])

  if data['name'] != 'Wild Palm Tree':
    # Respuestas básicas
    if data['text'] == 'bot?': send_message(random.choice(hihi))
    if 'back out' in data['text'] or 'backout' in data['text']: send_message('Bowls Time!')
    if 'good bot' in data['text']: send_message('🐶')
    if 'do you speak spanish?' in data['text'] and 'bot' in data['text']: send_message(random.choice(spanish))

    # Reglas del grupo
    if 'rules!' in data['text'] :
      if random.randint(1, 10) < 8 :
        msg = rules
        send_message(msg)
      else : 
        msg = 'You know, I like you '+data['name']+', have this:\n https://www.youtube.com/watch?v=GaAUS0GsG_M'
        send_message(msg)

    # Bromas personalizadas
    if 'fuck me' in data['text'] and data['name'] == 'Man Of War': send_message('If you gave a chance I would take it 🎵🎵')
    if 'thats it for me boys' in data['text'] or 'that’s it for me boys' in data['text'] or 'bye bye' in data['text']:
      send_message(random.choice(byebye))

    # Configuración del control
    if 'settings!' in data['text'] :
      send_message('***SENSITIVITY AND ACCELERATION \nlook acceleration 3.5\nlook sensitivity horizontal 3.5\nlook sensitivity vertical 3.5\n***TRIGGER DEADZONE\nLeft Inner DeadZone 0%\nLeft outer DeadZone 55%\nRight inner DeadZone 0%\nRight outer DeadZone 55%\n***MOVE THUMSTICK\ncenter Dedzone 1\nMax Input threshold 0.0\nAxial deadzone 0.0\n***LOOK THUMSTICK\nCenter deadzone 0\nMax Input threshold 0\nAxial deadzone 0.0')

    # Respuestas groseras
    if 'fuck' in data['text'] and 'you' in data['text'] and 'bot' in data['text']:
        send_message(random.choice(rude))

    # Preguntas sobre Halo
    if 'who is the best at halo?' in data['text'] or 'who is the best at halo' in data['text']:
        send_message(random.choice(trees))
    if 'what does ftbb mean?' in data['text'] in data['text']:
        send_message(random.choice(ftbb))

    # Consultas a Google Sheets
    if 'heavyrecords!' in data['text']:
        send_message(listToString(GetHeavyRecord(data['text'][14:])))
    if 'squadrecords!' in data['text']:
        send_message(listToString(GetSquadRecord(data['text'][14:])))
    if 'records!' in data['text']:
        send_message(listToString(GetRecord(data['text'][9:])))
    if 'random!' in data['text']:
        GetRandomImage()
    if 'mystats!' in data['text']:
        send_message(PersonalRecords(data['sender_id']))

    # Actualización de nombres
    if 'changed name' in originaldata and data['name'] == 'GroupMe':
        send_message(updatename(originaldata))

    # Días libres
    if 'daysoff!' in data['text'] :
        send_message(DaysOff())

    # Límite de insultos
    if 'butthole!' in data ['text'] :
        send_message('you have reached the butthole limit of the month')

    # Mención a todos (comentado)
    # if '@all' in data['text']:
    #     tagall('Calling All Trees', allids())

  return "ok", 200

# ==============================
# UTILIDADES DE ENVÍO DE MENSAJES
# ==============================
# =========================
# Variable global para el Bot ID
# =========================
GROUPME_BOT_ID = os.getenv("GROUPME_BOT_ID2")

# =========================
# Función para enviar mensajes de texto
# =========================
def send_message(msg):
    url = 'https://api.groupme.com/v3/bots/post'
    data = {
        'bot_id': GROUPME_BOT_ID,
        'text': msg,
    }
    request = requests.post(url, json=data)
    json = urlopen(request).read().decode()

# =========================
# Función para enviar imágenes
# =========================
def send_image(msg, imageurl):
    url = 'https://api.groupme.com/v3/bots/post'
    log(GROUPME_BOT_ID)
    data = {
        "bot_id": GROUPME_BOT_ID,
        "text": msg,
        "attachments": [
            {
                "type": "image",
                "url": imageurl
            }
        ]
    }
    request = requests.post(url, json=data)
    json = urlopen(request).read().decode()

# =========================
# Función para mencionar a todos
# =========================
def tagall(msg, ids):
    url = 'https://api.groupme.com/v3/bots/post'
    data = {
        "bot_id": GROUPME_BOT_ID,
        "text": msg,
        "attachments": [
            {
                "type": "mentions",
                "user_ids": ids,
                "loci": []
            }
        ]
    }
    request = requests.post(url, json=data)
    json = urlopen(request).read().decode()
# ==============================
# FUNCIONES DE LOGGING
# ==============================
def log(msg):
  print(str(msg))
  sys.stdout.flush()

# ==============================
# FUNCIONES DE GOOGLE SHEETS
# ==============================
# (GetRecord, GetHeavyRecord, GetSquadRecord, GetRandomImage, PersonalRecords, updatename, GetID, allids, DaysOff, etc.)
# → Aquí van todas tus funciones que interactúan con gspread
# (no modifiqué nada, solo indico que pertenecen a esta sección)

# ==============================
# OTRAS UTILIDADES
# ==============================
# listToString, CloseMatch, lastWord, FlatList
