import logging
import threading
import time

import colorlog

import bot

# Init logging
l_h = colorlog.StreamHandler()
formatter = colorlog.ColoredFormatter(
    '[%(asctime)s] %(log_color)s%(levelname)s:%(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red',
    },
)

formatter.converter = time.gmtime
l_h.setFormatter(formatter)

log = logging.getLogger('bot')
log.addHandler(l_h)
log.setLevel(logging.DEBUG)

def init():
    try:
        app = bot.RedditBot()
        app.handle_new()
    except KeyboardInterrupt:
        log.warning("Quitting...")
        return
if __name__ == '__main__':
    init()
