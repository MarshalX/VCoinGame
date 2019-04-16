import os
import asyncio

from vk_api.api import API
from vk_api.sessions import TokenSession
from vk_api.longpull import BotsLongPoll
from vk_api.updates import UpdateManager
from vk_api.handlers import MessageHandler

from vcoingame.coin_api import CoinAPI


async def ping(manager, update):
    from_id = update.object.from_id
    await manager.api.messages.send(user_id=from_id, message='pong')


if __name__ == '__main__':
    session = TokenSession(os.environ.get('GROUP_TOKEN'))
    api = API(session)
    lp = BotsLongPoll(api, mode=2, group_id=os.environ.get('GROUP_ID'))

    update_manager = UpdateManager(lp)
    update_manager.register_handler(MessageHandler(ping, 'ping'))

    coin_api = CoinAPI(os.environ.get('MERCHANT_ID'), os.environ.get('KEY'), os.environ.get('PAYLOAD'))
    coin_api.send(159179937, 1000)

    async def get_trans():
        while True:
            print(await coin_api.get_transactions())

    loop = asyncio.get_event_loop()
    task = loop.create_task(update_manager.start())
    task2 = loop.create_task(coin_api.do_transfers())
    task3 = loop.create_task(get_trans())

    loop.run_until_complete(task)
    loop.run_until_complete(task3)
    loop.run_until_complete(task2)
