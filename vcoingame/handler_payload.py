class HandlerPayload:
    def __init__(self, sessions, coin_api, keyboards):
        self.manager = self.update = self.api = None
        self.from_id = self.text = self.regex_result = self.session = self.keyboard = None

        self.sessions = sessions
        self.coin_api = coin_api
        self.keyboards = keyboards
