"""
Hockey Game Logic

Handles hockey-specific rules like goal detection, power plays, etc.
"""

import logging
from typing import Optional
from .state import GameState

logger = logging.getLogger(__name__)


class HockeyLogic:
    """
    Hockey game rules and event detection.

    Compares incoming data against previous state to detect
    events like goals, penalty expirations, period changes, etc.
    """

    def __init__(self):
        self._prev_home = 0
        self._prev_away = 0
        self._prev_period = "1"

    def process_update(self, new_data: dict) -> Optional[str]:
        """
        Process a game data update and detect events.

        Args:
            new_data: Dictionary with home, away, period, clock, penalties

        Returns:
            Event string if detected: "GOAL_HOME", "GOAL_AWAY",
            "PERIOD_CHANGE", or None
        """
        home = new_data.get("home", 0)
        away = new_data.get("away", 0)
        period = new_data.get("period", "1")

        event = None

        # Goal detection
        if home > self._prev_home:
            event = "GOAL_HOME"
            logger.info(f"GOAL! Home team scores! ({self._prev_home} -> {home})")
        elif away > self._prev_away:
            event = "GOAL_AWAY"
            logger.info(f"GOAL! Away team scores! ({self._prev_away} -> {away})")

        # Period change detection
        if period != self._prev_period:
            if event is None:
                event = "PERIOD_CHANGE"
            logger.info(f"Period change: {self._prev_period} -> {period}")

        # Update previous values
        self._prev_home = home
        self._prev_away = away
        self._prev_period = period

        return event

    def get_last_goal(self, new_data: dict) -> Optional[str]:
        """
        Check if a goal was scored.

        Returns:
            "HOME", "AWAY", or None
        """
        home = new_data.get("home", 0)
        away = new_data.get("away", 0)

        if home > self._prev_home:
            return "HOME"
        elif away > self._prev_away:
            return "AWAY"
        return None

    def is_power_play(self, home_penalties: list, away_penalties: list) -> dict:
        """
        Determine power play status.

        Args:
            home_penalties: List of home team penalty times (seconds)
            away_penalties: List of away team penalty times (seconds)

        Returns:
            Dictionary with power play info:
            {
                "home_pp": bool,  # Home team has power play
                "away_pp": bool,  # Away team has power play
                "home_adv": int,  # Home team player advantage
                "away_adv": int,  # Away team player advantage
            }
        """
        home_pen_count = len([p for p in home_penalties if p and p > 0])
        away_pen_count = len([p for p in away_penalties if p and p > 0])

        return {
            "home_pp": away_pen_count > home_pen_count,
            "away_pp": home_pen_count > away_pen_count,
            "home_adv": away_pen_count - home_pen_count,
            "away_adv": home_pen_count - away_pen_count,
        }

    def reset(self) -> None:
        """Reset tracking state for new game."""
        self._prev_home = 0
        self._prev_away = 0
        self._prev_period = "1"
