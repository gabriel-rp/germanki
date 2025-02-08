import logging
import os
from typing import Optional


def get_logger(
    name: str = __file__,
    level: str = os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format: Optional[str] = None,
):
    logging.basicConfig(level=level, format=format)
    return logging.getLogger(name)


logger = get_logger()
