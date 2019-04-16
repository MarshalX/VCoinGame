import aiohttp

from aiohttp import hdrs
from multidict import CIMultiDict
from multidict import CIMultiDictProxy


class CustomClientResponse(aiohttp.ClientResponse):
    # you have to use this class in response_class parameter of any aiohttp.ClientSession instance
    # example: aiohttp.ClientSession(response_class=CustomClientResponse)
    # read more: https://github.com/Fahreeve/aiovk/issues/3

    async def start(self, connection, read_until_eof=False):
        # vk.com return url like this: http://REDIRECT_URI#access_token=...
        # but aiohttp by default removes all parameters after '#'
        await super().start(connection)
        headers = CIMultiDict(self._headers)
        location = headers.get(hdrs.LOCATION, None)
        if location:
            headers[hdrs.LOCATION] = location.replace('#', '?')
        self._headers = CIMultiDictProxy(headers)
        self._raw_headers = tuple(headers.items())
        return self


class BaseDriver:
    def __init__(self, timeout=10, loop=None):
        self.timeout = timeout
        self._loop = loop

    async def json(self, url, params, timeout=None):
        '''
        :param params: dict of query params
        :return: dict from json response
        '''
        raise NotImplementedError

    async def get_text(self, url, params, timeout=None):
        '''
        :param params: dict of query params
        :return: http status code, text body of response
        '''
        raise NotImplementedError

    async def get_bin(self, url, params, timeout=None):
        '''
        :param params: dict of query params
        :return: http status code, binary body of response
        '''
        raise NotImplementedError

    async def post_text(self, url, data, timeout=None):
        '''
        :param data: dict pr string
        :return: redirect url and text body of response
        '''
        raise NotImplementedError

    async def close(self):
        raise NotImplementedError


class HttpDriver(BaseDriver):
    def __init__(self, timeout=10, loop=None, session=None):
        super().__init__(timeout, loop)
        if not session:
            self.session = aiohttp.ClientSession(
                response_class=CustomClientResponse, loop=loop)
        else:
            self.session = session

    async def json(self, url, params, timeout=None):
        # timeouts - https://docs.aiohttp.org/en/v3.0.0/client_quickstart.html#timeouts
        async with self.session.get(url, params=params, timeout=timeout or self.timeout) as response:
            return await response.json()

    async def get_text(self, url, params, timeout=None):
        async with self.session.get(url, params=params, timeout=timeout or self.timeout) as response:
            return response.status, await response.text()

    async def get_bin(self, url, params, timeout=None):
        async with self.session.get(url, params=params, timeout=timeout or self.timeout) as response:
            return await response.read()

    async def post_text(self, url, data, timeout=None):
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            return response.url, await response.text()

    async def close(self):
        await self.session.close()
