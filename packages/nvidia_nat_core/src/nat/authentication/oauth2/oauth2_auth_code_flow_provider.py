# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import UTC
from datetime import datetime

import httpx
from authlib.integrations.httpx_client import OAuth2Client as AuthlibOAuth2Client
from pydantic import SecretStr

from nat.authentication.interfaces import AuthProviderBase
from nat.authentication.oauth2.oauth2_auth_code_flow_provider_config import OAuth2AuthCodeFlowProviderConfig
from nat.authentication.token_storage import TokenStorageBase
from nat.builder.context import Context
from nat.data_models.authentication import AuthenticatedContext
from nat.data_models.authentication import AuthFlowType
from nat.data_models.authentication import AuthResult
from nat.data_models.authentication import BearerTokenCred
from nat.runtime.session import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)


class OAuth2AuthCodeFlowProvider(AuthProviderBase[OAuth2AuthCodeFlowProviderConfig]):

    def __init__(self, config: OAuth2AuthCodeFlowProviderConfig, token_storage: TokenStorageBase | None = None):
        super().__init__(config)
        self._auth_callback = None
        # Always use token storage - defaults to in-memory if not provided
        if token_storage is None:
            from nat.authentication.token_storage import InMemoryTokenStorage
            self._token_storage = InMemoryTokenStorage()
        else:
            self._token_storage = token_storage

    async def _attempt_token_refresh(self, user_id: str, auth_result: AuthResult) -> AuthResult | None:
        refresh_token = auth_result.raw.get("refresh_token")
        if not isinstance(refresh_token, str):
            return None

        try:
            with AuthlibOAuth2Client(
                    client_id=self.config.client_id,
                    client_secret=self.config.client_secret,
            ) as client:
                new_token_data = client.refresh_token(
                    self.config.token_url,
                    refresh_token=refresh_token,
                    client_id=self.config.client_id,  # Required by MaaS OAuth
                )

                expires_at_ts = new_token_data.get("expires_at")
                new_expires_at = datetime.fromtimestamp(expires_at_ts, tz=UTC) if expires_at_ts else None

            new_auth_result = AuthResult(
                credentials=[BearerTokenCred(token=SecretStr(new_token_data["access_token"]))],
                token_expires_at=new_expires_at,
                raw=new_token_data,
            )

            await self._token_storage.store(user_id, new_auth_result)
        except httpx.HTTPStatusError:
            return None
        except httpx.RequestError:
            return None
        except Exception:
            # On any other failure, we'll fall back to the full auth flow.
            return None

        return new_auth_result

    def _set_custom_auth_callback(self,
                                  auth_callback: Callable[[OAuth2AuthCodeFlowProviderConfig, AuthFlowType],
                                                          Awaitable[AuthenticatedContext]]):
        self._auth_callback = auth_callback

    async def authenticate(self, user_id: str | None = None, **kwargs) -> AuthResult:
        context = Context.get()
        if user_id is None and hasattr(context, "metadata") and hasattr(
                context.metadata, "cookies") and context.metadata.cookies is not None:
            session_id = context.metadata.cookies.get(SESSION_COOKIE_NAME, None)
            if not session_id:
                raise RuntimeError("Authentication failed. No session ID found. Cannot identify user.")

            user_id = session_id

        if user_id:
            # Try to retrieve from token storage
            auth_result = await self._token_storage.retrieve(user_id)

            if auth_result:
                if not auth_result.is_expired():
                    logger.info(
                        "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: valid cached token found for user_id=%s\n*********************\n",
                        user_id)
                    return auth_result

                logger.info(
                    "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: cached token is expired for user_id=%s, attempting refresh\n*********************\n",
                    user_id)
                refreshed_auth_result = await self._attempt_token_refresh(user_id, auth_result)
                if refreshed_auth_result:
                    logger.info(
                        "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: token refresh succeeded for user_id=%s\n*********************\n",
                        user_id)
                    return refreshed_auth_result
                logger.info(
                    "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: token refresh failed for user_id=%s, falling through to interactive flow\n*********************\n",
                    user_id)
            else:
                logger.info(
                    "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: no cached token for user_id=%s, proceeding to interactive OAuth flow\n*********************\n",
                    user_id)
        else:
            logger.info(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: no user_id, proceeding to interactive OAuth flow\n*********************\n"
            )

        # Try getting callback from the context if that's not set, use the default callback
        try:
            logger.info(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: attempting to get auth from context for user_id=%s\n*********************\n",
                user_id)
            ctx_callback = Context.get().user_auth_callback
            logger.info(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: got auth callback from Context: %s\n*********************\n",
                type(ctx_callback).__name__ if ctx_callback else None)
            auth_callback = ctx_callback
        except RuntimeError as e:
            logger.info(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: Context.get() raised RuntimeError: %s, falling back to _auth_callback=%s\n*********************\n",
                e,
                type(self._auth_callback).__name__ if self._auth_callback else None)
            auth_callback = self._auth_callback

        if not auth_callback:
            logger.error(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: no auth callback available for user_id=%s\n*********************\n",
                user_id)
            raise RuntimeError("Authentication callback not set on Context.")

        logger.info(
            "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: invoking auth callback %s for user_id=%s\n*********************\n",
            type(auth_callback).__name__,
            user_id)
        try:
            authenticated_context = await auth_callback(self.config, AuthFlowType.OAUTH2_AUTHORIZATION_CODE)
            logger.info(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: auth callback returned for user_id=%s\n*********************\n",
                user_id)
        except Exception as e:
            logger.error(
                "\n*********************\nOAuth2AuthCodeFlowProvider.authenticate: auth callback raised %s for user_id=%s: %s\n*********************\n",
                type(e).__name__,
                user_id,
                e,
                exc_info=True)
            raise RuntimeError(f"Authentication callback failed: {e}") from e

        headers = authenticated_context.headers or {}
        auth_header = headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise RuntimeError("Invalid Authorization header")

        token = auth_header.split(" ")[1]

        # Safely access metadata
        metadata = authenticated_context.metadata or {}
        auth_result = AuthResult(
            credentials=[BearerTokenCred(token=SecretStr(token))],
            token_expires_at=metadata.get("expires_at"),
            raw=metadata.get("raw_token") or {},
        )

        if user_id:
            await self._token_storage.store(user_id, auth_result)

        return auth_result
