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


async def main():
    session = TokenSession(os.environ.get('GROUP_TOKEN'))
    api = API(session)
    lp = BotsLongPoll(api, mode=2, group_id=os.environ.get('GROUP_ID'))

    update_manager = UpdateManager(lp)
    update_manager.register_handler(MessageHandler(ping, 'ping'))

    coin_api = CoinAPI(os.environ.get('MERCHANT_ID'), os.environ.get('KEY'), os.environ.get('PAYLOAD'))
    coin_api.send(159179937, 1000)

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
