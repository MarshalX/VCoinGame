import aiohttp
import logging

logger = logging.getLogger('vk_api.drivers')


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
            self.session = aiohttp.ClientSession(loop=loop)
        else:
            self.session = session

    async def json(self, url, data, timeout=None):
        logger.debug(f'URL: {url}; Data: {data}; Timeout: {timeout}')
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            logger.debug(f'Response: {await response.text()}')
            return await response.json()

    async def get_text(self, url, data, timeout=None):
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            return response.status, await response.text()

    async def get_bin(self, url, data, timeout=None):
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            return await response.read()

    async def post_text(self, url, data, timeout=None):
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            return response.url, await response.text()

    async def close(self):
        await self.session.close()
