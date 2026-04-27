from urllib.parse import urlencode
from app.utils.http_client import HttpClient
import os
from dotenv import load_dotenv

load_dotenv()

URL_BASE = os.getenv("URL_FRESHDESK", None)

class FreshDeskError(Exception):
    """Generic FreshDesk API error."""


class FreshDeskAuthenticateError(Exception):
    """Raised when FreshDesk authentication fails."""


class FreshDeskAPI:
    """
    Wrapper for interacting with the FreshDesk API used by the monitoring system.

    Responsibilities:
        - Authenticate against the FreshDesk API.
        - Retrieve company information.
        - Resolve company IDs from company names.
        - Build direct FreshDesk UI links for ticket searches.

    The class relies on the internal HttpClient utility for performing
    HTTP requests and translates API errors into domain-specific exceptions.
    """

    URL_BASE = f'{URL_BASE}/api/v2'

    async def login(self, username: str, password: str) -> None:
        """
        Authenticate against the FreshDesk API using Basic Authentication.

        Args:
            username:
                FreshDesk API username.

            password:
                FreshDesk API password.

        Raises
        ------
        FreshDeskAuthenticateError
            If authentication with the FreshDesk API fails.
        """
        self.__username = username
        self.__password = password
        self.__http     = HttpClient()
        # FreshDesk usa Basic Auth: el header se construye por httpx vía `auth`,
        # pero HttpClient no expone `auth`. Lo codificamos manualmente en Base64.
        import base64
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.__http.set_header("Authorization", f"Basic {credentials}")
        await self.validate()

    async def validate(self) -> None:
        """
        Validate FreshDesk authentication credentials.

        This method should perform a lightweight request to confirm
        that the provided credentials are valid.
        """
        pass

    async def _request(self, method: str = 'GET', endpoint: str = None, **parameters):
        """
        Perform a request to the FreshDesk API.

        Args:
            method:
                HTTP method used for the request (GET, POST, etc.).

            endpoint:
                FreshDesk API endpoint path.

            **parameters:
                Query parameters included in the request.

        Returns
        -------
        dict | list
            Parsed response returned by the FreshDesk API.

        Raises
        ------
        FreshDeskAuthenticateError
            If authentication fails (401 or 403).

        FreshDeskError
            If the request fails for any other reason.
        """
        url    = f'{self.URL_BASE}{endpoint}'
        result = await self.__http.fetch(
            method=method,
            url=url,
            params=parameters if parameters else None,
        )

        if not result["success"]:
            status = result["status_code"]
            if status in (401, 403):
                raise FreshDeskAuthenticateError(
                    f"Error de autenticación con FreshDesk: {result.get('error')}"
                )
            raise FreshDeskError(
                f"Error en petición FreshDesk [{status}]: {result.get('error')}"
            )

        return result["data"]

    async def get_all_companies(self) -> list:
        """
        Retrieve all companies available in the FreshDesk account.

        Returns
        -------
        list
            List of company objects returned by the FreshDesk API.
        """
        return await self._request(endpoint='/companies')

    async def get_id_by_name_company(self, name: str) -> int | None:
        """
        Retrieve the FreshDesk company ID based on the company name.

        Args:
            name:
                Company name as registered in FreshDesk.

        Returns
        -------
        int | None
            Company ID if found, otherwise None.
        """
        companies = await self.get_all_companies()

        for company in companies:
            if company.get('name', '').lower() == name.lower():
                return company.get('id')

        return None

    def build_freshdesk_ui_url(self, company_id: int, status_id: int = 0) -> str:
        """
        Build a FreshDesk web UI search URL filtered by company and ticket status.

        Args:
            company_id:
                FreshDesk company ID.

            status_id:
                Ticket status filter (default: 0).

        Returns
        -------
        str
            Fully constructed FreshDesk UI URL that can be opened in a browser.
        """
        base_url = f"{URL_BASE}/a/tickets/filters/search"

        params = [
            ("orderBy", "created_at"),
            ("orderType", "desc"),
            ("q[]", f"company?is_in:[{company_id}]"),
            ("q[]", f"status?is_in:[{status_id}]"),
            ("ref", "_created"),
        ]

        return f"{base_url}?{urlencode(params)}"