import logging

from vcoingame.database import Database

logger = logging.getLogger('vcoingame.statistics')


class Statistics:
    def __init__(self, database: Database, user_id):
        self.database = database
        self.user_id = user_id

    async def add_win(self):
        logger.info(f'Add win for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET win = win + 1 WHERE user_id = ($1::int)''', self.user_id)

    async def add_lose(self):
        logger.info(f'Add lose for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET lose = lose + 1 WHERE user_id = ($1::int)''', self.user_id)

    async def add_bet(self, value):
        logger.info(f'Add bet {value} for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET bet = bet + ($1::bigint) WHERE user_id = ($2::int)''', value, self.user_id)

    async def add_prize(self, value):
        logger.info(f'Add prize {value} for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET prize = prize + ($1::bigint) WHERE user_id = ($2::int)''', value, self.user_id)

    async def add_deposit(self, value):
        logger.info(f'Add deposit {value} for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET deposit = deposit + ($1::bigint) WHERE user_id = ($2::int)''', value, self.user_id)

    async def add_withdraw(self, value):
        logger.info(f'Add withdraw {value} for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET withdraw = withdraw + ($1::bigint) WHERE user_id = ($2::int)''', value, self.user_id)