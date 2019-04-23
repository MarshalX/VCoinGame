import asyncio
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

    GROUP_JOIN = 'group_join'
    GROUP_LEAVE = 'group_leave'


class Update:
    def __init__(self, update=None, type: UpdateType = None, object=None):
        if update:
            self.type = UpdateType(update.get('type'))

            if self.type is UpdateType.MESSAGE_NEW:
                self.object = Message.to_python(update.get('object'))
            elif self.type in [UpdateType.GROUP_LEAVE, UpdateType.GROUP_JOIN]:
                self.object = update.get('object')
        else:
            self.type = type
            self.object = object

    @staticmethod
    async def process_updates(response):
        return [Update(obj) for obj in response.get('updates')]

    def __str__(self):
        return f'[Update] Type: {self.type}; Object: {self.object}'


class UpdateManager:
    def __init__(self, longpoll):
        self.longpoll = longpoll
        self.api = self.longpoll.api
        self._handlers = []

    async def process_unread_conversation(self):
        updates = []

        offset = 0
        while True:
            response = await self.api.messages.getConversations(filter='unanswered', offset=offset, count=200)

            for conversation in response.get('items'):
                updates.append(Update(type=UpdateType.MESSAGE_NEW, object=Message.to_python(conversation.get('last_message'))))

            if response.get('count') <= offset + 200:
                break
            else:
                offset += 200

        await self._process_updates(updates)

    async def _process_updates(self, updates):
        for update in updates:
            for handler in self._handlers:
                if update.type in handler.TYPES and await handler.check(update.object):
                    logger.debug(f'[HandlerCall] ({handler}) for ({update})')
                    await handler.start(update)
                    if handler.final:
                        break

    async def start(self):
        while True:
            updates = await self.longpoll.wait()
            await self._process_updates(updates)

    def register_handler(self, handler):
        self._handlers.append(handler)

