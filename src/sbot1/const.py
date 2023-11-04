from enum import Enum

bombs_threshold = 1650  # ms
invalid_pos_set = {1, 3, 4, 5, 13}
valid_pos_set = {0, 6, 7, 8}
target_pos_set = {6, 7, 8}
spoil_set = {6, 7, 8, 9}


class NextMove(Enum):
    UP = '3'
    DOWN = '4'
    LEFT = '1'
    RIGHT = '2'
    BOMB = 'b'


class InvalidPos(Enum):
    TEMP = -1
    WALL = 1
    TELE_GATE = 3
    QUARANTINE = 4
    EGG_GST = 5
    BOMB = 13


class ValidPos(Enum):
    ROAD = 0
    BALK = 2
    EGG_SPEED = 6
    EGG_ATTACK = 7
    EGG_DELAY = 8


class TargetPos(Enum):
    EGG_SPEED = 6
    EGG_ATTACK = 7
    EGG_DELAY = 8


class Spoil(Enum):
    """Increase by 3 units."""
    BIAS = 3
    EGG_SPEED = 6
    EGG_ATTACK = 7
    EGG_DELAY = 8
    EGG_MYSTIC = 9
