import os
import sys
import requests
headers = 
{
 'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)     Chrome/37.0.2049.0 Safari/537.36'
}

r = requests.get('http://www.booking.com/reviewlist.html?cc1=tr;pagename=sapphire', headers=headers)
print r
print r.headers
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, request

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
  request = Request(url, urlencode(data).encode())
  json = urlopen(request).read().decode()
  
def log(msg):
  print(str(msg))
  sys.stdout.flush()