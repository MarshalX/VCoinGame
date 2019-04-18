import re

from vk_api.updates import UpdateType

from vcoingame.handler_payload import HandlerPayload
from vcoingame.states import State


class MessageHandler:
    TYPES = [UpdateType.MESSAGE_NEW]

    def __init__(self, target, pattern, state: State or list,
                 payload: HandlerPayload, reset_state=False, regex=False, final=True):
        self.target = target
        self.regex = regex
        self.regex_result = None
        self.final = final
        self.pattern = pattern
        self.state = state if isinstance(state, list) else [state]
        self.payload = payload
        self.reset_state = reset_state

    async def check(self, message):
        session = await self.payload.sessions.get_or_create(self.payload.from_id)
        if State.ALL not in self.state and session.state not in self.state:
            return False

        if self.regex:
            self.regex_result = re.findall(self.pattern, message.text)
            return True if len(self.regex_result) else False
        else:
            return self.pattern in message.text

    async def start(self, manager, update):
        self.payload.api = manager.api
        self.payload.update = update
        self.payload.regex_result = self.regex_result

        message = update.object
        self.payload.from_id = message.from_id
        self.payload.text = message.text

        self.payload.session = await self.payload.sessions.get_or_create(message.from_id)

        main = self.payload.keyboards.get('main')
        game = self.payload.keyboards.get('game')
        self.payload.keyboard = game if self.payload.session.state == State.GAME else main

        if self.reset_state:
            self.payload.session.reset_state()

        await self.target(self.payload)

    def __str__(self):
        return f'[MessageHandler] Pattern: {self.pattern}'
