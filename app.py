import os
import sys
import requests

from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import Flask, request
from selenium import webdriver
app = Flask(__name__)
byebye = ["night-night", "sweet dreams, I love you", "Bye Fucker","Adios","Yeah, go away already. Everyone!, They're gone, lets play!"]
@app.route("/", methods=['GET'])
def hello():
    return "Trees in Space!", 200
@app.route('/', methods=['POST'])
def webhook():
  data = request.get_json()
  data['text'] = data['text'].lower()
  log('Recieved {}'.format(data))
  # We don't want to reply to ourselves!
  if data['name'] != 'Wild Palm Tree':
    if data['text'] == 'bot?':
        #msg = '{}, you sent "{}".'.format(data['name'], data['text'])
        msg ='Yes?'.format(data['name'], data['text'])
        send_message(msg)
    if 'back out' in data['text'] or 'backout' in data['text']:
        msg ='Bowls Time!'.format(data['name'], data['text'])
        send_message(msg)
    if 'soft off' in data['text'] or 'softoff' in data['text']:
        msg ='Manos Voice: softoffsoftoffsoftoffsoftoff everybody SOFT OFF!'.format(data['name'], data['text'])
        send_message(msg)
    if 'that’s it for me boys' in data['text'] or 'bye bye' in data['text']:
        msg =random.choice(byebye).format(data['name'], data['text'])
        send_message(msg)
  return "ok", 200

def send_message(msg):
  url  = 'https://api.groupme.com/v3/bots/post'
  data = {
          'bot_id' : os.getenv('GROUPME_BOT_ID'),
          'text'   : msg,
         }
  #request = Request(url, urlencode(data).encode())
  request = requests.post(url, json = data)
  json = urlopen(request).read().decode()
  
def log(msg):
  print(str(msg))
  sys.stdout.flush()