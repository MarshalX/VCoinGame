import os
import asyncio
import logging

from vk_api.api import API
from vk_api.execute import Pool
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
from vcoingame.session import SessionList, Session
from vcoingame.handler_payload import HandlerContext
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


async def help_handler(session: Session):
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=Message.Commands.format(Game.INITIAL_RATE / 1000),
        keyboard=session['keyboard'].get_keyboard()))


async def balance_handler(session: Session):
    game = session.game
    score = session.score

    if game.is_started:
        msg = Message.ScoreReward.format(score, game.cur_reward / 1000)
    else:
        msg = Message.Score.format(score)

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=msg,
        keyboard=session['keyboard'].get_keyboard()))


async def withdraw_handler_1(session: Session):
    session.state = State.WITHDRAW

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id, message=Message.Withdraw, keyboard=session['keyboard'].get_keyboard()))


async def withdraw_handler_2(session: Session):
    amount = Score.parse_score(session['message'].text)
    if amount > session.score.score:
        HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id, message=Message.Bum))
        return

    await session.score.sub(amount)
    await HandlerContext.coin_api.send(session.user_id, amount)

    msg = Message.Send.format(amount / 1000)
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id, message=msg, keyboard=session['keyboard'].get_keyboard()))


async def deposit_handler(session: Session):
    msg = Message.Deposit.format(HandlerContext.coin_api.create_transaction_url(0, fixed=False))
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id, message=msg, keyboard=session['keyboard'].get_keyboard()))


async def toss(session: Session):
    game = session.game
    user_score = session.score.score

    if game.bet > user_score:
        if game.is_started:
            msg = Message.Reward.format((game.bet - user_score) / 1000)
            keyboard = HandlerContext.keyboards.get('game')
        else:
            msg = Message.BumLeft.format((game.bet - user_score) / 1000)
            keyboard = HandlerContext.keyboards.get('main')

        HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id, message=msg, keyboard=keyboard.get_keyboard()))

        return

    await session.score.sub(game.bet)

    if game.get_random():
        session.state = State.GAME

        await game.next_round()
        HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id,
            message=Message.Win.format(game.cur_reward / 1000, game.bet / 1000),
            keyboard=HandlerContext.keyboards.get('game').get_keyboard(),
            attachment=os.environ.get('WIN_IMG')
        ))
    else:
        session.reset_state()

        await game.set_round(-1)
        HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id,
            message=Message.Lose,
            keyboard=HandlerContext.keyboards.get('main').get_keyboard(),
            attachment=os.environ.get('LOSE_IMG')
        ))


async def get_reward_handler(session: Session):
    game = session.game

    if not game.is_started:
        HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id,
            message=Message.NoWin,
            keyboard=HandlerContext.keyboards.get('main').get_keyboard(),
        ))
        return

    await session.score.add(game.cur_reward)

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=Message.PickUp.format(game.cur_reward / 1000),
        keyboard=HandlerContext.keyboards.get('main').get_keyboard(),
    ))

    await game.set_round(-1)


async def main():
    token_session = TokenSession(os.environ.get('GROUP_TOKEN'))
    api = API(token_session)
    pool = Pool(api)
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

    update_manager = UpdateManager(longpull)

    HandlerContext.initial(pool, update_manager, sessions, coin_api, keyboards)

    update_manager.register_handler(MessageHandler(
        toss, 'Подкинуть монетку'))
    update_manager.register_handler(MessageHandler(
        get_reward_handler, 'Забрать приз'))
    update_manager.register_handler(MessageHandler(
        deposit_handler, 'Пополнить'))
    update_manager.register_handler(MessageHandler(
        withdraw_handler_1, 'Вывести', reset_state=False))
    update_manager.register_handler(MessageHandler(
        withdraw_handler_2, r'\d*[.,]?\d+', State.WITHDRAW, regex=True))
    update_manager.register_handler(MessageHandler(
        balance_handler, 'Баланс'))
    update_manager.register_handler(MessageHandler(
        help_handler, ''))

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

                    pool.append(api.messages.send.code(
                        user_id=transaction.from_id,
                        message=Message.Credited.format(transaction.amount / 1000)
                    ))

            await asyncio.sleep(2)

    await asyncio.gather(
        pool.start(),
        update_manager.start(),
        coin_api.do_transfers(),
        get_trans()
    )

if __name__ == '__main__':
    asyncio.run(main())
