from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.http_client import HttpClient


class SlackError(Exception):
    """Raised when a request to the Slack API fails."""


class SlackErrorAuthenticate(Exception):
    """Raised when the Slack authentication token is invalid."""


class SlackAPI:
    """
    Wrapper around the Slack Web API used by the monitoring system.

    Responsibilities:
        - Authenticate the Slack bot.
        - Resolve user IDs from email addresses.
        - Send messages and images to Slack channels.

    The class uses two clients internally:

        • HttpClient
            Used for simple REST calls such as authentication checks.

        • AsyncWebClient (slack_sdk)
            Used for higher-level Slack operations such as posting messages
            and uploading files.

    This class raises custom exceptions when authentication or API requests fail.
    """

    URL_BASE = 'https://slack.com/api'

    async def login(self, token: str) -> None:
        """
        Authenticate the Slack bot using the provided token.

        This method validates the token using the Slack `auth.test` endpoint
        and initializes the internal AsyncWebClient instance.

        Raises
        ------
        SlackErrorAuthenticate
            If the token is invalid.
        """

        self.__token = token
        self.__http  = HttpClient()
        self.__http.set_header("Authorization", f"Bearer {self.__token}")
        await self._validate()
        self.__client = AsyncWebClient(token=token)

    async def _validate(self) -> None:
        """
        Validate the Slack token by calling the `auth.test` endpoint.

        Raises
        ------
        SlackErrorAuthenticate
            If Slack reports the token as invalid.
        """
        response = await self._request(method='GET', endpoint='/auth.test')
        if not response.get('ok', False):
            raise SlackErrorAuthenticate('Error al autenticar: Token inválido')

    async def _request(self, method: str = 'GET', endpoint: str = None, **parameters):
        """
        Perform a low-level request to the Slack Web API.

        Args:
            method:
                HTTP method to use (GET or POST).

            endpoint:
                Slack API endpoint path (e.g. "/auth.test").

            **parameters:
                Query parameters sent with the request.

        Returns
        -------
        dict
            JSON response returned by the Slack API.

        Raises
        ------
        SlackError
            If the request fails or Slack returns an error response.
        """

        url = f'{self.URL_BASE}{endpoint}'

        if method == 'POST':
            result = await self.__http.post(url, params=parameters)
        else:
            result = await self.__http.get(url, params=parameters)

        if not result["success"]:
            status = result["status_code"]
            if status in (401, 403, 404):
                raise SlackError('No se pudo realizar la petición a Slack')
            raise SlackError(f'Error en petición a Slack: {result.get("error")}')

        return result["data"]

    async def get_id_by_email(self, email: str = None) -> str | None:
        """
        Retrieve the Slack user ID associated with an email address.

        Args:
            email:
                Email address registered in the Slack workspace.

        Returns
        -------
        str | None
            Slack user ID if found, otherwise None.
        """
        response = await self._request(
            method='GET',
            endpoint='/users.lookupByEmail',
            email=email,
        )
        return response.get('user')['id'] if response.get('ok', False) else None

    async def get_list_users(self):
        """Placeholder for retrieving the list of users in the Slack workspace."""
        pass

    async def send_image(self, file, channel: str, tittle: str, comment: str) -> None:
        """
        Send an image to a Slack channel (typically used for charts).

        Args:
            file:
                Image bytes or file-like object to upload.

            channel:
                Slack channel ID or name.

            tittle:
                Title displayed above the uploaded file.

            comment:
                Initial comment accompanying the uploaded file.

        Raises
        ------
        SlackApiError
            If the bot lacks required permissions (e.g. files:write)
            or if the upload fails.
        """

        await self.__client.files_upload_v2(
            channels=channel,
            title=tittle,
            initial_comment=comment,
            file=file,
        )

    async def send_message(self, channel_name: str, message: str) -> None:
        """
        Send a text message to a Slack channel.

        Args:
            channel_name:
                Slack channel ID or name.

            message:
                Text message formatted in Slack mrkdwn.

        Raises
        ------
        SlackApiError
            If Slack rejects the message request.
        """
        try:
            await self.__client.chat_postMessage(channel=channel_name, text=message)
        except SlackApiError as e:
            raise SlackApiError(f"Error al enviar mensaje: {e.response['error']}", e.response)