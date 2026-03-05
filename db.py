import sqlite3
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / 'truth_or_dare.db'

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    creator_id INTEGER NOT NULL,
                    difficulty TEXT CHECK(difficulty IN ('easy', 'medium', 'hard', 'hardcore')),
                    context_tags TEXT,
                    status TEXT CHECK(status IN ('active', 'finished', 'abandoned')) DEFAULT 'active',
                    current_player_index INTEGER DEFAULT 0,
                    total_turns INTEGER DEFAULT 0,
                    current_task_text TEXT,         
                    current_task_title TEXT,          
                    current_task_context TEXT,        
                    current_task_type TEXT,           
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    user_id INTEGER, 
                    player_name TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_game ON game_players(game_id)')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    type TEXT CHECK(type IN ('truth', 'dare')),
                    difficulty TEXT CHECK(difficulty IN ('easy', 'medium', 'hard', 'hardcore')),
                    tags TEXT,
                    source TEXT CHECK(source IN ('ai', 'manual')) DEFAULT 'manual',
                    is_verified INTEGER DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER,
                    prompt TEXT,
                    response TEXT,
                    status TEXT CHECK(status IN ('success', 'error')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    role TEXT CHECK(role IN ('user', 'bot')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cards_diff ON cards(difficulty)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cards_verified ON cards(is_verified)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_chat ON games(chat_id)')
            
            print(f"✓ БД инициализирована: {self.db_path}")

    def add_user(self, user_id: int, username: str = None, first_name: str = None):
        with get_db_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO users (id, username, first_name) VALUES (?, ?, ?)',
                (user_id, username, first_name)
            )

    def create_game(self, chat_id: int, creator_id: int, difficulty: str, context_tags: str) -> int:
        with get_db_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO users (id) VALUES (?)',
                (creator_id,)
            )

            cursor = conn.execute(
                '''INSERT INTO games (chat_id, creator_id, difficulty, context_tags, status, total_turns) 
                   VALUES (?, ?, ?, ?, 'active', 0)''',
                (chat_id, creator_id, difficulty, context_tags)
            )
            return cursor.lastrowid

    def add_player_to_game(self, game_id: int, user_id: int, player_name: str):
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO game_players (game_id, user_id, player_name, score) VALUES (?, ?, ?, 0)',
                (game_id, user_id, player_name)
            )

    def get_active_game(self, chat_id: int) -> Optional[sqlite3.Row]:
        with get_db_connection() as conn:
            return conn.execute(
                "SELECT * FROM games WHERE chat_id = ? AND status = 'active' LIMIT 1",
                (chat_id,)
            ).fetchone()

    def get_game_players(self, game_id: int) -> List[sqlite3.Row]:
        with get_db_connection() as conn:
            return conn.execute(
                'SELECT * FROM game_players WHERE game_id = ? ORDER BY id',
                (game_id,)
            ).fetchall()

    def update_player_score_by_name(self, game_id: int, player_name: str, increment: int = 1):
        with get_db_connection() as conn:
            conn.execute(
                'UPDATE game_players SET score = score + ? WHERE game_id = ? AND player_name = ?',
                (increment, game_id, player_name)
            )

    def get_game_results(self, game_id: int) -> List[sqlite3.Row]:
        with get_db_connection() as conn:
            return conn.execute(
                'SELECT player_name, score FROM game_players WHERE game_id = ? ORDER BY score DESC',
                (game_id,)
            ).fetchall()

    def update_game_turn(self, game_id: int, player_index: int):
        """Обновляет индекс игрока и увеличивает счётчик ходов"""
        with get_db_connection() as conn:
            conn.execute(
                'UPDATE games SET current_player_index = ?, total_turns = total_turns + 1 WHERE id = ?',
                (player_index, game_id)
            )

    def get_total_turns(self, game_id: int) -> int:
        """Возвращает общее количество сделанных ходов"""
        with get_db_connection() as conn:
            result = conn.execute(
                'SELECT total_turns FROM games WHERE id = ?',
                (game_id,)
            ).fetchone()
            return result['total_turns'] if result else 0

    def get_player_count(self, game_id: int) -> int:
        """Возвращает количество игроков в игре"""
        with get_db_connection() as conn:
            result = conn.execute(
                'SELECT COUNT(*) as count FROM game_players WHERE game_id = ?',
                (game_id,)
            ).fetchone()
            return result['count'] if result else 0

    def finish_game(self, game_id: int):
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE games SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                (game_id,)
            )

    def get_card(self, difficulty: str, card_type: str, context: str = None) -> Optional[sqlite3.Row]:
        """Получает карточку из БД. Для hardcore только проверенные."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM cards WHERE type = ? AND difficulty = ?'
            params = [card_type, difficulty]
            
            # Для сложных уровней только верифицированные карточки
            if difficulty in ['hard', 'hardcore']:
                query += ' AND is_verified = 1'
            
            # Простой фильтр по контексту (поиск подстроки в тегах)
            if context and context != 'general':
                query += f" AND (tags LIKE '%{context}%' OR tags IS NULL)"
            
            query += ' ORDER BY RANDOM() LIMIT 1'
            
            result = cursor.execute(query, params).fetchone()
            
            # Увеличиваем счётчик использования
            if result:
                cursor.execute(
                    'UPDATE cards SET usage_count = usage_count + 1 WHERE id = ?',
                    (result['id'],)
                )
            
            return result

        def add_card(self, text: str, card_type: str, difficulty: str, 
                     tags: str = None, source: str = 'manual', is_verified: int = 0):
            with get_db_connection() as conn:
                conn.execute(
                    '''INSERT INTO cards (text, type, difficulty, tags, source, is_verified) 
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (text, card_type, difficulty, tags, source, is_verified)
                )

        # ================= GAMES =================
    def save_current_task(self, game_id: int, task_text: str, title: str, context: str, task_type: str):
        """Сохраняет текущее задание в БД"""
        with get_db_connection() as conn:
            conn.execute(
                '''UPDATE games SET 
                   current_task_text = ?, 
                   current_task_title = ?, 
                   current_task_context = ?, 
                   current_task_type = ?
                   WHERE id = ?''',
                (task_text, title, context, task_type, game_id)
            )

    def get_current_task(self, game_id: int) -> Optional[sqlite3.Row]:
        """Восстанавливает текущее задание из БД"""
        with get_db_connection() as conn:
            return conn.execute(
                'SELECT current_task_text, current_task_title, current_task_context, current_task_type FROM games WHERE id = ?',
                (game_id,)
            ).fetchone()

    def clear_current_task(self, game_id: int):
        """Очищает текущее задание после выполнения"""
        with get_db_connection() as conn:
            conn.execute(
                '''UPDATE games SET 
                   current_task_text = NULL, 
                   current_task_title = NULL, 
                   current_task_context = NULL, 
                   current_task_type = NULL
                   WHERE id = ?''',
                (game_id,)
            )

def init_db():
    return Database()

if __name__ == '__main__':
    db = Database()
    print("✓ Структура БД готова к работе")
