"""
Color text. Typical usage:

    red('red text', False)

Returns the string "red text" where the text will be red and the
background will be the default.

    red('red background')

Returns the string "red background" where the text will be the default
color and the background will be red.
"""

import logging
from colorama import init, Back, Fore  # BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET
init(autoreset=True)

__all__ = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']


def _color_it(text, color, bg):
    return getattr(bool(bg) and Back or Fore, color) + str(text) + getattr(bool(bg) and Back or Fore, 'RESET')


def black(text, background=True):
    return _color_it(text, 'BLACK', background)


def red(text, background=True):
    return _color_it(text, 'RED', background)


def green(text, background=True):
    return _color_it(text, 'GREEN', background)


def yellow(text, background=True):
    return _color_it(text, 'YELLOW', background)


def blue(text, background=True):
    return _color_it(text, 'BLUE', background)


def magenta(text, background=True):
    return _color_it(text, 'MAGENTA', background)


def cyan(text, background=True):
    return _color_it(text, 'CYAN', background)


def white(text, background=True):
    return _color_it(text, 'WHITE', background)


def add_color_log_levels(center=False):
    if center:
        c = 'CRITICAL'.center(8)
        e = 'ERROR'.center(8)
        w = 'WARNING'.center(8)
        i = 'INFO'.center(8)
        d = 'DEBUG'.center(8)
        n = 'NOTSET'.center(8)
    else:
        c = 'CRITICAL'
        e = 'ERROR'
        w = 'WARNING'
        i = 'INFO'
        d = 'DEBUG'
        n = 'NOTSET'
    logging.addLevelName(50, black(red(c, True)))
    logging.addLevelName(40, black(magenta(e, True)))
    logging.addLevelName(30, black(yellow(w, True)))
    logging.addLevelName(20, black(blue(i, True)))
    logging.addLevelName(10, black(green(d, True)))
    logging.addLevelName(0, black(white(n, True)))
