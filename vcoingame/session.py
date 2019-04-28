import logging

from vcoingame.top import Top
from vcoingame.score import Score
from vcoingame.states import State
from vcoingame.statistics import Statistics

logger = logging.getLogger('vcoingame.session')


class Session:
    def __init__(self, database, user_id, state=State.MENU):
        self.user_id = user_id
        self.database = database
        self.state = state
        self.bet = 0
        self.statistics = self.score = self.top = None
        self._fields = {}

    async def initial(self):
        self.score, new_user = await Score.get_or_create(self.database, self.user_id)
        self.state = await self.get_state()
        self.bet = await self.get_bet()
        self.statistics = Statistics(self.database, self.user_id)

        self.top = Top(self.database, self.user_id)
        if new_user:
            self.top.create()

        return self

    @staticmethod
    async def create(database, user_id):
        return await Session(database, user_id).initial()

    async def get_bet(self):
        logger.info(f'Get {self.user_id}`s current bet')
        self.bet = await self.database.fetchval(
            '''SELECT current_bet FROM user_scores WHERE user_id = ($1::int)''', self.user_id)
        return self.bet

    async def set_bet(self, bet):
        logger.info(f'Set current bet for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET current_bet = ($1::bigint) WHERE user_id = ($2::int)''', bet, self.user_id)
        self.bet = bet

    async def get_state(self):
        logger.info(f'Get {self.user_id}`s state')
        self.state = State(await self.database.fetchval(
            '''SELECT state FROM user_scores WHERE user_id = ($1::int)''', self.user_id))
        return self.state

    async def set_state(self, state: State):
        logger.info(f'Set state for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET state = ($1::smallint) WHERE user_id = ($2::int)''', state.value, self.user_id)
        self.state = state

    async def reset_state(self):
        await self.set_state(State.ALL)

    def __getitem__(self, item):
        return self._fields.get(item)

    def __setitem__(self, key, value):
        self._fields.update({key: value})

    def __delitem__(self, key):
        del self._fields[key]


class SessionList:
    def __init__(self, database):
        self.database = database
        self._sessions = {}

    def append(self, user_id: int, item: Session):
        self._sessions.update({user_id: item})
        logger.info(f'Appended session for {user_id}. Len: {len(self)}')

    def __len__(self):
        return len(self._sessions)

    async def get_or_create(self, user_id: int) -> Session:
        session = self._sessions.get(user_id)
        if session:
            return session

        session = await Session.create(self.database, user_id)
        self.append(user_id, session)

        return session
