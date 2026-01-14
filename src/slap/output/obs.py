"""
OBS WebSocket Client

Controls OBS Studio via WebSocket to create and manage scorebug overlays.
Requires OBS 28+ with WebSocket server enabled.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import obsws-python
try:
    import obsws_python as obs
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning("obsws-python not installed. OBS control disabled.")


class OBSClient:
    """Client for controlling OBS Studio via WebSocket."""

    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        """
        Initialize OBS WebSocket client.

        Args:
            host: OBS WebSocket host
            port: OBS WebSocket port (default 4455 for OBS 28+)
            password: WebSocket password (if set in OBS)
        """
        self.host = host
        self.port = port
        self.password = password
        self._client: Optional[obs.ReqClient] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """Check if connected to OBS."""
        return self._connected

    def connect(self) -> bool:
        """
        Connect to OBS WebSocket server.

        Returns:
            True if connected successfully
        """
        if not OBS_AVAILABLE:
            logger.error("obsws-python not installed")
            return False

        try:
            self._client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=5
            )
            self._connected = True
            logger.info(f"Connected to OBS at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OBS: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from OBS WebSocket server."""
        if self._client:
            try:
                self._client = None
            except:
                pass
        self._connected = False
        logger.info("Disconnected from OBS")

    def get_version(self) -> Optional[dict]:
        """Get OBS version info."""
        if not self._connected or not self._client:
            return None
        try:
            resp = self._client.get_version()
            return {
                "obs_version": resp.obs_version,
                "websocket_version": resp.obs_web_socket_version,
                "platform": resp.platform
            }
        except Exception as e:
            logger.error(f"Failed to get OBS version: {e}")
            return None

    def get_scene_list(self) -> list:
        """Get list of scenes in OBS."""
        if not self._connected or not self._client:
            return []
        try:
            resp = self._client.get_scene_list()
            return [s["sceneName"] for s in resp.scenes]
        except Exception as e:
            logger.error(f"Failed to get scene list: {e}")
            return []

    def get_current_scene(self) -> Optional[str]:
        """Get the current active scene name."""
        if not self._connected or not self._client:
            return None
        try:
            resp = self._client.get_current_program_scene()
            return resp.current_program_scene_name
        except Exception as e:
            logger.error(f"Failed to get current scene: {e}")
            return None

    def get_source_list(self, scene_name: str = None) -> list:
        """Get list of sources in a scene."""
        if not self._connected or not self._client:
            return []
        try:
            if scene_name is None:
                scene_name = self.get_current_scene()
            if not scene_name:
                return []
            resp = self._client.get_scene_item_list(scene_name)
            return [item["sourceName"] for item in resp.scene_items]
        except Exception as e:
            logger.error(f"Failed to get source list: {e}")
            return []

    def create_browser_source(
        self,
        source_name: str,
        url: str,
        width: int = 1920,
        height: int = 1080,
        scene_name: str = None
    ) -> bool:
        """
        Create a browser source for the scorebug overlay.

        Args:
            source_name: Name for the browser source
            url: URL to load in the browser source
            width: Browser width
            height: Browser height
            scene_name: Scene to add source to (default: current scene)

        Returns:
            True if created successfully
        """
        if not self._connected or not self._client:
            return False

        try:
            if scene_name is None:
                scene_name = self.get_current_scene()
            if not scene_name:
                logger.error("No scene available")
                return False

            # Check if source already exists
            existing_sources = self.get_source_list(scene_name)
            if source_name in existing_sources:
                logger.info(f"Source '{source_name}' already exists, updating URL")
                return self.update_browser_source(source_name, url, width, height)

            # Create the browser source input
            input_settings = {
                "url": url,
                "width": width,
                "height": height,
                "css": "body { background-color: rgba(0, 0, 0, 0); margin: 0px auto; overflow: hidden; }",
                "shutdown": False,
                "restart_when_active": False,
                "reroute_audio": False
            }

            self._client.create_input(
                sceneName=scene_name,
                inputName=source_name,
                inputKind="browser_source",
                inputSettings=input_settings,
                sceneItemEnabled=True
            )

            logger.info(f"Created browser source '{source_name}' in scene '{scene_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to create browser source: {e}")
            return False

    def update_browser_source(
        self,
        source_name: str,
        url: str = None,
        width: int = None,
        height: int = None
    ) -> bool:
        """
        Update an existing browser source.

        Args:
            source_name: Name of the browser source
            url: New URL (optional)
            width: New width (optional)
            height: New height (optional)

        Returns:
            True if updated successfully
        """
        if not self._connected or not self._client:
            return False

        try:
            settings = {}
            if url is not None:
                settings["url"] = url
            if width is not None:
                settings["width"] = width
            if height is not None:
                settings["height"] = height

            if settings:
                self._client.set_input_settings(
                    inputName=source_name,
                    inputSettings=settings,
                    overlay=True
                )
                logger.info(f"Updated browser source '{source_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to update browser source: {e}")
            return False

    def remove_source(self, source_name: str, scene_name: str = None) -> bool:
        """
        Remove a source from a scene.

        Args:
            source_name: Name of the source to remove
            scene_name: Scene to remove from (default: current scene)

        Returns:
            True if removed successfully
        """
        if not self._connected or not self._client:
            return False

        try:
            if scene_name is None:
                scene_name = self.get_current_scene()
            if not scene_name:
                return False

            # Get scene item ID
            resp = self._client.get_scene_item_list(sceneName=scene_name)
            item_id = None
            for item in resp.scene_items:
                if item["sourceName"] == source_name:
                    item_id = item["sceneItemId"]
                    break

            if item_id is None:
                logger.warning(f"Source '{source_name}' not found in scene")
                return False

            self._client.remove_scene_item(sceneName=scene_name, sceneItemId=item_id)
            logger.info(f"Removed source '{source_name}' from scene '{scene_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to remove source: {e}")
            return False

    def set_source_visible(self, source_name: str, visible: bool, scene_name: str = None) -> bool:
        """
        Show or hide a source in a scene.

        Args:
            source_name: Name of the source
            visible: True to show, False to hide
            scene_name: Scene name (default: current scene)

        Returns:
            True if successful
        """
        if not self._connected or not self._client:
            return False

        try:
            if scene_name is None:
                scene_name = self.get_current_scene()
            if not scene_name:
                return False

            # Get scene item ID
            resp = self._client.get_scene_item_list(sceneName=scene_name)
            item_id = None
            for item in resp.scene_items:
                if item["sourceName"] == source_name:
                    item_id = item["sceneItemId"]
                    break

            if item_id is None:
                return False

            self._client.set_scene_item_enabled(
                sceneName=scene_name,
                sceneItemId=item_id,
                sceneItemEnabled=visible
            )
            return True

        except Exception as e:
            logger.error(f"Failed to set source visibility: {e}")
            return False

    def refresh_browser_source(self, source_name: str) -> bool:
        """
        Refresh a browser source (reload the page).

        Args:
            source_name: Name of the browser source

        Returns:
            True if successful
        """
        if not self._connected or not self._client:
            return False

        try:
            self._client.press_input_properties_button(inputName=source_name, propertyName="refreshnocache")
            logger.info(f"Refreshed browser source '{source_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh browser source: {e}")
            return False

    def setup_scorebug(self, slap_url: str = "http://localhost:9876") -> bool:
        """
        Set up the SLAP scorebug overlay in OBS.

        This creates a browser source pointing to the SLAP scorebug template.

        Args:
            slap_url: Base URL of the SLAP server

        Returns:
            True if setup successfully
        """
        scorebug_url = f"{slap_url}/templates/scorebug.html"
        return self.create_browser_source(
            source_name="SLAP Scorebug",
            url=scorebug_url,
            width=1920,
            height=1080
        )
