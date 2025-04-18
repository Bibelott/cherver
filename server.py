import socket, sys, select

class Connection:

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.sock.setblocking(False)

        self.send_queue: bytearray = bytearray()

    def queue_write(self, msg: str) -> None:
        self.send_queue.extend(bytes(f"{str(len(msg)).rjust(3)}{msg}", encoding="ascii"))

    def write(self) -> None:
        sent = self.sock.send(self.send_queue)

        if sent == 0:
            raise Exception("Socket closed unexpectedly")

        self.send_queue = self.send_queue[sent:]

    @property
    def queue_empty(self) -> bool:
        return len(self.send_queue) == 0


class Player(Connection):

    def __init__(self, sock: socket.socket) -> None:
        super().__init__(sock)

        self.read_buf = bytearray(1024)
        self.read_prog = 0
        self.msg_len = 0

    def read(self) -> str | None:
        prefix = False

        if self.read_prog == self.msg_len:
            self.msg_len = 3
            self.read_prog = 0
            prefix = True
        
        view = memoryview(self.read_buf)

        bytes_read = self.sock.recv_into(view[self.read_prog:], min(self.msg_len - self.read_prog, 1024))

        if bytes_read == 0:
            raise Exception("Socket closed unexpectedly")

        self.read_prog += bytes_read

        if self.read_prog == self.msg_len:
            msg = self.read_buf.decode("ascii")[:self.msg_len]
            if prefix:
                self.msg_len = int(msg) + 3
            else:
                return msg[3:]

        return None

class Game:

    def __init__(self) -> None:

        self.white: Player = None
        self.black: Player = None

        self.write_to: list[Connection] = []

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.setblocking(False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    def shutdown(self) -> None:
        print("Shutting down...")

        for con in self.write_to:
            print(f"Closing connection to {con.sock.getpeername()}")
            con.sock.close()

        self.serversocket.close()
        
    def serve(self, port: int) -> None:

        self.serversocket.bind((socket.gethostname(), port))
        self.serversocket.listen(5)

        print(f"Server started on port {port}")

        read_from = [self.serversocket]

        while True:
            ready_read, ready_write, _ = select.select(read_from, [c.sock for c in self.write_to if not c.queue_empty], [], 0.5)

            if self.serversocket in ready_read:
                (client, address) = self.serversocket.accept()

                print(f"Connection estabilished: {address}")

                if self.white is None or self.black is None:
                    player = Player(client)

                    if self.white is None:
                        self.white = player
                    else:
                        self.black = player

                    self.write_to.append(player)
                    read_from.append(player.sock)
                else:
                    self.write_to.append(Connection(client))
                ready_read.remove(self.serversocket)

            for sock in ready_read:
                if self.white.sock == sock:
                    player = self.white
                else:
                    player = self.black

                msg = player.read()

                if msg == None:
                    continue

                print(msg)

                for c in self.write_to:
                    if c == player:
                        continue
                    c.queue_write(msg)

            for sock in ready_write:
                for c in self.write_to:
                    if c.sock == sock:
                        con = c
                
                try:
                    con.write()
                except:
                    if con != self.white and con != self.black:
                        print(f"Spectator at {con.sock.getpeername()} closed unexpectedly. Anyway...")
                        con.sock.close()
                        self.write_to.remove(con)
                    else:
                        raise Exception("Socket closed unexpectedly")


if __name__ == "__main__":
    with Game() as game:
        try:
            game.serve(40000 if len(sys.argv) == 1 else int(sys.argv[1]))
        except:
            pass
