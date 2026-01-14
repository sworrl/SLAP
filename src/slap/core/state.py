"""
SLAP State Management

Centralized state for the entire application.
"""

import json
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from datetime import datetime


@dataclass
class GameState:
    """Current game state."""
    home_score: int = 0
    away_score: int = 0
    period: str = "1"
    clock: str = "20:00"
    home_penalties: List[int] = field(default_factory=list)
    away_penalties: List[int] = field(default_factory=list)
    last_goal: Optional[str] = None  # "HOME", "AWAY", or None
    last_update: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "home": self.home_score,
            "away": self.away_score,
            "period": self.period,
            "clock": self.clock,
            "home_penalties": self.home_penalties,
            "away_penalties": self.away_penalties,
            "last_goal": self.last_goal,
            "last_update": self.last_update.isoformat() if self.last_update else None
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def period_display(self) -> str:
        """Get display-friendly period string."""
        if self.period == "1":
            return "1st"
        elif self.period == "2":
            return "2nd"
        elif self.period == "3":
            return "3rd"
        elif self.period.upper() in ("OT", "O", "4"):
            return "OT"
        elif self.period.upper() in ("SO", "S"):
            return "SO"
        else:
            return self.period


class SystemState:
    """
    Global system state with thread-safe updates and change notifications.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._game = GameState()
        self._bug_visible = True
        self._replay_active = False
        self._serial_connected = False
        self._caspar_connected = False
        self._simulator_running = False
        self._listeners: List[Callable[[], None]] = []

    @property
    def game(self) -> GameState:
        """Get current game state."""
        with self._lock:
            return self._game

    @property
    def bug_visible(self) -> bool:
        with self._lock:
            return self._bug_visible

    @bug_visible.setter
    def bug_visible(self, value: bool) -> None:
        with self._lock:
            self._bug_visible = value
        self._notify_listeners()

    @property
    def replay_active(self) -> bool:
        with self._lock:
            return self._replay_active

    @replay_active.setter
    def replay_active(self, value: bool) -> None:
        with self._lock:
            self._replay_active = value
        self._notify_listeners()

    @property
    def serial_connected(self) -> bool:
        with self._lock:
            return self._serial_connected

    @serial_connected.setter
    def serial_connected(self, value: bool) -> None:
        with self._lock:
            self._serial_connected = value
        self._notify_listeners()

    @property
    def caspar_connected(self) -> bool:
        with self._lock:
            return self._caspar_connected

    @caspar_connected.setter
    def caspar_connected(self, value: bool) -> None:
        with self._lock:
            self._caspar_connected = value
        self._notify_listeners()

    @property
    def simulator_running(self) -> bool:
        with self._lock:
            return self._simulator_running

    @simulator_running.setter
    def simulator_running(self, value: bool) -> None:
        with self._lock:
            self._simulator_running = value
        self._notify_listeners()

    def update_game(self, **kwargs) -> None:
        """
        Update game state fields.

        Args:
            **kwargs: Fields to update (home_score, away_score, period, clock, etc.)
        """
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._game, key):
                    setattr(self._game, key, value)
            self._game.last_update = datetime.now()
        self._notify_listeners()

    def set_game(self, game: GameState) -> None:
        """Replace entire game state."""
        with self._lock:
            self._game = game
            self._game.last_update = datetime.now()
        self._notify_listeners()

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Add a state change listener."""
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        """Remove a state change listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        with self._lock:
            listeners = self._listeners.copy()
        for callback in listeners:
            try:
                callback()
            except Exception:
                pass

    def to_dict(self) -> dict:
        """Get full system state as dictionary."""
        with self._lock:
            return {
                "game": self._game.to_dict(),
                "bug_visible": self._bug_visible,
                "replay_active": self._replay_active,
                "serial_connected": self._serial_connected,
                "caspar_connected": self._caspar_connected,
                "simulator_running": self._simulator_running
            }

    def to_json(self) -> str:
        """Get full system state as JSON."""
        return json.dumps(self.to_dict())


# Global state instance
state = SystemState()
