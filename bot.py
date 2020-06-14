import threading
import berserk
import stockfish
import logging
import chess

WHITE = "\033[1m"
logging.basicConfig(level=logging.INFO,
                    format=WHITE + "%(asctime)s.%(msecs)03d [%(name)s] "
                                   "%(levelname)s: %(message)s",
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)


class LichessBot:
    def __init__(self, api_key: str):
        session = berserk.TokenSession(api_key)
        self.client = berserk.Client(session)
        self.user_id = self.client.account.get()['id']

    def run(self):
        for event in self.client.bots.stream_incoming_events():
            logger.info(event)
            if event['type'] == 'challenge':
                logger.info("Accepting challenge!")
                self.client.bots.accept_challenge(event['challenge']['id'])

            elif event['type'] == 'gameStart':
                game_id = event['game']['id']

                game = LichessGame(self.client, self.user_id, game_id)
                threading.Thread(target=game.run).start()


class LichessGame:
    def __init__(self, client: berserk.Client, user_id: str, game_id: str):
        self.client = client
        self.user_id = user_id
        self.game_id = game_id

        self.stream = client.bots.stream_game_state(game_id)

        event = next(self.stream)
        if user_id == event['white']['id']:
            self.color = 'white'
        elif user_id == event['black']['id']:
            self.color = 'black'
        else:
            raise RuntimeError("This bot is not playing in the game.")

        self.board = chess.Board()
        self.engine = stockfish.Stockfish(r'C:\Users\danie\PythonProjects\lichess-bot'
                                          r'\stockfish-11-win\Windows\stockfish_20011801_32bit.exe')
        self.engine.set_skill_level(3)

    def select_move(self) -> str:
        # return self.random_move()
        # return self.stockfish_move()
        return self.minimax_move(depth=4)

    def random_move(self) -> str:
        import random

        random_move = random.choice(list(self.board.legal_moves))
        return str(random_move)

    @staticmethod
    def _evaluate_board(board: chess.Board):
        """Simple valuation function.

        Just sums the piece values.
        """
        pieces = board.epd().split()[0]
        piece_values = {
            'p': 1,
            'n': 3,
            'b': 3.25,
            'k': 10000,
            'q': 9,
            'r': 5,
            'P': -1,
            'N': -3,
            'B': -3.25,
            'K': -10000,
            'Q': -9,
            'R': -5
        }
        return sum(piece_values.get(c, 0) for c in pieces)

    def _minimax(self, board: chess.Board, alpha: float, beta: float, depth: int):
        if depth == 0 and any(board.legal_moves):
            return self._evaluate_board(board), None
        # Draw
        elif (board.can_claim_draw() or
                board.is_stalemate() or
                board.is_insufficient_material()):
            return 0, None
        # White wins
        elif board.is_checkmate() and board.turn == chess.BLACK:
            return float('inf'), None
        # Black wins
        elif board.is_checkmate() and board.turn == chess.WHITE:
            return float('-inf'), None

        best_eval, best_move = float('-inf'), None
        for move in board.legal_moves:
            board.push_uci(str(move))
            cur_eval, cur_move = self._minimax(board, -beta, -alpha, depth - 1)
            cur_eval = -cur_eval
            board.pop()
            if best_eval < cur_eval:
                best_eval = cur_eval
                alpha = cur_eval
                best_move = move
            if best_eval >= beta:
                break
        return best_eval, best_move

    def minimax_move(self, depth) -> str:
        value, best_move = self._minimax(self.board, float('-inf'), float('inf'), depth)
        logger.info(f"Evaluation: {value:.2f}")
        return str(best_move)

    def stockfish_move(self) -> str:
        self.engine.set_position(self.board.move_stack)
        return self.engine.get_best_move_time(100)

    def uci_to_san(self, move: str):
        move = chess.Move.from_uci(move)
        return self.board.san(move)

    def move(self):
        move = self.select_move()
        logger.info(self.uci_to_san(move))

        self.board.push_uci(move)
        self.client.bots.make_move(self.game_id, move)

        # Skip the confirmation event
        next(self.stream)

    def run(self):
        try:
            if self.color == 'white':
                # We go first; make a move
                self.move()
            for event in self.stream:
                if event.get('status') == 'started':
                    last_move = event['moves'].split()[-1]
                    logger.info(self.uci_to_san(last_move))

                    self.board.push_uci(last_move)
                    self.move()
                else:
                    # Game is over
                    logger.info(event)
                    break
        except Exception:
            self.client.bots.resign_game(self.game_id)
            raise


def main():
    import configparser

    config = configparser.ConfigParser()
    config.read('consts.ini')
    api_key = config['lichess']['API_KEY']

    bot = LichessBot(api_key)
    bot.run()


if __name__ == '__main__':
    main()
