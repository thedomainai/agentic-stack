"""
HashiCorp Vault client for secret management.

Provides interface for retrieving secrets from Vault.
"""

from typing import Any

import hvac
from hvac.exceptions import VaultError

from ..config import get_settings
from ..utils import get_logger

logger = get_logger(__name__)


class VaultClient:
    """Vault client wrapper."""

    def __init__(
        self,
        address: str | None = None,
        token: str | None = None,
    ):
        """
        Initialize Vault client.

        Args:
            address: Vault server address. If not provided, uses settings.
            token: Vault token. If not provided, uses settings.
        """
        settings = get_settings()
        self._address = address or settings.vault.address
        self._token = token or settings.vault.token
        self._client: hvac.Client | None = None

    def _get_client(self) -> hvac.Client:
        """Get or create Vault client."""
        if self._client is None:
            self._client = hvac.Client(
                url=self._address,
                token=self._token,
            )
        return self._client

    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        try:
            client = self._get_client()
            return client.is_authenticated()
        except VaultError as e:
            logger.error(f"Vault authentication check failed: {e}")
            return False

    def ping(self) -> bool:
        """Check if Vault is available and accessible."""
        try:
            client = self._get_client()
            status = client.sys.read_health_status(method="GET")
            return status.get("initialized", False)
        except Exception as e:
            logger.error(f"Vault ping failed: {e}")
            return False

    def get_secret(
        self,
        path: str,
        mount_point: str = "secret",
    ) -> dict[str, Any] | None:
        """
        Get a secret from Vault.

        Args:
            path: Path to the secret (e.g., "agent/api_keys")
            mount_point: Mount point for the KV engine

        Returns:
            Secret data dictionary or None if not found
        """
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=mount_point,
            )

            if response and "data" in response:
                logger.debug(f"Retrieved secret from {mount_point}/{path}")
                return response["data"]["data"]

            return None
        except VaultError as e:
            logger.error(f"Failed to get secret {path}: {e}")
            return None

    def set_secret(
        self,
        path: str,
        secret: dict[str, Any],
        mount_point: str = "secret",
    ) -> bool:
        """
        Store a secret in Vault.

        Args:
            path: Path to store the secret
            secret: Secret data dictionary
            mount_point: Mount point for the KV engine

        Returns:
            True if successful, False otherwise
        """
        try:
            client = self._get_client()
            client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=secret,
                mount_point=mount_point,
            )
            logger.info(f"Stored secret at {mount_point}/{path}")
            return True
        except VaultError as e:
            logger.error(f"Failed to store secret {path}: {e}")
            return False

    def delete_secret(
        self,
        path: str,
        mount_point: str = "secret",
    ) -> bool:
        """
        Delete a secret from Vault.

        Args:
            path: Path to the secret
            mount_point: Mount point for the KV engine

        Returns:
            True if successful, False otherwise
        """
        try:
            client = self._get_client()
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=mount_point,
            )
            logger.info(f"Deleted secret at {mount_point}/{path}")
            return True
        except VaultError as e:
            logger.error(f"Failed to delete secret {path}: {e}")
            return False

    def get_api_key(self, service: str) -> str | None:
        """
        Get an API key for a specific service.

        Args:
            service: Name of the service (e.g., "anthropic", "openai")

        Returns:
            API key string or None if not found
        """
        secret = self.get_secret(f"agent/api_keys/{service}")
        if secret:
            return secret.get("api_key")
        return None

    def list_secrets(
        self,
        path: str = "",
        mount_point: str = "secret",
    ) -> list[str]:
        """
        List secrets at a path.

        Args:
            path: Path to list
            mount_point: Mount point for the KV engine

        Returns:
            List of secret names
        """
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=mount_point,
            )

            if response and "data" in response:
                return response["data"].get("keys", [])

            return []
        except VaultError as e:
            logger.error(f"Failed to list secrets at {path}: {e}")
            return []
