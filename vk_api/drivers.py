import aiohttp
import logging

from abc import ABC, abstractmethod

logger = logging.getLogger('vk_api.drivers')


def log_request(url, data, timeout):
    data = str(data).encode("utf-8")
    logger.debug(f'URL: {url}; Data: {data}; Timeout: {timeout}')


class BaseDriver(ABC):
    def __init__(self, timeout=10, loop=None):
        self.timeout = timeout
        self._loop = loop

    @abstractmethod
    async def json(self, url, params, timeout=None):
        """
        :param url: url to request
        :param params: dict of query params
        :param timeout: timeout
        :return: dict from json response
        """
        raise NotImplementedError

    @abstractmethod
    async def get_text(self, url, params, timeout=None):
        """
        :param url: url to request
        :param params: dict of query params
        :param timeout: timeout
        :return: http status code, text body of response
        """
        raise NotImplementedError

    @abstractmethod
    async def get_bin(self, url, params, timeout=None):
        """
        :param url: url to request
        :param params: dict of query params
        :param timeout: timeout
        :return: http status code, binary body of response
        """
        raise NotImplementedError

    @abstractmethod
    async def post_text(self, url, data, timeout=None):
        """
        :param url: url to request
        :param data: dict pr string
        :param timeout: timeout
        :return: redirect url and text body of response
        """
        raise NotImplementedError

    @abstractmethod
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
        log_request(url, data, timeout)
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            return await response.json()

    async def post_text(self, url, data, timeout=None):
        log_request(url, data, timeout)
        async with self.session.post(url, data=data, timeout=timeout or self.timeout) as response:
            return response.status, await response.text()

    async def get_bin(self, url, params, timeout=None):
        log_request(url, params, timeout)
        async with self.session.get(url, params=params, timeout=timeout or self.timeout) as response:
            return await response.read()

    async def get_text(self, url, params, timeout=None):
        log_request(url, params, timeout)
        async with self.session.get(url, params=params, timeout=timeout or self.timeout) as response:
            return response.status, await response.text()

    async def close(self):
        await self.session.close()
