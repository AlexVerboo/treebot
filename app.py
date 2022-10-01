import os
import sys
import requests
import random
import time

from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import Flask, request
from selenium import webdriver
app = Flask(__name__)
@app.route("/", methods=['GET'])
def hello():
    return "Trees in Space!", 200
@app.route('/', methods=['POST'])

def webhook():
  data = request.get_json()
  data['text'] = data['text'].lower()
  log('Recieved {}'.format(data))
  time.sleep( 1 )
  byebye = ["night-night "+data['name'], "sweet dreams, I love you "+data['name'], "Bye Fucker","Adiós "+data['name'],"Yeah, go away already. Everyone!, "+data['name']+" is gone, lets play!"]
  hihi = ["Hello", "Yes?", "Hola","uh?",data['name']+"?"]
  rules = "This are the Group rules (this also apply for the parties and any communication channels as a group)\n-) No discrimination\n-) No religion\n-) No politics (including other countries)\n-) No spamming"
  rude = ["Say that one more time and I wont sell you my bath water again.", "Fuck you "+data['name'], "Yeah right, says the halo 4 lover","Watch Out, this one learned from Drawn Together...🤪🤪","Oh no, what do I do now? 💥💥 "]
  # We don't want to reply to ourselves!
  if data['name'] != 'Wild Palm Tree':
    if data['text'] == 'bot?':
        #msg = '{}, you sent "{}".'.format(data['name'], data['text'])
        msg =random.choice(hihi).format(data['name'], data['text'])
        send_message(msg)
    if 'back out' in data['text'] or 'backout' in data['text']:
        msg ='Bowls Time!'.format(data['name'], data['text'])
        send_message(msg)
    if 'rules!' in data['text'] :
      if random.randint(1, 10) > 9 :
        msg =rules.format(data['name'], data['text'])
      else : 
        msg ='https://www.youtube.com/watch?v=GaAUS0GsG_M'.format(data['name'], data['text'])
      send_message(msg)
    #if 'fuck me' in data['text'] and data['name'] = :
     #   msg ='Manos Voice: softoffsoftoffsoftoffsoftoff everybody SOFT OFF!'.format(data['name'], data['text'])
      #  send_message(msg)
    if 'thats it for me boys' in data['text'] or 'that’s it for me boys' in data['text'] or'bye bye' in data['text']:
        msg =random.choice(byebye).format(data['name'], data['text'])
        send_message(msg)
    if 'fuck' in data['text'] and 'you' in data['text'] and 'bot' in data['text']:
        msg =random.choice(rude).format(data['name'], data['text'])
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