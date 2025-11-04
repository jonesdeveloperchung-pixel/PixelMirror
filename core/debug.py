import logging

class Debug:
    """A class for handling debugging functionalities."""

    def __init__(self, enabled: bool = False):
        self._enabled = enabled
        if enabled:
            logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def log(self, name: str, message: str):
        if self._enabled:
            logger = logging.getLogger(name)
            logger.debug(message)
