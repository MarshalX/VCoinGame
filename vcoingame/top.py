import asyncio
import logging

from vcoingame.database import Database

logger = logging.getLogger('vcoingame.top')


class Position:
    def __init__(self, data: dict):
        self.user_id = data.get('user_id')
        self.number = data.get('position')
        self.value = data.get('value')

    def __str__(self):
        return f'[Position] User: {self.user_id}; Number: {self.number}; Value: {self.value}'

    def __repr__(self):
        return str(self)


class Top:
    _WIN_TOP = {}
    _WINRATE_TOP = {}
    _SCORE_TOP = {}
    _GAMES_TOP = {}
    _PROFIT_TOP = {}

    WIN_TOP_10 = []
    WINRATE_TOP_10 = []
    SCORE_TOP_10 = []
    GAMES_TOP_10 = []
    PROFIT_TOP_10 = []

    def __init__(self, database: Database, user_id=None):
        self.database = database
        self.user_id = user_id

    @staticmethod
    def __update_top_10(result):
        return [Position(row) for row in result[0:10]]

    @staticmethod
    def __update_top(top, result):
        for row in result:
            top.update({row['user_id']: Position(row)})

    async def _update_profit_top(self):
        result = await self.database.fetch(
            '''SELECT  user_id, 
                       (prize - bet)::float / 1000 as value, 
                       rank() over (order by prize - bet desc) as position 
               FROM user_scores''')
        Top.PROFIT_TOP_10 = self.__update_top_10(result)
        self.__update_top(Top._PROFIT_TOP, result)

    async def _update_games_top(self):
        result = await self.database.fetch(
            '''SELECT  user_id, 
                       win + lose as value, 
                       rank() over (order by win + lose desc) as position 
               FROM user_scores''')
        Top.GAMES_TOP_10 = self.__update_top_10(result)
        self.__update_top(Top._GAMES_TOP, result)

    async def _update_win_top(self):
        result = await self.database.fetch(
            '''SELECT  user_id, 
                       win as value, 
                       rank() over (order by win desc) as position 
               FROM user_scores''')
        Top.WIN_TOP_10 = self.__update_top_10(result)
        self.__update_top(Top._WIN_TOP, result)

    async def _update_winrate_top(self):
        result = await self.database.fetch(
            '''SELECT user_id, 
                      round((win::float / (win + lose)) * 100)::int as value,
                      rank() over (order by win::float / (win + lose) desc) as position 
               FROM user_scores
               WHERE (lose != 0 or win != 0) and lose + win > 20''')
        Top.WINRATE_TOP_10 = self.__update_top_10(result)
        self.__update_top(Top._WINRATE_TOP, result)

    async def _update_score_top(self):
        result = await self.database.fetch(
            '''SELECT user_id, 
                      score::float / 1000 as value,
                      rank() over (order by score desc) as position 
               FROM user_scores''')
        Top.SCORE_TOP_10 = self.__update_top_10(result)
        self.__update_top(Top._SCORE_TOP, result)

    async def update_tops(self):
        await self._update_win_top()
        await self._update_winrate_top()
        await self._update_score_top()
        await self._update_games_top()
        await self._update_profit_top()

    async def start(self):
        while True:
            asyncio.create_task(self.update_tops())
            logger.info('TOPs has been updated')
            await asyncio.sleep(180)

    @property
    def profit(self):
        return Top._PROFIT_TOP.get(self.user_id)

    @property
    def games(self):
        return Top._GAMES_TOP.get(self.user_id)

    @property
    def win(self):
        return Top._WIN_TOP.get(self.user_id)

    @property
    def score(self):
        return Top._SCORE_TOP.get(self.user_id)

    @property
    def winrate(self):
        return Top._WINRATE_TOP.get(self.user_id)
