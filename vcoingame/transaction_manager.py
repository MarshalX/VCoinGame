from datetime import datetime

from vcoingame.database import Database


class TransactionManager:
    def __init__(self, database: Database):
        self.database = database

    async def get_all_ids(self):
        result = await self.database.fetch('''SELECT tid FROM transactions ORDER BY tid DESC LIMIT 1000''')
        return [r['tid'] for r in result]

    async def save_transaction(self, transaction):
        await self.database.fetchval('''INSERT INTO transactions (from_id, to_id, amount, created_at, tid) 
                                        VALUES (($1::int), ($2::int), ($3::bigint), ($4::timestamp), ($5::int))''',
                                     transaction.from_id, transaction.to_id, transaction.amount,
                                     datetime.fromtimestamp(transaction.created_at), transaction.id)
