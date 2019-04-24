from enum import Enum


class State(Enum):
    ALL = -1

    MENU = 0
    GAME = 1
    WITHDRAW = 3
    BET = 4
    TOP = 5
