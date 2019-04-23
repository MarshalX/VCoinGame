import os
import random
import asyncio
import logging
import aiohttp

from vk_api.api import API
from vk_api.drivers import HttpDriver
from vk_api.execute import Pool
from vk_api.sessions import TokenSession
from vk_api.longpoll import BotsLongPoll
from vk_api.updates import UpdateManager
from vk_api.keyboard import Keyboard, ButtonColor
from vk_api.handlers import MessageHandler, GroupJoinHandler, GroupLeaveHandler

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


async def not_group_member_handler(session: Session):
    if session.user_id not in HandlerContext.group_members:
        HandlerContext.pool.append(
            HandlerContext.api.messages.send.code(user_id=session.user_id, message=Message.NotGroupMember))


async def help_handler(session: Session):
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=Message.Commands,
        keyboard=HandlerContext.keyboards.get('main').get_keyboard()))


async def balance_handler(session: Session):
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=Message.Score.format(session.score),
        keyboard=HandlerContext.keyboards.get('main').get_keyboard()))


async def withdraw_handler_1(session: Session):
    await session.set_state(State.WITHDRAW)

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=Message.Withdraw,
        keyboard=HandlerContext.keyboards.get('main').get_keyboard()))


async def withdraw_handler_2(session: Session):
    amount = Score.parse_score(session['message'].text)
    if amount > session.score.score:
        HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id, message=Message.Bum))
        return

    await session.statistics.add_withdraw(amount)

    await session.score.sub(amount)
    await HandlerContext.coin_api.send(session.user_id, amount)

    msg = Message.Send.format(amount / 1000)
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id, message=msg, keyboard=HandlerContext.keyboards.get('main').get_keyboard()))


async def deposit_handler(session: Session):
    msg = Message.Deposit.format(HandlerContext.coin_api.create_transaction_url(0, fixed=False))
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id, message=msg, keyboard=HandlerContext.keyboards.get('main').get_keyboard()))


async def toss_handler_1(session: Session):
    await session.set_state(State.BET)

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id, message=Message.Bet, keyboard=HandlerContext.keyboards.get('bet').get_keyboard()))


async def toss_handler_2(session: Session):
    amount = Score.parse_score(session['message'].text)
    await session.set_bet(amount)
    user_score = session.score.score
    max_bet = int(os.environ.get('MAX_BET'))

    if amount > max_bet:
        await session.set_state(State.BET)

        msg = Message.OverMaxBet.format(max_bet / 1000)
        kbr = 'bet'
    elif amount > user_score:
        await session.set_state(State.ALL)

        msg = Message.BumLeft.format((amount - user_score) / 1000)
        kbr = 'main'
    else:
        await session.set_state(State.GAME)

        await session.statistics.add_bet(amount)

        await session.score.sub(session.bet)

        msg = Message.BetMade.format(amount * 2 / 1000)
        kbr = 'game'

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=msg,
        keyboard=HandlerContext.keyboards.get(kbr).get_keyboard()))


async def im_game_handler(session: Session):
    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
            user_id=session.user_id,
            message=Message.MakeAChoice.format(session.bet * 2 / 1000),
            keyboard=HandlerContext.keyboards.get('game').get_keyboard()))


async def game_handler(session: Session):
    not_user_choice_msg = 'Орёл' if session['message'].text == 'Решка' else 'Решка'
    not_user_choice_img = 'HEADS_IMG' if session['message'].text == 'Решка' else 'TAILS_IMG'
    user_choice_img = 'HEADS_IMG' if session['message'].text == 'Орёл' else 'TAILS_IMG'

    if random.randint(0, 100) < int(os.environ.get('WIN_RATE')):
        msg = Message.Win.format(session.bet * 2 / 1000)
        img = os.environ.get(user_choice_img)

        await session.statistics.add_win()
        await session.statistics.add_prize(session.bet * 2)

        await session.score.add(session.bet * 2)
    else:
        msg = Message.Lose.format(not_user_choice_msg)
        img = os.environ.get(not_user_choice_img)

        await session.statistics.add_lose()

    HandlerContext.pool.append(HandlerContext.api.messages.send.code(
        user_id=session.user_id,
        message=msg,
        keyboard=HandlerContext.keyboards.get('main').get_keyboard(),
        attachment=img
    ))


async def get_members(api):
    members = []

    offset = 0
    while True:
        response = await api.groups.getMembers(group_id=os.environ.get('GROUP_ID'), offset=offset, count=1000)

        members.extend([members for members in response.get('items')])

        if response.get('count') <= offset + 1000:
            break
        else:
            offset += 1000

    return members


async def main():
    token_session = TokenSession(access_token=os.environ.get('GROUP_TOKEN'), timeout=15)
    api = API(token_session)
    pool = Pool(api)
    longpoll = BotsLongPoll(api, mode=2, group_id=os.environ.get('GROUP_ID'))

    coin_api = CoinAPI(os.environ.get('MERCHANT_ID'), os.environ.get('KEY'), os.environ.get('PAYLOAD'))

    database = await Database.create()
    sessions = SessionList(database)

    transaction_manager = TransactionManager(database)

    main_keyboard = Keyboard()
    main_keyboard.add_button('Бросить монету', color=ButtonColor.POSITIVE)
    main_keyboard.add_line()
    main_keyboard.add_button('Пополнить')
    main_keyboard.add_button('Баланс')
    main_keyboard.add_button('Вывести')

    bet_keyboard = Keyboard()
    bet_keyboard.add_button('0', color=ButtonColor.POSITIVE)
    bet_keyboard.add_button('1000')
    bet_keyboard.add_button('5000')
    bet_keyboard.add_button('10000')
    bet_keyboard.add_line()
    bet_keyboard.add_button('15000')
    bet_keyboard.add_button('20000')
    bet_keyboard.add_button('30000')
    bet_keyboard.add_button('65000', color=ButtonColor.NEGATIVE)
    bet_keyboard.add_line()
    bet_keyboard.add_button('Назад', color=ButtonColor.PRIMARY)

    game_keyboard = Keyboard()
    game_keyboard.add_button('Орёл', color=ButtonColor.PRIMARY)
    game_keyboard.add_button('Решка', color=ButtonColor.PRIMARY)

    keyboards = {
        'main': main_keyboard,
        'game': game_keyboard,
        'bet': bet_keyboard
    }

    update_manager = UpdateManager(longpoll)

    HandlerContext.initial(await get_members(api), pool, update_manager, sessions, coin_api, keyboards)

    update_manager.register_handler(GroupJoinHandler())
    update_manager.register_handler(GroupLeaveHandler())

    update_manager.register_handler(MessageHandler(
        not_group_member_handler, '', final=False, reset_state=False))

    update_manager.register_handler(MessageHandler(
        game_handler, 'Орёл', State.GAME))
    update_manager.register_handler(MessageHandler(
        game_handler, 'Решка', State.GAME))
    update_manager.register_handler(MessageHandler(
        im_game_handler, '', State.GAME, reset_state=False, final=True))

    update_manager.register_handler(MessageHandler(
        toss_handler_1, 'Бросить монету', reset_state=False))
    update_manager.register_handler(MessageHandler(
        help_handler, 'Назад', State.BET))
    update_manager.register_handler(MessageHandler(
        toss_handler_2, r'\d*[.,]?\d+', State.BET, regex=True, reset_state=False))

    update_manager.register_handler(MessageHandler(
        withdraw_handler_1, 'Вывести', reset_state=False))
    update_manager.register_handler(MessageHandler(
        withdraw_handler_2, r'\d*[.,]?\d+', State.WITHDRAW, regex=True))

    update_manager.register_handler(MessageHandler(
        deposit_handler, 'Пополнить'))
    update_manager.register_handler(MessageHandler(
        balance_handler, 'Баланс'))

    update_manager.register_handler(MessageHandler(
        help_handler, ''))

    asyncio.create_task(update_manager.process_unread_conversation())

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
                    await session.statistics.add_deposit(transaction.amount)
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
