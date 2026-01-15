"""
SLAP Database Module
SQLite-based storage for game history, statistics, and events.

Database location:
- Linux: ~/.local/share/slap/slap.db
- macOS: ~/Library/Application Support/slap/slap.db
- Windows: %LOCALAPPDATA%/slap/slap.db
"""

from .database import Database, get_db, get_data_dir, get_default_db_path

__all__ = ["Database", "get_db", "get_data_dir", "get_default_db_path"]
