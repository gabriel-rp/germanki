import logging
import os


def get_logger(name: str):
    logging.basicConfig(
        level=os.environ.get('GERMANKI_LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(message)s',
    )
    return logging.getLogger(name)
