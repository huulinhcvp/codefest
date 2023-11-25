import time
import copy
import socketio
import numpy as np
from queue import PriorityQueue
from game_info import GameInfo
from collections import deque
from const import (
    NextMove,
    Spoil,
    ValidPos,
    InvalidPos,
    valid_pos_set,
    invalid_pos_set,
    target_pos_set,
    bombs_threshold
)

sio = socketio.Client()

map_states = []
counter = 0
count_opp = 0
opp_pos = None
normal_queue = []
saved_routes = dict()
delay_time = 320
player_speed = 320
time_explosed_bomb = 0
previous_pos = None
previous_timestamp = 0
max_time = 0
max_len = -1
last_directions = ''

bomb_timestamp = 0
list_bombs = dict()
attack_directions = np.array(
    [[-1, 0], [0, -1], [0, 1], [1, 0]])
egg_directions = np.array(
    [[-1, 0], [0, -1], [0, 1], [1, 0],
     [-1, 1], [1, -1], [1, 1], [-1, -1]])
new_my_directions = np.array(
    [[-1, 2], [1, 2], [-1, -2], [1, -2]])
new_opp_directions = np.array(
    [[-1, 2], [1, 2], [-1, -2], [1, -2],
     [-1, 3], [1, 3], [-1, -3], [1, -3],
     [-2, 3], [2, 3], [-2, -3], [2, -3]])
add_opp_directions = np.array(
    [[-1, 2], [1, 2], [-1, -2], [1, -2],
     [-1, 3], [1, 3], [-1, -3], [1, -3],
     [-2, 3], [2, 3], [-2, -3], [2, -3],
     [-1, 4], [1, 4], [-1, -4], [1, -4],
     [-2, 4], [2, 4], [-2, -4], [2, -4],
     [-3, 4], [3, 4], [-3, -4], [3, -4]])
directions = {
    NextMove.UP: (-1, 0),
    NextMove.LEFT: (0, -1),
    NextMove.RIGHT: (0, 1),
    NextMove.DOWN: (1, 0)
}
map_routes = {
    NextMove.UP.value: NextMove.DOWN.value,
    NextMove.DOWN.value: NextMove.UP.value,
    NextMove.LEFT.value: NextMove.RIGHT.value,
    NextMove.RIGHT.value: NextMove.LEFT.value,
    NextMove.BOMB.value: None
}


class GameBot:
    def __init__(
            self,
            player_id,
            cur_pos,
            lives,
            speed,
            power,
            score,
            delay
    ):
        self._id = player_id
        self._pos = cur_pos
        self._lives = lives
        self._speed = speed
        self._power = power
        self._score = score
        self._delay = delay
        self._egg = None

    @property
    def id(self):
        return self._id

    @property
    def pos(self):
        return self._pos

    @property
    def lives(self):
        return self._lives

    @property
    def speed(self):
        return self._speed

    @property
    def power(self):
        return self._power

    @property
    def score(self):
        return self._score

    @property
    def delay(self):
        return self._delay

    @property
    def egg(self):
        return self._egg

    @egg.setter
    def egg(self, pos):
        self._egg = pos


class GameMap:

    def __init__(self, data):
        self._tag = data['tag']
        self._id = data['id']
        self._timestamp = data['timestamp']
        self._map_info = data["map_info"]
        self._player_id = data.get('player_id')
        self._my_bot = None
        self._opp_bot = None
        self._max_row = self.map_info['size']['rows']
        self._max_col = self.map_info['size']['cols']
        self.map_matrix = np.array(self.map_info['map'])  # convert 2d matrix into nd-array data type
        self.spoils = dict()
        self.targets = dict()
        self.bombs = dict()
        self.bomb_targets = dict()
        self.bombs_danger = dict()

    @property
    def tag(self):
        return self._tag

    @property
    def id(self):
        return self._id

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def map_info(self):
        return self._map_info

    @property
    def player_id(self):
        return self._player_id

    @property
    def my_bot(self):
        return self._my_bot

    @my_bot.setter
    def my_bot(self, value):
        self._my_bot = value

    @property
    def opp_bot(self):
        return self._opp_bot

    @opp_bot.setter
    def opp_bot(self, value):
        self._opp_bot = value

    @property
    def max_row(self):
        return self._max_row

    @property
    def max_col(self):
        return self._max_col

    def find_bots(self):
        """Retrieve information about yourself and your opponents."""
        for player in self.map_info['players']:
            player_id = player.get('id')
            player_pos = (
                player.get('currentPosition')['row'],
                player.get('currentPosition')['col']
            )
            player_lives = player.get('lives')
            player_speed = player.get('speed')
            player_power = player.get('power')
            player_score = player.get('score')
            player_delay = player.get('delay')
            game_bot = GameBot(
                player_id,
                player_pos,
                player_lives,
                player_speed,
                player_power,
                player_score,
                player_delay
            )
            if player_id and player_id in GameInfo.PLAYER_ID:
                self.my_bot = game_bot
            else:
                self.opp_bot = game_bot

        # Fill eggs info
        for egg in self.map_info['dragonEggGSTArray']:
            egg_pos = (egg.get('row'), egg.get('col'))
            player_id = egg.get('id')
            if player_id and player_id in GameInfo.PLAYER_ID:
                self.my_bot.egg = egg_pos
            else:
                self.opp_bot.egg = egg_pos

    def num_balk(self, pos):
        """Return True if pos near the balk."""
        num_balk = 0
        power = min(self.my_bot.power, 4)
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(InvalidPos.TEMP.value)
        tmp.add(InvalidPos.BOMB.value)
        tmp.add(Spoil.EGG_MYSTIC.value)
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                row = pos[0] + attack[0]
                col = pos[1] + attack[1]
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    break
                if self.map_matrix[row][col] in tmp:
                    continue
                if self.map_matrix[row][col] == ValidPos.BALK.value:
                    if row == self.opp_bot.pos[0] and col == self.opp_bot.pos[1]:
                        continue
                    elif row == self.opp_bot.egg[0] and col == self.opp_bot.egg[1]:
                        num_balk += 3
                    else:
                        num_balk += 1
                elif self.map_matrix[row][col] == 1:
                    break
                elif self.map_matrix[row][col] == 5:
                    break
        return num_balk

    def is_opp_safe_time(self):
        diff = self.opp_bot.score - self.my_bot.score
        num_balks = np.count_nonzero(self.map_matrix == 2)
        num_spoils = 0
        for spoil_value in target_pos_set:
            num_spoils = num_spoils + np.count_nonzero(self.map_matrix == spoil_value)

        bias = diff - (num_balks + num_spoils) // 2

        return bias

    def is_connected_to_opp(self):
        cur_pos = self.my_bot.pos
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(Spoil.EGG_MYSTIC.value)
        saved = set()
        saved.add(cur_pos)
        move_queue = deque()
        move_queue.append([cur_pos, [], [], 0])

        while len(move_queue) > 0:
            pos, routes, poses, score = move_queue.popleft()
            # Move to 4 directions next to current position.
            if self.can_attack(pos):
                return pos, routes, poses, score

            next_routes = []  # Save all routes along with related information.
            for route, direction in directions.items():
                next_pos = (pos[0] + direction[0], pos[1] + direction[1])

                if next_pos in saved:
                    continue
                # invalid positions
                if next_pos[0] < 0 or next_pos[0] >= self.max_row or next_pos[1] < 0 or next_pos[1] >= self.max_col:
                    continue
                # valid positions
                if self.map_matrix[next_pos[0]][next_pos[1]] in tmp:
                    saved.add(next_pos)
                    next_routes.append([next_pos, score + 1, score, route.value])

            # next_routes.sort(key=lambda x: x[2])
            for move in next_routes:
                r = copy.deepcopy(routes)
                r.append(move[3])
                p = copy.deepcopy(poses)
                p.append(move[0])
                move_queue.append([move[0], r, p, move[1]])

        return cur_pos, [], [], 0

    def can_attack(self, pos):
        power = min(self.my_bot.power, 4)
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(Spoil.EGG_MYSTIC.value)
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                row = pos[0] + attack[0]
                col = pos[1] + attack[1]
                if row == self.opp_bot.pos[0] and col == self.opp_bot.pos[1]:
                    return True
                elif row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    break
                elif self.map_matrix[row][col] in tmp:
                    continue
                elif self.map_matrix[row][col] == ValidPos.BALK.value:
                    break
                elif self.map_matrix[row][col] == 1:
                    break
                elif self.map_matrix[row][col] == 5:
                    break
        return False

    def near_spoil(self, pos):
        """Return True if pos near the balk."""
        for direction in directions.values():
            row = pos[0] + direction[0]
            col = pos[1] + direction[1]
            if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                continue
            if self.map_matrix[row][col] in target_pos_set:
                return True
        return False

    def _fill_eggs(self):
        my_egg_pos = self.my_bot.egg
        opp_egg_pos = self.opp_bot.egg
        self.map_matrix[opp_egg_pos[0]][opp_egg_pos[1]] = ValidPos.BALK.value  # need to attack
        self.map_matrix[my_egg_pos[0]][my_egg_pos[1]] = InvalidPos.WALL.value
        for direction in egg_directions:
            for i in range(1, 3):
                attack = i * direction
                row = my_egg_pos[0] + attack[0]
                col = my_egg_pos[1] + attack[1]
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    continue
                if self.map_matrix[row][col] in valid_pos_set:
                    continue
                if self.map_matrix[row][col] == Spoil.EGG_MYSTIC.value:
                    self.map_matrix[row][col] = ValidPos.ROAD.value
                if self.map_matrix[row][col] == ValidPos.BALK.value:
                    # Please do not place bombs to explode in the vicinity of your eggs.
                    self.map_matrix[row][col] = InvalidPos.WALL.value  # 1
            for i in range(1, 4):
                attack = i * direction
                opp_row = opp_egg_pos[0] + attack[0]
                opp_col = opp_egg_pos[1] + attack[1]
                if opp_row < 0 or opp_row >= self.max_row or opp_col < 0 or opp_col >= self.max_col:
                    continue
                if self.map_matrix[opp_row][opp_row] in valid_pos_set:
                    continue
                if self.map_matrix[opp_row][opp_col] == Spoil.EGG_MYSTIC.value:
                    self.map_matrix[opp_row][opp_col] = ValidPos.ROAD.value

        for attack in new_my_directions:
            row = my_egg_pos[0] + attack[0]
            col = my_egg_pos[1] + attack[1]
            if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                continue
            if self.map_matrix[row][col] in valid_pos_set:
                continue
            if self.map_matrix[row][col] == Spoil.EGG_MYSTIC.value:
                self.map_matrix[row][col] = ValidPos.ROAD.value
            if self.map_matrix[row][col] == ValidPos.BALK.value:
                # Please do not place bombs to explode in the vicinity of your eggs.
                self.map_matrix[row][col] = InvalidPos.WALL.value  # 1

        for attack in new_opp_directions:
            opp_row = opp_egg_pos[0] + attack[0]
            opp_col = opp_egg_pos[1] + attack[1]
            if opp_row < 0 or opp_row >= self.max_row or opp_col < 0 or opp_col >= self.max_col:
                continue
            if self.map_matrix[opp_row][opp_row] in valid_pos_set:
                continue
            if self.map_matrix[opp_row][opp_col] == Spoil.EGG_MYSTIC.value:
                self.map_matrix[opp_row][opp_col] = ValidPos.ROAD.value

    def fill_opp(self):
        # power = min(self.opp_bot.power, 4)
        self.map_matrix[self.opp_bot.pos[0]][self.opp_bot.pos[1]] = InvalidPos.WALL.value
        for direction in attack_directions:
            for i in range(1, 3):
                attack = i * direction
                row = self.opp_bot.pos[0] + attack[0]
                col = self.opp_bot.pos[1] + attack[1]
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    continue
                if self.map_matrix[row][col] in valid_pos_set:
                    self.map_matrix[row][col] = InvalidPos.WALL.value  # -1
        for attack in new_my_directions:
            opp_row = self.opp_bot.pos[0] + attack[0]
            opp_col = self.opp_bot.pos[1] + attack[1]
            if opp_row < 0 or opp_row >= self.max_row or opp_col < 0 or opp_col >= self.max_col:
                continue
            if self.map_matrix[opp_row][opp_col] in valid_pos_set:
                self.map_matrix[opp_row][opp_col] = InvalidPos.WALL.value  # -1

    def un_fill_opp(self):
        # power = min(self.opp_bot.power, 4)
        self.map_matrix[self.opp_bot.pos[0]][self.opp_bot.pos[1]] = ValidPos.BALK.value
        for direction in attack_directions:
            for i in range(1, 3):
                attack = i * direction
                row = self.opp_bot.pos[0] + attack[0]
                col = self.opp_bot.pos[1] + attack[1]
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    continue
                if row != 0 and row != self.max_row - 1 and col != 0 and col != self.max_col - 1:
                    if self.map_matrix[row][col] == InvalidPos.WALL.value:
                        self.map_matrix[row][col] = ValidPos.ROAD.value  # 0
        for attack in new_my_directions:
            opp_row = self.opp_bot.pos[0] + attack[0]
            opp_col = self.opp_bot.pos[1] + attack[1]
            if opp_row < 0 or opp_row >= self.max_row or opp_col < 0 or opp_col >= self.max_col:
                continue
            if self.map_matrix[opp_row][opp_col] == InvalidPos.WALL.value:
                self.map_matrix[opp_row][opp_col] = ValidPos.ROAD.value  # 0

    def _fill_spoils(self, map_spoils):
        """Fill all spoils into the map matrix."""
        for spoil in map_spoils:
            row = spoil['row']
            col = spoil['col']
            spoil_type = spoil['spoil_type'] + Spoil.BIAS.value

            if self.map_matrix[row][col] == ValidPos.ROAD.value:
                # 6: Speed, 7: Power, 8: Delay, 9: Mystic
                self.map_matrix[row][col] = spoil_type
                if spoil_type in target_pos_set:
                    # save all position of targets
                    self.targets[(row, col)] = spoil_type

                self.spoils[(row, col)] = spoil_type

    def _fill_bombs(self, map_bombs):
        """Fill all bombs into the map matrix."""
        tmp_bombs = copy.deepcopy(list_bombs)
        for bomb in map_bombs:
            bomb_pos = (bomb['row'], bomb['col'])
            bomb_power = bomb['power']
            remain_time = bomb['remainTime']
            player_id = bomb['playerId']

            # Finding all bombs about to explode
            if remain_time <= bombs_threshold:  # default 2000ms
                self.bombs_danger[bomb_pos] = {
                    'power': bomb_power,
                    'remain_time': remain_time
                }
            else:
                self.bombs[bomb_pos] = {
                    'power': bomb_power,
                    'remain_time': remain_time
                }
            list_bombs[bomb_pos] = {
                'player_id': player_id,
                'power': bomb_power,
                'remain_time': remain_time,
                'timestamp': self.timestamp
            }
            if bomb_pos in tmp_bombs:
                del tmp_bombs[bomb_pos]

        for old_bomb_pos, old_bomb_value in tmp_bombs.items():
            old_timestamp = old_bomb_value['timestamp']
            if self.timestamp - old_timestamp <= 800:
                self.bombs_danger[old_bomb_pos] = {
                    'power': old_bomb_value['power'],
                    'remain_time': 0
                }
            else:
                del list_bombs[old_bomb_pos]

    def _fill_bomb_danger_zones(self):
        """Update danger positions to wall."""
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(InvalidPos.TEMP.value)
        tmp.add(InvalidPos.BOMB.value)
        tmp.add(Spoil.EGG_MYSTIC.value)
        for bomb_pos, bomb_info in self.bombs_danger.items():
            power = bomb_info.get('power', 4)
            self.map_matrix[bomb_pos[0]][bomb_pos[1]] = InvalidPos.BOMB.value
            for direction in attack_directions:
                for i in range(1, power + 1):  # increase safe
                    attack = i * direction
                    danger_row = bomb_pos[0] + attack[0]
                    danger_col = bomb_pos[1] + attack[1]
                    # fill with value of WALL
                    if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                        continue
                    if self.map_matrix[danger_row][danger_col] == 1:
                        break
                    elif self.map_matrix[danger_row][danger_col] == 2:
                        break
                    elif self.map_matrix[danger_row][danger_col] == 5:
                        break
                    elif self.map_matrix[danger_row][danger_col] in invalid_pos_set:
                        continue
                    elif self.map_matrix[danger_row][danger_col] in tmp:
                        self.map_matrix[danger_row][danger_col] = InvalidPos.BOMB.value

    def fill_opp_danger_zones(self, tmp_matrix=None):
        power = min(self.opp_bot.power, 4)
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(Spoil.EGG_MYSTIC.value)
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                danger_row = self.opp_bot.pos[0] + attack[0]
                danger_col = self.opp_bot.pos[1] + attack[1]
                if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                    continue
                if tmp_matrix[danger_row][danger_col] == 1:
                    break
                elif tmp_matrix[danger_row][danger_col] == 2:
                    break
                elif tmp_matrix[danger_row][danger_col] == 5:
                    break
                elif tmp_matrix[danger_row][danger_col] in invalid_pos_set:
                    continue
                elif tmp_matrix[danger_row][danger_col] in tmp:
                    tmp_matrix[danger_row][danger_col] = InvalidPos.BOMB.value  # attack opp

    def in_opp_danger_zones(self):
        power = min(self.opp_bot.power, 4)
        delta_row = self.my_bot.pos[0] - self.opp_bot.pos[0]
        delta_col = self.my_bot.pos[1] - self.opp_bot.pos[1]

        if delta_row == 0:
            if abs(delta_col) <= power:
                if delta_col == 0:
                    return True
                elif delta_col < 0:
                    for i in range(1, abs(delta_col)):
                        new_col = self.my_bot.pos[1] + i
                        if self.map_matrix[self.my_bot.pos[0]][new_col] in {1, 2, 5}:
                            return False
                        else:
                            return True
                else:
                    for i in range(1, delta_col):
                        new_col = self.my_bot.pos[1] - i
                        if self.map_matrix[self.my_bot.pos[0]][new_col] in {1, 2, 5}:
                            return False
                        else:
                            return True
            else:
                return False
        elif delta_col == 0:
            if abs(delta_row) <= power:
                if delta_row == 0:
                    return True
                elif delta_row < 0:
                    for i in range(1, abs(delta_row)):
                        new_row = self.my_bot.pos[0] + i
                        if self.map_matrix[new_row][self.my_bot.pos[1]] in {1, 2, 5}:
                            return False
                        else:
                            return True
                else:
                    for i in range(1, delta_row):
                        new_row = self.my_bot.pos[0] - i
                        if self.map_matrix[new_row][self.my_bot.pos[1]] in {1, 2, 5}:
                            return False
                        else:
                            return True
            else:
                return False
        else:
            return False

    def in_opp_bomb_zones(self):
        for bomb_pos, bomb_info in self.bombs_danger.items():
            power = bomb_info.get('power', 4)
            delta_row = self.my_bot.pos[0] - bomb_pos[0]
            delta_col = self.my_bot.pos[1] - bomb_pos[1]

            if delta_row == 0:
                if abs(delta_col) <= power:
                    if delta_col == 0:
                        return True
                    elif delta_col < 0:
                        for i in range(1, abs(delta_col)):
                            new_col = self.my_bot.pos[1] + i
                            if self.map_matrix[self.my_bot.pos[0]][new_col] in {1, 2, 5}:
                                break
                            else:
                                return True
                    else:
                        for i in range(1, delta_col):
                            new_col = self.my_bot.pos[1] - i
                            if self.map_matrix[self.my_bot.pos[0]][new_col] in {1, 2, 5}:
                                break
                            else:
                                return True
            elif delta_col == 0:
                if abs(delta_row) <= power:
                    if delta_row == 0:
                        return True
                    elif delta_row < 0:
                        for i in range(1, abs(delta_row)):
                            new_row = self.my_bot.pos[0] + i
                            if self.map_matrix[new_row][self.my_bot.pos[1]] in {1, 2, 5}:
                                break
                            else:
                                return True
                    else:
                        for i in range(1, delta_row):
                            new_row = self.my_bot.pos[0] - i
                            if self.map_matrix[new_row][self.my_bot.pos[1]] in {1, 2, 5}:
                                break
                            else:
                                return True
        return False

    def in_stopped_by_server(self):
        for bomb_pos, bomb_info in self.bombs.items():
            power = bomb_info.get('power', 4)
            delta_row = self.my_bot.pos[0] - bomb_pos[0]
            delta_col = self.my_bot.pos[1] - bomb_pos[1]

            if delta_row == 0:
                if abs(delta_col) <= power:
                    if delta_col == 0:
                        return True
                    elif delta_col < 0:
                        for i in range(1, abs(delta_col)):
                            new_col = self.my_bot.pos[1] + i
                            if self.map_matrix[self.my_bot.pos[0]][new_col] in {1, 2, 5}:
                                break
                            else:
                                return True
                    else:
                        for i in range(1, delta_col):
                            new_col = self.my_bot.pos[1] - i
                            if self.map_matrix[self.my_bot.pos[0]][new_col] in {1, 2, 5}:
                                break
                            else:
                                return True
            elif delta_col == 0:
                if abs(delta_row) <= power:
                    if delta_row == 0:
                        return True
                    elif delta_row < 0:
                        for i in range(1, abs(delta_row)):
                            new_row = self.my_bot.pos[0] + i
                            if self.map_matrix[new_row][self.my_bot.pos[1]] in {1, 2, 5}:
                                break
                            else:
                                return True
                    else:
                        for i in range(1, delta_row):
                            new_row = self.my_bot.pos[0] - i
                            if self.map_matrix[new_row][self.my_bot.pos[1]] in {1, 2, 5}:
                                break
                            else:
                                return True
        return False

    def _retrieve_all_targets(self):
        roads = list(zip(*np.where(self.map_matrix == 0)))
        return roads

    def _retrieve_all_telegate(self):
        tele_gates = list(zip(*np.where(self.map_matrix == InvalidPos.TELE_GATE.value)))
        return tele_gates

    def _retrieve_all_bombs(self):
        bombs = list(zip(*np.where(self.map_matrix == InvalidPos.BOMB.value)))
        return bombs

    def _fill_telegate(self):
        gates = self._retrieve_all_telegate()
        for gate in gates:
            for direction in attack_directions:
                row = gate[0] + direction[0]
                col = gate[1] + direction[1]
                # fill with value of WALL
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    continue
                if self.map_matrix[row][col] == 0:
                    self.map_matrix[row][col] = Spoil.EGG_MYSTIC.value

    def _fill_bomb_neighbor(self):
        bombs = self._retrieve_all_bombs()
        for bomb in bombs:
            for direction in attack_directions:
                row = bomb[0] + direction[0]
                col = bomb[1] + direction[1]
                # fill with value of WALL
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    continue
                if self.map_matrix[row][col] == 0:
                    self.map_matrix[row][col] = Spoil.EGG_MYSTIC.value

    def _update_targets(self):
        if self.my_bot.speed > 100:
            roads = self._retrieve_all_targets()
            for pos in roads:
                num_balks = self.num_balk(pos)
                if num_balks >= 1:
                    self.bomb_targets[pos] = num_balks

    def _fill_my_danger_zones(self, cur_pos, power, tmp_matrix):
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                danger_row = cur_pos[0] + attack[0]
                danger_col = cur_pos[1] + attack[1]
                # fill with value of WALL
                if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                    break
                if tmp_matrix[danger_row][danger_col] == 1:
                    break
                if tmp_matrix[danger_row][danger_col] == 2:
                    break
                elif tmp_matrix[danger_row][danger_col] == 5:
                    break
                elif tmp_matrix[danger_row][danger_col] in invalid_pos_set:
                    continue
                tmp_matrix[danger_row][danger_col] = InvalidPos.TEMP.value

    def fill_map(self):
        """Fill all map matrix"""
        self._fill_bombs(self.map_info['bombs'])
        self._fill_bomb_danger_zones()
        self._fill_spoils(self.map_info['spoils'])
        self.map_matrix[self.opp_bot.pos[0]][self.opp_bot.pos[1]] = ValidPos.BALK.value
        self._fill_eggs()
        interval = self.timestamp - bomb_timestamp
        if interval >= self.my_bot.delay:
            self._update_targets()

    def avail_moves(self, cur_pos, temp=False):
        """All available moves with current position."""
        tmp_valid_pos_set = copy.deepcopy(valid_pos_set)
        tmp_valid_pos_set.add(Spoil.EGG_MYSTIC.value)
        if temp:
            tmp_valid_pos_set.add(InvalidPos.TEMP.value)
        res = []
        for route, direction in directions.items():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            if next_move[0] < 0 or next_move[0] >= self.max_row or next_move[1] < 0 or next_move[1] >= self.max_col:
                continue

            if self.map_matrix[next_move[0]][next_move[1]] in tmp_valid_pos_set:
                res.append((route.value, next_move))
        return res

    def finding_safe_zones_v2(self, cur_pos):
        power = min(self.my_bot.power, 4)
        unsafe_routes = deque()
        safe_routes = None
        greedy_routes = deque()
        perfected_routes = None
        saved = set()
        saved.add(cur_pos)
        move_queue = deque()
        move_queue.append([cur_pos, deque(), deque(), 0])

        # count = 1
        tmp_matrix = np.array(self.map_matrix)

        while len(move_queue) > 0:
            # if count == 2:
            #     self._fill_my_danger_zones(cur_pos, power, tmp_matrix)
            pos, routes, poses, score = move_queue.popleft()

            # Move to 4 directions next to current position.
            if tmp_matrix[pos[0]][pos[1]] in valid_pos_set:
                delta = self.heuristic_func(pos, cur_pos, -1)
                if pos in self.targets.keys():
                    if pos[0] != cur_pos[0] and pos[1] != cur_pos[1]:
                        if delta < 13:
                            perfected_routes = routes, poses, score
                            break
                    else:
                        if power + 1 <= delta < power + 9:
                            greedy_routes.appendleft((routes, poses, score))
                            break
                elif pos in self.bomb_targets.keys():
                    delta = self.heuristic_func(pos, cur_pos, 0)
                    if self.bomb_targets[pos] >= 3:
                        if pos[0] != cur_pos[0] and pos[1] != cur_pos[1]:
                            if delta < 13:
                                perfected_routes = routes, poses, score
                                break
                        else:
                            if power + 1 <= delta < power + 9:
                                greedy_routes.appendleft((routes, poses, score))
                                break
                    elif self.bomb_targets[pos] == 2:
                        if pos[0] != cur_pos[0] and pos[1] != cur_pos[1]:
                            if delta < 9:
                                perfected_routes = routes, poses, score
                                break
                        else:
                            if power + 1 <= delta < power + 5:
                                greedy_routes.appendleft((routes, poses, score))
                                break
                else:
                    if pos[0] != cur_pos[0] and pos[1] != cur_pos[1]:
                        if not safe_routes:
                            safe_routes = routes, poses, score
                    else:
                        if power + 1 <= delta:
                            unsafe_routes.appendleft((routes, poses, score))

            next_routes = []  # Save all routes along with related information.
            for route, direction in directions.items():
                next_pos = (pos[0] + direction[0], pos[1] + direction[1])
                neighbor_pos = (pos[0] + 2 * direction[0], pos[1] + 2 * direction[1])
                if next_pos in saved:
                    continue
                # invalid positions
                if next_pos[0] < 0 or next_pos[0] >= self.max_row or next_pos[1] < 0 or next_pos[1] >= self.max_col:
                    continue
                if next_pos == self.my_bot.pos:
                    continue
                # valid positions
                if tmp_matrix[next_pos[0]][next_pos[1]] in valid_pos_set:
                    min_score = 1000000
                    # Estimate costs from current position (next_pos) to targets.
                    for spoil_pos, spoil_type in self.targets.items():
                        est_score = self.heuristic_func(next_pos, spoil_pos, spoil_type)
                        if est_score < min_score:
                            min_score = est_score
                    saved.add(next_pos)
                    if 0 <= neighbor_pos[0] < self.max_row and 0 <= neighbor_pos[1] < self.max_col:
                        if tmp_matrix[next_pos[0]][next_pos[1]] not in target_pos_set:
                            if tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.TELE_GATE.value:
                                min_score += 1000000
                            elif tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.WALL.value:
                                min_score += 1500000
                        if tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.BOMB.value:
                            min_score += 2000000
                    min_score = min_score - 1000 * self.heuristic_func(next_pos, self.opp_bot.pos, -1)
                    next_routes.append([next_pos, score + 1, score + min_score, route.value])

            next_routes.sort(key=lambda x: x[2])
            for move in next_routes:
                r = copy.deepcopy(routes)
                r.append(move[3])
                p = copy.deepcopy(poses)
                p.append(move[0])
                move_queue.append([move[0], r, p, move[1]])
            # count += 1

        # self._fill_my_danger_zones(cur_pos, power)

        if perfected_routes:
            return perfected_routes
        elif len(greedy_routes) > 0:
            return greedy_routes.pop()
        elif safe_routes:
            return safe_routes
        elif len(unsafe_routes) > 0:
            return unsafe_routes.pop()

        return deque(), deque(), 0

    def finding_safe_zones(self, cur_pos):
        power = min(self.my_bot.power, 4)
        unsafe_routes = deque()
        safe_routes = deque()
        greedy_routes = deque()
        perfected_routes = deque()
        saved = set()
        saved.add(cur_pos)
        move_queue = deque()
        move_queue.append([cur_pos, deque(), deque(), 0])

        # count = 1
        tmp_matrix = np.array(self.map_matrix)
        # self.fill_opp_danger_zones(tmp_matrix)

        while len(move_queue) > 0:
            # if count == 2:
            #     self._fill_my_danger_zones(cur_pos, power, tmp_matrix)
            pos, routes, poses, score = move_queue.popleft()

            # Move to 4 directions next to current position.
            if tmp_matrix[pos[0]][pos[1]] in valid_pos_set:
                delta1 = self.heuristic_func(pos, cur_pos, -1)
                delta2 = self.heuristic_func(pos, self.opp_bot.pos, -1)
                if pos in self.targets.keys():
                    if pos[0] != cur_pos[0] and pos[1] != cur_pos[1] and pos[0] != self.opp_bot.pos[0] and pos[1] != \
                            self.opp_bot.pos[1]:
                        if delta1 < 13:
                            perfected_routes.append((routes, poses, score))
                            break
                    else:
                        if power + 1 <= delta1 < power + 9 and delta2 > 5:
                            greedy_routes.append((routes, poses, score))
                            break
                elif pos in self.bomb_targets.keys():
                    if self.bomb_targets[pos] < 2:
                        if pos[0] != cur_pos[0] and pos[1] != cur_pos[1] and pos[0] != self.opp_bot.pos[0] and pos[1] != \
                                self.opp_bot.pos[1]:
                            if delta1 < 9:
                                perfected_routes.append((routes, poses, score))
                                break
                        else:
                            if power + 1 <= delta1 < power + 5 and delta2 > 5:
                                greedy_routes.appendleft((routes, poses, score))
                                break
                else:
                    if pos[0] != cur_pos[0] and pos[1] != cur_pos[1] and pos[0] != self.opp_bot.pos[0] and pos[1] != \
                            self.opp_bot.pos[1]:
                        safe_routes.append((routes, poses, score))
                        break
                    else:
                        if power + 1 <= delta1 < power + 5 and delta2 > 5:
                            unsafe_routes.append((routes, poses, score))
                            break

            next_routes = []  # Save all routes along with related information.
            for route, direction in directions.items():
                next_pos = (pos[0] + direction[0], pos[1] + direction[1])
                neighbor_pos = (pos[0] + 2 * direction[0], pos[1] + 2 * direction[1])
                if next_pos in saved:
                    continue
                # invalid positions
                if next_pos[0] < 0 or next_pos[0] >= self.max_row or next_pos[1] < 0 or next_pos[1] >= self.max_col:
                    continue
                if next_pos == self.my_bot.pos:
                    continue
                # valid positions
                if tmp_matrix[next_pos[0]][next_pos[1]] in valid_pos_set:
                    min_score = 1000000
                    # Estimate costs from current position (next_pos) to targets.
                    for spoil_pos, spoil_type in self.targets.items():
                        est_score = self.heuristic_func(next_pos, spoil_pos, spoil_type)
                        if est_score < min_score:
                            min_score = est_score
                    saved.add(next_pos)
                    if 0 <= neighbor_pos[0] < self.max_row and 0 <= neighbor_pos[1] < self.max_col:
                        if tmp_matrix[next_pos[0]][next_pos[1]] not in target_pos_set:
                            if tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.TELE_GATE.value:
                                min_score += 1000000
                            elif tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.WALL.value:
                                min_score += 1500000
                        if tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.BOMB.value:
                            min_score += 2000000
                    min_score = min_score - 1000 * self.heuristic_func(next_pos, self.opp_bot.pos, -1)
                    next_routes.append([next_pos, score + 1, score + min_score, route.value])

            next_routes.sort(key=lambda x: x[2])
            for move in next_routes:
                r = copy.deepcopy(routes)
                r.append(move[3])
                p = copy.deepcopy(poses)
                p.append(move[0])
                move_queue.append([move[0], r, p, move[1]])
            # count += 1

        # self._fill_my_danger_zones(cur_pos, power)

        if len(perfected_routes) > 0:
            return perfected_routes.pop()
        elif len(greedy_routes) > 0:
            return greedy_routes.pop()
        elif len(safe_routes) > 0:
            return safe_routes.pop()
        elif len(unsafe_routes) > 0:
            return unsafe_routes.pop()

        return deque(), deque(), 0

    def finding_safe_zones_v3(self, cur_pos):
        unsafe_routes = deque()
        safe_routes = deque()
        greedy_routes = deque()
        saved = set()
        saved.add(cur_pos)
        move_queue = deque()
        move_queue.append([cur_pos, [], [], 0])

        # count = 1
        tmp_matrix = np.array(self.map_matrix)

        while len(move_queue) > 0:
            pos, routes, poses, score = move_queue.popleft()
            # Move to 4 directions next to current position.
            if tmp_matrix[pos[0]][pos[1]] in valid_pos_set:
                delta2 = self.heuristic_func(pos, self.opp_bot.pos, -1)
                if pos[0] != cur_pos[0] and pos[1] != cur_pos[1] and pos[0] != self.opp_bot.pos[0] and pos[1] != \
                        self.opp_bot.pos[1]:
                    safe_routes.append((routes, poses, score))
                    break
                else:
                    unsafe_routes.append((routes, poses, score))
                    if delta2 > 5 and score > 5:
                        break

            next_routes = []  # Save all routes along with related information.
            for route, direction in directions.items():
                next_pos = (pos[0] + direction[0], pos[1] + direction[1])
                neighbor_pos = (pos[0] + 2 * direction[0], pos[1] + 2 * direction[1])
                if next_pos in saved:
                    continue
                # invalid positions
                if next_pos[0] < 0 or next_pos[0] >= self.max_row or next_pos[1] < 0 or next_pos[1] >= self.max_col:
                    continue
                if next_pos == self.my_bot.pos:
                    continue
                # valid positions
                if tmp_matrix[next_pos[0]][next_pos[1]] in valid_pos_set:
                    min_score = 1000000
                    saved.add(next_pos)
                    if 0 <= neighbor_pos[0] < self.max_row and 0 <= neighbor_pos[1] < self.max_col:
                        if tmp_matrix[next_pos[0]][next_pos[1]] not in target_pos_set:
                            if tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.TELE_GATE.value:
                                min_score += 1000000
                            elif tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.WALL.value:
                                min_score += 1500000
                        if tmp_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.BOMB.value:
                            min_score += 2000000
                    min_score = min_score - 1000 * self.heuristic_func(next_pos, self.opp_bot.pos, -1)
                    next_routes.append([next_pos, score + 1, score + min_score, route.value])

            next_routes.sort(key=lambda x: x[2])
            for move in next_routes:
                r = copy.deepcopy(routes)
                r.append(move[3])
                p = copy.deepcopy(poses)
                p.append(move[0])
                move_queue.append([move[0], r, p, move[1]])
            # count += 1

        if len(greedy_routes) > 0:
            return greedy_routes.pop()
        elif len(safe_routes) > 0:
            return safe_routes.pop()
        elif len(unsafe_routes) > 0:
            return unsafe_routes.pop()

        return [], [], 0

    def greedy_place_bombs(self, cur_pos, bombs_power=0, attack=False, is_setup=False):
        """Return next_move is 'b' if my bot can place a bomb."""
        avail_moves = self.avail_moves(cur_pos)
        if len(avail_moves) == 0:
            return 0, [], []

        interval = self.timestamp - bomb_timestamp
        if interval > self.my_bot.delay:
            # before placing a bomb, please find a place to hide
            if not attack:
                moves, poses, _ = self.finding_safe_zones_v2(cur_pos)
            else:
                moves, poses, _ = self.finding_safe_zones(cur_pos)
            if len(moves) >= 2 and len(poses) >= 2:
                if not is_setup:
                    moves.appendleft('b')
                return bombs_power, moves, poses
        return 0, [], []

    def run_away(self):
        delta_row = self.my_bot.pos[0] - self.opp_bot.pos[0]
        delta_col = self.my_bot.pos[1] - self.opp_bot.pos[1]

        if delta_row == 0:
            if 3 < abs(delta_col) <= 7:
                return True
            else:
                return False
        elif delta_col == 0:
            if 3 < abs(delta_row) <= 7:
                return True
            else:
                return False
        else:
            delta = abs(delta_col) + abs(delta_row)
            if 6 < delta <= 9:
                return True
        return False

    def heuristic_func(self, current_pos, target_pos, spoil_type=0):
        cost = abs(current_pos[0] - target_pos[0]) + abs(current_pos[1] - target_pos[1])
        if spoil_type == 0:
            bombs_power = self.num_balk(current_pos)
            if bombs_power >= 3:
                cost -= 13
            elif bombs_power == 2:
                cost -= 7
        elif spoil_type != -1:
            cost -= 3
        return cost

    @staticmethod
    def all_moves(cur_pos):
        res = []
        for action, direction in directions.values():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            res.append((action, next_move))
        return res


def free_bfs(game_map):
    tmp_valid_pos_set = copy.deepcopy(valid_pos_set)
    tmp_valid_pos_set.add(Spoil.EGG_MYSTIC.value)  # add egg mystic to valid pos
    # tmp_valid_pos_set.add(InvalidPos.TEMP.value)
    free_route = tuple()
    saved = set()
    my_pos = game_map.my_bot.pos
    saved.add(my_pos)
    move_queue = deque()
    move_queue.append([my_pos, [], [], 0])

    while len(move_queue) > 0:
        pos, routes, poses, score = move_queue.popleft()
        # Move to 4 directions next to current position.
        if game_map.map_matrix[pos[0]][pos[1]] == Spoil.EGG_MYSTIC.value:
            free_route = (score, routes, poses, Spoil.EGG_MYSTIC.value)
            break
        next_routes = []  # Save all routes along with related information.
        for route, direction in directions.items():
            next_pos = (pos[0] + direction[0], pos[1] + direction[1])
            if next_pos in saved:
                continue
            # invalid positions
            if next_pos[0] < 0 or next_pos[0] >= game_map.max_row or next_pos[1] < 0 or next_pos[1] >= game_map.max_col:
                continue
            if next_pos == game_map.my_bot.pos:
                continue
            # valid positions
            if game_map.map_matrix[next_pos[0]][next_pos[1]] in tmp_valid_pos_set:
                saved.add(next_pos)
                # At the current position (next_pos), add to the queue the direction of movement closest to the target.
                score = score - 1000 * game_map.heuristic_func(next_pos, game_map.opp_bot.pos, -1)
                next_routes.append([next_pos, score + 1, route.value])

        next_routes.sort(key=lambda x: x[1])
        for move in next_routes:
            r = copy.deepcopy(routes)
            r.append(move[2])
            p = copy.deepcopy(poses)
            p.append(move[0])
            move_queue.append([move[0], r, p, move[1]])

    return free_route


def attack_mode_v1(game_map):
    normal_routes = PriorityQueue()
    delta = game_map.heuristic_func(game_map.my_bot.pos, game_map.opp_bot.pos, -1)
    if delta <= 7:
        pos, routes, poses, score = game_map.is_connected_to_opp()
        if pos and len(poses) <= 13:
            _, place_bombs, next_poses = game_map.greedy_place_bombs(pos, attack=True)
            if len(place_bombs) > 2 and len(next_poses) > 1:
                if len(routes) == 0:
                    routes.extend(place_bombs)
                    poses.extend(next_poses)
                    normal_routes.put((score, (score, routes, poses, 13)))
                else:
                    normal_routes.put((score, (score, routes, poses, -1)))
    return normal_routes


def finding_path(game_map):
    normal_routes = PriorityQueue()

    move_queue = deque()
    # queue element [pos, routes, score]
    my_pos = game_map.my_bot.pos
    saved = set()
    saved.add(my_pos)
    move_queue.append([my_pos, [], [], 0])

    while len(move_queue) > 0:
        pos, routes, poses, score = move_queue.popleft()

        # Check whether the current position is the target or not.
        if pos in game_map.targets:
            normal_routes.put((score - 17, (score, routes, poses, game_map.targets[pos])))
            break
        elif pos in game_map.bomb_targets:
            if not game_map.near_spoil(pos):
                _, place_bombs, next_poses = game_map.greedy_place_bombs(pos, game_map.bomb_targets[pos])
                if len(place_bombs) >= 3 and 2 <= len(next_poses):
                    if len(routes) == 0:
                        routes.extend(place_bombs)
                        poses.extend(next_poses)
                        normal_routes.put((score - game_map.bomb_targets[pos] - 7, (score, routes, poses, 13)))
                    else:
                        normal_routes.put((score - game_map.bomb_targets[pos], (score, routes, poses, -1)))
                    break

        # Move to 4 directions next to current position.
        next_routes = []  # Save all routes along with related information.
        for route, direction in directions.items():
            next_pos = (pos[0] + direction[0], pos[1] + direction[1])
            neighbor_pos = (pos[0] + 2 * direction[0], pos[1] + 2 * direction[1])

            if next_pos in saved:
                continue
            # invalid positions
            if next_pos[0] < 0 or next_pos[0] >= game_map.max_row or next_pos[1] < 0 or next_pos[1] >= game_map.max_col:
                continue
            # valid positions
            if game_map.map_matrix[next_pos[0]][next_pos[1]] in valid_pos_set:
                min_score = 1000000
                # Estimate costs from current position (next_pos) to targets.
                for spoil_pos, spoil_type in game_map.targets.items():
                    est_score = game_map.heuristic_func(next_pos, spoil_pos, spoil_type)

                    # penalty = game_map.heuristic_func(spoil_pos, game_map.opp_bot.pos, -1)
                    # est_score -= penalty
                    if est_score < min_score:
                        min_score = est_score
                # Estimate costs from current position (next_pos) to targets.
                for bomb_target_pos in game_map.bomb_targets.keys():
                    est_score = game_map.heuristic_func(next_pos, bomb_target_pos, 0)
                    if est_score < min_score:
                        min_score = est_score
                saved.add(next_pos)
                if 0 <= neighbor_pos[0] < game_map.max_row and 0 <= neighbor_pos[1] < game_map.max_col:
                    if game_map.map_matrix[next_pos[0]][next_pos[1]] not in target_pos_set:
                        if game_map.map_matrix[neighbor_pos[0]][neighbor_pos[1]] == ValidPos.BALK.value:
                            min_score += 500000
                        elif game_map.map_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.TELE_GATE.value:
                            min_score += 1000000
                        elif game_map.map_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.WALL.value:
                            min_score += 1500000
                    if game_map.map_matrix[neighbor_pos[0]][neighbor_pos[1]] == InvalidPos.BOMB.value:
                        min_score += 2000000
                min_score = min_score - 10000 * game_map.heuristic_func(next_pos, game_map.opp_bot.pos, -1)
                # At the current position (next_pos), add to the queue the direction of movement closest to the target.
                next_routes.append([next_pos, score + 1, score + min_score, route.value])

        next_routes.sort(key=lambda x: x[2])
        for move in next_routes:
            r = copy.deepcopy(routes)
            r.append(move[3])
            p = copy.deepcopy(poses)
            p.append(move[0])
            move_queue.append([move[0], r, p, move[1]])

    return normal_routes


def can_move():
    global previous_timestamp
    global delay_time
    global time_explosed_bomb
    tmp = delay_time + time_explosed_bomb
    if tmp > 448:
        tmp = 448
    if tmp < 301 and tmp != 10:
        tmp = 301
    current_time = int(time.time() * 1000)
    delta = current_time - previous_timestamp
    if delta > tmp:
        previous_timestamp = current_time
        return True
    return False


@sio.event
def send_infor():
    infor = {"game_id": GameInfo.GAME_ID, "player_id": GameInfo.PLAYER_ID}
    sio.emit('join game', infor)


@sio.on('join game')
def join_game(data):
    player_id = data.get('player_id', 'Hello world!')
    print(f'joined game!!!!, your id: {player_id}')


@sio.on('drive player')
def receive_moves(data):
    global delay_time
    player_id = data.get('player_id', 'Hello world!')
    direction = data.get('direction', 'n')
    if player_id and player_id in GameInfo.PLAYER_ID:
        print(f'Directions sent: {direction}')
        if 'x' in direction:
            delay_time = 10
        else:
            n = len(direction)
            delay_time = n * player_speed


@sio.event
def next_moves(moves):
    sio.emit('drive player', {"direction": moves})


@sio.event
def connect():
    print('connection established')
    send_infor()


@sio.on('ticktack player')
def map_state(data):
    global count_opp
    global opp_pos
    global counter
    global normal_queue
    global bomb_timestamp
    global time_explosed_bomb
    global previous_pos
    global player_speed

    map_states.append(data)
    cur_map = map_states.pop()
    game_map = GameMap(cur_map)
    game_map.find_bots()
    game_map.fill_map()
    player_speed = game_map.my_bot.speed  # update player speed

    player_id = game_map.player_id
    game_tag = game_map.tag
    my_pos = game_map.my_bot.pos

    if game_tag == 'bomb:explosed':
        time_explosed_bomb = 233
    else:
        time_explosed_bomb = 0

    if game_tag == 'player:be-isolated' and (player_id and player_id in GameInfo.PLAYER_ID):
        normal_queue = []
    elif game_tag == 'player:back-to-playground' and (player_id and player_id in GameInfo.PLAYER_ID):
        normal_queue = []

    if len(normal_queue) > 0:
        next_move = normal_queue.pop()
        direction = next_move[1][0]
        if len(direction) > 0:
            if next_move[1][3] == 13 or next_move[1][3] == 5:
                bomb_timestamp = game_map.timestamp
            # print(f'My pos: {my_pos} ** {next_move}')
            next_moves(direction)

    normal_routes = PriorityQueue()
    in_bomb = game_map.in_opp_bomb_zones()
    is_stopped = game_map.in_stopped_by_server()
    if in_bomb or (
            is_stopped and ((game_tag == 'player:stop-moving' or game_tag == 'player:moving-banned') and (
            player_id and player_id in GameInfo.PLAYER_ID))):
        place_bombs, next_poses, _ = game_map.finding_safe_zones_v3(game_map.my_bot.pos)
        if len(place_bombs) > 0:
            normal_routes.put((-1, (-1, place_bombs, next_poses, -1)))
        if not normal_routes.empty():
            priority_routes = normal_routes.get()[1]
            my_route = priority_routes[1]
            normal_queue.append(
                (game_map.id, (''.join(my_route), game_map.my_bot.pos, priority_routes[2], priority_routes[3])))
            opp_pos = game_map.opp_bot.pos
            count_opp = 0
            counter = 0
    elif normal_routes.empty():
        move = can_move()
        # print(f'{game_map.id} ** Can move: {move}')
        # if not (game_tag == 'player:start-moving' and (player_id and player_id in GameInfo.PLAYER_ID)):
        #     if not (game_tag == 'player:pick-spoil' and (player_id and player_id not in GameInfo.PLAYER_ID)):
        if move:
            drive_bot(game_map, normal_routes)


def drive_bot(game_map, normal_routes):
    global count_opp
    global opp_pos
    global counter
    global bomb_timestamp
    global max_time
    global max_len

    if normal_routes.empty():
        normal_routes = attack_mode_v1(game_map)
        if not normal_routes.empty():
            priority_routes = normal_routes.get()[1]
            my_route = priority_routes[1]
            normal_queue.append(
                (game_map.id, (''.join(my_route), game_map.my_bot.pos, priority_routes[2], priority_routes[3])))
            opp_pos = game_map.opp_bot.pos
            count_opp = 0
            counter = 0
        elif len(game_map.bomb_targets) > 0 or len(game_map.targets) > 0:
            normal_routes = finding_path(game_map)
            if not normal_routes.empty():
                priority_routes = normal_routes.get()[1]
                my_route = priority_routes[1]
                normal_queue.append(
                    (game_map.id, (''.join(my_route), game_map.my_bot.pos, priority_routes[2], priority_routes[3])))
                opp_pos = game_map.opp_bot.pos
                count_opp = 0
                counter = 0
    if normal_routes.empty():
        if game_map.opp_bot.pos == opp_pos:
            count_opp += 1
        counter += 1
        if count_opp == 10 or counter == 10:
            free_route = free_bfs(game_map)
            if len(free_route) > 0:
                my_route = free_route[1]
                normal_queue.append(
                    (game_map.id, (''.join(my_route), game_map.my_bot.pos, free_route[2], free_route[3])))
            else:
                count_opp = 0
                counter = 0


def main():
    sio.connect('http://localhost', transports=['websocket'])
    sio.wait()


if __name__ == '__main__':
    main()
