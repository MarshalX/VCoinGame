from vcoingame.score import Score


class Session:
    def __init__(self, database, user_id):
        self.user_id = user_id
        self.database = database
        self.game = self.score = None
        self._fields = {}

    async def initial(self):
        self.score = await Score.get_or_create(self.database, self.user_id)
        return self

    @staticmethod
    async def create(database, user_id):
        return await Session(database, user_id).initial()

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

    def __len__(self):
        return len(self._sessions)

    async def get_or_create(self, user_id: int) -> Session:
        session = self._sessions.get(user_id)
        if session:
            return session

        session = await Session.create(self.database, user_id)
        self.append(user_id, session)
        return session
