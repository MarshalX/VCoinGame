import logging

from vk_api.keyboard import Keyboard, ButtonColor

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
        self.max_bet = 0
        self.donation_amount = 0
        self.bet_keyboard = None
        self.statistics = self.score = self.top = None
        self._fields = {}

    async def initial(self):
        self.score, new_user = await Score.get_or_create(self.database, self.user_id)
        self.state = await self.get_state()
        self.bet = await self.get_bet()
        self.max_bet = await self.get_max_bet()
        self.donation_amount = await self.get_donation_amount()
        self.statistics = Statistics(self.database, self.user_id)
        self.bet_keyboard = await self.generate_bet_keyboard(self.max_bet)

        self.top = Top(self.database, self.user_id)
        if new_user:
            self.top.create()

        return self

    @staticmethod
    async def create(database, user_id):
        return await Session(database, user_id).initial()

    @staticmethod
    async def generate_bet_keyboard(max_bet: int):
        count = 8
        start = 0
        stop = int(max_bet / 1000)

        bets = [round(int(stop + x * (start - stop) / (count - 1)), -3) for x in range(count)]
        bets.reverse()

        bet_keyboard = Keyboard()
        bet_keyboard.add_button('Повысить максимальную ставку', color=ButtonColor.POSITIVE)
        bet_keyboard.add_line()

        for i, bet in enumerate(bets):
            button_number = i + 1
            if not button_number % 5:
                bet_keyboard.add_line()
            if button_number == count:
                bet_keyboard.add_button(stop, color=ButtonColor.NEGATIVE)
                continue

            color = ButtonColor.POSITIVE if button_number == 1 else ButtonColor.DEFAULT
            bet_keyboard.add_button(bet, color=color)

        bet_keyboard.add_line()
        bet_keyboard.add_button('Назад', color=ButtonColor.PRIMARY)

        return bet_keyboard

    async def get_donation_amount(self):
        logger.info(f'Get {self.user_id}`s donation amount')
        self.donation_amount = await self.database.fetchval(
            '''SELECT
                    sum(coins)
               FROM used_codes
               WHERE user_id = ($1::int)''', self.user_id)
        return self.donation_amount

    async def get_max_bet(self):
        logger.info(f'Get {self.user_id}`s max bet')
        self.max_bet = await self.database.fetchval(
            '''SELECT max_bet FROM user_scores WHERE user_id = ($1::int)''', self.user_id)
        return self.max_bet

    async def get_bet(self):
        logger.info(f'Get {self.user_id}`s current bet')
        self.bet = await self.database.fetchval(
            '''SELECT current_bet FROM user_scores WHERE user_id = ($1::int)''', self.user_id)
        return self.bet

    async def add_to_max_bet(self, max_bet):
        logger.info(f'Set max bet for {self.user_id}')
        await self.database.fetchval(
            '''UPDATE user_scores SET max_bet = max_bet + ($1::bigint) WHERE user_id = ($2::int)''', max_bet, self.user_id)
        self.max_bet += max_bet
        self.bet_keyboard = await self.generate_bet_keyboard(self.max_bet)

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
