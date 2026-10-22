import json
import tempfile
import unittest
from pathlib import Path

from policy_gatekeeper import Gatekeeper, load_policy


ADDRESS = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"


class PolicyGatekeeperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.audit = root / "audit.jsonl"
        self.config = root / "policy.json"
        self.config.write_text(json.dumps({
            "spend_limit": {"asset": "USDC", "max_amount": "100"},
            "allowlist": {"addresses": [ADDRESS]},
            "time_window": {"timezone": "UTC", "start": "09:00", "end": "17:00"}
        }))
        self.policy = load_policy(self.config)
        self.calls = []
        self.gatekeeper = Gatekeeper(self.policy, self.audit)

    def request(self, **changes):
        value = {"action": "transfer", "asset": "USDC", "amount": "25",
                 "to": ADDRESS, "requested_at": "2026-10-22T12:00:00+00:00"}
        value.update(changes)
        return value

    def prepare(self, request):
        self.calls.append(request)
        return {"status": "prepared", "broadcast": False}

    def test_spend_limit_denies_without_preparing(self):
        result = self.gatekeeper.handle(self.request(amount="100.01"), self.prepare)
        self.assertEqual((result["decision"], result["deciding_rule"]),
                         ("deny", "spend_limit"))
        self.assertEqual(self.calls, [])

    def test_allowlist_denies_without_preparing(self):
        result = self.gatekeeper.handle(self.request(to=OTHER), self.prepare)
        self.assertEqual((result["decision"], result["deciding_rule"]),
                         ("deny", "allowlist"))
        self.assertEqual(self.calls, [])

    def test_time_window_denies_without_preparing(self):
        result = self.gatekeeper.handle(
            self.request(requested_at="2026-10-22T18:00:00+00:00"), self.prepare)
        self.assertEqual((result["decision"], result["deciding_rule"]),
                         ("deny", "time_window"))
        self.assertEqual(self.calls, [])

    def test_allowed_request_is_prepared_but_never_signed_or_broadcast(self):
        result = self.gatekeeper.handle(self.request(), self.prepare)
        self.assertEqual((result["decision"], result["deciding_rule"]),
                         ("allow", "all_rules_passed"))
        self.assertEqual(result["prepared"], {"status": "prepared", "broadcast": False})
        self.assertEqual(len(self.calls), 1)

    def test_audit_log_is_append_only_and_persists_all_decisions(self):
        requests = [self.request(amount="101"), self.request(to=OTHER),
                    self.request(requested_at="2026-10-22T08:59:59+00:00"), self.request()]
        for request in requests:
            self.gatekeeper.handle(request, self.prepare)
        Gatekeeper(self.policy, self.audit).handle(self.request(), self.prepare)
        records = [json.loads(line) for line in self.audit.read_text().splitlines()]
        self.assertEqual(len(records), 5)
        self.assertEqual([item["deciding_rule"] for item in records],
                         ["spend_limit", "allowlist", "time_window",
                          "all_rules_passed", "all_rules_passed"])
        self.assertTrue(all("request" in item and "decision" in item for item in records))

    def test_invalid_request_is_denied_and_audited(self):
        result = self.gatekeeper.handle(self.request(amount="NaN"), self.prepare)
        self.assertEqual((result["decision"], result["deciding_rule"]),
                         ("deny", "invalid_request"))
        self.assertEqual(self.calls, [])
        record = json.loads(self.audit.read_text())
        self.assertEqual(record["deciding_rule"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
