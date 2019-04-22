from vk_api.execute import Pool
from vk_api.updates import UpdateManager

from vcoingame.coin_api import CoinAPI
from vcoingame.session import SessionList


class HandlerContext:
    group_members = pool = api = update_manager = sessions = coin_api = keyboards = None

    @staticmethod
    def initial(group_members: list, pool: Pool, update_manager: UpdateManager, sessions: SessionList,
                coin_api: CoinAPI, keyboards: dict):
        HandlerContext.group_members = group_members
        HandlerContext.pool = pool
        HandlerContext.update_manager = update_manager
        HandlerContext.api = update_manager.api
        HandlerContext.sessions = sessions
        HandlerContext.coin_api = coin_api
        HandlerContext.keyboards = keyboards
