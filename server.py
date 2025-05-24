import socket, sys, select
from enum import Enum

class IncorrectMove(Exception):
    pass

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

    def blocking_write(self, msg: str) -> None:
        self.queue_write(msg)
        while not self.queue_empty:
            self.write()

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

    def blocking_read(self) -> str:
        while (msg := read) is None:
            pass
        return msg

class Piece(Enum):
    NONE = 0

    PAWN_W = 1
    ROOK_W = 2
    KNIGHT_W = 3
    BISHOP_W = 4
    QUEEN_W = 5
    KING_W = 6

    PAWN_B = 9
    ROOK_B = 10
    KNIGHT_B = 11
    BISHOP_B = 12
    QUEEN_B = 13
    KING_B = 14

class Game:

    START_POS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    WHITE_TURN = 0
    BLACK_TURN = 1

    def __init__(self) -> None:

        self.white: Player = None
        self.black: Player = None

        self.write_to: list[Connection] = []

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.setblocking(False)

        self.move = 1
        self.caclock = 0

        self.in_progress = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    def fen_decode(self, FEN: str) -> None:

        self.board: list[list[Piece]] = []

        rank: list[Piece] = []
        for i, p in enumerate(FEN):
            at = i
            match p:
                case 'P':
                    rank.append(Piece.PAWN_W)
                case 'R':
                    rank.append(Piece.ROOK_W)
                case 'N':
                    rank.append(Piece.KNIGHT_W)
                case 'B':
                    rank.append(Piece.BISHOP_W)
                case 'Q':
                    rank.append(Piece.QUEEN_W)
                case 'K':
                    rank.append(Piece.KING_W)

                case 'p':
                    rank.append(Piece.PAWN_B)
                case 'r':
                    rank.append(Piece.ROOK_B)
                case 'n':
                    rank.append(Piece.KNIGHT_B)
                case 'b':
                    rank.append(Piece.BISHOP_B)
                case 'q':
                    rank.append(Piece.QUEEN_B)
                case 'k':
                    rank.append(Piece.KING_B)

                case '/':
                    if len(rank) != 8:
                        raise Exception("Incorrect FEN string", FEN)

                    self.board.append(rank.copy())
                    rank.clear()

                case ' ':
                    if len(rank) != 8:
                        raise Exception("Incorrect FEN string", FEN)

                    self.board.append(rank.copy())
                    break

                case _:
                    rank.extend([Piece.NONE for _ in range(int(p))])

        i += 1

        if FEN[i] == 'w':
            self.turn = self.WHITE_TURN
        elif FEN[i] == 'b':
            self.turn == self.BLACK_TURN
        else:
            raise Exception("Incorrect FEN string", FEN)
        
        i += 9

        next_space = FEN.find(" ", i)
        self.caclock = int(FEN[i:next_space])

        i = next_space + 1

        self.move = int(FEN[i:])
            

    def fen_encode(self) -> str:

        FEN = ""

        for rank in self.board:
            no_len = 0
            for piece in rank:
                if piece == Piece.NONE:
                    no_len += 1
                    continue
                
                if no_len > 0:
                    FEN += str(no_len)
                    no_len = 0

                match piece:
                    case Piece.PAWN_W:
                        FEN += 'P'
                    case Piece.ROOK_W:
                        FEN += 'R'
                    case Piece.KNIGHT_W:
                        FEN += 'N'
                    case Piece.BISHOP_W:
                        FEN += 'B'
                    case Piece.QUEEN_W:
                        FEN += 'Q'
                    case Piece.KING_W:
                        FEN += 'K'

                    case Piece.PAWN_B:
                        FEN += 'p'
                    case Piece.ROOK_B:
                        FEN += 'r'
                    case Piece.KNIGHT_B:
                        FEN += 'n'
                    case Piece.BISHOP_B:
                        FEN += 'b'
                    case Piece.QUEEN_B:
                        FEN += 'q'
                    case Piece.KING_B:
                        FEN += 'k'

            FEN += '/'

        FEN += ' '
        FEN += 'w' if self.turn == self.WHITE_TURN else 'b'

        FEN += 'KQkq'  # Change when we have castling
        FEN += ' '
        FEN += '-'  # Change when we have en passant
        FEN += ' '
        FEN += str(self.caclock)
        FEN += ' '
        FEN += str(self.move)

        return FEN

    def get_piece(self, r: int, f: int) -> Piece | None:
        if r < 0 or r >= 8 or f < 0 or f >= 8:
            return None
        
        return self.board[r][f]
    
    def get_possible_moves(self, r: int, f: int) -> list[tuple[int, int]]:
        piece = self.board[r][f]

        moves: list[tuple[int, int]] = []

        if piece == Piece.NONE:
            return []

        elif piece == Piece.PAWN_W:
            if self.get_piece(r - 1, f) == Piece.NONE:
                moves.append((r - 1, f))
                if r == 6:
                    moves.append((r - 2, f))

            if self.get_piece(r - 1, f - 1) not in [None, Piece.NONE]:
                moves.append((r - 1, f - 1))

            if self.get_piece(r - 1, f + 1) not in [None, Piece.NONE]:
                moves.append((r - 1, f + 1))

        elif piece == Piece.PAWN_B:
            if self.get_piece(r + 1, f) == Piece.NONE:
                moves.append((r + 1, f))
                if r == 1:
                    moves.append((r + 2, f))

            if self.get_piece(r + 1, f - 1) not in [None, Piece.NONE]:
                moves.append((r + 1, f - 1))

            if self.get_piece(r + 1, f + 1) not in [None, Piece.NONE]:
                moves.append((r + 1, f + 1))

        elif piece in [Piece.KNIGHT_W, Piece.KNIGHT_B]:
            for (nr, nf) in [(r - 2, f - 1), (r - 2, f + 1), (r - 1, f + 2), (r + 1, f + 2), (r + 2, f - 1), (r + 2, f + 1), (r - 1, f - 2), (r + 1, f - 2)]:
                np = self.get_piece(nr, nf)
                if np != Piece.NONE and (np == None or (piece.value & 8 == np.value & 8)):
                    continue

                moves.append((nr, nf))

        elif piece in [Piece.KING_W, Piece.KING_B]:
            for nr in [r - 1, r, r + 1]:
                for nf in [f - 1, f, f + 1]:
                    if (nr, nf) == (r, f):
                        continue

                    np = self.get_piece(nr, nf)

                    if np != Piece.NONE and (np == None or (piece.value & 8 == np.value & 8)):
                        continue

                    moves.append((nr, nf))

        if piece in [Piece.ROOK_W, Piece.ROOK_B, Piece.QUEEN_W, Piece.QUEEN_B]:
            for nr in range(r + 1, 8):
                np = self.get_piece(nr, f)

                if np not in [None, Piece.NONE] and (piece.value & 8 == np.value & 8):  # Same color
                    break

                moves.append((nr, f))

                if np != Piece.NONE:
                    break
            
            for nr in range(r - 1, -1, -1):
                np = self.get_piece(nr, f)

                if np not in [None, Piece.NONE] and (piece.value & 8 == np.value & 8):  # Same color
                    break

                moves.append((nr, f))
                if np != Piece.NONE:
                    break

            for nf in range(f + 1, 8):
                np = self.get_piece(r, nf)

                if np not in [None, Piece.NONE] and (piece.value & 8 == np.value & 8):  # Same color
                    break

                moves.append((r, nf))
                if np != Piece.NONE:
                    break
            
            for nf in range(f - 1, -1, -1):
                np = self.get_piece(r, nf)

                if np not in [None, Piece.NONE] and (piece.value & 8 == np.value & 8):  # Same color
                    break

                moves.append((r, nf))
                if np != Piece.NONE:
                    break

        if piece in [Piece.BISHOP_W, Piece.BISHOP_B, Piece.QUEEN_W, Piece.QUEEN_B]:
            for (ar, af) in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nr = r + ar
                nf = f + af
                while True:
                    np = self.get_piece(nr, nf)
                    if np == None:
                        break

                    if np != Piece.NONE and (piece.value & 8 == np.value & 8):  # Same color
                        break

                    moves.append((nr, nf))

                    if np != Piece.NONE:
                        break

                    nr += ar
                    nf += af
        
        return moves

    def make_move(self, player: Player, move: str) -> None:
        if len(move) != 4:
            raise IncorrectMove()
        
        src_r, src_f = self.decode_alg(move[:2])
        dst_r, dst_f = self.decode_alg(move[2:])

        if self.board[src_r][src_f] == Piece.NONE:
            raise IncorrectMove("Cannot move a NULL piece", move)

        if (self.board[src_r][src_f].value & 8) != self.turn << 3:
            raise IncorrectMove()
        
        moves = self.get_possible_moves(src_r, src_f)

        if (dst_r, dst_f) not in moves:
            raise IncorrectMove()

        self.board[dst_r][dst_f] = self.board[src_r][src_f]
        self.board[src_r][src_f] = Piece.NONE

    @staticmethod
    def decode_alg(alg: str) -> tuple[int, int]:
        if len(alg) != 2:
            raise IncorrectMove("Incorrect length of algebraic position", alg)

        file = ord(alg[0]) - ord('a')
        rank = 8 - int(alg[1])

        if file < 0 or file >= 8 or rank < 0 or rank >= 8:
            raise IncorrectMove("Incorrect position", alg)

        return (rank, file)


    def init_con(self, sock: socket.socket) -> Connection:
        msg = ""
        
        if self.white is None:
            msg += "w"
        
        if self.black is None:
            msg += "b"

        msg += "s"

        self.blocking_write(sock, msg)

        resp = self.blocking_read(sock)

        if len(resp) != 1:
            raise Exception("Incorrect response")

        if resp == "w":
            if self.white is not None:
                raise Exception("Incorrect response")
            
            con = Player(sock)
            self.white = con
            self.write_to.append(con)

        elif resp == "b":
            if self.black is not None:
                raise Exception("Incorrect response")
            
            con = Player(sock)
            self.black = con
            self.write_to.append(con)

        elif resp == "s":
            con = Connection(sock)
            self.write_to.append(con)

        self.blocking_write(sock, "initok")

        return con

    def shutdown(self) -> None:
        print("Shutting down...")

        for con in self.write_to:
            print(f"Closing connection to {con.sock.getpeername()}")
            con.sock.close()

        self.serversocket.close()
        
    def serve(self, port: int, pos: str = START_POS) -> None:

        self.serversocket.bind((socket.gethostname(), port))
        self.serversocket.listen(5)

        print(f"Server started on port {port}")

        read_from = [self.serversocket]

        self.fen_decode(pos)

        while True:
            ready_read, ready_write, _ = select.select(read_from, [c.sock for c in self.write_to if not c.queue_empty], [], 0.5)

            if self.serversocket in ready_read:
                (client, address) = self.serversocket.accept()

                print(f"Connection estabilished: {address}")

                try:
                    con = self.init_con(client)
                    if con == self.white or con == self.black:
                        read_from.append(con.sock)
                except Exception as err:
                    print(f"Failed to initialize connection, because '{err}'. Shutting it down")
                    self.blocking_write(client, "initfail")
                    client.close()

                ready_read.remove(self.serversocket)

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

            if not self.in_progress and self.white is not None and self.black is not None:
                self.in_progress = True
                read_from = [self.serversocket]

                if self.turn == self.WHITE_TURN:
                    read_from.append(self.white.sock)
                else:
                    read_from.append(self.black.sock)

            if not self.in_progress:
                for sock in ready_read:
                    if self.white is not None and self.white.sock == sock:
                        con = self.white
                    else:
                        con = self.black
                    
                    try:
                        msg = con.read()
                    except:
                        print(f"Connection at {con.sock.getpeername()} closed")
                        con.sock.close()
                        if con == self.white:
                            self.white = None
                        elif con == self.black:
                            self.black = None
                        read_from.remove(sock)
                        self.write_to.remove(con)

            if len(ready_read) == 0 or not self.in_progress:
                continue

            # Read move

            sock = ready_read[0]

            if self.white.sock == sock:
                player = self.white
            else:
                player = self.black

            if (self.turn == self.WHITE_TURN and player == self.black) or (self.turn == self.BLACK_TURN and player == self.white):
                raise Exception("Wrong player made a move. That shouldn't be possible")

            msg = player.read()

            if msg == None:
                continue

            print(("White: " if player == self.white else "Black: ") + msg)

            try:
                self.make_move(player, msg)
                player.queue_write("ok")
                print("ok")
                if self.turn == self.BLACK_TURN:
                    self.move += 1
                self.turn ^= 1
                self.caclock += 1
            except IncorrectMove:
                player.queue_write("no")
                print("no")
                continue

            for c in self.write_to:
                if c == player:
                    continue
                c.queue_write(msg)


            read_from = [self.serversocket]

            if self.turn == self.WHITE_TURN:
                read_from.append(self.white.sock)
            else:
                read_from.append(self.black.sock)

    @staticmethod
    def blocking_read(sock: socket.socket) -> str:
        blocking = sock.getblocking()
        sock.setblocking(True)

        read_buf = bytearray(1024)
        view = memoryview(read_buf)

        read_prog = 0
        msg_len = 3

        while read_prog < msg_len:
            recvd = sock.recv_into(view[read_prog:], msg_len - read_prog)

            if recvd == 0:
                raise Exception("Socket closed unexpectedly")

            read_prog += recvd

        msg_len = int(read_buf[:msg_len].decode("ascii"))
        read_prog = 0

        while read_prog < msg_len:
            recvd = sock.recv_into(view[read_prog:], msg_len - read_prog)

            if recvd == 0:
                raise Exception("Socket closed unexpectedly")

            read_prog += recvd

        sock.setblocking(blocking)

        return read_buf[:msg_len].decode("ascii")

    @staticmethod
    def blocking_write(sock: socket.socket, msg: str) -> None:
        blocking = sock.getblocking()
        sock.setblocking(True)

        msg = bytearray(f"{str(len(msg)).rjust(3)}{msg}", encoding="ascii")
        view = memoryview(msg)
        write_prog = 0
        msg_len = len(msg)

        while write_prog < msg_len:
            sent = sock.send(view[write_prog:])

            if sent == 0:
                raise Exception("Socket closed unexpectedly")

            write_prog += sent

        sock.setblocking(blocking)


if __name__ == "__main__":
    with Game() as game:
        try:
            game.serve(40000 if len(sys.argv) == 1 else int(sys.argv[1]), game.START_POS if len(sys.argv) < 3 else sys.argv[2])
        except Exception as err:
            print(err)
