import socket, sys, select
from enum import Enum
import copy
from collections import defaultdict
import time

class IncorrectMove(Exception):
    pass

class Connection:

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.sock.setblocking(False)

        self.send_queue: bytearray = bytearray()

    def queue_write(self, msg: str) -> None:
        self.send_queue.extend(bytes(f"{str(len(msg)).rjust(3, '0')}{msg}", encoding="ascii"))

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

        self.en_passant_tgt = None
        self.castle_pos = [True, True, True, True]  # [White Kingside, White Queenside, Black Kingside, Black Queenside]

        self.in_progress = False
        self.ended = False

        self.white_boards = defaultdict(int)
        self.black_boards = defaultdict(int)

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

            if no_len > 0:
                FEN += str(no_len)
                no_len = 0
            if rank != self.board[-1]:
                FEN += '/'

        FEN += ' '
        FEN += 'w' if self.turn == self.WHITE_TURN else 'b'
        FEN += ' '

        if self.castle_pos[0]:
            FEN += 'K' 
        if self.castle_pos[1]:
            FEN += 'Q'
        if self.castle_pos[2]:
            FEN += 'k'
        if self.castle_pos[3]:
            FEN += 'q'
        if not self.castle_pos[0] and not self.castle_pos[1] and not self.castle_pos[2] and not self.castle_pos[3]:
            FEN += '-'
        FEN += ' '
        FEN += '-' if self.en_passant_tgt == None else self.encode_alg(self.en_passant_tgt[0], self.en_passant_tgt[1])
        FEN += ' '
        FEN += str(self.caclock)
        FEN += ' '
        FEN += str(self.move)

        return FEN

    def get_piece(self, r: int, f: int) -> Piece | None:
        if r < 0 or r >= 8 or f < 0 or f >= 8:
            return None
        
        return self.board[r][f]

    def move_piece(self, orig_r: int, orig_f: int, tgt_r: int, tgt_f: int, prom: Piece = Piece.NONE) -> bool:  # Returns True if capture occured
        captured = False
        piece = self.get_piece(orig_r, orig_f)

        if piece == None:
            raise ValueError("Tried moving NULL piece")

        if piece in [Piece.PAWN_W, Piece.PAWN_B] and (tgt_r, tgt_f) == self.en_passant_tgt:
            if tgt_r == 5:
                if self.board[4][tgt_f] != Piece.NONE:
                    captured = True
                self.board[4][tgt_f] = Piece.NONE
            else:
                if self.board[3][tgt_f] != Piece.NONE:
                    captured = True
                self.board[3][tgt_f] = Piece.NONE

        if piece in [Piece.PAWN_W, Piece.PAWN_B]:
            if tgt_r in [0, 7]:
                piece = prom

        if piece in [Piece.KING_W, Piece.KING_B]:
            if tgt_f - orig_f == 2:
                self.board[orig_r][orig_f + 1] = Piece(Piece.ROOK_W.value | (piece.value & 8))
                self.board[orig_r][7] = Piece.NONE
            elif tgt_f - orig_f == -2:
                self.board[orig_r][orig_f - 1] = Piece(Piece.ROOK_W.value | (piece.value & 8))
                self.board[orig_r][0] = Piece.NONE

        if self.board[tgt_r][tgt_f] != Piece.NONE:
            captured = True
        self.board[tgt_r][tgt_f] = piece
        self.board[orig_r][orig_f] = Piece.NONE
        return captured

    def check_check(self, move_dict = None) -> int:  # -1 = no check, 0 = white is checked, 1 = black is checked, 2 = both checked
        if move_dict is None:
            move_dict = self.moves

        white_checked = False
        black_checked = False
        for moves in move_dict.values():
            for r, f in moves:
                piece = self.get_piece(r, f)

                if piece == Piece.KING_W:
                    white_checked = True
                if piece == Piece.KING_B:
                    black_checked = True
                
        if white_checked and black_checked:
            return 2
        if black_checked:
            return 1
        if white_checked:
            return 0
        return -1

    def has_moves(self, not_player: Player) -> bool:
        color = int(not_player == self.white) << 3
        for r, f in self.moves.keys():
            if len(self.moves[(r, f)]) == 0:
                continue
            piece = self.get_piece(r, f)

            if (piece.value & 8) == color:
                return True

        return False

    def will_check(self, src_r: int, src_f: int, dst_r: int, dst_f: int) -> int:  # -1 = no check, 0 = white will be checked, 1 = black will be checked, 2 = both will be checked
        origboard = copy.deepcopy(self.board)
         
        self.move_piece(src_r, src_f, dst_r, dst_f)

        moves = self.get_all_moves()
        check = self.check_check(moves)

        self.board = origboard   
        return check

    def get_possible_moves(self, r: int, f: int) -> list[tuple[int, int]]:
        piece = self.board[r][f]

        moves: list[tuple[int, int]] = []

        if piece == Piece.NONE:
            return []

        elif piece == Piece.PAWN_W:
            if self.get_piece(r - 1, f) == Piece.NONE:
                moves.append((r - 1, f))
                if r == 6:
                    if self.get_piece(r - 2, f) == Piece.NONE:
                        moves.append((r - 2, f))

            nr = r - 1
            nf = f - 1
            np = self.get_piece(nr, nf)
            if (np not in [None, Piece.NONE] and (np.value & 8 != piece.value & 8)) or (nr, nf) == self.en_passant_tgt:
                moves.append((nr, nf))

            nr = r - 1
            nf = f + 1
            np = self.get_piece(nr, nf)
            if (np not in [None, Piece.NONE] and (np.value & 8 != piece.value & 8)) or (nr, nf) == self.en_passant_tgt:
                moves.append((nr, nf))

        elif piece == Piece.PAWN_B:
            if self.get_piece(r + 1, f) == Piece.NONE:
                moves.append((r + 1, f))
                if r == 1:
                    moves.append((r + 2, f))

            nr = r + 1
            nf = f - 1
            np = self.get_piece(nr, nf)
            if (np not in [None, Piece.NONE] and (np.value & 8 != piece.value & 8)) or (nr, nf) == self.en_passant_tgt:
                moves.append((nr, nf))

            nr = r + 1
            nf = f + 1
            np = self.get_piece(nr, nf)
            if (np not in [None, Piece.NONE] and (np.value & 8 != piece.value & 8)) or (nr, nf) == self.en_passant_tgt:
                moves.append((nr, nf))

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

            if self.castle_pos[((piece.value & 8) >> 3) * 2 + 1] and self.get_piece(r, f - 4) in [Piece.ROOK_W, Piece.ROOK_B] and self.get_piece(r, f - 3) == Piece.NONE and self.get_piece(r, f - 2) == Piece.NONE and self.get_piece(r, f - 1) == Piece.NONE:
                moves.append((r, f - 2))

            if self.castle_pos[((piece.value & 8) >> 3) * 2] and self.get_piece(r, f + 3) in [Piece.ROOK_W, Piece.ROOK_B] and self.get_piece(r, f + 2) == Piece.NONE and self.get_piece(r, f + 1) == Piece.NONE:
                moves.append((r, f + 2))

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

    def get_legal_moves(self, r: int, f: int) -> list[tuple[int, int]]:
        moves = self.get_possible_moves(r, f)
        p = self.get_piece(r, f)

        remove: list[tuple[int, int]] = []

        for nr, nf in moves:
            check = self.will_check(r, f, nr, nf)
            if (check == -1 or check == 1 - ((p.value & 8) >> 3)) and p in [Piece.KING_W, Piece.KING_B]:  # Can't castle through check
                if nf - f == 2:
                    check = self.will_check(r, f, nr, f + 1)
                elif nf - f == -2:
                    check = self.will_check(r, f, nr, f - 1)

            if check == 2 or check == ((p.value & 8) >> 3):  # Checked yourself
                remove.append((nr, nf))

            if p in [Piece.KING_W, Piece.KING_B] and abs(nf - f) == 2:
                move_dict = self.get_all_moves()
                check = self.check_check(move_dict)
                if check == 2 or check == ((p.value & 8) >> 3): 
                    remove.append((nr, nf))


        for move in remove:
            try:
                moves.remove(move)
            except:
                continue

        return moves

    def get_all_moves(self) -> dict[tuple[int, int], list[tuple[int, int]]]:
        moves = {}

        for r in range(8):
            for f in range(8):
                piece = self.get_piece(r, f)

                if piece == Piece.NONE:
                    continue

                nm = self.get_possible_moves(r, f)

                moves[(r, f)] =  nm

        return moves

    def get_all_legal_moves(self) -> dict[tuple[int, int], list[tuple[int, int]]]:
        moves = {}

        for r in range(8):
            for f in range(8):
                piece = self.get_piece(r, f)

                if piece == Piece.NONE:
                    continue

                nm = self.get_legal_moves(r, f)

                moves[(r, f)] =  nm

        return moves

    def save_board_pos(self, turn: int) -> bool:
        if self.en_passant_tgt != None:
            for orig_r, orig_f in self.moves.keys():
                piece = self.get_piece(orig_r, orig_f)
                if (piece == Piece.PAWN_W and turn == self.WHITE_TURN) or (piece == Piece.PAWN_B and turn == self.BLACK_TURN):
                    continue
                moves = self.moves[(orig_r, orig_f)]
                for move in moves:
                    if move == self.en_passant_tgt:
                        return
        
        board_tuple = []
        for row in self.board:
            board_tuple.append(tuple(row))
        board_tuple = tuple(board_tuple)
        boards = self.white_boards if turn == self.WHITE_TURN else self.black_boards
        boards[(board_tuple, tuple(self.castle_pos))] += 1   
        return boards[(board_tuple, tuple(self.castle_pos))] >= 3

    def make_move(self, player: Player, move: str) -> None:
        length = len(move)
        if length != 4 and length != 6:
            raise IncorrectMove()
        
        src_r, src_f = self.decode_alg(move[:2])
        dst_r, dst_f = self.decode_alg(move[2:4])

        if self.board[src_r][src_f] == Piece.NONE:
            raise IncorrectMove("Cannot move a NULL piece", move)

        if (self.board[src_r][src_f].value & 8) != self.turn << 3:
            raise IncorrectMove()
        
        self.score = "0-0"
        moves = self.moves[(src_r, src_f)]

        if (dst_r, dst_f) not in moves:
            raise IncorrectMove()

        next_en_passant = None

        piece = self.get_piece(src_r, src_f)

        prom = Piece.NONE

        if piece in [Piece.PAWN_W, Piece.PAWN_B] and dst_r in [0, 7] and length != 6:
            raise IncorrectMove()

        if length >= 6:
            if piece not in [Piece.PAWN_W, Piece.PAWN_B]:
                raise IncorrectMove()
            if move[4] != '=':
                raise IncorrectMove()
            
            match move[5]:
                case 'Q':
                    prom = Piece.QUEEN_W
                case 'N':
                    prom = Piece.KNIGHT_W
                case 'R':
                    prom = Piece.ROOK_W
                case 'B':
                    prom = Piece.BISHOP_W
                case _:
                    raise IncorrectMove("Incorrect promotion target")
            
            prom = Piece(prom.value | (piece.value & 8))

        if piece in [Piece.PAWN_W, Piece.PAWN_B] and abs(dst_r - src_r) == 2:
            next_en_passant = (round((dst_r + src_r)/2), src_f)

        elif piece in [Piece.ROOK_W, Piece.ROOK_B]:
            if src_f == 0:
                self.castle_pos[((piece.value & 8) >> 3) * 2 + 1] = False
            elif src_f == 8:
                self.castle_pos[((piece.value & 8) >> 3) * 2] = False

        elif piece == Piece.KING_W:
            self.castle_pos[0] = False
            self.castle_pos[1] = False
        
        elif piece == Piece.KING_B:
            self.castle_pos[2] = False
            self.castle_pos[3] = False

        captured = self.move_piece(src_r, src_f, dst_r, dst_f, prom)

        if captured or piece in [Piece.PAWN_W, Piece.PAWN_B]:
            self.caclock = 0

        self.en_passant_tgt = next_en_passant

    @staticmethod
    def decode_alg(alg: str) -> tuple[int, int]:
        if len(alg) != 2:
            raise IncorrectMove("Incorrect length of algebraic position", alg)

        file = ord(alg[0]) - ord('a')
        rank = 8 - int(alg[1])

        if file < 0 or file >= 8 or rank < 0 or rank >= 8:
            raise IncorrectMove("Incorrect position", alg)

        return (rank, file)

    @staticmethod
    def encode_alg(rank: int, file: int) -> str:
        if file < 0 or file >= 8 or rank < 0 or rank >= 8:
            raise IncorrectMove("Incorrect position", rank, file)

        f = chr(ord('a') + file)
        r = str(8 - rank)

        return f + r


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

        self.blocking_write(sock, self.fen_encode())

        self.blocking_write(sock, "initok")

        return con

    def shutdown(self) -> None:
        print("Shutting down...")

        for con in self.write_to:
            try:
                con.blocking_write("end " + self.score)
                print(f"Closing connection to {con.sock.getpeername()}")
            except:
                print(f"Closing connection")
            con.sock.close()

        self.serversocket.close()
        
    def serve(self, port: int, pos: str = START_POS) -> None:

        self.serversocket.bind(('', port))
        self.serversocket.listen(5)

        print(f"Server started on port {port}")

        read_from = [self.serversocket]

        self.fen_decode(pos)

        self.moves = self.get_all_moves()
        self.save_board_pos(self.turn)
        self.save_board_pos(self.turn ^ 1)

        while True:
            ready_read, ready_write, _ = select.select(read_from, [c.sock for c in self.write_to if not c.queue_empty], [], 0.5)

            if self.serversocket in ready_read:
                (client, address) = self.serversocket.accept()

                print(f"Connection estabilished: {address}")

                if self.in_progress:
                    con = Connection(client)
                    con.queue_write("s")
                    con.queue_write(self.fen_encode())
                    con.queue_write("initok")
                    self.write_to.append(con)
                
                else:
                    try:
                        con = self.init_con(client)
                        if con == self.white or con == self.black:
                            read_from.append(con.sock)
                    except Exception as err:
                        print(f"Failed to initialize connection, because '{err}'. Shutting it down")
                        try:
                            self.blocking_write(client, "initfail")
                        except:
                            pass
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
                        print(f"Spectator closed unexpectedly. Anyway...")
                        con.sock.close()
                        self.write_to.remove(con)
                        continue
                    elif con == self.white:
                        self.score = '0-1'
                        print("White abandoned game")
                    else:
                        self.score = '1-0'
                        print("Black abandoned game")
                    self.end_game(self.score)
                    con.sock.close()
                    self.write_to.remove(con)
                        

            if not self.in_progress and self.white is not None and self.black is not None and not self.ended:
                self.in_progress = True
                read_from = [self.serversocket]

                if self.turn == self.WHITE_TURN:
                    read_from.append(self.white.sock)
                else:
                    read_from.append(self.black.sock)

            if not self.in_progress and not self.ended:
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

            if self.ended:
                if len(self.write_to) == 0:
                    return
                
                remove = []
                for con in self.write_to:
                    if con.queue_empty:
                        print(f"Closing connection to {con.sock.getpeername()}")
                        con.sock.close()
                        remove.append(con)
                for con in remove:
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

            try:
                msg = player.read()
            except:
                if player == self.white:
                    print("White abandoned game")
                    self.score = '0-1'
                else:
                    print("Black abandoned game")
                    self.score = '1-0'
                self.end_game()
                self.write_to.remove(player)
                msg = None

            if msg == None:
                continue

            print(("White: " if player == self.white else "Black: ") + msg)

            if msg.startswith("moves "):
                try:
                    (r, f) = self.decode_alg(msg[6:8])
                    moves = self.moves.get((r, f), [])
                    resp = "moves " + msg[6:8] + " "
                    for move in moves:
                        resp += self.encode_alg(move[0], move[1])
                    player.queue_write(resp)
                    print(resp)
                    continue
                except IncorrectMove:
                    player.queue_write("no")
                    print("no")
                    continue

            check = -1
            has_moves = True
            try:
                self.caclock += 1
                self.make_move(player, msg)
                self.moves = self.get_all_legal_moves()
                rep = self.save_board_pos(self.turn)
                resp = "ok"
                check = self.check_check()
                has_moves = self.has_moves(player)
                if check == (1 - self.turn):
                    if has_moves:
                        resp += "+"
                    else:
                        resp += "#"
                        self.in_progress = False
                        self.ended = True
                        self.score = "1-0" if player == self.white else "0-1"
                elif not has_moves or self.caclock >= 100 or rep:
                    resp += "-"
                    self.in_progress = False
                    self.ended = True
                    self.score = "1/2-1/2"
                player.queue_write(resp)
                print(resp)
                if self.turn == self.BLACK_TURN:
                    self.move += 1
                self.turn ^= 1
            except IncorrectMove:
                player.queue_write("no")
                print("no")
                continue

            if check != -1:
                if has_moves:
                    msg += "+"
                else:
                    msg += "#"
            elif not has_moves:
                msg += "-"
            for c in self.write_to:
                if c == player:
                    continue
                c.queue_write(msg)

            if self.ended:
                self.end_game()
                read_from = []
                continue

            read_from = [self.serversocket]

            if self.turn == self.WHITE_TURN:
                read_from.append(self.white.sock)
            else:
                read_from.append(self.black.sock)

    def end_game(self) -> None:
        print(self.score)
        self.ended = True
        self.in_progress = False
        for c in self.write_to:
            c.queue_write("end " + self.score)

    @staticmethod
    def blocking_read(sock: socket.socket) -> str:
        sock.settimeout(0.5)

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

        sock.setblocking(False)

        return read_buf[:msg_len].decode("ascii")

    @staticmethod
    def blocking_write(sock: socket.socket, msg: str) -> None:
        sock.settimeout(0.5)

        msg = bytearray(f"{str(len(msg)).rjust(3, '0')}{msg}", encoding="ascii")
        view = memoryview(msg)
        write_prog = 0
        msg_len = len(msg)

        while write_prog < msg_len:
            sent = sock.send(view[write_prog:])

            if sent == 0:
                raise Exception("Socket closed unexpectedly")

            write_prog += sent

        sock.setblocking(False)


if __name__ == "__main__":
    with Game() as game:
        try:
            game.serve(40000 if len(sys.argv) == 1 else int(sys.argv[1]), game.START_POS if len(sys.argv) < 3 else sys.argv[2])
        except Exception as err:
            print(err)
