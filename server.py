import socket, sys, select
from collections import deque

try:
    port = int(sys.argv[1])
except:
    port = 40000

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.bind(("localhost", port))
serversocket.setblocking(False)
serversocket.listen(5)

players = []
spectators = []

print(f"Server started on port {port}")

def cleanup():
    serversocket.close()
    for p in players:
        p.close()
    for s in spectators:
        s.close()

while True:
    ready_read, ready_write, _ = select.select([serversocket] + players, players + spectators, [])

    if serversocket in ready_read:
        (client, address) = serversocket.accept()

        print(f"Connection estabilished: {address}")

        if len(players) < 2:
            players.append(client)
        else:
            spectators.append(client)
        ready_read.remove(serversocket)
    for sock in ready_read:
        msg = sock.recv(2048)
        if msg == b'':
            cleanup()
            raise Exception("Socket closed")
        print(msg)
        for p in players:
            if p == sock:
                continue
            p.send(msg)
        for s in spectators:
            s.send(msg)
    ready_read.clear()

