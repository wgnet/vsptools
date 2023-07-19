#!/usr/bin/env python3
import sys


class SpecialChar:
    END    = ''
    RED    = ''
    GREEN  = ''
    YELLOW = ''
    BLUE   = ''
    BG_RED = ''


def init_color():
    SpecialChar.END    = '\x1b[0m'
    SpecialChar.RED    = '\x1b[91m'
    SpecialChar.GREEN  = '\x1b[92m'
    SpecialChar.YELLOW = '\x1b[93m'
    SpecialChar.BLUE   = '\x1b[94m'
    SpecialChar.BG_RED = '\x1b[41;30m'


def add_color(msg, color):
    return "{}{}{}".format(color, msg, SpecialChar.END)


if sys.stdout.isatty():
    init_color()
