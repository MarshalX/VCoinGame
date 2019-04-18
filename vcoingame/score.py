import os
import re

from decimal import Decimal

from vcoingame.database import Database


class Score:
    def __init__(self, database: Database, user_id):
        self.database = database
        self.user_id = user_id
        self.score = 0

    @staticmethod
    async def get_or_create(database: Database, user_id):
        score = Score(database, user_id)
        if await score.is_exists():
            await score.get()
        else:
            await score.create()

        return score

    async def is_exists(self):
        return await self.database.fetchval(
            '''SELECT COUNT(*) FROM user_scores WHERE user_id = ($1::int)''', self.user_id)

    async def create(self):
        await self.database.fetchval(
            '''INSERT INTO user_scores (user_id, score) VALUES (($1::int), ($2::bigint))''',
            self.user_id, int(os.environ.get('INITIAL_RATE')))
        self.score = int(os.environ.get('INITIAL_RATE'))

    async def set(self, amount):
        await self.database.fetchval(
            '''UPDATE user_scores SET score = ($1::bigint) WHERE user_id = ($2::int)''', amount, self.user_id)
        self.score = amount

    async def add(self, amount):
        await self.database.fetchval(
            '''UPDATE user_scores SET score = score + ($1::bigint) WHERE user_id = ($2::int)''', amount, self.user_id)
        self.score += amount

    async def sub(self, amount):
        await self.database.fetchval(
            '''UPDATE user_scores SET score = score - ($1::bigint) WHERE user_id = ($2::int)''', amount, self.user_id)
        self.score -= amount

    async def get(self) -> Decimal:
        self.score = await self.database.fetchval(
            '''SELECT score FROM user_scores WHERE user_id = ($1::int)''', self.user_id)
        return self.score

    def __str__(self):
        return str(self.score / 1000)

    @staticmethod
    def parse_score(message):
        finds = re.findall(r'\d*[.,]?\d+', message)
        return int(float(finds[0].replace(',', '.')) * 1000) if len(finds) else None
