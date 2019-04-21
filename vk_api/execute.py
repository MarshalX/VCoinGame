import six
import json
import asyncio


class Pool:
    __slots__ = ('api', 'execute', '_pool')

    def __init__(self, api):
        self.api = api
        self.execute = self.api.execute._method_name
        self._pool = []

    async def compile(self):
        methods = self._pool[0:25]
        methods = ','.join(methods)

        del self._pool[0:25]

        return f'return [{methods}];'

    def append(self, request):
        self._pool.append(request)

    async def start(self):
        while True:
            if len(self._pool) > 0:
                await self.api._session.send_api_request(self.execute, {'code': await self.compile()})
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
