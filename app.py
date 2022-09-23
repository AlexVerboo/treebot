import os
import sys
import groupy
from urllib.parse import urlencode
from groupy.client import Client as groupmeClient
from urllib.request import Request, urlopen
from flask import Flask, request
from selenium import webdriver
app = Flask(__name__)
@app.route('/', methods=['POST'])
def webhook():
  data = request.get_json()
  log('Recieved {}'.format(data))
  # We don't want to reply to ourselves!
  if data['name'] != 'Wild Palm Tree':
    if data['text'] == 'Bot?':
        #msg = '{}, you sent "{}".'.format(data['name'], data['text'])
        msg ='Yes?'.format(data['name'], data['text'])
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