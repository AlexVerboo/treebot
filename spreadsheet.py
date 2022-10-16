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
      str1 += ele +" "
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
data= {'attachments': [], 'avatar_url': None, 'created_at': 1665942450, 'group_id': '18341291', 'id': '166594245014720944', 'name': 'GroupMe', 'sender_id': 'system', 'sender_type': 'system', 'source_guid': '879297202fa8013b377c625eb7081970', 'system': True, 'text': 'Hidan changed name to UNHidan', 'user_id': '0'}
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
print(updatename(data['text']))