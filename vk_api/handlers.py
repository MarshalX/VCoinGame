import re

from vk_api.updates import UpdateType


class MessageHandler:
    TYPES = [UpdateType.MESSAGE_NEW]

    def __init__(self, target, pattern, regex=False, final=True, **kwargs):
        self.target = target
        self.regex = regex
        self.final = final
        self.pattern = pattern
        self.kwargs = kwargs

    def check(self, message):
        if self.regex:
            result = re.findall(self.pattern, message.text)
            return True if len(result) else False
        else:
            return self.pattern in message.text

    async def start(self, manager, update):
        await self.target(manager, update, **self.kwargs)
