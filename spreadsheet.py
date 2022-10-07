import gspread
import difflib
from oauth2client.service_account import ServiceAccountCredentials
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(
    'client_secret.json', scope)
client = gspread.authorize(creds)
sheet = client.open("Trees in space game Records").sheet1
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

possibilities = ["breaker", "fragmentation", "highpower", "deathlock"]
comando = "records! deaDlock"
mapa= comando[9:]
flat_list = []
for sublist in sheet.get("C:C"):
    for item in sublist:
        flat_list.append(item)
seleccion=CloseMatch(mapa,flat_list)
print (seleccion)
print (sheet.get("A:D"))