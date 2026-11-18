"""Azure SRE Agent sandbox tokens: sidecar-issued placeholders keep tenant, client and audience verifiable."""

import importlib.util
import unittest
from pathlib import Path

CASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("case10_sidecar", CASE / "engine.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

TENANT = "22222222-2222-4222-8222-222222222222"
CLIENT = "33333333-3333-4333-8333-333333333333"


def sidecar(scope, tenant=TENANT, client=CLIENT):
    return {"iss": "adc-msi-sidecar", "tid": tenant, "cid": "", "clientId": client, "scp": scope,
            "kind": "workspace-mi", "exp": 4102444800, "iat": 1700000000}


class SidecarTokenTest(unittest.TestCase):
    def test_arm_scope_maps_to_arm_audience_and_client(self):
        claims = tool.normalize_sidecar_claims(sidecar("https://management.core.windows.net/.default"))
        self.assertEqual(claims["aud"], "https://management.azure.com")
        self.assertEqual(claims["appid"], CLIENT)
        self.assertEqual(claims["tid"], TENANT)

    def test_data_plane_scopes_keep_their_resource(self):
        self.assertEqual(tool.normalize_sidecar_claims(sidecar("https://vault.azure.net/.default"))["aud"], "https://vault.azure.net")
        self.assertEqual(tool.normalize_sidecar_claims(sidecar("https://api.loganalytics.io/.default"))["aud"], "https://api.loganalytics.io")

    def test_mismatches_stay_visible_to_the_validator(self):
        claims = tool.normalize_sidecar_claims(sidecar("https://management.core.windows.net/.default", tenant="44444444-4444-4444-8444-444444444444", client="55555555-5555-4555-8555-555555555555"))
        self.assertNotEqual(claims["tid"], TENANT)
        self.assertNotEqual(claims["appid"], CLIENT)
        self.assertIsNone(tool.normalize_sidecar_claims(sidecar(""))["aud"])

    def test_real_entra_tokens_are_unchanged(self):
        real = {"iss": "https://sts.windows.net/" + TENANT + "/", "tid": TENANT, "appid": CLIENT, "aud": "https://management.azure.com/"}
        self.assertIs(tool.normalize_sidecar_claims(real), real)
        self.assertEqual(tool.normalize_sidecar_claims("not-a-dict"), "not-a-dict")


if __name__ == "__main__":
    unittest.main()
