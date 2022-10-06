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
  for i in range(len(sheet.get("B:B"))):
    if i:
      sheet.get("B:B")[i][0] = sheet.get("B:B")[i][0].lower()
possibilities = ["breaker", "fragmentation", "highpower", "deathlock"]
n = 1
cutoff = 0.8
comando = "records! deadlock"
mapa= comando[9:]
print (mapa)
close_matches = difflib.get_close_matches(mapa, 
                possibilities, n, cutoff)
print(close_matches)
ObtenerHoja(mapa)