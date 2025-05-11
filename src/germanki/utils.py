import logging
import os


def get_logger(name: str):
    logging.basicConfig(
        level=os.environ.get('GERMANKI_LOG_LEVEL', 'INFO'),
        format='%(asctime)s %(levelname)s %(filename)s %(message)s',
    )
    return logging.getLogger(name)
