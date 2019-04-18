import os
import asyncio

from vk_api.api import API
from vk_api.keyboard import Keyboard, ButtonColor
from vk_api.sessions import TokenSession
from vk_api.longpull import BotsLongPoll
from vk_api.updates import UpdateManager
from vk_api.handlers import MessageHandler

from vcoingame.score import Database
from vcoingame.coin_api import CoinAPI
from vcoingame.session import SessionList
from vcoingame.messages import Message
from vcoingame.score import Score


async def help_handler(manager, update, **kwargs):
    user_id = update.object.from_id
    keyboard = kwargs.get('keyboard')
    await manager.api.messages.send(user_id=user_id, message=Message.Commands, keyboard=keyboard.get_keyboard())


async def balance_handler(manager, update, **kwargs):
    user_id = update.object.from_id
    sessions = kwargs.get('sessions')
    keyboard = kwargs.get('keyboard')
    session = await sessions.get_or_create(user_id)

    await manager.api.messages.send(
        user_id=user_id, message=Message.Score.format(session.score), keyboard=keyboard.get_keyboard())


async def withdraw_handler_1(manager, update, **kwargs):
    user_id = update.object.from_id
    sessions = kwargs.get('sessions')
    keyboard = kwargs.get('keyboard')
    session = await sessions.get_or_create(user_id)

    session['withdraw'] = True

    await manager.api.messages.send(
        user_id=user_id, message=Message.Withdraw, keyboard=keyboard.get_keyboard())


async def withdraw_handler_2(manager, update, **kwargs):
    user_id = update.object.from_id
    sessions = kwargs.get('sessions')
    keyboard = kwargs.get('keyboard')
    amount = Score.parse_score(update.object.text)
    session = await sessions.get_or_create(user_id)

    if not session['withdraw']:
        return await help_handler(manager, update, **kwargs)
    del session['withdraw']

    # send coins

    await manager.api.messages.send(
        user_id=user_id, message=Message.Send.format(amount / 1000), keyboard=keyboard.get_keyboard())


async def main():
    session = TokenSession(os.environ.get('GROUP_TOKEN'))
    api = API(session)
    lp = BotsLongPoll(api, mode=2, group_id=os.environ.get('GROUP_ID'))
    database = await Database.create()
    sessions = SessionList(database)

    main_keyboard = Keyboard()
    main_keyboard.add_button('Подкинуть монетку', color=ButtonColor.POSITIVE)
    main_keyboard.add_line()
    main_keyboard.add_button('Пополнить')
    main_keyboard.add_button('Баланс')
    main_keyboard.add_button('Вывести')

    update_manager = UpdateManager(lp)
    update_manager.register_handler(MessageHandler(
        withdraw_handler_1, 'Вывести', sessions=sessions, keyboard=main_keyboard))
    update_manager.register_handler(MessageHandler(
        withdraw_handler_2, r'\d*[.,]?\d+', regex=True, sessions=sessions, keyboard=main_keyboard))
    update_manager.register_handler(MessageHandler(
        balance_handler, 'Баланс', sessions=sessions, keyboard=main_keyboard))
    update_manager.register_handler(MessageHandler(
        help_handler, '', sessions=sessions, keyboard=main_keyboard))

    coin_api = CoinAPI(os.environ.get('MERCHANT_ID'), os.environ.get('KEY'), os.environ.get('PAYLOAD'))

    async def get_trans():
        while True:
            transactions = await coin_api.get_transactions()
            for item in transactions:
                print(item)
            await asyncio.sleep(2)

    await asyncio.gather(
        update_manager.start(),
        coin_api.do_transfers(),
        get_trans()
    )

if __name__ == '__main__':
    asyncio.run(main())
