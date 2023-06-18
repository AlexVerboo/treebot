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
#from selenium import webdriver
from oauth2client.service_account import ServiceAccountCredentials
def GetHeavyRecord(mapa):
  scope = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']
  creds = ServiceAccountCredentials.from_json_keyfile_name(
      'client_secret.json', scope)
  client = gspread.authorize(creds)
  sheet = client.open("Trees in space game Records").worksheet('Heavies')
  MatrizRecords = sheet.get("A:D")
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
            if x[2].lower() == seleccion:
                output+= x[0]+"\t➡️\t"+x[1]+" "+ x[3]+"\n "
  elif CloseMatch(mapa,ListaGameModes):
    output="These are the records for GAMEMODE " +CloseMatch(mapa,ListaGameModes)+" \n "
    for x in MatrizRecords:
        if x:
            if x[1].lower() == CloseMatch(mapa,ListaGameModes):
                output+= x[0]+"\t➡️\t"+x[2]+" "+ x[3]+"\n "
  else:
    output = "Yeah, dude, I dont see that one on the Big team maps or Heavies GameMode"
  return output

data=input('Enter text')
if 'heavyrecords!' in data['f']:
        print(listToString(GetHeavyRecord(data['text'][9:])))