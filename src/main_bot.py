import time
import copy
import socketio
import numpy as np
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
cnt = 1
normal_queue = []
saved_routes = set()
previous_pos = None
# make_decision_pos = None
last_directions = ''

my_power = 1
opp_power = 1
bomb_timestamp = 0
my_bombs = dict()
opp_bombs = dict()
attack_directions = np.array([[-1, 0], [0, -1], [0, 1], [1, 0]])
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
        bomb_power = 1
        for bomb in map_bombs:
            bomb_pos = (bomb['row'], bomb['col'])
            remain_time = bomb['remainTime']
            player_id = bomb['playerId']

            # 13: Bomb
            self.map_matrix[bomb_pos[0]][bomb_pos[1]] = InvalidPos.BOMB.value

            # set power to bombs in map matrix
            if player_id == GameInfo.PLAYER_ID:
                if my_bombs.get(bomb_pos, None):
                    bomb_power = my_bombs.get(bomb_pos)['power']
                else:
                    bomb_power = my_power

                # update my global bombs with new power
                my_bombs[bomb_pos] = {
                    'power': my_power,
                    'remain_time': remain_time
                }

            else:
                if opp_bombs.get(bomb_pos, None):
                    bomb_power = opp_bombs.get(bomb_pos)['power']
                else:
                    bomb_power = opp_power

                # update opp global bombs with new power
                opp_bombs[bomb_pos] = {
                    'power': opp_power,
                    'remain_time': remain_time
                }

            # Finding all bombs about to explode
            if remain_time <= bombs_threshold:  # default 100ms
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
            power = bomb_info['power']
            for direction in attack_directions:
                for i in range(1, power + 1):
                    attack = i * direction
                    danger_row = bomb_pos[0] + attack[0]
                    danger_col = bomb_pos[1] + attack[1]
                    # fill with value of WALL
                    if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                        continue
                    self.map_matrix[danger_row][danger_col] = InvalidPos.BOMB.value

    def _fill_opp_danger_zones(self):
        self.map_matrix[self.opp_bot.pos[0]][self.opp_bot.pos[1]] = InvalidPos.TEMP.value
        delta_row = self.opp_bot.pos[0] - self.my_bot.pos[0]
        delta_col = self.opp_bot.pos[1] - self.my_bot.pos[1]
        if delta_row == 0:
            if delta_col <= 0:
                for i in range(1, abs(delta_col)):
                    self.map_matrix[self.my_bot.pos[0]][self.opp_bot.pos[1] + i] = InvalidPos.TEMP.value
            else:
                for i in range(1, delta_col):
                    self.map_matrix[self.my_bot.pos[0]][self.opp_bot.pos[1] - i] = InvalidPos.TEMP.value
        elif delta_col == 0:
            if delta_row <= 0:
                for i in range(1, abs(delta_row)):
                    self.map_matrix[self.opp_bot.pos[0] + i][self.my_bot.pos[1]] = InvalidPos.TEMP.value
            else:
                for i in range(1, delta_row):
                    self.map_matrix[self.opp_bot.pos[0] - i][self.my_bot.pos[1]] = InvalidPos.TEMP.value

        for direction in attack_directions:
            for i in range(1, self.opp_bot.power + 1):
                attack = i * direction
                danger_row = self.opp_bot.pos[0] + attack[0]
                danger_col = self.opp_bot.pos[1] + attack[1]
                # fill with value of WALL
                if danger_row < 0 or danger_row >= self.max_row or danger_col < 0 or danger_col >= self.max_col:
                    continue
                self.map_matrix[danger_row][danger_col] = InvalidPos.TEMP.value

    def fill_map(self):
        """Fill all map matrix"""
        self._fill_spoils(self.map_info['spoils'])
        self._fill_bombs(self.map_info['bombs'])
        self._fill_bomb_danger_zones()
        self._fill_opp_danger_zones()

    def avail_moves(self, cur_pos):
        """All available moves with current position."""
        res = []
        for route, direction in directions.items():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            if next_move[0] < 0 or next_move[0] >= self.max_row or next_move[1] < 0 or next_move[1] >= self.max_col:
                continue
            # if next_move == self.opp_bot.pos:
            #     continue

            if self.map_matrix[next_move[0]][next_move[1]] in valid_pos_set:
                res.append((route.value, next_move))
        return res

    def finding_safe_zones(self, cur_pos):
        """Returns moves to the nearest safe position."""
        saved = set()
        saved.add(cur_pos)
        # answer_routes = [(deque(), deque(), 0)]
        answer_route = (deque(), deque(), 0)
        pos_queue = deque()
        init_routes = deque()
        init_pos = deque()
        pos_queue.append([cur_pos, init_routes, init_pos, 0])
        while len(pos_queue) > 0:
            pos, r, p, score = pos_queue.popleft()
            delta_row = abs(cur_pos[0] - pos[0])
            delta_col = abs(cur_pos[1] - pos[1])
            if delta_row != 0 and delta_col != 0:
                # answer_routes.append((r, p, score))
                answer_route = (r, p, score)
                break
            elif delta_col == 0:
                tmp = self.my_bot.power
                if tmp > 4:
                    tmp = 4
                if delta_row > tmp:
                    # answer_routes.append((r, p, score))
                    answer_route = (r, p, score)
                    break
            elif delta_row == 0:
                tmp = self.my_bot.power
                if tmp > 4:
                    tmp = 4
                if delta_col > tmp:
                    # answer_routes.append((r, p, score))
                    answer_route = (r, p, score)
                    break
            avail_moves = self.avail_moves(pos)
            for move in avail_moves:
                if move[1] not in saved:
                    routes = copy.deepcopy(r)
                    routes.append(move[0])
                    poses = copy.deepcopy(p)
                    poses.append(move[1])
                    saved.add(move[1])
                    pos_queue.append([move[1], routes, poses, score + 1])

        # return max(answer_routes, key=itemgetter(2))
        return answer_route

    def place_bombs(self, cur_pos):
        """Return next_move is 'b' if my bot can place a bomb."""
        avail_moves = self.avail_moves(cur_pos)
        if len(avail_moves) == 0:
            return [], []

        if self.near_balk(cur_pos):
            interval = self.timestamp - bomb_timestamp
            if interval > self.my_bot.delay:
                # before placing a bomb, please find a place to hide
                moves, poses, _ = self.finding_safe_zones(cur_pos)
                if len(moves) > 0:
                    moves.appendleft('b')
                    return moves, poses
        return [], []

    @staticmethod
    def heuristic_func(current_pos, target_pos):
        cost = abs(current_pos[0] - target_pos[0]) + abs(current_pos[1] - target_pos[1])
        return cost

    @staticmethod
    def all_moves(cur_pos):
        res = []
        for action, direction in directions.values():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            res.append((action, next_move))
        return res


def finding_path(game_map):
    normal_routes = []

    move_queue = deque()
    # queue element [pos, routes, score]
    my_pos = game_map.my_bot.pos
    saved = set()
    saved.add(my_pos)
    move_queue.append([my_pos, [], [], 0])

    while len(move_queue) > 0:
        pos, routes, poses, score = move_queue.popleft()
        place_bombs, next_poses = game_map.place_bombs(pos)
        if len(place_bombs) > 0:
            r = copy.deepcopy(routes)
            r.extend(place_bombs)
            p = copy.deepcopy(poses)
            p.extend(next_poses)
            normal_routes.append((-1, r, p, 13))
            break

        # Check whether the current position is the target or not.
        for spoil_pos, spoil_type in game_map.targets.items():
            if game_map.map_matrix[spoil_pos[0]][spoil_pos[1]] not in valid_pos_set:
                continue
            est_score = game_map.heuristic_func(pos, spoil_pos)
            if pos == spoil_pos:
                normal_routes.append((est_score, copy.deepcopy(routes), copy.deepcopy(poses), spoil_type))

        # Move to 4 directions next to current position.
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

                min_score = 1000000

                # Estimate costs from current position (next_pos) to targets.
                for spoil_pos in game_map.targets.keys():
                    est_score = game_map.heuristic_func(next_pos, spoil_pos)
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


# @sio.on('drive player')
# def receive_moves(data):
#     print(f'Received: {data}')


@sio.event
def next_moves(moves):
    sio.emit('drive player', {"direction": moves})


@sio.event
def connect():
    print('connection established')
    send_infor()


@sio.on('ticktack player')
def map_state(data):
    global counter
    global my_power
    global opp_power
    global normal_queue
    global saved_routes

    map_states.append(data)
    cur_map = map_states.pop()
    game_map = GameMap(cur_map)
    game_map.find_bots()
    game_tag = game_map.tag
    my_pos = game_map.my_bot.pos

    if game_tag == 'player:be-isolated' and game_map.map_matrix[my_pos[0]][my_pos[1]] == InvalidPos.QUARANTINE.value:
        saved_routes = set()
        normal_queue = []

    if len(normal_queue) > 0:
        next_move = normal_queue.pop()
        start_pos = next_move[1][1]

        if len(saved_routes) == 0 or (start_pos in saved_routes):
            saved_routes = set(next_move[1][2])
            next_moves(next_move[1][0])
    else:
        saved_routes = set()

    if len(saved_routes) == 0 or my_pos in saved_routes:
        drive_bot(game_map)
    # update latest power of bots
    if game_map.my_bot.power <= 4:
        my_power = game_map.my_bot.power
    else:
        my_power = 4
    if game_map.opp_bot.power <= 4:
        opp_power = game_map.opp_bot.power
    else:
        opp_power = 4


def drive_bot(game_map):
    game_map.fill_map()
    normal_routes = finding_path(game_map)
    if len(normal_routes) > 0:
        normal_routes.sort(key=lambda x: x[0])
        priority_route = normal_routes[0]
        my_route = priority_route[1]

        normal_queue.append((-1 * game_map.id, (''.join(my_route), game_map.my_bot.pos, priority_route[2])))


def main():
    sio.connect('http://localhost:80', transports=['websocket'])
    sio.wait()


if __name__ == '__main__':
    main()
