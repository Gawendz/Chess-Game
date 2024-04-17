 import sys
import threading
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QMutex, QEvent, QPointF
from PyQt5.QtGui import QPixmap, QColor, QFont, QMouseEvent
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsRectItem, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsProxyWidget, QLabel,QLineEdit, QRadioButton, QPushButton
import sqlite3
from datetime import datetime
import json



# Connect to SQLite database (create if not exists)
conn = sqlite3.connect('Chess_sessions.db')
cursor = conn.cursor()

# Use try-except block to handle table creation
try:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            session_name TEXT,
            move_history TEXT
        )
    ''')
    print("Table 'sessions' created successfully.")
except sqlite3.Error as e:
    print(f"Error creating table: {e}")

# Commit changes and close connection
conn.commit()
conn.close()


class LogThread(QObject):
    log_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.log = ""
        self.mutex = QMutex()

    def append_log(self, message):
        self.mutex.lock()
        self.log += message + "\n"
        self.log_updated.emit(self.log)
        self.mutex.unlock()

    def clear_log(self):
        self.mutex.lock()
        self.log = ""
        self.log_updated.emit(self.log)
        self.mutex.unlock()

    def get_log(self):
        self.mutex.lock()
        log_copy = self.log
        self.mutex.unlock()
        return log_copy

    def run(self):
        pass  # Możesz dodać więcej funkcjonalności wątku, jeśli jest to konieczne
    
class ChessPiece(QGraphicsPixmapItem):
    def __init__(self, piece_type, size, player, log_thread):
        super().__init__()
        self.player = player
        self.log_thread = log_thread
        self.last_move = None  
        self.initial_pos = None  
        self.piece_type = piece_type  # Dodajemy atrybut przechowujący typ pionka
        

        pixmap = QPixmap(f'images/{piece_type}.png')
        pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)

        self.highlighted_square = None  

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.scene().current_player == self.player:
            self.initial_pos = self.pos()  
            self.setOpacity(0.7)  
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.scene().current_player == self.player:
            newPos = self.mapToScene(event.pos())
            self.setPos(newPos)

            self.update_highlighted_square()
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if self.scene().current_player == self.player:
            square_size = self.scene().square_size
            col = round(self.x() / square_size)
            row = round(self.y() / square_size)

            new_x = col * square_size + (square_size - self.pixmap().width()) / 2
            new_y = row * square_size + (square_size - self.pixmap().height()) / 2

            if self.initial_pos != self.pos():
                if self.is_valid_move(col, row):
                    target_piece = self.scene().board[row][col]

                    if target_piece and target_piece.player != self.player:
                        # Capture opponent's piece
                        self.scene().remove_chess_piece(col, row)

                    self.log_thread.append_log(
                        f"Player {self.player}: Moved {self.piece_type} from square {chr(ord('a') + round(self.initial_pos.x() / square_size))}{8 - round(self.initial_pos.y() / square_size)} "
                        f"to square {chr(ord('a') + col)}{8 - row}")
                    self.last_move = ((self.initial_pos.x(), self.initial_pos.y()), (col, row))

                    self.setPos(new_x, new_y)

                    # Update the board
                    current_col = round(self.initial_pos.x() / square_size)
                    current_row = round(self.initial_pos.y() / square_size)
                    self.scene().board[current_row][current_col] = None
                    self.scene().board[row][col] = self

                    # Check for endgame condition: Verify if any king is still on the board
                    white_king_exists = False
                    black_king_exists = False

                    for row in range(8):
                        for col in range(8):
                            piece = self.scene().board[row][col]
                            if isinstance(piece, ChessPiece):
                                if piece.piece_type == 'w_king':
                                    white_king_exists = True
                                elif piece.piece_type == 'b_king':
                                    black_king_exists = True

                    if not white_king_exists:
                        self.log_thread.append_log("Game Over: Black Wins!")
                        log_history = self.log_thread.get_log()
                        mainWindow.save_session_to_database(log_history)

                    elif not black_king_exists:
                        self.log_thread.append_log("Game Over: White Wins!")
                        log_history = self.log_thread.get_log()
                        mainWindow.save_session_to_database(log_history)


                else:
                    self.setPos(self.initial_pos)  # Revert to the original position
                    self.log_thread.append_log(
                        f"Player {self.player}: Illegal move attempted by {self.piece_type} from square {chr(ord('a') + round(self.initial_pos.x() / square_size))}{8 - round(self.initial_pos.y() / square_size)} "
                        f"to square {chr(ord('a') + col)}{8 - row}. Move denied.")

            if self.highlighted_square:
                self.scene().removeItem(self.highlighted_square)
                self.highlighted_square = None

            self.setOpacity(1.0)

            self.scene().change_turn()

        super().mouseReleaseEvent(event)

        
    def is_empty_or_opponent(self, piece):
        if piece is None:
            return True  # Square is empty
        elif isinstance(piece, ChessPiece) and piece.player != self.player:
            return True  # Square is occupied by an opponent's piece
        else:
            return False  # Square is occupied by own piece


    def is_valid_move(self, col, row):
        square_size = self.scene().square_size
        current_col = round(self.initial_pos.x() / square_size)
        current_row = round(self.initial_pos.y() / square_size)
        board = self.scene().board

        # Check if the target position is the same as the current position
        if (current_col, current_row) == (col, row):
            return False

        # Check if the target position is within the board bounds
        if not (0 <= col < 8 and 0 <= row < 8):
            return False

        # Get the piece at the target position
        target_piece = board[row][col]

        # Determine if the target position is empty or occupied by an opponent's piece
        if self.is_empty_or_opponent(target_piece):
            if self.piece_type == 'b_pawn':
                # Black pawn moves
                if col == current_col and row == current_row + 1 and target_piece is None:
                    return True
                elif current_row == 1 and col == current_col and row == current_row + 2 and board[current_row + 1][col] is None and target_piece is None:
                    return True
                elif abs(col - current_col) == 1 and row == current_row + 1 and target_piece is not None:
                    return True
            elif self.piece_type == 'w_pawn':
                # White pawn moves
                if col == current_col and row == current_row - 1 and target_piece is None:
                    return True
                elif current_row == 6 and col == current_col and row == current_row - 2 and board[current_row - 1][col] is None and target_piece is None:
                    return True
                elif abs(col - current_col) == 1 and row == current_row - 1 and target_piece is not None:
                    return True
            elif self.piece_type == 'b_rook' or self.piece_type == 'w_rook':
                # Rook moves
                if col == current_col:  # Vertical movement
                    step = 1 if row > current_row else -1
                    for i in range(current_row + step, row, step):
                        if board[i][col] is not None:
                            return False
                    return True
                elif row == current_row:  # Horizontal movement
                    step = 1 if col > current_col else -1
                    for j in range(current_col + step, col, step):
                        if board[row][j] is not None:
                            return False
                    return True

            elif self.piece_type == 'b_bishop' or self.piece_type == 'w_bishop':
                # Bishop moves
                if abs(col - current_col) == abs(row - current_row):
                    step_x = 1 if col > current_col else -1
                    step_y = 1 if row > current_row else -1
                    check_col = current_col + step_x
                    check_row = current_row + step_y
                    while check_col != col and check_row != row:
                        if self.scene().board[check_row][check_col] is not None:
                            return False
                        check_col += step_x
                        check_row += step_y
                    return True
            elif self.piece_type == 'b_knight' or self.piece_type == 'w_knight':
                # Knight moves
                if (abs(col - current_col) == 2 and abs(row - current_row) == 1) or \
                (abs(col - current_col) == 1 and abs(row - current_row) == 2):
                    return True
            elif self.piece_type == 'b_queen' or self.piece_type == 'w_queen':
                # Queen moves (combination of rook and bishop)
                if (col == current_col or row == current_row) or (abs(col - current_col) == abs(row - current_row)):
                    # Check rook-like movement
                    if col == current_col or row == current_row:
                        step = 1 if col == current_col else -1
                        axis = row if col == current_col else col
                        for i in range(min(current_row, row) + 1, max(current_row, row)):
                            if self.scene().board[i][axis] is not None:
                                return False
                    else:  # Check bishop-like movement
                        step_x = 1 if col > current_col else -1
                        step_y = 1 if row > current_row else -1
                        check_col = current_col + step_x
                        check_row = current_row + step_y
                        while check_col != col and check_row != row:
                            if self.scene().board[check_row][check_col] is not None:
                                return False
                            check_col += step_x
                            check_row += step_y
                    return True
            elif self.piece_type == 'b_king' or self.piece_type == 'w_king':
                # King moves
                if abs(col - current_col) <= 1 and abs(row - current_row) <= 1:
                    return True
                # Check for castling
                

        return False



    

    def is_square_attacked(self, col, row):
        # Sprawdzenie czy pole jest atakowane przez pionka przeciwnika
        if self.is_square_attacked_by_enemy_pawn(col, row):
            return True

        # Sprawdzenie czy pole jest atakowane przez gońca, wieżę, hetmana lub króla przeciwnika
        if self.is_square_attacked_by_enemy_bishop(col, row) or \
        self.is_square_attacked_by_enemy_rook(col, row) or \
        self.is_square_attacked_by_enemy_queen(col, row) or \
        self.is_square_attacked_by_enemy_knight(col, row) or \
        self.is_square_attacked_by_enemy_king(col, row):
            return True

        return False

    def is_square_attacked_by_enemy_pawn(self, col, row):
        # Sprawdzenie czy pole jest atakowane przez pionka przeciwnika
        if self.player == 'white':
            # Sprawdzamy ruchy pionka czarnego w kierunku pola (col, row)
            if col > 0 and row > 0 and isinstance(self.scene().board[row - 1][col - 1], ChessPiece) and \
            self.scene().board[row - 1][col - 1].player == 'black' and \
            self.scene().board[row - 1][col - 1].piece_type == 'b_pawn':
                return True
            if col < 7 and row > 0 and isinstance(self.scene().board[row - 1][col + 1], ChessPiece) and \
            self.scene().board[row - 1][col + 1].player == 'black' and \
            self.scene().board[row - 1][col + 1].piece_type == 'b_pawn':
                return True
        else:
            # Sprawdzamy ruchy pionka białego w kierunku pola (col, row)
            if col > 0 and row < 7 and isinstance(self.scene().board[row + 1][col - 1], ChessPiece) and \
            self.scene().board[row + 1][col - 1].player == 'white' and \
            self.scene().board[row + 1][col - 1].piece_type == 'w_pawn':
                return True
            if col < 7 and row < 7 and isinstance(self.scene().board[row + 1][col + 1], ChessPiece) and \
            self.scene().board[row + 1][col + 1].player == 'white' and \
            self.scene().board[row + 1][col + 1].piece_type == 'w_pawn':
                return True
        return False


    def update_highlighted_square(self):
        if self.scene():
            square_size = self.scene().square_size
            col = round(self.x() / square_size)
            row = round(self.y() / square_size)

            new_x = col * square_size
            new_y = row * square_size

            if self.highlighted_square:
                self.highlighted_square.setRect(new_x, new_y, square_size, square_size)
            else:
                self.highlighted_square = HighlightedSquare(new_x, new_y, square_size)
                self.scene().addItem(self.highlighted_square)
                self.highlighted_square.highlight()




class HighlightedSquare(QGraphicsRectItem):
    def __init__(self, x, y, size):
        super().__init__(x, y, size, size)
        self.setBrush(QColor(0, 255, 0, 100))  # Kolor z przezroczystością

    def highlight(self):
        self.setBrush(QColor(0, 255, 0, 100))

    def unhighlight(self):
        self.setBrush(Qt.NoBrush)

class PlayerLabel(QLabel):
    def __init__(self, initial_player):
        super().__init__()
        self.setText(f"Current player: {initial_player}")

    def update_player(self, player):
        self.setText(f"Current player: {player}")



class ChessboardScene(QGraphicsScene):
    current_player_updated = pyqtSignal(str)  # Aktualizacja sygnału

    def __init__(self, log_thread):
        super().__init__()

        self.chessboard_size = 8
        self.square_size = 60
        self.current_player = 'white'  # Dodanie zmiennej dla aktualnego gracza
        self.init_chessboard()
        self.log_thread = log_thread
        self.board = [[None] * self.chessboard_size for _ in range(self.chessboard_size)]  # Inicjalizacja planszy

    def init_chessboard(self):
        colors = [Qt.lightGray, Qt.darkGray]

        for row in range(self.chessboard_size):
            for col in range(self.chessboard_size):
                square_color = colors[(row + col) % 2]
                square = self.addRect(col * self.square_size, row * self.square_size,
                                      self.square_size, self.square_size)
                square.setBrush(square_color)

                # Dodajemy etykiety kolumn i rzędów
                if col == 0:
                    label = QGraphicsTextItem(str(8 - row))
                    label.setFont(QFont("Arial", 12))
                    label.setPos(col * self.square_size - 20, row * self.square_size)
                    self.addItem(label)

                if row == self.chessboard_size - 1:
                    label = QGraphicsTextItem(chr(ord('a') + col))
                    label.setFont(QFont("Arial", 12))
                    label.setPos(col * self.square_size + 10, row * self.square_size + 60)
                    self.addItem(label)

    def remove_chess_piece(self, col, row):
        piece = self.board[row][col]
        if piece:
            self.removeItem(piece)
            self.board[row][col] = None  # Clear the board position
    
    def change_turn(self):
        if self.current_player == 'white':
            self.current_player = 'black'
        else:
            self.current_player = 'white'

        self.current_player_updated.emit(self.current_player)  # Emitowanie sygnału

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if isinstance(item, ChessPiece):
            self.clear_highlight()
            self.highlight_square(item)

        super().mousePressEvent(event)

    def highlight_square(self, chess_piece):
        square_size = self.square_size
        col = round(chess_piece.x() / square_size)
        row = round(chess_piece.y() / square_size)

        chess_piece.highlighted_square = HighlightedSquare(col * square_size, row * square_size, square_size)
        self.addItem(chess_piece.highlighted_square)
        chess_piece.highlighted_square.highlight()

    def clear_highlight(self):
        for item in self.items():
            if isinstance(item, HighlightedSquare):
                self.removeItem(item)
    def add_chess_piece(self, piece, col, row):
        self.addItem(piece)
        piece.setPos(col * self.square_size + (self.square_size - piece.pixmap().width()) / 2,
                     row * self.square_size + (self.square_size - piece.pixmap().height()) / 2)
        self.board[row][col] = piece  # Aktualizacja planszy

    def remove_chess_piece(self, col, row):
        piece = self.board[row][col]
        if piece:
            self.removeItem(piece)
            self.board[row][col] = None  # Usunięcie pionka z planszy
    def process_chess_notation(self, notation):
        try:
            # Parse the chess notation (e.g., "a3-a2")
            from_col = ord(notation[0]) - ord('a')
            from_row = 8 - int(notation[1])  # Convert 1-based row to 0-based index
            to_col = ord(notation[3]) - ord('a')
            to_row = 8 - int(notation[4])  # Convert 1-based row to 0-based index

            # Get the piece from the board
            piece = self.board[from_row][from_col]

            if piece and piece.player == self.current_player:
                # Simulate mouse press, move, and release events programmatically
                mouse_event = QMouseEvent(QEvent.MouseButtonPress, QPointF(0, 0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                piece.mousePressEvent(mouse_event)

                # Move the piece to the new position
                piece.setPos(to_col * self.square_size, to_row * self.square_size)

                mouse_event = QMouseEvent(QEvent.MouseButtonRelease, QPointF(0, 0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                piece.mouseReleaseEvent(mouse_event)

                # Clear any highlights after the move
                self.clear_highlight()

                # Change turn after successful move
                self.change_turn()

        except Exception as e:
            print(f"Invalid move: {e}")




    

class ChessboardView(QGraphicsView):
    def __init__(self, scene, square_size, log_thread):
        super().__init__(scene)
        self.setWindowTitle("Szachy")
        self.square_size = square_size
        self.init_chess_pieces(square_size, log_thread)

    def init_chess_pieces(self, square_size, log_thread):
        pieces = [
            ('b_rook', 0, 0, 'black'),
            ('b_knight', 1, 0, 'black'),
            ('b_bishop', 2, 0, 'black'),
            ('b_queen', 3, 0, 'black'),
            ('b_king', 4, 0, 'black'),
            ('b_bishop', 5, 0, 'black'),
            ('b_knight', 6, 0, 'black'),
            ('b_rook', 7, 0, 'black'),
            ('b_pawn', 0, 1, 'black'),
            ('b_pawn', 1, 1, 'black'),
            ('b_pawn', 2, 1, 'black'),
            ('b_pawn', 3, 1, 'black'),
            ('b_pawn', 4, 1, 'black'),
            ('b_pawn', 5, 1, 'black'),
            ('b_pawn', 6, 1, 'black'),
            ('b_pawn', 7, 1, 'black'),
            ('w_rook', 0, 7, 'white'),
            ('w_knight', 1, 7, 'white'),
            ('w_bishop', 2, 7, 'white'),
            ('w_queen', 3, 7, 'white'),
            ('w_king', 4, 7, 'white'),
            ('w_bishop', 5, 7, 'white'),
            ('w_knight', 6, 7, 'white'),
            ('w_rook', 7, 7, 'white'),
            ('w_pawn', 0, 6, 'white'),
            ('w_pawn', 1, 6, 'white'),
            ('w_pawn', 2, 6, 'white'),
            ('w_pawn', 3, 6, 'white'),
            ('w_pawn', 4, 6, 'white'),
            ('w_pawn', 5, 6, 'white'),
            ('w_pawn', 6, 6, 'white'),
            ('w_pawn', 7, 6, 'white'),
        ]

        for piece_type, col, row, player in pieces:
            chess_piece = ChessPiece(piece_type, square_size, player, log_thread)
            self.scene().add_chess_piece(chess_piece, col, row)



class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.session_names = set()  # To store unique session names


    def initUI(self):
        layout = QVBoxLayout()

        # Chessboard View
        self.scene = ChessboardScene(log_thread)
        view = ChessboardView(self.scene, self.scene.square_size, log_thread)
        layout.addWidget(view)

        # Current Player Label
        self.current_player_label = PlayerLabel(self.scene.current_player)
        layout.addWidget(self.current_player_label)

        # IP Address Input
        ip_label = QLabel("IP Address:")
        self.ip_input = QLineEdit()
        layout.addWidget(ip_label)
        layout.addWidget(self.ip_input)

        # Port Input
        port_label = QLabel("Port:")
        self.port_input = QLineEdit()
        layout.addWidget(port_label)
        layout.addWidget(self.port_input)

        # Log TextEdit
        self.log_textedit = QTextEdit()
        layout.addWidget(self.log_textedit)

        # Chess Notation Input
        self.chess_notation_input = QLineEdit()
        self.chess_notation_input.setPlaceholderText("Enter chess move (e.g., e2-e4)")
        layout.addWidget(self.chess_notation_input)

        # Connect chess notation input signal
        self.chess_notation_input.returnPressed.connect(self.process_chess_notation)

        # Connect log update signal
        log_thread.log_updated.connect(self.update_log_textedit)

        # Connect player change signal
        self.scene.current_player_updated.connect(self.current_player_label.update_player)

        # Start Game Button
        start_game_button = QPushButton("Start Game")
        start_game_button.clicked.connect(self.start_game)
        layout.addWidget(start_game_button)
        
        # Radio Buttons for Game Mode Selection
        self.human_vs_human_radio = QRadioButton("Human vs Human")
        self.human_vs_computer_radio = QRadioButton("Human vs Computer")

        # Set default mode (Human vs Human)
        self.human_vs_human_radio.setChecked(True)

        # Create layout for radio buttons
        radio_layout = QHBoxLayout()
        radio_layout.addWidget(self.human_vs_human_radio)
        radio_layout.addWidget(self.human_vs_computer_radio)
        layout.addLayout(radio_layout)

        self.setLayout(layout)
        self.setWindowTitle("Chess")
    
    def save_session_to_database(self, log_history):
        conn = sqlite3.connect('Chess_sessions.db')
        cursor = conn.cursor()

        # Generate a unique session name based on current date and time
        session_name = self.generate_unique_session_name()
        
        # Store session name in set to keep track of saved sessions
        self.session_names.add(session_name)

        # Insert session details into the database
        cursor.execute('''
            INSERT INTO sessions (session_name, move_history) 
            VALUES (?, ?)
        ''', (session_name, log_history))

        conn.commit()
        conn.close()
    
    def set_human_vs_human_mode(self):
        self.human_vs_computer_radio.setChecked(False)
        # Handle setting the game mode to Human vs Human
        # Implement your logic here (e.g., disable AI)

    def set_human_vs_computer_mode(self):
        self.human_vs_human_radio.setChecked(False)
        # Handle setting the game mode to Human vs Computer
        # Implement your logic here (e.g., enable AI)


    def generate_unique_session_name(self):
        # Format the session name using current date and time
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        session_name = f"Session_data_{timestamp}"
        return session_name


    def start_game(self):
        ip_address = self.ip_input.text()
        port = self.port_input.text()
        game_mode = "Human vs Human" if self.human_vs_human_radio.isChecked() else "Human vs Computer"

        # Create a dictionary with configuration data
        config_data = {
            "game_mode": game_mode,
            "ip_address": ip_address,
            "port": port
        }

        # Save configuration data to JSON file
        with open("config.json", "w") as json_file:
            json.dump(config_data, json_file)

        print("Configuration saved to config.json")

    def set_human_vs_human_mode(self):
        # Handle setting the game mode to Human vs Human
        pass  # Implement your logic here

    def set_human_vs_computer_mode(self):
        # Handle setting the game mode to Human vs Computer
        pass  # Implement your logic here
    
    def process_chess_notation(self):
        notation = self.chess_notation_input.text().strip()
        self.scene.process_chess_notation(notation)
        self.chess_notation_input.clear()



    def update_log_textedit(self, log):
        self.log_textedit.setPlainText(log)
        
class Piece:
    def __init__(self, piece_type, player):
        self.piece_type = piece_type
        self.player = player




if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Utwórz wątek logowania
    log_thread = LogThread()

    # Uruchom wątek logowania
    log_thread_thread = threading.Thread(target=log_thread.run)
    log_thread_thread.start()

    # Utwórz i wyświetl główne okno
    mainWindow = MainWindow()
    mainWindow.show()

    sys.exit(app.exec_())