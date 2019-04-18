import os
import random

from vcoingame.database import Database


class Game:
    INITIAL_RATE = int(os.environ.get('INITIAL_RATE'))
    WIN_RATE = int(os.environ.get('WIN_RATE'))

    def __init__(self, database: Database, user_id):
        self.database = database
        self.user_id = user_id
        self.round = 0

    @staticmethod
    async def create(database: Database, user_id):
        return await Game(database, user_id).initial()

    async def initial(self):
        self.round = await self.get_round()
        return self

    async def get_round(self):
        return await self.database.fetchval('''SELECT round FROM user_scores WHERE user_id = ($1::int)''', self.user_id)

    async def set_round(self, value):
        await self.database.fetchval(
            '''UPDATE user_scores SET round = ($1::int) WHERE user_id = ($2::int)''', value, self.user_id)
        self.round = value

    async def next_round(self):
        await self.database.fetchval(
            '''UPDATE user_scores SET round = round + 1 WHERE user_id = ($1::int)''', self.user_id)
        self.round += 1

    @property
    def is_started(self):
        return self.round != -1

    @staticmethod
    def get_random():
        return random.randint(0, 100) < Game.WIN_RATE

    @property
    def bet(self):
        return Game.INITIAL_RATE if self.round == -1 else Game.INITIAL_RATE * (2 ** self.round)

    @property
    def cur_reward(self):
        return self.bet * 2

    @property
    def reward(self):
        return Game.INITIAL_RATE * (2 ** self.round)
