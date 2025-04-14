import socket, sys, select
from collections import deque

def serve(port: int) -> None:

    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind((socket.gethostname(), port))
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


if __name__ == "__main__":
    serve(40000 if len(sys.argv) == 1 else sys.argv[1])
