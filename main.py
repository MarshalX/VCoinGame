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
logger.setLevel(logging.INFO if os.environ.get("DEBUG") is None else logging.DEBUG)


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
        self.amount = int(amount)
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
        logger.debug(response)

        transactions = [Transaction.to_python(transaction) for transaction in response]

        return transactions

    def send(self, to_id, amount):
        method_url = CoinAPI.api_url.format(CoinAPI.Method.SEND.value)

        params = self.params.copy()
        params.update({'toId': to_id})
        params.update({'amount': amount})

        logger.debug(CoinAPI._send_request(method_url, json.dumps(params)))

    def create_transaction_url(self, amount, fixed=True):
        def to_hex(dec):
            return hex(int(dec)).split('x')[-1]

        params = [to_hex(self.merchant_id), to_hex(amount), to_hex(random.randint(int(-2e9), int(2e9)))]

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
        logger.debug(f'SQL: {sql_query}; {amount}, {self.user_id}')
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

    def print(self):
        return self.get() / 1000

    @staticmethod
    def parse_score(message):
        finds = re.findall(r'\d*[.,]?\d+', message)
        return int(float(finds[0].replace(',', '.')) * 1000) if len(finds) else None


class Game(Database):
    INITIAL_RATE = int(os.environ.get('INITIAL_RATE'))
    WIN_RATE = int(os.environ.get('WIN_RATE'))

    def __init__(self, user_id):
        super().__init__()

        self.user_id = user_id
        self.round = self.get_round()

    @staticmethod
    def random():
        return random.randint(0, 100) <= Game.WIN_RATE

    def play(self):
        self.__add__(1)

        if Game.random():
            self.end_game()
            return True
        else:
            return False

    def get_round(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT round FROM user_scores WHERE user_id = %s", (self.user_id,))
        result = cursor.fetchone()[0]
        cursor.close()

        return result

    def _update(self, sql_query, value):
        logger.debug(f'SQL: {sql_query}; {value}, {self.user_id}')
        cursor = self.connection.cursor()
        cursor.execute(sql_query, (value, self.user_id))
        self.connection.commit()
        cursor.close()

    def set_round(self, round):
        self._update("UPDATE user_scores SET round = %s WHERE user_id = %s", round)
        self.round = round

    def __add__(self, value):
        self._update("UPDATE user_scores SET round = round + %s WHERE user_id = %s", value)
        self.round += value

    def start_game(self):
        self.set_round(0)

    def end_game(self):
        self.set_round(-1)

    @property
    def in_progress(self):
        return self.round != -1

    @property
    def bet(self):
        return Game.INITIAL_RATE if self.round == -1 else Game.INITIAL_RATE * (2 ** self.round)

    @property
    def cur_reward(self):
        return self.bet * 2

    @property
    def reward(self):
        return Game.INITIAL_RATE * (2 ** self.round)


class Messages:
    Commands = """✌️ Привет! 

Со мной ты можешь поиграть в игру Орёл и Решка! Я люблю играть за решку, значит ты будешь играть за орла :)

Начальная ставка составляет {}. Каждый раз, когда ты подбрасываешь монету, с твоего счёта будет списываться соответствующая сумма. Если ты выиграл, ты можешь забрать приз или продолжить играть.

Если ты хочешь попытать удачу и сыграть еще раз, то новая ставка будет в два раза больше старой. Не волнуйся, твой возможный приз увеличивается в два раза вместе со ставкой!

⚔️ Да прибудет с тобой удача, джедай..."""
    Score = """💰 Ваш баланс: {}"""
    DepositFixed = """Пополнить счет на {} можно по следующей ссылке: {}"""
    Deposit = """Пополнить счет можно по следующей ссылке: {}"""
    WithdrawError = """Пожалуйста, используйте команду правильно!

Вывести <количество>"""

    Bum = """😢 На Вашем баланс недостаточно средств.
Вы можете пополнить его с помощью команды
Пополнить <количество>"""
    BumLeft = """😢 На Вашем баланс не хватает {} монет, чтобы сделать ставку!
Вы можете пополнить его с помощью команды
Пополнить <количество>"""
    Send = """✅ {} монет было успешно выведено!"""
    Credited = """✅ {} монет успешно зачислены на Ваш баланс!"""
    PickUp = """💰 Вы забрали приз в размере {}"""
    Lose = """😢 Выпала решка, Вы проиграли :("""
    Win = """🙂 Опа, орёл, поздравляю! Текущий приз: {}. 
Сыграем еще? Новая ставка составляет {}"""
    NoWin = """😞 Ты ничего не выиграл"""


class Bot:
    def __init__(self, group_id, group_token, coin_api):
        self.lose_img = os.environ.get('LOSE_IMG')
        self.win_img = os.environ.get('WIN_IMG')

        self.coin_api = coin_api
        self.session = vk_api.VkApi(token=group_token)
        self.bot = VkBotLongPoll(self.session, group_id)
        self.api = self.session.get_api()

        def add_button(keyboard, text, color=VkKeyboardColor.DEFAULT, payload=''):
            keyboard.add_button(text, color=color, payload=payload)

        self.main_keyboard = VkKeyboard(one_time=False)

        add_button(self.main_keyboard, 'Подкинуть монетку', color=VkKeyboardColor.POSITIVE)
        self.main_keyboard.add_line()
        add_button(self.main_keyboard, 'Забрать приз')
        self.main_keyboard.add_line()
        add_button(self.main_keyboard, 'Пополнить')
        add_button(self.main_keyboard, 'Баланс')
        add_button(self.main_keyboard, 'Вывести')

    def send_message(self, id, message, keyboard=None, attachment=None):
        if not keyboard:
            keyboard = self.main_keyboard

        self.api.messages.send(
            peer_id=id,
            random_id=get_random_id(),
            keyboard=keyboard.get_keyboard(),
            attachment=attachment if attachment else '',
            message=message
        )

    def start(self):
        for event in self.bot.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                user_id = event.object.from_id
                score = Score(user_id)
                game = Game(user_id)

                if 'text' in event.object:
                    message = event.object.text.strip().lower()
                    amount = Score.parse_score(message)

                    if game.in_progress and message == 'забрать приз':
                        logger.info(f'{user_id} забрал приз в размере {game.cur_reward / 1000} коинов')
                        self.send_message(user_id, Messages.PickUp.format(game.cur_reward / 1000))
                        score += game.cur_reward
                        game.end_game()
                    elif not game.in_progress and message == 'забрать приз':
                        self.send_message(user_id, Messages.NoWin)
                    elif message == 'подкинуть монетку':
                        logger.info(f'{user_id} подкинул монетку')
                        if game.bet > score.get():
                            logger.info(f'У {user_id} не хватает средств для броска ({game.bet} > {score.get()})')
                            
                            self.send_message(user_id, Messages.BumLeft.format((game.bet - score.get()) / 1000))
                        else:
                            score -= game.bet
                            if game.play():
                                logger.info(f'{user_id} проиграл')
                                self.send_message(user_id, Messages.Lose, attachment=self.lose_img)
                            else:
                                logger.info(f'{user_id} выиграл {game.cur_reward / 1000}. '
                                            f'След. ставка {game.cur_reward / 1000}')
                                self.send_message(user_id, Messages.Win.format(
                                    game.cur_reward / 1000, game.cur_reward / 1000), attachment=self.win_img)
                    elif message == 'баланс':
                        logger.info(f'{user_id} посмотрел свой баланс')
                        self.send_message(user_id, Messages.Score.format(score.print()))
                    elif message.startswith('пополнить'):
                        logger.info(f'{user_id} хочет пополнить баланс')
                        if amount:
                            self.send_message(user_id, Messages.DepositFixed.format(
                                amount / 1000, coin_api.create_transaction_url(amount)))
                        else:
                            self.send_message(user_id, Messages.Deposit.format(
                                coin_api.create_transaction_url(0, False)))
                    elif message.startswith('вывести'):
                        logger.info(f'{user_id} хочет вывести баланс')
                        if amount:
                            if amount > score.get():
                                self.send_message(user_id, Messages.Bum)
                            else:
                                logger.info(f'{user_id} вывел {amount / 1000}')
                                score -= amount
                                coin_api.send(user_id, amount)

                                self.send_message(user_id, Messages.Send.format(amount / 1000))
                        else:
                            self.send_message(user_id, Messages.WithdrawError)
                    else:
                        self.send_message(user_id, Messages.Commands.format(Game.INITIAL_RATE / 1000))
                else:
                    self.send_message(user_id, Messages.Commands.format(Game.INITIAL_RATE / 1000))

                score.connection.close()
                game.connection.close()


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
                logger.info(f'{transaction.from_id} пополнил баланс на {transaction.amount / 1000}')
                transaction.save()
                score = Score(transaction.from_id)
                score += transaction.amount
                bot.send_message(transaction.from_id, Messages.Credited.format(transaction.amount / 1000))

    scheduler.start()
    bot.start()
