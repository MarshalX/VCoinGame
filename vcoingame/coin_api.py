import aiohttp
import asyncio

from enum import Enum


class Transaction:
    class Type(Enum):
        FROM_USER_TO_USER = 3
        FROM_USER_TO_MERCHANT = 4

    def __init__(self,
                 id,
                 from_id,
                 to_id,
                 amount,
                 type,
                 payload,
                 external_id,
                 created_at):
        super().__init__()

        self.id = id
        self.from_id = from_id
        self.to_id = to_id
        self.amount = int(amount)
        self.type = Transaction.Type(type)
        self.payload = payload
        self.external_id = external_id
        self.created_at = created_at

    @staticmethod
    def to_python(transaction):
        return Transaction(
            transaction.get('id'),
            transaction.get('from_id'),
            transaction.get('to_id'),
            transaction.get('amount'),
            transaction.get('type'),
            transaction.get('payload'),
            transaction.get('external_id'),
            transaction.get('created_at'),
        )

    def __str__(self):
        return f'ID: {self.id}; FROM: {self.from_id}; TO: {self.to_id}; AMOUNT: {self.amount}; TYPE {self.type}'

    def __repr__(self):
        return self.__str__()


class CoinAPI:
    class Method(Enum):
        GET_TRANSACTIONS = 'tx'
        SEND = 'send'

    api_url = 'https://coin-without-bugs.vkforms.ru/merchant/{}/'

    def __init__(self, merchant_id, key, payload):
        self.session = aiohttp.ClientSession()
        self.transfers = asyncio.Queue()
        self.merchant_id = merchant_id
        self.payload = payload
        self.key = key

        self.params = {
            'merchantId': self.merchant_id,
            'key': self.key
        }

    async def get_transactions(self, to_merchant=True):
        method_url = CoinAPI.api_url.format(CoinAPI.Method.GET_TRANSACTIONS.value)

        params = self.params.copy()
        params.update({'tx': [1] if to_merchant else [2]})

        response = await self._send_request(method_url, params)
        response = response['response']

        transactions = [Transaction.to_python(transaction) for transaction in response]

        return transactions

    def send(self, to_id, amount):
        method_url = CoinAPI.api_url.format(CoinAPI.Method.SEND.value)

        params = self.params.copy()
        params.update({'toId': to_id})
        params.update({'amount': amount})

        self.transfers.put_nowait((method_url, params))

    def create_transaction_url(self, amount, fixed=True):
        def to_hex(dec):
            return hex(int(dec)).split('x')[-1]

        params = [to_hex(self.merchant_id), to_hex(amount), to_hex(self.payload)]

        return 'vk.com/coin#m' + '_'.join(params) + ('' if fixed else '_1')

    async def do_transfers(self):
        while True:
            await self._send_request(*await self.transfers.get())

    async def _send_request(self, url, params):
        async with self.session.post(url, json=params) as response:
            return await response.json(content_type=response.content_type)
