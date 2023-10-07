import copy
import asyncio
import socketio
from collections import deque
from const import GAME_ID

sio = socketio.AsyncClient()

map_states = []
counter = 0
# queue = PriorityQueue()
normal_queue = []
directions = {'3': [-1, 0], '1': [0, -1], '2': [0, 1], '4': [1, 0]}

# 9 is 'b' - bombs
map_routes = {'3': '4', '4': '3', '1': '2', '2': '1', '9': None}

# 10 is 'h' - humans
# 8 is 'v' - viruses
targets = {10, 5, 3, 4}
previous_pos = None


class GameMap:
    def __init__(self, data):
        self.tag = data['tag']
        self.id = int(data['id'])
        self.map_info = data["map_info"]
        self.my_bot = self.map_info["players"][1]
        self.opp_bot = self.map_info["players"][0]
        self.my_pos = (
            self.my_bot["currentPosition"]["row"],
            self.my_bot["currentPosition"]["col"]
        )
        self.opp_pos = (
            self.opp_bot["currentPosition"]["row"],
            self.opp_bot["currentPosition"]["col"]
        )
        self.power = self.my_bot['power']
        self.pill_avail = self.my_bot["pill"]
        self.max_row = self.map_info['size']['rows']
        self.max_col = self.map_info['size']['cols']
        self.map_matrix = self.map_info['map']
        self.spoils = dict()
        self.bombs = dict()
        self.viruses = dict()
        self.humans = dict()
        self.bombs_threshold = 50
        self.bombs_danger = []

    def near_wall(self, pos):
        """Return True if pos near the wall."""
        for direction in directions.values():
            if self.map_matrix[pos[0] + direction[0]][pos[1] + direction[1]] == 2:
                return True
        return False

    def _fill_spoils(self, map_spoils):
        """Fill all spoils into the map matrix."""
        for spoil in map_spoils:
            row = spoil['row']
            col = spoil['col']
            spoil_type = spoil['spoil_type']
            self.map_matrix[row][col] = spoil_type
            self.spoils[(row, col)] = {
                'type': str(spoil_type)
            }

    def _fill_bombs(self, map_bombs):
        """Fill all bombs into the map matrix."""
        for bomb in map_bombs:
            row = bomb['row']
            col = bomb['col']
            self.map_matrix[row][col] = 9
            self.bombs[(row, col)] = {
                'type': 'b',
                'remain_time': bomb['remainTime']
            }

    def _fill_viruses(self, map_viruses):
        """Fill all viruses into the map matrix."""
        for virus in map_viruses:
            row = virus.get('position')['row']
            col = virus.get('position')['col']
            if self.map_matrix[row][col] not in {6, 7}:
                self.map_matrix[row][col] = 8
                self.viruses[(row, col)] = {
                    'type': 'v',
                    'direction': str(virus.get('direction'))
                }

    def _fill_humans(self, map_humans):
        """Fill all human into the map matrix."""
        for human in map_humans:
            row = human.get('position')['row']
            col = human.get('position')['col']
            if self.map_matrix[row][col] not in {6, 7}:
                self.map_matrix[row][col] = 10
                self.humans[(row, col)] = {
                    'type': 'h',
                    'infected': human.get('infected'),
                    'direction': human.get('direction'),
                    'curedRemainTime': human.get('curedRemainTime')
                }

    def fill_map(self):
        """Fill all"""
        self._fill_spoils(self.map_info['spoils'])
        self._fill_bombs(self.map_info['bombs'])
        self._fill_viruses(self.map_info['viruses'])
        self._fill_humans(self.map_info['human'])

    def avail_moves(self, cur_pos):
        """All available moves with current position."""
        res = []
        for route, direction in directions.items():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            if next_move[0] < 0 or next_move[0] >= self.max_row or next_move[1] < 0 or next_move[1] >= self.max_col:
                continue
            if next_move == self.opp_pos:
                continue
            if self.map_matrix[next_move[0]][next_move[1]] == 10:
                hum_info = self.humans.get(next_move, False)
                if hum_info:
                    if hum_info.get('infected', False):
                        if self.pill_avail > 0:
                            res.append((route, next_move))
            elif self.map_matrix[next_move[0]][next_move[1]] == 8:
                if self.pill_avail > 0:
                    res.append((route, next_move))
            elif self.map_matrix[next_move[0]][next_move[1]] in {0, 3, 4, 5}:
                res.append((route, next_move))
        return res

    def avail_cells(self, cur_pos, tmp_matrix):
        """All available moves with current position in the specific map. Only for map traversal."""
        res = []
        for route, direction in directions.items():
            next_move = (cur_pos[0] + direction[0], cur_pos[1] + direction[1])
            if next_move[0] < 0 or next_move[0] >= self.max_row or next_move[1] < 0 or next_move[1] >= self.max_col:
                continue
            if next_move == self.opp_pos:
                continue
            if tmp_matrix[next_move[0]][next_move[1]] == 10:
                hum_info = self.humans.get(next_move, False)
                if hum_info:
                    if hum_info.get('infected', False):
                        if self.pill_avail > 0:
                            res.append((route, next_move))
            elif tmp_matrix[next_move[0]][next_move[1]] == 8:
                if self.pill_avail > 0:
                    res.append((route, next_move))
            elif tmp_matrix[next_move[0]][next_move[1]] in {0, 3, 4, 5}:
                res.append((route, next_move))
        return res

    def bomb_warning_level_1(self, cur_pos):
        """Return True if current position near bomb."""
        avail_moves = self.avail_moves(cur_pos)
        for bomb_pos, bomb_info in self.bombs.items():
            for move in avail_moves:
                if move[1] == bomb_pos and bomb_info['remain_time'] <= 50:
                    return True
        return False

    def in_bomb_danger_zones(self, cur_pos):
        """Return all danger positions."""
        danger_row_zone = None
        danger_col_zone = None
        for bomb_pos, bomb_info in self.bombs.items():
            for direction in directions.values():
                danger_row = bomb_pos[0] + direction[0]
                danger_col = bomb_pos[1] + direction[1]
                if bomb_info['remain_time'] <= 50:
                    if cur_pos[0] == danger_row:
                        danger_row_zone = danger_row
                        break
                    elif cur_pos[1] == danger_col:
                        danger_col_zone = danger_col
                        break
                if danger_row_zone or danger_col_zone:
                    break
        return danger_row_zone, danger_col_zone

    def in_opp_danger_zones(self, cur_pos):
        return cur_pos[0] == self.opp_pos[0] or cur_pos[1] == self.opp_pos[1]

    def avoid_bombs(self, cur_pos):
        """Move to the nearest safe position."""
        res = []
        stop = False
        max_loop = 100
        tmp_poss = deque()
        tmp_poss.append((-1, copy.deepcopy(cur_pos)))
        while max_loop > 0 and len(tmp_poss) > 0:
            tmp_pos = tmp_poss.popleft()
            danger_row_zone, danger_col_zone = self.in_bomb_danger_zones(tmp_pos[1])
            avail_moves = self.avail_moves(tmp_pos[1])
            for move in avail_moves:
                if move[1][0] != danger_row_zone and move[1][1] != danger_col_zone:
                    res.append(move[0])
                    stop = True
                    break
                tmp_poss.append((move[0], move[1]))
            if stop:
                break
            else:
                if len(tmp_poss) > 0:
                    res.append(tmp_poss[0][0])
            max_loop -= 1

        return res

    def heuristic_func(self, current_pos, target_pos, target_info):
        """
        First, the cost estimate is based on the target type.
        We calculate the Manhattan distance between the current position and
        the target position, then multiply by the corresponding "penalty" factors.
        Next, depending on the relative position of the current position compared to
        dangerous objects (viruses, bombs,...), deduct appropriate penalty points.
            Parameters:
                current_pos (tuple): current position
                target_pos (tuple): target position
                target_info (dict): target information
            Returns:
                cost (int): Estimated costs from current position to target position.
        """
        cost = 0
        manhattan_dist = abs(current_pos[0] - target_pos[0]) + abs(current_pos[1] - target_pos[1])

        if target_info['type'] == 'h':  # human
            if target_info['infected']:
                if self.pill_avail > 0:
                    cost = 2 * (1 / (self.pill_avail + 1)) * manhattan_dist
                else:
                    cost = 10 * manhattan_dist
            else:
                cost = 2 * manhattan_dist
        elif target_info['type'] == 'v':  # virus
            if self.pill_avail > 0:
                cost = (1 / (self.pill_avail + 1)) * manhattan_dist
            else:
                cost = 14 * manhattan_dist
        elif target_info['type'] == '3' or target_info['type'] == '4':  # bomb
            cost = 3 * manhattan_dist
        elif target_info['type'] == '5':  # pill
            cost = 1 * manhattan_dist

        # As far away from opponents as possible
        if self.in_opp_danger_zones(current_pos):
            cost = cost - (abs(current_pos[0] - self.opp_pos[0]) + abs(current_pos[1] - self.opp_pos[1]))

        # As far away from bombs as possible
        danger_row_zone, danger_col_zone = self.in_bomb_danger_zones(current_pos)
        if danger_row_zone:
            cost = cost - abs(current_pos[0] - danger_row_zone)
        if danger_col_zone:
            cost = cost - abs(current_pos[1] - danger_col_zone)

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
    tmp_matrix = copy.deepcopy(game_map.map_matrix)
    move_queue = deque()
    move_queue.append([game_map.my_pos, [], 0])

    while len(move_queue) > 0:
        pos, routes, score = move_queue.popleft()
        pill_avail = copy.deepcopy(game_map.pill_avail)
        tmp_matrix[pos[0]][pos[1]] = -1  # marked
        avail_cells = game_map.avail_cells(pos, tmp_matrix)

        # Place a bomb if there is no way left.
        if len(avail_cells) == 0 and game_map.near_wall(pos):
            r = copy.deepcopy(routes)
            r.append('b')
            normal_routes.append((1000000, r, 'b'))
            continue

        danger_row_zone, danger_col_zone = game_map.in_bomb_danger_zones(pos)
        if danger_row_zone or danger_col_zone:
            r = copy.deepcopy(routes)
            avoid_bombs = game_map.avoid_bombs(pos)
            r.extend(avoid_bombs)
            normal_routes.append((1000000, r, 'b'))
            continue

        # Check whether the current position is the target or not.
        for spoil_pos, spoil_info in game_map.spoils.items():
            est_score = game_map.heuristic_func(pos, spoil_pos, spoil_info)
            if pos[0] == spoil_pos[0] and pos[1] == spoil_pos[1]:
                normal_routes.append((est_score, copy.deepcopy(routes), spoil_info['type']))
        for hum_pos, hum_info in game_map.humans.items():
            if hum_info['infected']:
                if pill_avail == 0:
                    continue
            est_score = game_map.heuristic_func(pos, hum_pos, hum_info)
            if pos[0] == hum_pos[0] and pos[1] == hum_pos[1]:
                normal_routes.append((est_score, copy.deepcopy(routes), hum_info['type']))
                if hum_info['infected']:
                    pill_avail -= 1

        for virus_pos, virus_info in game_map.viruses.items():
            if pill_avail > 0:
                est_score = game_map.heuristic_func(pos, virus_pos, virus_info)
                if pos[0] == virus_pos[0] and pos[1] == virus_pos[1]:
                    normal_routes.append((est_score, copy.deepcopy(routes), virus_info['type']))
                    pill_avail -= 1

        # Move to 4 directions next to current position.
        next_routes = []  # Save all routes along with related information.
        for route, direction in directions.items():
            next_pos = (pos[0] + direction[0], pos[1] + direction[1])

            # invalid positions
            if next_pos[0] < 0 or next_pos[0] >= game_map.max_row or next_pos[1] < 0 or next_pos[1] >= game_map.max_col:
                continue
            if next_pos == game_map.opp_pos:
                continue
            if game_map.bomb_warning_level_1(next_pos):
                continue

            if game_map.humans.get(next_pos, False):
                hum_info = game_map.humans.get(next_pos)
                if hum_info.get('infected', False):
                    if pill_avail == 0:
                        continue
                    else:
                        pill_avail -= 1
            if game_map.viruses.get(next_pos, False):
                if pill_avail == 0:
                    continue
                else:
                    pill_avail -= 1

            # valid positions
            if tmp_matrix[next_pos[0]][next_pos[1]] in {0, 3, 4, 5, 8, 10}:
                tmp_matrix[next_pos[0]][next_pos[1]] = -1  # marked
                min_score = 1000000

                # Estimate costs from current position (next_pos) to targets.
                for spoil_pos, spoil_info in game_map.spoils.items():
                    est_score = game_map.heuristic_func(next_pos, spoil_pos, spoil_info)
                    if est_score < min_score:
                        min_score = est_score
                for hum_pos, hum_info in game_map.humans.items():
                    est_score = game_map.heuristic_func(next_pos, hum_pos, hum_info)
                    if est_score < min_score:
                        min_score = est_score
                for virus_pos, virus_info in game_map.viruses.items():
                    est_score = game_map.heuristic_func(next_pos, virus_pos, virus_info)
                    if est_score < min_score:
                        min_score = est_score

                # If you have placed a bomb before, please do not move again.
                if len(routes) > 1:
                    if routes[-2] == 'b':
                        if map_routes[routes[-1]] == route:
                            continue

                # At the current position (next_pos), add to the queue the direction of movement closest to the target.
                next_routes.append([next_pos, score + 1, score + min_score, route])

        next_routes.sort(key=lambda x: x[2])
        for move in next_routes:
            r = copy.deepcopy(routes)
            r.append(move[3])
            move_queue.append([move[0], r, move[1]])

    return normal_routes


@sio.event
async def send_infor():
    infor = {"game_id": GAME_ID, "player_id": "player2-xxx"}
    await sio.emit('join game', infor)


@sio.on('join game')
async def join_game(data):
    print('joined game!!!!')


# @sio.on('drive player')
# async def receive_moves(data):
#     print(f'Received: {data}')


@sio.event
async def next_moves(moves):
    await sio.emit('drive player', {"direction": moves})


@sio.event
async def connect():
    print('connection established')
    await send_infor()


@sio.on('ticktack player')
async def map_state(data):
    global counter
    global normal_queue
    global previous_pos

    map_states.append(data)
    if data['tag'] == 'update-data':
        map_info = data["map_info"]
        # print(f"Timestamp: {data['timestamp']} ***** MapId: {data['id']} ***** MapTag: {data['tag']}")
        my_pos = (
            map_info["players"][1]["currentPosition"]["row"],
            map_info["players"][1]["currentPosition"]["col"]
        )
        if len(normal_queue) > 0:
            next_move = normal_queue.pop()
            tmp = -1 * next_move[0]
            current_pos = next_move[1][1]
            if current_pos == my_pos and tmp > counter:
                counter = tmp
                # print(f'Move with map ID: {counter} ** {next_move[1][0]} ** {current_pos}')
                previous_pos = current_pos
                await next_moves(next_move[1][0])
        await drive_bot()


async def drive_bot():
    cur_map = map_states.pop()
    game_map = GameMap(cur_map)
    game_map.fill_map()

    avail_moves = game_map.avail_moves(game_map.my_pos)
    if len(avail_moves) == 0:
        normal_queue.append((-1 * game_map.id, ('b', game_map.my_pos)))
    else:
        # priority_routes = PriorityQueue()
        normal_routes = []
        if len(game_map.spoils) > 0 or len(game_map.humans) > 0:
            normal_routes = finding_path(game_map)

        normal_routes.sort(key=lambda x: x[0])
        if len(normal_routes) > 0:
            priority_route = normal_routes[0]
            my_route = priority_route[1]
            normal_queue.append((-1 * game_map.id, (''.join(my_route), game_map.my_pos)))


async def main():
    await sio.connect('http://localhost:5000', transports=['websocket'])
    await sio.wait()


if __name__ == '__main__':
    asyncio.run(main())
