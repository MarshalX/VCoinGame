import os
import re
import json
import random
import logging
import psycopg2
import requests
import threading

from enum import Enum
from queue import Queue
from datetime import datetime

from vk_api import vk_api
from vk_api.utils import get_random_id
from vk_api.exceptions import ApiError
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

    def save_transaction(self, transaction):
        cursor = self.connection.cursor()
        cursor.execute("INSERT INTO transactions (from_id, to_id, amount, created_at, tid) SELECT %s, %s, %s, %s, %s "
                       "WHERE NOT EXISTS ( "
                       "    SELECT id FROM transactions WHERE tid = %s)",
                       (transaction.from_id, transaction.to_id, transaction.amount,
                        datetime.fromtimestamp(transaction.created_at), transaction.id,
                        transaction.id))
        self.connection.commit()
        cursor.close()

    def save_transactions(self, transactions):
        for transaction in transactions:
            self.save_transaction(transaction)


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
    headers = {'Content-Type': 'application/json'}

    PAYLOAD = os.environ.get('PAYLOAD')

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

        params = [to_hex(self.merchant_id), to_hex(amount), to_hex(CoinAPI.PAYLOAD)]

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
        cursor.execute("INSERT INTO user_scores (user_id, score) VALUES (%s, %s)", (self.user_id, Game.INITIAL_RATE))
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
        return random.randint(0, 99) <= Game.WIN_RATE

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
Со мной Вы можете поиграть в игру Орёл и Решка! Я люблю играть за решку, значит Вы будете играть за орла :)
Начальная ставка составляет {}. Каждый раз, когда Вы подбрасываете монету, с Вашего счёта будет списываться соответствующая сумма. Если Вам выпал орёл, Вы можете забрать приз или продолжить играть.
Если Вы хотите попытать удачу и сыграть еще раз, то новая ставка будет в два раза больше старой. Не волнуйтесь, Ваш возможный приз увеличивается в два раза вместе со ставкой!
🛑 Будь осторожнее 🛑 Если Вы жмёте «Подкинуть монетку», Ваш текущий выигрыш Вам не начисляется! Чтобы получить коины на свой счет, недостаточно получить «Орла». Вы должны нажать на «Забрать приз».
Часто задаваемые вопросы: vk.cc/9hAcg8
⚔️ Да прибудет с тобой удача, джедай..."""
    ScoreReward = """💰 Ваш баланс: {}
    
Ваша приз: {} (нажмите "Забрать приз")"""
    Score = """💰 Ваш баланс: {}"""
    DepositFixed = """Пополнить счет на {} можно по следующей ссылке: {}"""
    Deposit = """Пополнить счет можно по следующей ссылке: {}"""
    Withdraw = """Пожалуйста, напишите сколько хотите вывести"""
    WithdrawError = """Вы неправильно ввели значение... Попробуйте ещё раз"""

    Bum = """😢 На Вашем баланс недостаточно средств.
    
Вы можете пополнить его с помощью команды
Пополнить <количество>"""
    BumLeft = """😢 На Вашем балансе не хватает {} монет, чтобы сделать ставку!
    
Вы можете пополнить его нажав на кнопку "Пополнить" """

    Reward = """😢 На Вашем балансе не хватает {} монет, чтобы сделать ставку!
    
Вы можете пополнить его нажав на кнопку "Пополнить"
Также Вы можете забрать свой текущий приз."""
    Send = """✅ {} монет было успешно выведено!"""
    Credited = """✅ {} монет успешно зачислены на Ваш баланс!"""
    PickUp = """💰 Вы забрали приз в размере {}"""
    Lose = """😢 Выпала решка, Вы проиграли :("""
    Win = """🙂 Опа, орёл, поздравляю! Текущий приз: {}. 
Вы можете забрать его либо попробовать сыграть новый раунд! 
🛑 Если Вы начинаете играть новый раунд, Ваш текущий приз может сгореть, будьте осторожнее! Чтобы получить коины на свой счет, недостаточно получить «Орла». Вы должны нажать на «Получить приз». 🛑
Новая ставка составляет {} коинов"""
    NoWin = """😞 Вы ничего не выиграли. Чтобы начать игру, нажмите «Подкинуть монетку»"""


class Bot:
    def __init__(self, group_id, group_token, coin_api, transfers):
        self.lose_img = os.environ.get('LOSE_IMG')
        self.win_img = os.environ.get('WIN_IMG')

        self.withdraw = []

        self.coin_api = coin_api
        self.transfers = transfers
        self.session = vk_api.VkApi(token=group_token)
        self.bot = VkBotLongPoll(self.session, group_id)
        self.api = self.session.get_api()

        def add_button(keyboard, text, color=VkKeyboardColor.DEFAULT, payload=''):
            keyboard.add_button(text, color=color, payload=payload)

        self.main_keyboard = VkKeyboard(one_time=False)

        add_button(self.main_keyboard, 'Подкинуть монетку', color=VkKeyboardColor.POSITIVE)
        self.main_keyboard.add_line()
        add_button(self.main_keyboard, 'Пополнить')
        add_button(self.main_keyboard, 'Баланс')
        add_button(self.main_keyboard, 'Вывести')

        self.game_keyboard = VkKeyboard(one_time=False)

        add_button(self.game_keyboard, 'Подкинуть монетку', color=VkKeyboardColor.POSITIVE)
        self.game_keyboard.add_line()
        add_button(self.game_keyboard, 'Забрать приз')
        self.game_keyboard.add_line()
        add_button(self.game_keyboard, 'Пополнить')
        add_button(self.game_keyboard, 'Баланс')
        add_button(self.game_keyboard, 'Вывести')

    def _send_message(self, id, message, attachment=None, game=False):
        keyboard = self.game_keyboard if game else self.main_keyboard

        try:
            self.api.messages.send(
                peer_id=id,
                random_id=get_random_id(),
                keyboard=keyboard.get_keyboard(),
                attachment=attachment if attachment else '',
                message=message
            )
        except ApiError as e:
            logger.error(e)

    def message_handler(self, event):
        user_id = event.object.from_id
        score = Score(user_id)
        game = Game(user_id)

        def send_message(id, message, attachment=None):
            self._send_message(id, message, attachment, game.in_progress)

        if 'text' in event.object:
            message = event.object.text.strip().lower()
            amount = Score.parse_score(message)

            if game.in_progress and message == 'забрать приз':
                logger.info(f'{user_id} забрал приз в размере {game.cur_reward / 1000} коинов')

                score += game.cur_reward

                send_message(user_id, Messages.PickUp.format(game.cur_reward / 1000))

                game.end_game()
            elif not game.in_progress and message == 'забрать приз':
                send_message(user_id, Messages.NoWin)
            elif message == 'подкинуть монетку':
                logger.info(f'{user_id} подкинул монетку')
                if game.bet > score.get():
                    logger.info(f'У {user_id} не хватает средств для броска ({game.bet} > {score.get()})')

                    if not game.in_progress:
                        send_message(user_id, Messages.BumLeft.format((game.bet - score.get()) / 1000))
                    else:
                        send_message(user_id, Messages.Reward.format((game.bet - score.get()) / 1000))
                else:
                    score -= game.bet
                    if game.play():
                        logger.info(f'{user_id} проиграл')
                        send_message(user_id, Messages.Lose, attachment=self.lose_img)
                    else:
                        logger.info(f'{user_id} выиграл {game.cur_reward / 1000}. '
                                    f'След. ставка {game.cur_reward / 1000}')
                        send_message(user_id, Messages.Win.format(
                            game.cur_reward / 1000, game.bet / 1000), attachment=self.win_img)
            elif message == 'баланс':
                logger.info(f'{user_id} посмотрел свой баланс')
                if game.in_progress:
                    send_message(user_id, Messages.ScoreReward.format(score.print(), game.cur_reward / 1000))
                else:
                    send_message(user_id, Messages.Score.format(score.print()))
            elif message.startswith('пополнить'):
                logger.info(f'{user_id} хочет пополнить баланс')
                if amount:
                    send_message(user_id, Messages.DepositFixed.format(
                        amount / 1000, coin_api.create_transaction_url(amount)))
                else:
                    send_message(user_id, Messages.Deposit.format(
                        coin_api.create_transaction_url(0, False)))
            elif message == 'вывести' and user_id not in self.withdraw:
                self.withdraw.append(user_id)
                send_message(user_id, Messages.Withdraw)
            elif user_id in self.withdraw:
                logger.info(f'{user_id} хочет вывести баланс')
                del self.withdraw[self.withdraw.index(user_id)]
                if amount:
                    if amount > score.get():
                        if game.in_progress:
                            send_message(user_id, Messages.Bum + Messages.ScoreReward.format(
                                score.print(), game.cur_reward / 1000))
                        else:
                            send_message(user_id, Messages.Bum)
                    else:
                        logger.info(f'{user_id} вывел {amount / 1000}')
                        score -= amount
                        self.transfers.put((user_id, amount))
                        send_message(user_id, Messages.Send.format(amount / 1000))
                else:
                    send_message(user_id, Messages.WithdrawError)
            else:
                send_message(user_id, Messages.Commands.format(Game.INITIAL_RATE / 1000))
        else:
            send_message(user_id, Messages.Commands.format(Game.INITIAL_RATE / 1000))

        score.connection.close()
        game.connection.close()

    def start(self):
        for event in self.bot.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                threading.Thread(target=self.message_handler, args=(event,)).start()


if __name__ == '__main__':
    group_id = int(os.environ.get('GROUP_ID'))
    group_token = os.environ.get('GROUP_TOKEN')

    merchant_id = int(os.environ.get('MERCHANT_ID'))
    key = os.environ.get('KEY')

    transfers = Queue()

    coin_api = CoinAPI(merchant_id, key)
    bot = Bot(group_id, group_token, coin_api, transfers)
    transaction_manager = TransactionManager()

    scheduler = BackgroundScheduler(daemon=True)

    def do_transfers(transfers_queue):
        while True:
            user_id, amount = transfers_queue.get()
            coin_api.send(user_id, amount)

    @scheduler.scheduled_job(trigger='interval', seconds=5)
    def update_status():
        all_transactions = transaction_manager.get_all_ids()

        transactions = coin_api.get_transactions()
        transactions.extend(coin_api.get_transactions(False))
        transactions = [transaction for transaction in transactions if transaction.from_id != merchant_id]

        for transaction in transactions:
            if transaction.id not in all_transactions:
                logger.info(f'{transaction.from_id} пополнил баланс на {transaction.amount / 1000}')
                transaction_manager.save_transaction(transaction)

                score = Score(transaction.from_id)
                score += transaction.amount
                score.connection.close()

                bot._send_message(transaction.from_id, Messages.Credited.format(transaction.amount / 1000))

    threading.Thread(target=do_transfers, args=(transfers,)).start()
    scheduler.start()
    bot.start()
