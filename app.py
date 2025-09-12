# =====================================
# 📌 Imports
# =====================================
import os
import requests
import random
import time
import gspread
from flask import Flask, request
from oauth2client.service_account import ServiceAccountCredentials

# =====================================
# 📌 Configuración inicial
# =====================================
# Flask: servidor que recibe webhooks de GroupMe
app = Flask(__name__)

# Configuración de acceso a Google Sheets
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

credentials = ServiceAccountCredentials.from_json_keyfile_name(
    'client_secret.json', scope
)
client = gspread.authorize(credentials)

# ID de la hoja de Google Sheets
spreadsheet = client.open_by_key("tu_google_sheet_id")

# Token del bot de GroupMe (cámbialo por tuyo)
BOT_ID = "tu_bot_id"

# =====================================
# 📌 Funciones utilitarias
# =====================================

def log(msg):
    """Imprime mensajes en consola para debug."""
    print(str(msg))


def send_message(msg):
    """Envía un mensaje de texto al chat de GroupMe."""
    url = 'https://api.groupme.com/v3/bots/post'
    data = {"bot_id": BOT_ID, "text": msg}
    response = requests.post(url, json=data)
    if response.status_code != 202:
        log(f"❌ Error enviando mensaje: {response.text}")


def send_image(img_url):
    """Envía una imagen al chat de GroupMe."""
    url = 'https://api.groupme.com/v3/bots/post'
    data = {"bot_id": BOT_ID, "text": "", "attachments": [{"type": "image", "url": img_url}]}
    response = requests.post(url, json=data)
    if response.status_code != 202:
        log(f"❌ Error enviando imagen: {response.text}")

# =====================================
# 📌 Funciones relacionadas con Google Sheets
# =====================================

def GetRecord(name):
    """Obtiene récord de la hoja 'Records' según el nombre."""
    worksheet = spreadsheet.worksheet("Records")
    records = worksheet.get_all_records()
    for r in records:
        if r["Name"].lower() == name.lower():
            return f"{r['Name']} → {r['Score']}"
    return "No encontré ese récord."

def GetHeavyRecord(name):
    """Obtiene récord de la hoja 'HeavyRecords'."""
    worksheet = spreadsheet.worksheet("HeavyRecords")
    records = worksheet.get_all_records()
    for r in records:
        if r["Name"].lower() == name.lower():
            return f"{r['Name']} → {r['Score']}"
    return "No encontré ese récord pesado."

def GetSquadRecord(name):
    """Obtiene récord de la hoja 'SquadRecords'."""
    worksheet = spreadsheet.worksheet("SquadRecords")
    records = worksheet.get_all_records()
    for r in records:
        if r["Name"].lower() == name.lower():
            return f"{r['Name']} → {r['Score']}"
    return "No encontré ese récord de escuadra."

# =====================================
# 📌 Respuestas predefinidas
# =====================================
rules = "Aquí van las reglas del juego 🎮"
hihi = ["😂 jajaja", "😎 eso estuvo bueno", "🔥 épico"]

# =====================================
# 📌 Rutas de Flask
# =====================================
@app.route('/', methods=['POST'])
def webhook():
    """Recibe mensajes desde GroupMe y responde según el contenido."""
    data = request.get_json()
    log(f"Mensaje recibido: {data}")

    if 'text' not in data:
        return "ok", 200

    text = data['text'].lower()

    # Comandos básicos
    if "bot?" in text:
        send_message(random.choice(hihi))

    elif "rules!" in text:
        send_message(rules)

    elif "records!" in text:
        send_message(GetRecord(text[9:]))

    elif "heavy!" in text:
        send_message(GetHeavyRecord(text[7:]))

    elif "squad!" in text:
        send_message(GetSquadRecord(text[7:]))

    return "ok", 200

# =====================================
# 📌 Main (para correr el servidor)
# =====================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
