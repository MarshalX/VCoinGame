import logging

from abc import ABC, abstractmethod

from vk_api.exceptions import VkCaptchaNeeded, VkAPIError, VkAuthError, CAPTCHA_IS_NEEDED, AUTHORIZATION_FAILED
from vk_api.drivers import HttpDriver

logger = logging.getLogger('vk_api.sessions')


class BaseSession(ABC):
    """Interface for all types of sessions"""

    @abstractmethod
    async def __aenter__(self):
        """Make avaliable usage of "async with" context manager"""

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes session after usage of context manager with Session"""
        await self.close()

    async def close(self) -> None:
        """Perform the actions associated with the completion of the current session"""

    @abstractmethod
    async def send_api_request(self, method_name: str, params: dict = None, timeout: int = None) -> dict:
        """Method that use API instance for sending request to vk server

        :param method_name: any value from the left column of the methods table from `https://vk.com/dev/methods`
        :param params: dict of params that available for current method.
                       For example see `Parameters` block from: `https://vk.com/dev/account.getInfo`
        :param timeout: timeout for response from the server
        :return: dict that contain data from `Result` block. Example see here: `https://vk.com/dev/account.getInfo`
        """


class TokenSession(BaseSession):
    """Implements simple session that uses existed token for work"""

    API_VERSION = '5.74'
    REQUEST_URL = 'https://api.vk.com/method/'

    def __init__(self, access_token: str = None, timeout: int = 10, driver=None):
        """
        :param access_token: see `User Token` block from `https://vk.com/dev/access_token`
        :param timeout: default time out for any request in current session
        :param driver: TODO add description
        """
        self.timeout = timeout
        self.access_token = access_token
        self.driver = driver if driver else HttpDriver(timeout)

    async def __aenter__(self) -> BaseSession:
        """Make available usage of `async with` context manager"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.driver.close()

    async def send_api_request(self, method_name: str, params: dict = None, timeout: int = None) -> dict:
        timeout = self.timeout if not timeout else timeout
        params = {} if not params else params

        if self.access_token:
            params['access_token'] = self.access_token
        params['v'] = self.API_VERSION

        response = await self.driver.json(self.REQUEST_URL + method_name, params, timeout)

        error = response.get('error')
        if error:
            err_code = error.get('error_code')
            logger.error(f'{error}; err_code: {err_code}')
            if err_code == CAPTCHA_IS_NEEDED:
                captcha_sid = error.get('captcha_sid')
                captcha_url = error.get('captcha_img')

                params['captcha_key'] = await self.enter_captcha(captcha_url, captcha_sid)
                params['captcha_sid'] = captcha_sid

                return await self.send_api_request(method_name, params, timeout)
            elif err_code == AUTHORIZATION_FAILED:
                await self.authorize()

                return await self.send_api_request(method_name, params, timeout)
            else:
                raise VkAPIError(error, self.REQUEST_URL + method_name)

        return response['response']

    async def authorize(self) -> None:
        """Getting a new token from server"""
        raise VkAuthError('invalid_token', 'User authorization failed')

    async def enter_captcha(self, url: str, sid: str) -> str:
        """
        Override this method for processing captcha.

        :param url: link to captcha image
        :param sid: captcha id. I do not know why pass here but may be useful
        :return captcha value
        """
        raise VkCaptchaNeeded(url, sid)
