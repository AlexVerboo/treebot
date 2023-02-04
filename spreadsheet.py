from inspect import getsource
import gspread
import difflib
from oauth2client.service_account import ServiceAccountCredentials

scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(
    'client_secret.json', scope)
client = gspread.authorize(creds)
sheet = client.open("Trees in space game Records").worksheet('Images')
def listToString(s):
  str1 = ""
  for ele in s:
      str1 += ele
  return str1
def ObtenerHoja(mapa):
  scope = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']
  creds = ServiceAccountCredentials.from_json_keyfile_name(
      'client_secret.json', scope)
  client = gspread.authorize(creds)
  sheet = client.open("Trees in space game Records").sheet1
  list_of_hashes = sheet.get("B:D")
  output="Estos son los records del mapa :" +mapa+ " \n "
  for x in list_of_hashes:
      if x:
          if x[1].lower() == mapa:
              output+= x[0]+" "+ x[2]+"\n "
  print(sheet.get("B:B"))
def CloseMatch(str,posibilities):
    for i in range(len(posibilities)):
        if i:
             posibilities[i] = posibilities[i].lower()
    n = 1
    cutoff = 0.8
    close_matches = difflib.get_close_matches(str, 
                  posibilities, n, cutoff)

    return(close_matches)
data= {'attachments': [], 'avatar_url': 'https://i.groupme.com/500x500.jpeg.ba080d68abbe4da3b4f1d5927d6bc04e', 'created_at': 1673903869, 'group_id': '18341291', 'id': '167390386935244807', 'name': 'Hidan', 'sender_id': '96917940', 'sender_type': 'user', 'source_guid': 'f772ed5c-0e4b-431b-be4e-9f909fcdf9a4', 'system': False, 'text': 'records! breaker', 'user_id': '96917940'}
data['text'] = data['text'].lower()
#possibilities = ["breaker", "fragmentation", "highpower", "deathlock"]
#comando = "records! deaDlock"
#mapa= comando[9:]
#flat_list = []
#for sublist in sheet.get("C:C"):
#    for item in sublist:
#        flat_list.append(item)
#seleccion=CloseMatch(mapa,flat_list)
#print (seleccion)
#print (sheet.get("A:D"))
def FlatList(List):
    flatlist = []
    for sublist in List:
      for item in sublist:
          flatlist.append(item)
    return(flatlist)
def PersonalRecords(nombre):
    usergamertag =""
    output=""
    gamertags =client.open("Trees in space game Records").worksheet('Trees in Space Members').get("AA:AB")
    for x in gamertags:
        print (x)
        if x[1]==nombre:
            usergamertag=x[0]      
    if usergamertag:
        statsmatiz = client.open("Trees in space game Records").worksheet('Trees in Space Members').get("C3:H20")
        for x in statsmatiz:
            if x[0]==usergamertag:
                output +="This are the stats for " +usergamertag+"\n"
                for y in range(len(x)):
                    output +=  statsmatiz[0][y]+ " =>  "+x[y]+"\n"
    else: output+="I dont see your name on the Stats list. Tell my boss to update his shit....  NEXT!!!"
    return (output)
def lastWord(string):
    # split by space and converting
    # string to list and
    lis = list(string.split(" "))
    # length of list
    length = len(lis)
    # returning last element in list
    return lis[length-1]
def updatename(string):
    sheet=client.open("Trees in space game Records").worksheet('Trees in Space Members')
    groupmenames=sheet.get("AB:AB")
    cell=''
    for x in range(len(groupmenames)):
        if groupmenames[x][0] == string.split()[0]: 
            cell=str(x+1)
    if cell:
        outpout= 'I will update '+ string.split()[0]+' to '+lastWord(string)
        sheet.update('AB'+cell,lastWord(string))
    else:outpout='For starters, I dont know who you are, you may want to add your name to the list'
    return(outpout)

def GetID(string,string2):
    sheet=client.open("Trees in space game Records").worksheet('Trees in Space Members')
    groupmenames=sheet.get("AB:AB")
    cell=''
    for x in range(len(groupmenames)):
        if groupmenames[x][0] == string: 
            cell=str(x+1)
    if cell:
        sheet.update('AC'+cell,string2)
def tagall():
    sheet=client.open("Trees in space game Records").worksheet('Trees in Space Members')
    groupmenames=FlatList(sheet.get("AC:AC"))
    print(groupmenames)
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
  print(seleccion)
  ListaGameModes = []
  for sublist in sheet.get("B:B"):
      for item in sublist:
          ListaGameModes.append(item)
  if seleccion:
    output="These are the records for MAP " +seleccion[0]+" \n "
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
def DaysOff():
    scope = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(
      'client_secret.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trees in space game Records").worksheet('Unofficial Medals')
    output=""
    for item in FlatList(sheet.get("A:A")):
        output +=item +"\n "
    return output
print (DaysOff())