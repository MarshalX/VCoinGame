import os
import re
import json
import random
import logging
import psycopg2
import requests

from enum import Enum
from datetime import datetime

from vk_api import vk_api
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

from requests import RequestException
from apscheduler.schedulers.background import BackgroundScheduler


logFormatter = logging.Formatter(
    '%(levelname)-5s [%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('VCoinGame')

console_handler = logging.StreamHandler()
console_handler.setFormatter(logFormatter)

logger.addHandler(console_handler)
logger.setLevel(logging.INFO)


class Database:
    def __init__(self):
        self.connection = psycopg2.connect(os.environ.get('DATABASE_URL'))


class TransactionManager(Database):
    def __init__(self):
        super().__init__()

    def get_all_ids(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT tid FROM transactions")
        result = sum(cursor.fetchall(), ())
        cursor.close()

        return result


class Transaction(Database):
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
        self.amount = int(int(amount) / 1000)
        self.type = Transaction.Type(type)
        self.payload = payload
        self.external_id = external_id
        self.created_at = created_at

    def save(self):
        cursor = self.connection.cursor()
        cursor.execute("INSERT INTO transactions (from_id, to_id, amount, created_at, tid) SELECT %s, %s, %s, %s, %s "
                       "WHERE NOT EXISTS ( "
                       "    SELECT id FROM transactions WHERE tid = %s)",
                       (self.from_id, self.to_id, self.amount, datetime.fromtimestamp(self.created_at), self.id, self.id))
        self.connection.commit()
        cursor.close()

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
    headers = {'Content-Type': 'application/json'}

    def __init__(self, merchant_id, key):
        self.merchant_id = merchant_id
        self.key = key

        self.params = {
            'merchantId': self.merchant_id,
            'key': self.key
        }

    def get_transactions(self, to_merchant=True):
        method_url = CoinAPI.api_url.format(CoinAPI.Method.GET_TRANSACTIONS.value)

        params = self.params.copy()
        params.update({'tx': [1] if to_merchant else [2]})

        response = CoinAPI._send_request(method_url, json.dumps(params))
        transactions = [Transaction.to_python(transaction) for transaction in response]

        return transactions

    def send(self, to_id, amount):
        method_url = CoinAPI.api_url.format(CoinAPI.Method.SEND.value)

        params = self.params.copy()
        params.update({'toId': to_id})
        params.update({'amount': amount * 1000})

        CoinAPI._send_request(method_url, json.dumps(params))

    def create_transaction_url(self, amount, fixed=True):
        def to_hex(dec):
            return hex(int(dec)).split('x')[-1]

        params = [to_hex(self.merchant_id), to_hex(amount * 1000), to_hex(random.randint(int(-2e9), int(2e9)))]

        return 'vk.com/coin#m' + '_'.join(params) + ('' if fixed else '_1')

    @staticmethod
    def _send_request(url, params):
        try:
            response = requests.post(url, headers=CoinAPI.headers, data=params)

            if response.status_code == 200:
                return response.json().get('response')

            raise RequestException()
        except RequestException as e:
            logger.error(e)


class Score(Database):
    def __init__(self, user_id):
        super().__init__()

        self.user_id = user_id

        if not self.is_exists():
            self.create()

    def is_exists(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_scores WHERE user_id = %s", (self.user_id,))
        result = cursor.fetchone()[0] != 0
        cursor.close()

        return result

    def create(self):
        cursor = self.connection.cursor()
        cursor.execute("INSERT INTO user_scores (user_id, score) VALUES (%s, 0)", (self.user_id,))
        self.connection.commit()
        cursor.close()

    def _update(self, sql_query, amount):
        cursor = self.connection.cursor()
        cursor.execute(sql_query, (amount, self.user_id))
        self.connection.commit()
        cursor.close()

    def set(self, amount):
        self._update("UPDATE user_scores SET score = %s WHERE user_id = %s", amount)

    def __add__(self, amount):
        self._update("UPDATE user_scores SET score = score + %s WHERE user_id = %s", amount)

        return self

    def __sub__(self, amount):
        self._update("UPDATE user_scores SET score = score - %s WHERE user_id = %s", amount)

        return self

    def get(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT score FROM user_scores WHERE user_id = %s", (self.user_id,))
        result = cursor.fetchone()[0]
        cursor.close()

        return result


class Messages:
    Commands = """Da, net, mda"""
    Score = """Ваш баланс: {}"""
    Replenish = """Пополнить счет на {} можно по следующей ссылку: {}"""
    ReplenishError = """Пожалуйста, используйте команду правильно!
    
!пополнить <количество>"""
    Withdraw = """Для вывода средств пососите жопу"""
    WithdrawError = """Пожалуйста, используйте команду правильно!

!вывести <количество>"""

    Bum = """Вы бомж, у Вас столько нет!"""
    Send = """{} монет было успешно выведено!"""
    Credited = """{} успешно зачислены на Ваш баланс!"""


class Bot:
    def __init__(self, group_id, group_token, coin_api):
        self.coin_api = coin_api
        self.session = vk_api.VkApi(token=group_token)
        self.bot = VkBotLongPoll(self.session, group_id)
        self.api = self.session.get_api()

        self.main_keyboard = VkKeyboard(one_time=False)

        def add_button(text, color=VkKeyboardColor.DEFAULT, payload=''):
            self.main_keyboard.add_button(text, color=color, payload=payload)

        add_button('Подкинуть монетку', color=VkKeyboardColor.POSITIVE)
        self.main_keyboard.add_line()
        add_button('!пополнить')
        add_button('Баланс')
        add_button('!вывести')

    def send_message(self, id, message, keyboard=None):
        if not keyboard:
            keyboard = self.main_keyboard

        self.api.messages.send(
            peer_id=id,
            random_id=get_random_id(),
            keyboard=keyboard.get_keyboard(),
            message=message
        )

    def start(self):
        for event in self.bot.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                user_id = event.object.from_id
                score = Score(user_id)

                if 'text' in event.object:
                    message = event.object.text.strip().lower()
                    if message == 'баланс':
                        self.send_message(user_id, Messages.Score.format(score.get()))
                    elif message.startswith('!пополнить'):
                        finds = re.findall(r'\d+', message)
                        if len(finds):
                            amount = int(finds[0])
                            self.send_message(user_id, Messages.Replenish.format(
                                amount, coin_api.create_transaction_url(amount)))
                        else:
                            self.send_message(user_id, Messages.ReplenishError)
                    elif message.startswith('!вывести'):
                        finds = re.findall(r'\d+', message)
                        if len(finds):
                            amount = int(finds[0])
                            if amount > score.get():
                                self.send_message(user_id, Messages.Bum)
                            else:
                                score -= amount
                                coin_api.send(user_id, amount)

                                self.send_message(user_id, Messages.Send.format(amount))
                        else:
                            self.send_message(user_id, Messages.WithdrawError)
                    elif message == 'вывести':
                        self.send_message(user_id, Messages.Withdraw)
                    else:
                        self.send_message(user_id, Messages.Commands)
                else:
                    self.send_message(user_id, Messages.Commands)


if __name__ == '__main__':
    group_id = os.environ.get('GROUP_ID')
    group_token = os.environ.get('GROUP_TOKEN')

    merchant_id = os.environ.get('MERCHANT_ID')
    key = os.environ.get('KEY')

    coin_api = CoinAPI(merchant_id, key)
    bot = Bot(group_id, group_token, coin_api)
    transaction_manager = TransactionManager()

    scheduler = BackgroundScheduler(daemon=True)

    @scheduler.scheduled_job(trigger='interval', seconds=5)
    def update_status():
        all_transactions = transaction_manager.get_all_ids()
        for transaction in coin_api.get_transactions():
            if transaction.id not in all_transactions:
                transaction.save()
                score = Score(transaction.from_id)
                score += transaction.amount
                bot.send_message(transaction.from_id, Messages.Credited.format(transaction.amount))

    scheduler.start()
    bot.start()