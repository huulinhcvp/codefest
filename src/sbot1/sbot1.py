import time
import copy
import socketio
import numpy as np
from queue import PriorityQueue
from operator import itemgetter
from game_info import GameInfo
from collections import deque
from const import (
    NextMove,
    Spoil,
    ValidPos,
    InvalidPos,
    TargetPos,
    spoil_set,
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
previous_pos = None
previous_timestamp = 0
# make_decision = (None, None)
max_time = 0
last_directions = ''

my_power = 1
opp_power = 1
bomb_timestamp = 0
# my_bombs = dict()
# opp_bombs = dict()
attack_directions = np.array([[-1, 0], [0, -1], [0, 1], [1, 0]])
egg_directions = np.array([[-1, 0], [0, -1], [0, 1], [1, 0], [-1, 1], [1, -1], [1, 1], [-1, -1]])
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
            delay
    ):
        self._id = player_id
        self._pos = cur_pos
        self._lives = lives
        self._speed = speed
        self._power = power
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
        self._my_bot = None
        self._opp_bot = None
        self._max_row = self.map_info['size']['rows']
        self._max_col = self.map_info['size']['cols']
        self.map_matrix = np.array(self.map_info['map'])  # convert 2d matrix into ndarray data type
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
            player_delay = player.get('delay')
            game_bot = GameBot(
                player_id,
                player_pos,
                player_lives,
                player_speed,
                player_power,
                player_delay
            )
            if player_id == GameInfo.PLAYER_ID:
                self.my_bot = game_bot
            else:
                self.opp_bot = game_bot

        for egg in self.map_info['dragonEggGSTArray']:
            egg_pos = (egg.get('row'), egg.get('col'))
            player_id = egg.get('id')
            if player_id == GameInfo.PLAYER_ID:
                self.my_bot.egg = egg_pos
            else:
                self.opp_bot.egg = egg_pos

    def num_balk(self, pos):
        """Return True if pos near the balk."""
        num_balk = 0
        power = min(self.my_bot.power, 3)
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(InvalidPos.TEMP.value)
        tmp.add(Spoil.EGG_MYSTIC.value)
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                row = pos[0] + attack[0]
                col = pos[1] + attack[1]
                # print(f'Road {pos}: ({row}, {col})')
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    break
                if self.map_matrix[row][col] in tmp:
                    if (row, col) == self.opp_bot.pos:
                        num_balk += 1
                    continue
                if self.map_matrix[row][col] == ValidPos.BALK.value:
                    num_balk += 1
                    break
                elif self.map_matrix[row][col] == 1:
                    break
        # print(f'With pos: {pos} ** Num balk {num_balk}')
        return num_balk

    def near_balk(self, pos):
        """Return True if pos near the balk."""
        for direction in directions.values():
            row = pos[0] + direction[0]
            col = pos[1] + direction[1]
            if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                continue
            if self.map_matrix[pos[0] + direction[0]][pos[1] + direction[1]] == ValidPos.BALK.value:
                return True
        return False

    def _fill_eggs(self):
        my_egg_pos = self.my_bot.egg
        opp_egg_pos = self.opp_bot.egg
        power = 2
        # print(f'{self.id}: My egg: {my_egg_pos} ** Opp egg: {opp_egg_pos}')
        for direction in egg_directions:
            for i in range(1, power + 1):
                attack = i * direction
                row = my_egg_pos[0] + attack[0]
                col = my_egg_pos[1] + attack[1]
                if row < 0 or row >= self.max_row or col < 0 or col >= self.max_col:
                    continue
                if self.map_matrix[row][col] in valid_pos_set:
                    continue
                if self.map_matrix[row][col] == ValidPos.BALK.value:
                    # Please do not place bombs to explode in the vicinity of your eggs.
                    self.map_matrix[row][col] = InvalidPos.TEMP.value  # 5
        self.map_matrix[opp_egg_pos[0]][opp_egg_pos[1]] = ValidPos.BALK.value  # need to attack

    def _fill_spoils(self, map_spoils):
        """Fill all spoils into the map matrix."""
        for spoil in map_spoils:
            row = spoil['row']
            col = spoil['col']
            spoil_type = spoil['spoil_type'] + Spoil.BIAS.value

            # 6: Speed, 7: Power, 8: Delay, 9: Mystic
            self.map_matrix[row][col] = spoil_type
            if spoil_type in target_pos_set:
                # save all position of targets
                self.targets[(row, col)] = spoil_type

            self.spoils[(row, col)] = spoil_type

    def _fill_bombs(self, map_bombs):
        """Fill all bombs into the map matrix."""
        for bomb in map_bombs:
            bomb_pos = (bomb['row'], bomb['col'])
            bomb_power = 1
            remain_time = bomb['remainTime']
            player_id = bomb['playerId']

            # 13: Bomb
            # self.map_matrix[bomb_pos[0]][bomb_pos[1]] = InvalidPos.BOMB.value

            # set power to bombs in map matrix
            if GameInfo.PLAYER_ID in player_id:
                bomb_power = my_power

            else:
                bomb_power = opp_power

            # Finding all bombs about to explode
            if remain_time <= bombs_threshold:  # default 2000ms
                self.bombs_danger[bomb_pos] = {
                    'power': bomb_power,
                    'remain_time': remain_time
                }
            self.bombs[bomb_pos] = {
                'power': bomb_power,
                'remain_time': remain_time
            }

    def _fill_bomb_danger_zones(self):
        """Update danger positions to wall."""
        for bomb_pos, bomb_info in self.bombs_danger.items():
            # power = bomb_info['power']
            for direction in attack_directions:
                for i in range(1, 4):  # increase safe
                    attack = i * direction
                    danger_row = bomb_pos[0] + attack[0]
                    danger_col = bomb_pos[1] + attack[1]
                    # fill with value of WALL
                    if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                        continue
                    if self.map_matrix[danger_row][danger_col] == 1:
                        break
                    elif self.map_matrix[danger_row][danger_col] in invalid_pos_set:
                        continue
                    elif self.map_matrix[danger_row][danger_col] in valid_pos_set:
                        self.map_matrix[danger_row][danger_col] = InvalidPos.BOMB.value

    def _fill_opp_danger_zones(self):
        self.map_matrix[self.opp_bot.pos[0]][self.opp_bot.pos[1]] = ValidPos.BALK.value
        power = min(self.opp_bot.power, 3)
        tmp = copy.deepcopy(valid_pos_set)
        tmp.add(Spoil.EGG_MYSTIC.value)
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                danger_row = self.opp_bot.pos[0] + attack[0]
                danger_col = self.opp_bot.pos[1] + attack[1]
                # fill with value of WALL
                if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                    continue
                if self.map_matrix[danger_row][danger_col] == 1:
                    break
                elif self.map_matrix[danger_row][danger_col] in invalid_pos_set:
                    continue
                elif self.map_matrix[danger_row][danger_col] in tmp:
                    self.map_matrix[danger_row][danger_col] = InvalidPos.TEMP.value  # attack opp

    def _retrieve_all_targets(self):
        roads = list(zip(*np.where(self.map_matrix == 0)))
        return roads

    def _update_targets(self):
        roads = self._retrieve_all_targets()
        for pos in roads:
            num_balks = self.num_balk(pos)
            if num_balks >= 1:
                self.bomb_targets[pos] = num_balks

    def _fill_my_danger_zones(self, cur_pos, power, tmp_matrix):
        # power = min(self.my_bot.power, 4)
        for direction in attack_directions:
            for i in range(1, power + 1):
                attack = i * direction
                danger_row = cur_pos[0] + attack[0]
                danger_col = cur_pos[1] + attack[1]
                # fill with value of WALL
                if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                    continue
                if tmp_matrix[danger_row][danger_col] == 1:
                    break
                elif tmp_matrix[danger_row][danger_col] in invalid_pos_set:
                    continue
                tmp_matrix[danger_row][danger_col] = InvalidPos.TEMP.value

    def fill_map(self):
        """Fill all map matrix"""
        self._fill_spoils(self.map_info['spoils'])
        self._fill_bombs(self.map_info['bombs'])
        self._fill_bomb_danger_zones()
        self._fill_opp_danger_zones()
        interval = self.timestamp - bomb_timestamp
        if interval >= self.my_bot.delay:
            self._update_targets()
        self._fill_eggs()
        # print(f'All targets: {self.targets}')

    def avail_moves(self, cur_pos):
        """All available moves with current position."""
        res = []
        for route, direction in directions.items():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            if next_move[0] < 0 or next_move[0] >= self.max_row or next_move[1] < 0 or next_move[1] >= self.max_col:
                continue

            if self.map_matrix[next_move[0]][next_move[1]] in valid_pos_set:
                res.append((route.value, next_move))
        return res

    def finding_safe_zones_v2(self, cur_pos):
        power = min(self.my_bot.power, 3)
        # self._fill_my_danger_zones(cur_pos, power)
        unsafe_routes = deque()
        safe_routes = None
        greedy_routes = deque()
        perfected_routes = None
        saved = set()
        saved.add(cur_pos)
        move_queue = deque()
        move_queue.append([cur_pos, deque(), deque(), 0])

        count = 1
        tmp_matrix = np.array(self.map_matrix)

        while len(move_queue) > 0:
            if count == 2:
                self._fill_my_danger_zones(cur_pos, power, tmp_matrix)
            pos, routes, poses, score = move_queue.popleft()
            # Move to 4 directions next to current position.
            delta = self.heuristic_func(pos, cur_pos, -1)
            if tmp_matrix[pos[0]][pos[1]] in valid_pos_set:
                if pos in self.targets.keys():
                    if pos[0] != cur_pos[0] and pos[1] != cur_pos[1]:
                        perfected_routes = routes, poses, score
                        break
                    else:
                        if power + 1 < delta < power + 5:
                            greedy_routes.appendleft((routes, poses, score))
                            break
                else:
                    if pos[0] != cur_pos[0] and pos[1] != cur_pos[1]:
                        if not safe_routes:
                            safe_routes = routes, poses, score
                    else:
                        if power + 1 < delta < power + 5:
                            unsafe_routes.appendleft((routes, poses, score))

            next_routes = []  # Save all routes along with related information.
            for route, direction in directions.items():
                next_pos = (pos[0] + direction[0], pos[1] + direction[1])

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
                    next_routes.append([next_pos, score + 1, score + min_score, route.value])

            next_routes.sort(key=lambda x: x[2])
            for move in next_routes:
                r = copy.deepcopy(routes)
                r.append(move[3])
                p = copy.deepcopy(poses)
                p.append(move[0])
                move_queue.append([move[0], r, p, move[1]])
            count += 1

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

    def greedy_place_bombs(self, cur_pos, bombs_power=0):
        """Return next_move is 'b' if my bot can place a bomb."""
        avail_moves = self.avail_moves(cur_pos)
        # print(f'Greedy avail moves: {len(avail_moves)}')
        if len(avail_moves) == 0:
            return 0, [], []

        # bombs_power = self.num_balk(cur_pos)
        interval = self.timestamp - bomb_timestamp
        if interval >= self.my_bot.delay:
            # before placing a bomb, please find a place to hide
            moves, poses, _ = self.finding_safe_zones_v2(cur_pos)
            if len(moves) > 0:
                moves.appendleft('b')
                # bomb_timestamp = self.timestamp
                return bombs_power, moves, poses
        return 0, [], []

    def heuristic_func(self, current_pos, target_pos, spoil_type=0):
        cost = abs(current_pos[0] - target_pos[0]) + abs(current_pos[1] - target_pos[1])
        if spoil_type == 0:
            bombs_power = self.num_balk(current_pos)
            if bombs_power > 1:
                cost = cost - (bombs_power + 5)
        elif spoil_type != -1:
            cost -= 1
        return cost

    @staticmethod
    def all_moves(cur_pos):
        res = []
        for action, direction in directions.values():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            res.append((action, next_move))
        return res


def free_bfs(game_map):

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
            if game_map.map_matrix[next_pos[0]][next_pos[1]] in valid_pos_set:
                saved.add(next_pos)
                # At the current position (next_pos), add to the queue the direction of movement closest to the target.
                next_routes.append([next_pos, score + 1, route.value])

        # next_routes.sort(key=lambda x: x[2])
        for move in next_routes:
            r = copy.deepcopy(routes)
            r.append(move[2])
            p = copy.deepcopy(poses)
            p.append(move[0])
            move_queue.append([move[0], r, p, move[1]])

    return free_route


def finding_path(game_map):
    normal_routes = None

    move_queue = deque()
    # queue element [pos, routes, score]
    my_pos = game_map.my_bot.pos
    saved = set()
    saved.add(my_pos)
    move_queue.append([my_pos, [], [], 0])

    while len(move_queue) > 0:
        pos, routes, poses, score = move_queue.popleft()

        # Check whether the current position is the target or not.
        if pos in game_map.bomb_targets:
            _, place_bombs, next_poses = game_map.greedy_place_bombs(pos, game_map.bomb_targets[pos])
            if len(place_bombs) >= 3:
                routes.extend(place_bombs)
                poses.extend(next_poses)
                normal_routes = (score, routes, poses, 13)
                break
        if pos in game_map.targets:
            normal_routes = (score, routes, poses, game_map.targets[pos])
            break

        # Move to 4 directions next to current position.
        next_routes = []  # Save all routes along with related information.
        for route, direction in directions.items():
            next_pos = (pos[0] + direction[0], pos[1] + direction[1])

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
                    if est_score < min_score:
                        min_score = est_score
                # Estimate costs from current position (next_pos) to targets.
                for bomb_target_pos in game_map.bomb_targets.keys():
                    est_score = game_map.heuristic_func(next_pos, bomb_target_pos, 0)
                    if est_score < min_score:
                        min_score = est_score

                saved.add(next_pos)
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


@sio.event
def send_infor():
    infor = {"game_id": GameInfo.GAME_ID, "player_id": GameInfo.PLAYER_ID}
    sio.emit('join game', infor)


@sio.on('join game')
def join_game(data):
    print('joined game!!!!')


@sio.event
def next_moves(moves):
    sio.emit('drive player', {"direction": moves})


@sio.event
def connect():
    print('connection established')
    send_infor()


@sio.on('ticktack player')
def map_state(data):
    global my_power
    global opp_power
    global normal_queue
    global bomb_timestamp
    global previous_timestamp
    global previous_pos

    map_states.append(data)
    cur_map = map_states.pop()
    game_map = GameMap(cur_map)
    game_map.find_bots()

    game_tag = game_map.tag
    my_pos = game_map.my_bot.pos

    if game_tag == 'player:be-isolated' and game_map.map_matrix[my_pos[0]][my_pos[1]] == InvalidPos.QUARANTINE.value:
        normal_queue = []

    if len(normal_queue) > 0:
        next_move = normal_queue.pop()
        start_pos = next_move[1][1]
        if not previous_pos or start_pos != previous_pos:
            previous_pos = start_pos
            if next_move[1][3] == 13:
                bomb_timestamp = game_map.timestamp
            next_moves(next_move[1][0])
    else:
        previous_pos = None
        previous_timestamp = 0

    if game_map.my_bot.speed > 0:
        if not previous_pos:
            drive_bot(game_map)
        else:
            if my_pos != previous_pos and (game_map.timestamp - previous_timestamp) >= 16:
                previous_timestamp = game_map.timestamp
                drive_bot(game_map)

    # update latest power of bots
    my_power = min(game_map.my_bot.power, 3)
    opp_power = min(game_map.opp_bot.power, 3)


def drive_bot(game_map):
    global count_opp
    global opp_pos
    global counter
    global bomb_timestamp
    global max_time
    game_map.fill_map()
    if len(game_map.bomb_targets) > 0 or len(game_map.targets) > 0:
        normal_routes = finding_path(game_map)
        if normal_routes:
            my_route = normal_routes[1]
            normal_queue.append(
                (game_map.id, (''.join(my_route), game_map.my_bot.pos, normal_routes[2], normal_routes[3])))
            opp_pos = game_map.opp_bot.pos
            count_opp = 0
            counter = 0
        else:
            if game_map.opp_bot.pos == opp_pos:
                count_opp += 1
            counter += 1
            if count_opp == 16 or counter == 16:
                valid_pos_set.add(Spoil.EGG_MYSTIC.value)  # add egg mystic to valid pos
                valid_pos_set.add(InvalidPos.TEMP.value)
                free_route = free_bfs(game_map)
                if len(free_route) > 0:
                    my_route = free_route[1]
                    normal_queue.append(
                        (game_map.id, (''.join(my_route), game_map.my_bot.pos, free_route[2], free_route[3])))


def main():
    sio.connect('http://localhost:80', transports=['websocket'])
    sio.wait()


if __name__ == '__main__':
    main()
