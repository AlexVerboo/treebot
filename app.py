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
  hihi = ["Hello", "Mande","Yes?", "Hola","uh?",data['name']+"?"]
  rules = "These are the Group rules (They also apply for the parties and any communication channels as a group)\n-) No discrimination\n-) No religion\n-) No politics (including other countries)\n-) No spamming"
  rude = ["Say that one more time and I wont sell you my bath water again.", "Fuck you "+data['name'], "Yeah right, says the halo 4 lover","Watch Out, this one learned from Drawn Together...🤪🤪","Oh no, what do I do now? 💥💥 "]
  spanish = ["Si", "Sometimes","Yeah, turns out my father is Mexican, Can You belive it? I guess not everyone is going up the border after all", "Yes but please dont tell ICE","Yes sir, I can order TexMex the right way","👍 🤠"]
  trees =  ["IntangibleFancy","Andrew Says Ni, and some times says, hell no!! 🔫🔫","S O Tyrik","BattlebornValor","Dark Samurai112","TheDuDEwithAGuN if we ever see him playing","Hmmvvee98, S7 sniper here ❎","Hidan while cursing on spanish","K00PA00","Burrito, whenever he is not a simp with Kama","JRush77, you know how they say men are killers but gay people slay! ","Nut but after bowls time","snakemagic, He's got the reptile yuyu 🐍🧙","Man Of War, Set the defense, with a Hammer please 💢🔨","Kama At Me Bro, or Sister","WalkingWuhan","Sinova"]
  # We don't want to reply to ourselves!
  if data['name'] != 'Wild Palm Tree':
    if data['text'] == 'bot?': send_message(random.choice(hihi))
    if 'back out' in data['text'] or 'backout' in data['text']: send_message('Bowls Time!')
    if 'good bot' in data['text']: send_message('🐶')
    if 'do you speak spanish?' in data['text'] and 'bot' in data['text']: send_message(random.choice(spanish))
    if 'rules!' in data['text'] :
      if random.randint(1, 10) < 8 :
        msg =rules
        send_message(msg)
      else : 
        msg ='You know, I like you '+data['name']+', have this:\n https://www.youtube.com/watch?v=GaAUS0GsG_M'
        send_message(msg)
    if 'fuck me' in data['text'] and data['name'] == 'Man Of War': send_message('If you gave a chance I would take it 🎵🎵')
    if 'thats it for me boys' in data['text'] or 'that’s it for me boys' in data['text'] or'bye bye' in data['text']:
      send_message(random.choice(byebye))
    if 'fuck' in data['text'] and 'you' in data['text'] and 'bot' in data['text']:
        send_message(random.choice(rude))
    if 'who is the best at halo?' in data['text'] or 'who is the best at halo' in data['text']:
        send_message(random.choice(trees))
    if 'records!' in data['text']:
        send_message(listToString(GetRecord(data['text'][9:])))
    if 'random!' in data['text']:
        GetRandomImage()
    if 'mystats!' in data['text']:
        send_message(PersonalRecords(data['name']))
  return "ok", 200

def send_message(msg):
  url  = 'https://api.groupme.com/v3/bots/post'
  data = {
          'bot_id' : os.getenv('GROUPME_BOT_ID'),
          'text'   : msg,
         }
  request = requests.post(url, json = data)
  json = urlopen(request).read().decode()
def send_image(msg,imageurl):
  url  = 'https://api.groupme.com/v3/bots/post'
  data = {
          "bot_id"  : os.getenv('GROUPME_BOT_ID'),
          "text"    :  msg,
          "attachments" : [
            {
              "type"  : "image",
              "url"   : imageurl
            }
          ]
        }
  request = requests.post(url, json = data)
  json = urlopen(request).read().decode()  
def log(msg):
  print(str(msg))
  sys.stdout.flush()
def GetRecord(mapa):
  scope = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']
  creds = ServiceAccountCredentials.from_json_keyfile_name(
      'client_secret.json', scope)
  client = gspread.authorize(creds)
  sheet = client.open("Trees in space game Records").sheet1
  MatrizRecords = sheet.get("B:D")
  ListaMapas = []
  for sublist in sheet.get("C:C"):
      for item in sublist:
          ListaMapas.append(item)
  seleccion=CloseMatch(mapa,ListaMapas)
  ListaGameModes = []
  for sublist in sheet.get("B:B"):
      for item in sublist:
          ListaGameModes.append(item)
  if seleccion:
    output="These are the records for MAP " +seleccion+" \n "
    for x in MatrizRecords:
        if x:
            if x[1].lower() == seleccion:
                output+= x[0]+" "+ x[2]+"\n "
  elif CloseMatch(mapa,ListaGameModes):
    output="These are the records for GAMEMODE " +CloseMatch(mapa,ListaGameModes)+" \n "
    for x in MatrizRecords:
        if x:
            if x[0].lower() == CloseMatch(mapa,ListaGameModes):
                output+= x[1]+" "+ x[2]+"\n "
  else:
    output = "Yeah, dude, I dont see that one on the Big team maps or GameModes"
  return output
def listToString(s):
  str1 = ""
  for ele in s:
      str1 += ele
  return str1
def CloseMatch(str,posibilities):
  for i in range(len(posibilities)):
    if i:
      posibilities[i] = posibilities[i].lower()
  n = 1
  cutoff = 0.8
  close_matches = difflib.get_close_matches(str, 
                posibilities, n, cutoff)
  if close_matches: return(close_matches[0])
  else: return(close_matches)
def GetRandomImage():
  scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
  creds = ServiceAccountCredentials.from_json_keyfile_name(
    'client_secret.json', scope)
  client = gspread.authorize(creds)
  sheet = client.open("Trees in space game Records").worksheet('Images')
  imagepick = str(random.randrange(0,9260))
  imageurl= sheet.acell('A'+imagepick).value
  send_image("Picking Random Image  No"+imagepick+" from Trees in Spaces Archive", imageurl)
def PersonalRecords(nombre):
  scope = ['https://spreadsheets.google.com/feeds',
  'https://www.googleapis.com/auth/drive']
  creds = ServiceAccountCredentials.from_json_keyfile_name(
   'client_secret.json', scope)
  client = gspread.authorize(creds)
  output=""
  gamertags =client.open("Trees in space game Records").worksheet('Trees in Space Members').get("C21:D35")
  for x in gamertags:
      if x[1]==nombre:
          usergamertag=x[0]
  if usergamertag:
    statsmatiz = client.open("Trees in space game Records").worksheet('Trees in Space Members').get("C2:H19")
    for x in statsmatiz:
        if x[0]==usergamertag:
            output +="These are the stats for " +nombre+"\n"
            for y in range(len(x)):
                output +=  statsmatiz[0][y]+ " ➡️   "+x[y]+"\n"
  else:  output+="I dont see your name on the Stats list. Tell my boss to update his shit....  NEXT!!!"
  return (output)