import logging

from enum import Enum

from vk_api.messages import Message

logger = logging.getLogger('vk_api.updates')


class UpdateType(Enum):
    MESSAGE_NEW = 'message_new'
    MESSAGE_REPLY = 'message_reply'
    MESSAGE_ALLOW = 'message_allow'
    MESSAGE_EDIT = 'message_edit'
    MESSAGE_DENY = 'message_deny'


class Update:
    def __init__(self, update):
        self.type = UpdateType(update.get('type'))

        if self.type is UpdateType.MESSAGE_NEW:
            self.object = Message.to_python(update.get('object'))

    @staticmethod
    def process_updates(response):
        return [Update(obj) for obj in response.get('updates')]

    def __str__(self):
        return f'[Update] Type: {self.type}; Object: {self.object}'


class UpdateManager:
    def __init__(self, longpull):
        self.longpull = longpull
        self.api = self.longpull.api
        self._handlers = []

    async def start(self):
        while True:
            updates = await self.longpull.wait()
            for update in updates:
                for handler in self._handlers:
                    if update.type in handler.TYPES and await handler.check(update.object):
                        logger.info(f'[HandlerCall] ({handler}) for ({update})')
                        await handler.start(update)
                        if handler.final:
                            break

    def register_handler(self, handler):
        self._handlers.append(handler)

