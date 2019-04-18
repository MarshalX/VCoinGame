import os
import asyncio
import logging

from vk_api.api import API

from vk_api.sessions import TokenSession
from vk_api.longpull import BotsLongPoll
from vk_api.updates import UpdateManager
from vk_api.handlers import MessageHandler
from vk_api.keyboard import Keyboard, ButtonColor

from vcoingame.game import Game
from vcoingame.score import Score
from vcoingame.states import State
from vcoingame.coin_api import CoinAPI
from vcoingame.messages import Message
from vcoingame.database import Database
from vcoingame.session import SessionList
from vcoingame.handler_payload import HandlerPayload
from vcoingame.transaction_manager import TransactionManager


logFormatter = logging.Formatter(
    '%(levelname)-5s [%(asctime)s] %(name)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger()

console_handler = logging.StreamHandler()
console_handler.setFormatter(logFormatter)

logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG if os.environ.get("DEBUG") else logging.INFO)


async def help_handler(payload: HandlerPayload):
    await payload.api.messages.send(
        user_id=payload.from_id,
        message=Message.Commands.format(Game.INITIAL_RATE / 1000),
        keyboard=payload.keyboard.get_keyboard())


async def balance_handler(payload: HandlerPayload):
    game = payload.session.game
    score = payload.session.score

    if game.is_started:
        msg = Message.ScoreReward.format(score, game.cur_reward / 1000)
    else:
        msg = Message.Score.format(score)

    await payload.api.messages.send(
        user_id=payload.from_id,
        message=msg,
        keyboard=payload.keyboard.get_keyboard())


async def withdraw_handler_1(payload: HandlerPayload):
    payload.session.state = State.WITHDRAW

    await payload.api.messages.send(
        user_id=payload.from_id, message=Message.Withdraw, keyboard=payload.keyboard.get_keyboard())


async def withdraw_handler_2(payload: HandlerPayload):
    amount = Score.parse_score(payload.text)
    if amount > payload.session.score.score:
        await payload.api.messages.send(
            user_id=payload.from_id, message=Message.Bum)
        return

    await payload.session.score.sub(amount)
    await payload.coin_api.send(payload.from_id, amount)

    msg = Message.Send.format(amount / 1000)
    await payload.api.messages.send(
        user_id=payload.from_id, message=msg, keyboard=payload.keyboard.get_keyboard())


async def deposit_handler(payload: HandlerPayload):
    msg = Message.Deposit.format(payload.coin_api.create_transaction_url(0, fixed=False))
    await payload.api.messages.send(
        user_id=payload.from_id, message=msg, keyboard=payload.keyboard.get_keyboard())


async def toss(payload: HandlerPayload):
    game = payload.session.game
    user_score = payload.session.score.score

    if game.bet > user_score:
        if game.is_started:
            msg = Message.Reward.format((game.bet - user_score) / 1000)
            keyboard = payload.keyboards.get('game')
        else:
            msg = Message.BumLeft.format((game.bet - user_score) / 1000)
            keyboard = payload.keyboards.get('main')

        await payload.api.messages.send(
            user_id=payload.from_id, message=msg, keyboard=keyboard.get_keyboard())

        return

    await payload.session.score.sub(game.bet)

    if game.get_random():
        payload.session.state = State.GAME

        await game.next_round()
        await payload.api.messages.send(
            user_id=payload.from_id,
            message=Message.Win.format(game.cur_reward / 1000, game.bet / 1000),
            keyboard=payload.keyboards.get('game').get_keyboard(),
            attachment=os.environ.get('WIN_IMG')
        )
    else:
        payload.session.reset_state()

        await game.set_round(-1)
        await payload.api.messages.send(
            user_id=payload.from_id,
            message=Message.Lose,
            keyboard=payload.keyboards.get('main').get_keyboard(),
            attachment=os.environ.get('LOSE_IMG')
        )


async def get_reward_handler(payload: HandlerPayload):
    game = payload.session.game

    if not game.is_started:
        await payload.api.messages.send(
            user_id=payload.from_id,
            message=Message.NoWin,
            keyboard=payload.keyboards.get('main').get_keyboard(),
        )
        return

    await payload.session.score.add(game.cur_reward)

    await payload.api.messages.send(
        user_id=payload.from_id,
        message=Message.PickUp.format(game.cur_reward / 1000),
        keyboard=payload.keyboards.get('main').get_keyboard(),
    )

    await game.set_round(-1)


async def main():
    token_session = TokenSession(os.environ.get('GROUP_TOKEN'))
    api = API(token_session)
    longpull = BotsLongPoll(api, mode=2, group_id=os.environ.get('GROUP_ID'))

    coin_api = CoinAPI(os.environ.get('MERCHANT_ID'), os.environ.get('KEY'), os.environ.get('PAYLOAD'))

    database = await Database.create()
    sessions = SessionList(database)

    transaction_manager = TransactionManager(database)

    main_keyboard = Keyboard()
    main_keyboard.add_button('Подкинуть монетку', color=ButtonColor.POSITIVE)
    main_keyboard.add_line()
    main_keyboard.add_button('Пополнить')
    main_keyboard.add_button('Баланс')
    main_keyboard.add_button('Вывести')

    game_keyboard = Keyboard()
    game_keyboard.add_button('Подкинуть монетку', color=ButtonColor.POSITIVE)
    game_keyboard.add_line()
    game_keyboard.add_button('Забрать приз')
    game_keyboard.add_line()
    game_keyboard.add_button('Пополнить')
    game_keyboard.add_button('Баланс')
    game_keyboard.add_button('Вывести')

    keyboards = {
        'main': main_keyboard,
        'game': game_keyboard
    }

    payload = HandlerPayload(
        sessions,
        coin_api,
        keyboards
    )

    update_manager = UpdateManager(longpull)
    update_manager.register_handler(MessageHandler(
        toss, 'Подкинуть монетку', State.ALL, payload, reset_state=True))
    update_manager.register_handler(MessageHandler(
        get_reward_handler, 'Забрать приз', State.ALL, payload, reset_state=True))
    update_manager.register_handler(MessageHandler(
        deposit_handler, 'Пополнить', State.ALL, payload, reset_state=True))
    update_manager.register_handler(MessageHandler(
        withdraw_handler_1, 'Вывести', State.ALL, payload))
    update_manager.register_handler(MessageHandler(
        withdraw_handler_2, r'\d*[.,]?\d+', State.WITHDRAW, payload, regex=True, reset_state=True))
    update_manager.register_handler(MessageHandler(
        balance_handler, 'Баланс', State.ALL, payload, reset_state=True))
    update_manager.register_handler(MessageHandler(
        help_handler, '', State.ALL, payload))

    async def get_trans():
        while True:
            all_transactions = await transaction_manager.get_all_ids()
            transactions = await coin_api.get_transactions()
            transactions.extend(await coin_api.get_transactions(False))
            transactions = [transaction for transaction in transactions
                            if transaction.from_id != int(os.environ.get('MERCHANT_ID'))
                            and transaction.payload == int(os.environ.get('PAYLOAD'))]

            for transaction in transactions:
                if transaction.id not in all_transactions:
                    await transaction_manager.save_transaction(transaction)

                    session = await sessions.get_or_create(transaction.from_id)
                    await session.score.add(transaction.amount)

                    await api.messages.send(
                        user_id=transaction.from_id,
                        message=Message.Credited.format(transaction.amount / 1000)
                    )

            await asyncio.sleep(2)

    await asyncio.gather(
        update_manager.start(),
        coin_api.do_transfers(),
        get_trans()
    )

if __name__ == '__main__':
    asyncio.run(main())
