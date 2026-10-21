"""Tests for the parts of agent_identity that do not touch Azure."""

import base64
import json
import unittest
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import agent_identity as identity

from agent_identity import agent_resource_id, token_claims


def fake_token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "header.%s.signature" % payload


class TestTokenClaims(unittest.TestCase):
    def test_payload_is_decoded_without_padding(self):
        self.assertEqual(token_claims(fake_token({"oid": "abc"}))["oid"], "abc")

    def test_every_padding_length_decodes(self):
        for size in range(1, 9):
            claims = {"oid": "x" * size}
            self.assertEqual(token_claims(fake_token(claims))["oid"], claims["oid"])


class TestAgentResourceId(unittest.TestCase):
    """The agent resource is the route to the identity that holds the roles, so a token
    from anywhere else must not be mistaken for one."""

    def test_an_agent_token_yields_the_resource(self):
        mirid = "/subscriptions/s/resourcegroups/rg/providers/Microsoft.App/agents/a1"
        self.assertEqual(agent_resource_id(fake_token({"xms_mirid": mirid})), mirid)


class TestCredentialSelection(unittest.TestCase):
    def setUp(self):
        self.managed = Mock()
        self.developer = Mock()
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.modules = patch.dict(sys.modules, {
            "azure": SimpleNamespace(),
            "azure.identity": SimpleNamespace(ManagedIdentityCredential=self.managed, DefaultAzureCredential=self.developer),
        })
        self.environment.start()
        self.modules.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.modules.stop)

    def test_missing_selection_fails_closed(self):
        with self.assertRaises(ValueError):
            identity.agent_credential()
        self.managed.assert_not_called()
        self.developer.assert_not_called()

    def test_user_identity_is_explicit_and_not_discovered(self):
        os.environ["AZURE_CLIENT_ID"] = "selected"
        identity.agent_credential()
        self.managed.assert_called_once_with(client_id="selected")
        self.developer.assert_not_called()

    def test_explicit_argument_overrides_environment_deterministically(self):
        os.environ["AZURE_CLIENT_ID"] = "environment"
        identity.agent_credential("argument")
        self.managed.assert_called_once_with(client_id="argument")

    def test_system_identity_requires_explicit_mode(self):
        os.environ["SRE_IDENTITY_MODE"] = "system-assigned"
        identity.agent_credential()
        self.managed.assert_called_once_with()
        self.developer.assert_not_called()

    def test_developer_mode_is_explicit_and_excludes_managed_identity(self):
        os.environ["SRE_IDENTITY_MODE"] = "developer"
        identity.agent_credential()
        self.developer.assert_called_once_with(exclude_managed_identity_credential=True)
        self.managed.assert_not_called()

    def test_conflicting_mode_does_not_select_another_identity(self):
        os.environ.update(SRE_IDENTITY_MODE="system-assigned", AZURE_CLIENT_ID="uami")
        with self.assertRaises(ValueError):
            identity.agent_credential()
        self.managed.assert_not_called()

    def test_authentication_failure_propagates(self):
        os.environ["AZURE_CLIENT_ID"] = "denied"
        self.managed.return_value.get_token.side_effect = RuntimeError("denied")
        with self.assertRaisesRegex(RuntimeError, "denied"):
            identity.agent_token()
        self.developer.assert_not_called()

    def test_diagnostic_does_not_swallow_failure(self):
        os.environ["AZURE_CLIENT_ID"] = "denied"
        self.managed.return_value.get_token.side_effect = RuntimeError("denied")
        with self.assertRaises(RuntimeError):
            identity.identity_report()

    def test_invalid_mode_and_missing_user_client_id_fail_closed(self):
        for mode in ("automatic", "user-assigned"):
            os.environ["SRE_IDENTITY_MODE"] = mode
            with self.assertRaises(ValueError):
                identity.agent_credential()
        self.managed.assert_not_called()
        self.developer.assert_not_called()

    def test_a_user_token_has_no_agent_resource(self):
        self.assertIsNone(agent_resource_id(fake_token({"oid": "user"})))

    def test_a_non_agent_managed_identity_is_rejected(self):
        mirid = "/subscriptions/s/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
        self.assertIsNone(agent_resource_id(fake_token({"xms_mirid": mirid})))

    def test_casing_of_the_resource_path_does_not_matter(self):
        mirid = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.App/AGENTS/a1"
        self.assertEqual(agent_resource_id(fake_token({"xms_mirid": mirid})), mirid)


if __name__ == "__main__":
    unittest.main()
