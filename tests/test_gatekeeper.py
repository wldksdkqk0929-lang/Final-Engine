import sys
import os
import shutil
import unittest
import threading
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.gatekeeper import LLMGatekeeper

class TestLLMGatekeeper(unittest.TestCase):
    def setUp(self):
        self.gatekeeper = LLMGatekeeper()
        # Reset Files
        if os.path.exists(self.gatekeeper.state_file):
            os.remove(self.gatekeeper.state_file)
        if os.path.exists(self.gatekeeper.audit_log_file):
            os.remove(self.gatekeeper.audit_log_file)

    def test_scenario_full_cycle(self):
        print("\n🚀 [Test Start] Full Cycle + Concurrency Verification")
        TEST_CAP = 3
        SYMBOL = "TEST_TICKER"

        # --- Test A: Normal Increase ---
        print("   [Step A] Testing Normal Increment...")
        for i in range(1, 4):
            req_id = f"REQ_{i}"
            result = self.gatekeeper.check_access(SYMBOL, request_id=req_id, cap_override=TEST_CAP)
            self.assertTrue(result["allowed"])
            
            state = self.gatekeeper._load_state()
            self.assertEqual(state["call_count"], i)
            self.assertNotEqual(state["cap_limit"], TEST_CAP) # [Fix 4 Check] File should keep default, not override

        # --- Test B: Cap Exceeded ---
        print("   [Step B] Testing Cap Breach...")
        result = self.gatekeeper.check_access(SYMBOL, request_id="REQ_FAIL", cap_override=TEST_CAP)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "DAILY_CAP_EXCEEDED")
        
        state = self.gatekeeper._load_state()
        self.assertTrue(state["kill_switch"])

        # --- Test D: Date Reset ---
        print("   [Step D] Testing Date Reset...")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        result = self.gatekeeper.check_access(SYMBOL, date_override=tomorrow)
        self.assertTrue(result["allowed"])
        
        state = self.gatekeeper._load_state()
        self.assertEqual(state["date"], tomorrow)
        self.assertEqual(state["call_count"], 1)
        self.assertFalse(state["kill_switch"])

    def test_concurrency(self):
        # --- Test E: Race Condition Check ---
        print("\n⚡ [Step E] Testing Concurrency (Race Condition)...")
        
        # Reset for concurrency test
        if os.path.exists(self.gatekeeper.state_file):
            os.remove(self.gatekeeper.state_file)
        
        CONCURRENT_CAP = 10
        THREAD_COUNT = 20 # Try to exceed cap
        
        results = []
        
        def worker(idx):
            res = self.gatekeeper.check_access("CONC_TEST", request_id=f"THREAD_{idx}", cap_override=CONCURRENT_CAP)
            results.append(res["allowed"])

        threads = []
        for i in range(THREAD_COUNT):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()

        # Validation
        success_count = results.count(True)
        fail_count = results.count(False)
        state = self.gatekeeper._load_state()
        
        print(f"      Threads: {THREAD_COUNT}, Cap: {CONCURRENT_CAP}")
        print(f"      Success: {success_count}, Blocked: {fail_count}")
        print(f"      Final Call Count in File: {state['call_count']}")

        self.assertEqual(success_count, CONCURRENT_CAP, "Success count must match Cap exactly")
        self.assertEqual(state["call_count"], CONCURRENT_CAP, "File state call_count must match Cap exactly")
        self.assertTrue(state["kill_switch"], "Kill switch should be ON after breach")
        
        print("✅ [Test End] Concurrency Safe.")

if __name__ == '__main__':
    unittest.main()