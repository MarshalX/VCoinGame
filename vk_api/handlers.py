import re
import logging

from abc import ABC, abstractmethod

from vk_api.updates import UpdateType, Update

from vcoingame.handler_context import HandlerContext
from vcoingame.states import State


logger = logging.getLogger('vcoingame.handlers')


class GroupHandler(ABC):
    final = False

    @staticmethod
    async def check(object):
        return True

    @abstractmethod
    async def start(self, update: Update):
        raise NotImplementedError


class GroupJoinHandler(GroupHandler):
    TYPES = [UpdateType.GROUP_JOIN]

    async def start(self, update: Update):
        user_id = update.object.get('user_id')
        if user_id not in HandlerContext.group_members:
            HandlerContext.group_members.append(user_id)
            logger.info(f'{user_id} join to group')


class GroupLeaveHandler(GroupHandler):
    TYPES = [UpdateType.GROUP_LEAVE]

    async def start(self, update: Update):
        user_id = update.object.get('user_id')
        if user_id in HandlerContext.group_members:
            del HandlerContext.group_members[HandlerContext.group_members.index(user_id)]
            logger.info(f'{user_id} leave from group')


class MessageHandler:
    TYPES = [UpdateType.MESSAGE_NEW]

    def __init__(self, target, pattern, state: State or list = State.ALL,
                 reset_state=True, regex=False, final=True, equal=True):
        self.target = target
        self.regex = regex
        self.regex_result = None
        self.final = final
        self.pattern = pattern
        self.equal = equal
        self.state = state if isinstance(state, list) else [state]
        self.reset_state = reset_state

    async def check(self, message):
        session = await HandlerContext.sessions.get_or_create(message.from_id)
        if State.ALL not in self.state and session.state not in self.state:
            return False

        if self.regex:
            self.regex_result = re.findall(self.pattern, message.text)
            return len(self.regex_result) > 0
        elif self.equal:
            return self.pattern == message.text
        else:
            return self.pattern in message.text

    async def start(self, update: Update):
        message = update.object
        session = await HandlerContext.sessions.get_or_create(message.from_id) # Too bad it's here

        session['update'] = update
        session['regex_result'] = self.regex_result
        session['message'] = message

        if self.reset_state:
            await session.reset_state()

        await self.target(session)

    def __str__(self):
        return f'[MessageHandler] Pattern: {self.pattern}; State: {self.state}'
