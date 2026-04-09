"""Tests for AiDot LAN config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock aidot before importing the integration
# ---------------------------------------------------------------------------

MOCK_AIDOT_CLIENT = "tests.test_config_flow.MOCK_AIDOT_CLIENT"


class MockAidotUserOrPassIncorrect(Exception):
    """Mock aidot auth exception."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_flow_result(errors: dict | None = None, step_id: str = "user"):
    """Build a minimal ConfigFlowResult-like dict."""
    return {
        "type": "form",
        "flow_id": "flow_1",
        "step_id": step_id,
        "errors": errors or {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAidotLanConfigFlow:
    """Tests for AidotLanConfigFlow."""

    async def test_user_flow_creates_entry(self):
        """Successful credentials create a config entry."""
        mock_client_instance = MagicMock()
        mock_client_instance.async_post_login = AsyncMock(
            return_value={
                "accessToken": "token123",
                "refreshToken": "refresh456",
                "username": "test@example.com",
            }
        )
        mock_client_instance.get_identifier = MagicMock(
            return_value="test@example.com"
        )

        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.client": MagicMock(),
                "aidot.const": MagicMock(),
                "aidot.exceptions": MagicMock(
                    AidotUserOrPassIncorrect=MockAidotUserOrPassIncorrect
                ),
            },
        ):
            from homeassistant.config_entries import ConfigFlowResult

            from custom_components.aidot_lan.config_flow import AidotLanConfigFlow

            flow = AidotLanConfigFlow()
            flow.hass = MagicMock()
            flow.hass.config_entries = MagicMock()
            flow.hass.config_entries.async_update_entry = MagicMock()
            flow._async_current_entries = MagicMock(return_value=[])

            with patch(
                "custom_components.aidot_lan.config_flow.AidotClient",
                return_value=mock_client_instance,
            ):
                with patch(
                    "custom_components.aidot_lan.config_flow.async_get_clientsession",
                    return_value=MagicMock(),
                ):
                    user_input = {
                        "country_code": "US",
                        "username": "test@example.com",
                        "password": "password123",
                    }
                    result = await flow.async_step_user(user_input)

        assert result["type"] == "create_entry"
        assert (
            result["title"] == "AiDot LAN · test@example.com"
        )
        assert "login_info" in result["data"]

    async def test_user_flow_invalid_auth(self):
        """Invalid credentials return invalid_auth error."""
        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.client": MagicMock(),
                "aidot.const": MagicMock(),
                "aidot.exceptions": MagicMock(
                    AidotUserOrPassIncorrect=MockAidotUserOrPassIncorrect
                ),
            },
        ):
            mock_client_instance = MagicMock()
            mock_client_instance.async_post_login = AsyncMock(
                side_effect=MockAidotUserOrPassIncorrect()
            )
            mock_client_instance.get_identifier = MagicMock(
                return_value="test@example.com"
            )

            from custom_components.aidot_lan.config_flow import AidotLanConfigFlow

            flow = AidotLanConfigFlow()
            flow.hass = MagicMock()
            flow.hass.config_entries = MagicMock()
            flow._async_current_entries = MagicMock(return_value=[])

            with patch(
                "custom_components.aidot_lan.config_flow.AidotClient",
                return_value=mock_client_instance,
            ):
                with patch(
                    "custom_components.aidot_lan.config_flow.async_get_clientsession",
                    return_value=MagicMock(),
                ):
                    user_input = {
                        "country_code": "US",
                        "username": "test@example.com",
                        "password": "wrongpassword",
                    }
                    result = await flow.async_step_user(user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"

    async def test_reauth_confirm_success(self):
        """Reauth with valid password updates entry and aborts."""
        original_login_info = {
            "accessToken": "old_token",
            "refreshToken": "old_refresh",
            "username": "test@example.com",
        }
        new_login_info = {
            "accessToken": "new_token",
            "refreshToken": "new_refresh",
            "username": "test@example.com",
        }

        mock_client_instance = MagicMock()
        mock_client_instance.async_post_login = AsyncMock(
            return_value=new_login_info
        )

        mock_entry = MagicMock()
        mock_entry.data = {"login_info": original_login_info}
        mock_entry.entry_id = "test_entry"

        mock_hass = MagicMock()
        mock_hass.config_entries.async_get_entry = MagicMock(
            return_value=mock_entry
        )
        mock_hass.config_entries.async_update_entry = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.client": MagicMock(),
                "aidot.const": MagicMock(),
                "aidot.exceptions": MagicMock(
                    AidotUserOrPassIncorrect=MockAidotUserOrPassIncorrect
                ),
            },
        ):
            from custom_components.aidot_lan.config_flow import AidotLanConfigFlow

            flow = AidotLanConfigFlow()
            flow.hass = mock_hass
            flow.context = {"entry_id": "test_entry"}

            with patch(
                "custom_components.aidot_lan.config_flow.AidotClient",
                return_value=mock_client_instance,
            ):
                with patch(
                    "custom_components.aidot_lan.config_flow.async_get_clientsession",
                    return_value=MagicMock(),
                ):
                    result = await flow.async_step_reauth_confirm(
                        {"password": "newpassword"}
                    )

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        mock_hass.config_entries.async_update_entry.assert_called_once()
        call_args = mock_hass.config_entries.async_update_entry.call_args
        assert call_args[0][1]["data"]["login_info"] == new_login_info

    async def test_reauth_confirm_invalid_password(self):
        """Reauth with wrong password returns invalid_auth error."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "login_info": {
                "accessToken": "old_token",
                "refreshToken": "old_refresh",
                "username": "test@example.com",
            }
        }
        mock_entry.entry_id = "test_entry"

        mock_hass = MagicMock()
        mock_hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)

        mock_client_instance = MagicMock()
        mock_client_instance.async_post_login = AsyncMock(
            side_effect=MockAidotUserOrPassIncorrect()
        )

        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.client": MagicMock(),
                "aidot.const": MagicMock(),
                "aidot.exceptions": MagicMock(
                    AidotUserOrPassIncorrect=MockAidotUserOrPassIncorrect
                ),
            },
        ):
            from custom_components.aidot_lan.config_flow import AidotLanConfigFlow

            flow = AidotLanConfigFlow()
            flow.hass = mock_hass
            flow.context = {"entry_id": "test_entry"}

            with patch(
                "custom_components.aidot_lan.config_flow.AidotClient",
                return_value=mock_client_instance,
            ):
                with patch(
                    "custom_components.aidot_lan.config_flow.async_get_clientsession",
                    return_value=MagicMock(),
                ):
                    result = await flow.async_step_reauth_confirm(
                        {"password": "wrongpassword"}
                    )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"
