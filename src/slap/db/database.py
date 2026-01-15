"""
SLAP Database - SQLite storage for game history and statistics.

Database is stored in a platform-appropriate data directory:
- Linux: ~/.local/share/slap/slap.db
- macOS: ~/Library/Application Support/slap/slap.db
- Windows: %LOCALAPPDATA%/slap/slap.db

The database auto-creates and self-heals if corrupted.
"""

import os
import sys
import sqlite3
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """Get platform-appropriate data directory for SLAP."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # Linux/Unix - follow XDG spec
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return base / "slap"


def get_default_db_path() -> Path:
    """Get the default database path."""
    return get_data_dir() / "slap.db"


@dataclass
class Game:
    """Represents a completed or in-progress game."""
    id: Optional[int] = None
    home_team: str = "HOME"
    away_team: str = "AWAY"
    home_score: int = 0
    away_score: int = 0
    home_shots: int = 0
    away_shots: int = 0
    periods_played: int = 0
    status: str = "in_progress"  # in_progress, final, cancelled
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    venue: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GameEvent:
    """Represents a game event (goal, penalty, period change, etc.)."""
    id: Optional[int] = None
    game_id: int = 0
    event_type: str = ""  # goal, penalty, period_start, period_end, game_start, game_end
    team: str = ""  # home, away, or empty
    period: int = 0
    game_time: str = ""  # Clock time when event occurred
    player_number: str = ""
    player_name: str = ""
    assist1_number: str = ""
    assist1_name: str = ""
    assist2_number: str = ""
    assist2_name: str = ""
    penalty_minutes: int = 0
    penalty_type: str = ""
    details: str = ""  # JSON for additional data
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerStats:
    """Aggregated player statistics."""
    player_number: str = ""
    player_name: str = ""
    team: str = ""
    games_played: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0
    penalty_minutes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Database:
    """SQLite database manager for SLAP with self-healing capabilities."""

    # Current schema version for migrations
    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else get_default_db_path()
        self._ensure_data_dir()
        self._init_db()

    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Data directory: {self.db_path.parent}")

    def _check_db_health(self) -> bool:
        """Check if database is healthy and accessible."""
        if not self.db_path.exists():
            return False

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            # Run integrity check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def _backup_corrupted_db(self):
        """Backup corrupted database before recreation."""
        if self.db_path.exists():
            backup_path = self.db_path.with_suffix(
                f".corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            )
            try:
                shutil.move(str(self.db_path), str(backup_path))
                logger.warning(f"Corrupted database backed up to: {backup_path}")
            except Exception as e:
                logger.error(f"Failed to backup corrupted database: {e}")
                # Try to just delete it
                try:
                    self.db_path.unlink()
                except:
                    pass

    def _init_db(self):
        """Initialize database schema with self-healing."""
        # Check health and recreate if needed
        if self.db_path.exists() and not self._check_db_health():
            logger.warning("Database corruption detected, recreating...")
            self._backup_corrupted_db()

        try:
            self._create_schema()
            logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Last resort - delete and retry
            if self.db_path.exists():
                self._backup_corrupted_db()
                self._create_schema()

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections with auto-recovery."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database error: {e}")
                raise
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            logger.error(f"Database connection error: {e}")
            # Attempt recovery
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                logger.warning("Attempting database recovery...")
                self._backup_corrupted_db()
                self._create_schema()
                # Retry the connection
                conn = sqlite3.connect(str(self.db_path))
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                    conn.commit()
                finally:
                    conn.close()
            else:
                raise

    def _create_schema(self):
        """Create database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Schema version table for future migrations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Games table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    home_team TEXT NOT NULL DEFAULT 'HOME',
                    away_team TEXT NOT NULL DEFAULT 'AWAY',
                    home_score INTEGER DEFAULT 0,
                    away_score INTEGER DEFAULT 0,
                    home_shots INTEGER DEFAULT 0,
                    away_shots INTEGER DEFAULT 0,
                    periods_played INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'in_progress',
                    started_at TEXT,
                    ended_at TEXT,
                    venue TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Game events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    team TEXT DEFAULT '',
                    period INTEGER DEFAULT 0,
                    game_time TEXT DEFAULT '',
                    player_number TEXT DEFAULT '',
                    player_name TEXT DEFAULT '',
                    assist1_number TEXT DEFAULT '',
                    assist1_name TEXT DEFAULT '',
                    assist2_number TEXT DEFAULT '',
                    assist2_name TEXT DEFAULT '',
                    penalty_minutes INTEGER DEFAULT 0,
                    penalty_type TEXT DEFAULT '',
                    details TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
                )
            """)

            # Player season stats table (aggregated)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season TEXT NOT NULL,
                    player_number TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    team TEXT NOT NULL,
                    games_played INTEGER DEFAULT 0,
                    goals INTEGER DEFAULT 0,
                    assists INTEGER DEFAULT 0,
                    penalty_minutes INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(season, player_number, team)
                )
            """)

            # Indexes for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_started ON games(started_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_game ON game_events(game_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON game_events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_season ON player_stats(season)")

            # Record schema version
            cursor.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (self.SCHEMA_VERSION,)
            )

            conn.commit()
            logger.debug("Database schema initialized")
        finally:
            conn.close()

    # =====================
    # Game Management
    # =====================

    def create_game(self, home_team: str = "HOME", away_team: str = "AWAY",
                    venue: str = "") -> int:
        """Create a new game and return its ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO games (home_team, away_team, venue, started_at, status)
                VALUES (?, ?, ?, ?, 'in_progress')
            """, (home_team, away_team, venue, datetime.now().isoformat()))
            game_id = cursor.lastrowid

            # Log game start event
            cursor.execute("""
                INSERT INTO game_events (game_id, event_type, details)
                VALUES (?, 'game_start', '{}')
            """, (game_id,))

            logger.info(f"Created game {game_id}: {home_team} vs {away_team}")
            return game_id

    def get_game(self, game_id: int) -> Optional[Game]:
        """Get a game by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM games WHERE id = ?", (game_id,))
            row = cursor.fetchone()
            if row:
                return Game(**dict(row))
            return None

    def get_current_game(self) -> Optional[Game]:
        """Get the most recent in-progress game."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM games
                WHERE status = 'in_progress'
                ORDER BY started_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return Game(**dict(row))
            return None

    def get_recent_games(self, limit: int = 10) -> List[Game]:
        """Get recent games (most recent first)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM games
                ORDER BY started_at DESC LIMIT ?
            """, (limit,))
            return [Game(**dict(row)) for row in cursor.fetchall()]

    def get_games_by_date(self, date: str) -> List[Game]:
        """Get games for a specific date (YYYY-MM-DD format)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM games
                WHERE date(started_at) = date(?)
                ORDER BY started_at DESC
            """, (date,))
            return [Game(**dict(row)) for row in cursor.fetchall()]

    def update_game(self, game_id: int, **kwargs) -> bool:
        """Update game fields."""
        allowed_fields = ['home_team', 'away_team', 'home_score', 'away_score',
                         'home_shots', 'away_shots', 'periods_played', 'status',
                         'ended_at', 'venue', 'notes']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return False

        with self._get_conn() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [game_id]
            cursor.execute(f"""
                UPDATE games SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, values)
            return cursor.rowcount > 0

    def end_game(self, game_id: int, status: str = "final") -> bool:
        """Mark a game as ended."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE games SET status = ?, ended_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, datetime.now().isoformat(), game_id))

            if cursor.rowcount > 0:
                # Log game end event
                cursor.execute("""
                    INSERT INTO game_events (game_id, event_type, details)
                    VALUES (?, 'game_end', ?)
                """, (game_id, json.dumps({"status": status})))
                logger.info(f"Ended game {game_id} with status: {status}")
                return True
            return False

    def delete_game(self, game_id: int) -> bool:
        """Delete a game and all its events."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM games WHERE id = ?", (game_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted game {game_id}")
            return deleted

    # =====================
    # Event Logging
    # =====================

    def log_goal(self, game_id: int, team: str, period: int, game_time: str,
                 player_number: str = "", player_name: str = "",
                 assist1_number: str = "", assist1_name: str = "",
                 assist2_number: str = "", assist2_name: str = "") -> int:
        """Log a goal event and update game score."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Insert event
            cursor.execute("""
                INSERT INTO game_events
                (game_id, event_type, team, period, game_time, player_number, player_name,
                 assist1_number, assist1_name, assist2_number, assist2_name)
                VALUES (?, 'goal', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, team, period, game_time, player_number, player_name,
                  assist1_number, assist1_name, assist2_number, assist2_name))
            event_id = cursor.lastrowid

            # Update game score
            score_field = "home_score" if team.lower() == "home" else "away_score"
            cursor.execute(f"""
                UPDATE games SET {score_field} = {score_field} + 1,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (game_id,))

            # Update player stats
            season = datetime.now().strftime("%Y")
            if player_number:
                self._update_player_stat(cursor, season, player_number, player_name, team, goals=1)
            if assist1_number:
                self._update_player_stat(cursor, season, assist1_number, assist1_name, team, assists=1)
            if assist2_number:
                self._update_player_stat(cursor, season, assist2_number, assist2_name, team, assists=1)

            logger.info(f"Goal logged: Game {game_id}, {team}, #{player_number} {player_name}")
            return event_id

    def log_penalty(self, game_id: int, team: str, period: int, game_time: str,
                    player_number: str = "", player_name: str = "",
                    penalty_minutes: int = 2, penalty_type: str = "") -> int:
        """Log a penalty event."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO game_events
                (game_id, event_type, team, period, game_time, player_number, player_name,
                 penalty_minutes, penalty_type)
                VALUES (?, 'penalty', ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, team, period, game_time, player_number, player_name,
                  penalty_minutes, penalty_type))
            event_id = cursor.lastrowid

            # Update player PIM stats
            season = datetime.now().strftime("%Y")
            if player_number:
                self._update_player_stat(cursor, season, player_number, player_name, team,
                                        penalty_minutes=penalty_minutes)

            logger.info(f"Penalty logged: Game {game_id}, {team}, #{player_number} - {penalty_minutes}min")
            return event_id

    def log_period_change(self, game_id: int, period: int, event_type: str = "period_start") -> int:
        """Log period start or end."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO game_events (game_id, event_type, period)
                VALUES (?, ?, ?)
            """, (game_id, event_type, period))

            # Update periods played
            if event_type == "period_end":
                cursor.execute("""
                    UPDATE games SET periods_played = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (period, game_id))

            return cursor.lastrowid

    def log_shot(self, game_id: int, team: str) -> None:
        """Increment shot count for a team."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            shot_field = "home_shots" if team.lower() == "home" else "away_shots"
            cursor.execute(f"""
                UPDATE games SET {shot_field} = {shot_field} + 1,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (game_id,))

    def get_game_events(self, game_id: int, event_type: Optional[str] = None) -> List[GameEvent]:
        """Get all events for a game, optionally filtered by type."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if event_type:
                cursor.execute("""
                    SELECT * FROM game_events
                    WHERE game_id = ? AND event_type = ?
                    ORDER BY created_at ASC
                """, (game_id, event_type))
            else:
                cursor.execute("""
                    SELECT * FROM game_events WHERE game_id = ?
                    ORDER BY created_at ASC
                """, (game_id,))
            return [GameEvent(**dict(row)) for row in cursor.fetchall()]

    def get_game_goals(self, game_id: int) -> List[GameEvent]:
        """Get all goals for a game."""
        return self.get_game_events(game_id, event_type="goal")

    def get_game_penalties(self, game_id: int) -> List[GameEvent]:
        """Get all penalties for a game."""
        return self.get_game_events(game_id, event_type="penalty")

    # =====================
    # Player Statistics
    # =====================

    def _update_player_stat(self, cursor, season: str, player_number: str,
                           player_name: str, team: str, goals: int = 0,
                           assists: int = 0, penalty_minutes: int = 0):
        """Internal method to update player stats."""
        cursor.execute("""
            INSERT INTO player_stats (season, player_number, player_name, team,
                                      goals, assists, penalty_minutes, games_played)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(season, player_number, team) DO UPDATE SET
                player_name = excluded.player_name,
                goals = goals + excluded.goals,
                assists = assists + excluded.assists,
                penalty_minutes = penalty_minutes + excluded.penalty_minutes,
                updated_at = CURRENT_TIMESTAMP
        """, (season, player_number, player_name, team, goals, assists, penalty_minutes))

    def get_player_stats(self, season: Optional[str] = None,
                         team: Optional[str] = None) -> List[PlayerStats]:
        """Get player statistics, optionally filtered by season/team."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM player_stats WHERE 1=1"
            params = []

            if season:
                query += " AND season = ?"
                params.append(season)
            if team:
                query += " AND team = ?"
                params.append(team)

            query += " ORDER BY (goals + assists) DESC, goals DESC"
            cursor.execute(query, params)

            results = []
            for row in cursor.fetchall():
                stats = PlayerStats(
                    player_number=row['player_number'],
                    player_name=row['player_name'],
                    team=row['team'],
                    games_played=row['games_played'],
                    goals=row['goals'],
                    assists=row['assists'],
                    points=row['goals'] + row['assists'],
                    penalty_minutes=row['penalty_minutes']
                )
                results.append(stats)
            return results

    def get_season_leaders(self, season: Optional[str] = None,
                           stat: str = "points", limit: int = 10) -> List[PlayerStats]:
        """Get statistical leaders for a season."""
        if season is None:
            season = datetime.now().strftime("%Y")

        with self._get_conn() as conn:
            cursor = conn.cursor()

            order_by = {
                "points": "(goals + assists) DESC, goals DESC",
                "goals": "goals DESC",
                "assists": "assists DESC",
                "pim": "penalty_minutes DESC"
            }.get(stat, "(goals + assists) DESC")

            cursor.execute(f"""
                SELECT * FROM player_stats
                WHERE season = ?
                ORDER BY {order_by}
                LIMIT ?
            """, (season, limit))

            results = []
            for row in cursor.fetchall():
                stats = PlayerStats(
                    player_number=row['player_number'],
                    player_name=row['player_name'],
                    team=row['team'],
                    games_played=row['games_played'],
                    goals=row['goals'],
                    assists=row['assists'],
                    points=row['goals'] + row['assists'],
                    penalty_minutes=row['penalty_minutes']
                )
                results.append(stats)
            return results

    def increment_games_played(self, game_id: int):
        """Increment games played for all players who scored/assisted in a game."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            season = datetime.now().strftime("%Y")

            # Get unique players from goals
            cursor.execute("""
                SELECT DISTINCT player_number, player_name, team FROM game_events
                WHERE game_id = ? AND event_type = 'goal' AND player_number != ''
                UNION
                SELECT DISTINCT assist1_number, assist1_name, team FROM game_events
                WHERE game_id = ? AND event_type = 'goal' AND assist1_number != ''
                UNION
                SELECT DISTINCT assist2_number, assist2_name, team FROM game_events
                WHERE game_id = ? AND event_type = 'goal' AND assist2_number != ''
            """, (game_id, game_id, game_id))

            players = cursor.fetchall()
            for player in players:
                cursor.execute("""
                    UPDATE player_stats SET games_played = games_played + 1
                    WHERE season = ? AND player_number = ? AND team = ?
                """, (season, player[0], player[2]))

    # =====================
    # Statistics & Reports
    # =====================

    def get_team_record(self, team: str, season: Optional[str] = None) -> Dict[str, int]:
        """Get win/loss/otl record for a team."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            query_base = """
                SELECT
                    SUM(CASE WHEN (home_team = ? AND home_score > away_score) OR
                             (away_team = ? AND away_score > home_score) THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN (home_team = ? AND home_score < away_score) OR
                             (away_team = ? AND away_score < home_score) THEN 1 ELSE 0 END) as losses,
                    COUNT(*) as games
                FROM games
                WHERE status = 'final' AND (home_team = ? OR away_team = ?)
            """
            params = [team, team, team, team, team, team]

            if season:
                query_base += " AND strftime('%Y', started_at) = ?"
                params.append(season)

            cursor.execute(query_base, params)
            row = cursor.fetchone()

            return {
                "wins": row['wins'] or 0,
                "losses": row['losses'] or 0,
                "games": row['games'] or 0
            }

    def get_head_to_head(self, team1: str, team2: str) -> Dict[str, Any]:
        """Get head-to-head record between two teams."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM games
                WHERE status = 'final' AND
                      ((home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?))
                ORDER BY started_at DESC
            """, (team1, team2, team2, team1))

            games = [Game(**dict(row)) for row in cursor.fetchall()]

            team1_wins = sum(1 for g in games if
                           (g.home_team == team1 and g.home_score > g.away_score) or
                           (g.away_team == team1 and g.away_score > g.home_score))
            team2_wins = len(games) - team1_wins

            return {
                "team1": team1,
                "team2": team2,
                "team1_wins": team1_wins,
                "team2_wins": team2_wins,
                "games": [g.to_dict() for g in games]
            }

    def export_game_summary(self, game_id: int) -> Dict[str, Any]:
        """Export complete game summary with all events."""
        game = self.get_game(game_id)
        if not game:
            return {}

        events = self.get_game_events(game_id)
        goals = [e for e in events if e.event_type == "goal"]
        penalties = [e for e in events if e.event_type == "penalty"]

        return {
            "game": game.to_dict(),
            "goals": [g.to_dict() for g in goals],
            "penalties": [p.to_dict() for p in penalties],
            "scoring_summary": {
                "home": [g.to_dict() for g in goals if g.team.lower() == "home"],
                "away": [g.to_dict() for g in goals if g.team.lower() == "away"]
            },
            "total_events": len(events)
        }


# Global database instance
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """Get or create the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
