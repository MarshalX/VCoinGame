from vk_api.updates import UpdateManager

from vcoingame.coin_api import CoinAPI
from vcoingame.session import SessionList


class HandlerContext:
    api = update_manager = sessions = coin_api = keyboards = None

    @staticmethod
    def initial(update_manager: UpdateManager, sessions: SessionList, coin_api: CoinAPI, keyboards: dict):
        HandlerContext.update_manager = update_manager
        HandlerContext.api = update_manager.api
        HandlerContext.sessions = sessions
        HandlerContext.coin_api = coin_api
        HandlerContext.keyboards = keyboards
