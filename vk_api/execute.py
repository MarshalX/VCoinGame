import six
import json
import asyncio
import logging

logger = logging.getLogger('vk_api.execute')


class Pool:
    __slots__ = ('api', 'execute', '_pool')

    def __init__(self, api):
        self.api = api
        self.execute = self.api.execute._method_name
        self._pool = asyncio.Queue()

    async def compile(self):
        methods = []
        for _ in range(0, 25):
            if self._pool.empty():
                break

            methods.append(self._pool.get_nowait())

        logger.info(f'Pool queue size: {self._pool.qsize()}; Current methods in request: {len(methods)}')
        methods = ','.join(methods)
        return f'return [{methods}];'

    def append(self, request):
        self._pool.put_nowait(request)

    async def start(self):
        while True:
            if not self._pool.empty():
                asyncio.get_event_loop().create_task(
                    self.api._session.send_api_request(self.execute, {'code': await self.compile()}))
            await asyncio.sleep(0.55)


class Function:
    __slots__ = 'method'

    def __init__(self, method):
        self.method = method

    def __call__(self, **method_args):
        compiled_args = {}

        for key, value in six.iteritems(method_args):
            if key in method_args:
                compiled_args[key] = str(value)
            else:
                compiled_args[key] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))

        return f'API.{self.method._method_name}({json.dumps(compiled_args, ensure_ascii=False)})'
