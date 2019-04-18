import os
import logging
import asyncpg

logger = logging.getLogger('vcoingame.database')


class Database:
    def __init__(self):
        self.pool = None

    async def initial(self):
        self.pool = await asyncpg.create_pool(dsn=os.environ.get('DATABASE_URL'))
        return self

    @staticmethod
    async def create():
        return await Database().initial()

    @property
    async def connection(self):
        return await self.pool.acquire()

    async def fetchval(self, query, *args):
        logger.debug(f'{query}; {args}')
        conn = await self.connection
        try:
            stmt = await conn.prepare(query)
            return await stmt.fetchval(*args)
        finally:
            await self.pool.release(conn)

    async def fetch(self, query, *args):
        logger.debug(f'{query}; {args}')
        conn = await self.connection
        try:
            stmt = await conn.prepare(query)
            return await stmt.fetch(*args)
        finally:
            await self.pool.release(conn)
