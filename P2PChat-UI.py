import sys
import os
import socket
import threading
import _thread
import time
import datetime
from tkinter import *

USERNAME = ""	
SYSTEM_STATUS = "STARTED"

SYNC_THREAD_SYNC_LOCK = threading.Lock()

# This is the hash function for generating a unique
# Hash ID for each peer.
# Source: http://www.cse.yorku.ca/~oz/hash.html
#
# Concatenate the peer's USERNAME, str(IP address), 
# and str(Port) to form the input to this hash function
#
def sdbm_hash(instr):
	hash = 0
	for c in instr:
		hash = int(ord(c)) + (hash << 6) + (hash << 16) - hash
	return hash & 0xffffffffffffffff


#
# Functions to handle user input
#

def do_User():
	if userentry.get():
		global SYSTEM_STATUS									
		if SYSTEM_STATUS != "JOINED" and SYSTEM_STATUS != "CONNECTED":
			global USERNAME	
			USERNAME = userentry.get()
			SYSTEM_STATUS = "NAMED"						
			CmdWin.insert(1.0, "\nRegister your username: "+USERNAME)
			userentry.delete(0, END)
		else:
			CmdWin.insert(1.0, "\nError: You have already joinned a chatroom with this username.")
	else:
		CmdWin.insert(1.0, "\nEnter your username: ")

def do_List():
	server_socket.send("L::\r\n".encode("ascii"))
	response = server_socket.recv(1024)							
	response = str(response.decode("ascii"))						
	if response:
		if response[0] == 'G':									
			response = response[2:-4]							
			if len(response) == 0:								
				CmdWin.insert(1.0, "\nNo active chatrooms")
			else:		
				rooms = response.split(":")
				for room in rooms:
					CmdWin.insert(1.0, "\n\t"+room)
				CmdWin.insert(1.0, "\nHere are the active chat rooms:")	
		elif response[0] == 'F':
			response = response[2:-4]	
			CmdWin.insert(1.0, "\nError fetching chatroom list: "+response)
	else:
		raise socket.error("IndexError due to broken socket")	

#http://stackoverflow.com/questions/38680508/how-to-vstack-efficiently-a-sequence-of-large-numpy-array-chunks
def chunker(array, chunkSize):
    return (array[pos:pos + chunkSize] for pos in range(0, len(array), chunkSize))	

USERS = []
TEMP = ""
ACTIVE_ROOM = ""

def do_Join():
	global SYSTEM_STATUS
	try:
		if userentry.get():
			if USERNAME != "":
				if not (SYSTEM_STATUS == "JOINED" or SYSTEM_STATUS == "CONNECTED"):
					global roomname 
					roomname = userentry.get()
					msg = "J:"+roomname+":"+USERNAME+":"+myIP+":"+myPort+"::\r\n"
					server_socket.send(msg.encode("ascii"))
					response = server_socket.recv(1024)
					response = str(response.decode("ascii"))
					
					if response:
						if response[0] == 'M':	
							response = response[2:-4]				
							members = response.split(":")				

							global TEMP 
							TEMP = members[0]					

							global USERS
							CmdWin.insert(1.0, "\nJoined chat room: "+roomname)
							for group in chunker(members[1:], 3):			
								USERS.append(group)
								CmdWin.insert(1.0, "\n\t"+str(group))
							CmdWin.insert(1.0, "\nHere are the members:")	
							SYSTEM_STATUS = "JOINED"
							userentry.delete(0, END)
					
							global ACTIVE_ROOM
							ACTIVE_ROOM = roomname				
							_thread.start_new_thread (keepAliveProcedure, ())	
							_thread.start_new_thread (serverProcedure, ())		
							findP2PPeer(USERS)	
						elif response[0] == 'F':
							response = response[2:-4]
							CmdWin.insert(1.0, "\nError performing JOIN req: "+response)
					else:
						raise socket.error("IndexError due to broken socket")
				else:
					CmdWin.insert(1.0, "\nAlready joined/connected to another chatroom!!")
			else:
				CmdWin.insert(1.0, "\nPlease set USERNAME first.")
		else:
			CmdWin.insert(1.0, "\nPlease enter room name!")
	except socket.error as err:
		print(str(err))
		CmdWin.insert(1.0, "\nConnection to Room Server broken, reconnecting;")
		server_socket.close()	
		_thread.start_new_thread (roomServerConnect, (do_Join, ))


def keepAliveProcedure():
	CmdWin.insert(1.0, "\nStarted KeepAlive Thread")
	while server_socket:						
		time.sleep(20)						
		updateUSERS("Keep Alive")				
		if SYSTEM_STATUS == "JOINED" or not FORWARD_LINKS:
			global USERS
			findP2PPeer(USERS)

MESSAGE_ID = 0
PREVIOUS_LINKS = []
FORWARD_LINKS = ()

def serverProcedure():
	sockfd = socket.socket()
	sockfd.bind( ('', int(myPort)) )
	while sockfd:
		sockfd.listen(5)					
		conn, address = sockfd.accept()
		print ("Accepted connection from" + str(address))	
		response = conn.recv(1024)
		response = str(response.decode("ascii"))
		
		if response:
			if response[0] == 'P':	
				response = response[2:-4]
				connectorInfo = response.split(":")
				connectorRoomname = connectorInfo[0]
				connectorUSERNAME = connectorInfo[1]
				connectorIP = connectorInfo[2]
				connectorPort = connectorInfo[3]
				connectorMESSAGE_ID = connectorInfo[4]
				global USERS			
				try:						
					memberIndex = USERS.index(connectorInfo[1:4])			
				except ValueError:									
					if updateUSERS("Server Procedure"):					
						try:
							memberIndex = USERS.index(connectorInfo[1:4])
						except ValueError:
							memberIndex = -1
							print("Unable to connect to " + str(address))
							conn.close()
					else:
						print("Unable to update member's list, so connection was rejected.")
						conn.close()					
				if memberIndex != -1:
					msg = "S:"+str(MESSAGE_ID)+"::\r\n"
					conn.send(msg.encode("ascii"))	
					concat = connectorUSERNAME + connectorIP + connectorPort
					PREVIOUS_LINKS.append(((connectorInfo[1:4],sdbm_hash(concat)), conn))		
					global SYSTEM_STATUS
					SYSTEM_STATUS = "CONNECTED"							
					_thread.start_new_thread (handlePeer, ("Backward", conn, ))			
					CmdWin.insert(1.0, "\n" + connectorUSERNAME + " has linked to me")
			else:
				conn.close()
		else:
			conn.close()									

HASH = []
CHAT = []
def handlePeer(linkType, conn):
	while conn:											
		response = conn.recv(1024)								
		response = str(response.decode("ascii"))
		
		if response:											
			if response[0] == 'T':							
				response = response[2:-4]
				msgInfo = response.split(":")
				room = msgInfo[0]								
			
				if room == ACTIVE_ROOM:								
					originHashID = msgInfo[1]
					originUSERNAME = msgInfo[2]
					originMESSAGE_ID = msgInfo[3]
					originMsgLen = msgInfo[4]
					originMsg = response[-(int(originMsgLen)):]				
					
					SYNC_THREAD_SYNC_LOCK.acquire()								
					global CHAT
					if (originHashID, originMESSAGE_ID) not in CHAT:				
						MsgWin.insert(1.0, "\n["+originUSERNAME+"] "+originMsg)
						CHAT.append((originHashID, originMESSAGE_ID))
						SYNC_THREAD_SYNC_LOCK.release()								
						echoMessage(originHashID, originUSERNAME, originMsg, originMESSAGE_ID)	
						arr = [member for member in HASH if str(member[1]) == str(originHashID) ] 
						if not arr:							
							print("Not found hash", str(arr))
							updateUSERS("Peer Handler")
					else:
						print("Recvd repeated message")
						SYNC_THREAD_SYNC_LOCK.release()							
				else:
					print("Recvd message from wrong chat room")
		else:
			break										
	
	if linkType == "Forward":					
		updateUSERS("Peer Quit")
		global FORWARD_LINKS
		FORWARD_LINKS = ()
		global SYSTEM_STATUS
		SYSTEM_STATUS = "JOINED"
		findP2PPeer(USERS)
	else:				
		global PREVIOUS_LINKS
		for back in PREVIOUS_LINKS:
			if back[1] == conn:
				PREVIOUS_LINKS.remove(back)
				break
		
def updateUSERS(*src):
	msg = "J:"+roomname+":"+USERNAME+":"+myIP+":"+myPort+"::\r\n"
	try:
		server_socket.send(msg.encode("ascii"))
		response = server_socket.recv(1024)
		response = str(response.decode("ascii"))
		if response:
			if response[0] == 'M':									
				now = datetime.datetime.now()
				print(src, "Performing JOIN at", now.strftime("%Y-%m-%d %H:%M:%S"))
				response = response[2:-4]
				members = response.split(":")
				global TEMP
				if TEMP != members[0]:						
					global USERS
					TEMP = members[0]
					USERS = []
					for group in chunker(members[1:], 3):
						USERS.append(group)
					print("Member list updated!")
					calculateHASH(USERS)						
				return True
			elif response[0] == 'F':								
				response = response[2:-4]
				CmdWin.insert(1.0, "\nError performing JOIN req: "+response)
				return False
		else:
			return False
	except:
		CmdWin.insert(1.0, "\nConnection to Room Server broken, reconnecting;")
		server_socket.close()	
		_thread.start_new_thread (roomServerConnect, (updateUSERS, ))		
		
def calculateHASH(USERS):
	global HASH 
	HASH = []
	for member in USERS:
		concat = ""									
		for info in member:
			concat = concat + info
		HASH.append((member,sdbm_hash(concat)))	
		if member[0] == USERNAME:							
			myInfo = member
	HASH = sorted(HASH, key=lambda tup: tup[1])						
	return myInfo

def findP2PPeer(USERS):
	myInfo = calculateHASH(USERS)
	global HASH
	global myHashID
	
	myHashID = sdbm_hash(USERNAME+myIP+myPort)									
	start = (HASH.index((myInfo, myHashID)) + 1) % len(HASH)						

	while HASH[start][1] != myHashID:										
		if [item for item in PREVIOUS_LINKS if item[0] == HASH[start]]:							
			start = (start + 1) % len(HASH) 
			continue
		else:
			peerSocket = socket.socket()
			try:						
				peerSocket.connect((HASH[start][0][1], int(HASH[start][0][2])))
			except:
				print("Cannot make peer socket connection with ["+HASH[start][0][1]+"], trying another peer")
				start = (start + 1) % len(HASH) 
				continue
			if peerSocket:										
				if P2PHandshake(peerSocket):								
					CmdWin.insert(1.0, "\nConnected via - " + HASH[start][0][0])
					global SYSTEM_STATUS
					SYSTEM_STATUS = "CONNECTED"							
					global FORWARD_LINKS				
					FORWARD_LINKS = (HASH[start], peerSocket)					
					_thread.start_new_thread (handlePeer, ("Forward", peerSocket, ))		
					break
				else:
					peerSocket.close()								
					start = (start + 1) % len(HASH) 
					continue
			else:
				peerSocket.close()									
				start = (start + 1) % len(HASH) 
				continue		
	if SYSTEM_STATUS != "CONNECTED":
		print("Unable to find forward connection")

def P2PHandshake(peer):
	peer.send("P:"+roomname+":"+USERNAME+":"+myIP+":"+myPort+":"+str(MESSAGE_ID)+"::\r\n".encode("ascii")) 
	response = peer.recv(1024)
	response = str(response.decode("ascii"))
	if response:
		if response[0] == 'S':
			return True
		else:
			return False

def do_Send():
	if userentry.get():
		if SYSTEM_STATUS == "JOINED" or SYSTEM_STATUS == "CONNECTED":
			global MESSAGE_ID
			MESSAGE_ID += 1
			MsgWin.insert(1.0, "\n["+USERNAME+"] "+userentry.get())
			echoMessage(myHashID, USERNAME, userentry.get(), MESSAGE_ID)
		else:
			CmdWin.insert(1.0, "\nNot joined any chat!")
	userentry.delete(0, END)	

def echoMessage(originHashID, USERNAME, message, MESSAGE_ID):
	msg = "T:"+roomname+":"+str(originHashID)+":"+USERNAME+":"+str(MESSAGE_ID)+":"+str(len(message))+":"+message+"::\r\n"
	if FORWARD_LINKS:
		if str(FORWARD_LINKS[0][1]) != str(originHashID):				
			FORWARD_LINKS[1].send(msg.encode("ascii"))		
			sentTo.append(str(FORWARD_LINKS[0][1]))
			
	for back in PREVIOUS_LINKS:							
		if str(back[0][1]) != str(originHashID):				
			back[1].send(msg.encode("ascii"))			
			sentTo.append(str(back[0][1]))

def roomServerConnect(callback):	
	global server_socket
	global serverip
	global serverPort
	global myIP
	
	while True:
		try:
			server_socket = socket.socket()
			server_socket.connect((serverip, int(serverPort)))
			myIP = server_socket.getsockname()[0]
			CmdWin.insert(1.0, "\nConnected to Room Server!")
			
			Butt01['state'] = 'normal'
			Butt02['state'] = 'normal'
			Butt03['state'] = 'normal'
			Butt04['state'] = 'normal'
			
			break		
		except ConnectionRefusedError:
			CmdWin.insert(1.0, "\nConnection Failed")
	
	callback()


def do_Quit():
	if server_socket:
		server_socket.close()
		print("Connection Terminated")
	sys.exit(0)

#
# Set up of Basic UI
#
win = Tk()
win.title("MyP2PChat")

#Top Frame for Message display
topframe = Frame(win, relief=RAISED, borderwidth=1)
topframe.pack(fill=BOTH, expand=True)
topscroll = Scrollbar(topframe)
MsgWin = Text(topframe, height='15', padx=5, pady=5, fg="red", exportselection=0, insertofftime=0)
MsgWin.pack(side=LEFT, fill=BOTH, expand=True)
topscroll.pack(side=RIGHT, fill=Y, expand=True)
MsgWin.config(yscrollcommand=topscroll.set)
topscroll.config(command=MsgWin.yview)

#Top Middle Frame for buttons
topmidframe = Frame(win, relief=RAISED, borderwidth=1)
topmidframe.pack(fill=X, expand=True)
Butt01 = Button(topmidframe, width='8', relief=RAISED, text="User", state=DISABLED, command=do_User)
Butt01.pack(side=LEFT, padx=8, pady=8);
Butt02 = Button(topmidframe, width='8', relief=RAISED, text="List", state=DISABLED, command=do_List)
Butt02.pack(side=LEFT, padx=8, pady=8);
Butt03 = Button(topmidframe, width='8', relief=RAISED, text="Join", state=DISABLED, command=do_Join)
Butt03.pack(side=LEFT, padx=8, pady=8);
Butt04 = Button(topmidframe, width='8', relief=RAISED, text="Send", state=DISABLED, command=do_Send)
Butt04.pack(side=LEFT, padx=8, pady=8);
Butt05 = Button(topmidframe, width='8', relief=RAISED, text="Quit", command=do_Quit)
Butt05.pack(side=LEFT, padx=8, pady=8);

#Lower Middle Frame for User input
lowmidframe = Frame(win, relief=RAISED, borderwidth=1)
lowmidframe.pack(fill=X, expand=True)
userentry = Entry(lowmidframe, fg="blue")
userentry.pack(fill=X, padx=4, pady=4, expand=True)

#Bottom Frame for displaying action info
bottframe = Frame(win, relief=RAISED, borderwidth=1)
bottframe.pack(fill=BOTH, expand=True)
bottscroll = Scrollbar(bottframe)
CmdWin = Text(bottframe, height='15', padx=5, pady=5, exportselection=0, insertofftime=0)
CmdWin.pack(side=LEFT, fill=BOTH, expand=True)
bottscroll.pack(side=RIGHT, fill=Y, expand=True)
CmdWin.config(yscrollcommand=bottscroll.set)
bottscroll.config(command=CmdWin.yview)


def main():
	global serverip
	global serverPort
	global myPort

	if len(sys.argv) != 4:
		print("P2PChat.py <server address> <server port no.> <my port no.>")
		sys.exit(2)

	_ , serverip, serverPort, myPort = sys.argv

	#Thread for running the server
	_thread.start_new_thread (roomServerConnect, (do_User, ))
	
	win.mainloop()


if __name__ == "__main__":
	main()