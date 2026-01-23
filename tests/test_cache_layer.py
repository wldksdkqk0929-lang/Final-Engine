import sys
import os
import time
import shutil
import unittest
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.cache import SniperCacheLayer

class TestSniperCache(unittest.TestCase):
    def setUp(self):
        self.cache = SniperCacheLayer(ttl_minutes=0.05) # 3 seconds TTL
        self.test_symbol = "TEST_CACHE"
        today = datetime.now().strftime("%Y-%m-%d")
        cache_dir = os.path.join(self.cache.cache_root, today)
        if os.path.exists(cache_dir):
            try: shutil.rmtree(cache_dir)
            except: pass

    def mock_llm_call(self):
        print("   >> [API] Calling Expensive LLM...")
        return {"analysis": "Success", "timestamp": time.time()}

    def test_ghost_mode_and_ttl(self):
        print("\n🚀 [Test] Cache Layer & Ghost Mode")

        print("\n[Step 1] Initial Call (Gatekeeper OK)")
        gatekeeper_ok = {"allowed": True}
        res1 = self.cache.resolve_request("gemini", "pro", self.test_symbol, "Analyze this", gatekeeper_ok, self.mock_llm_call)
        self.assertIsNotNone(res1)

        print("\n[Step 2] Second Call (Should be HIT)")
        res2 = self.cache.resolve_request("gemini", "pro", self.test_symbol, "Analyze this", gatekeeper_ok, lambda: self.fail("LLM called on HIT"))
        self.assertEqual(res1["timestamp"], res2["timestamp"])
        print("   ✅ HIT Verified")

        print("\n[Step 3] Ghost Mode (Gatekeeper BLOCKED + Cache HIT)")
        gatekeeper_block = {"allowed": False, "reason": "KILL_SWITCH"}
        try:
            res3 = self.cache.resolve_request("gemini", "pro", self.test_symbol, "Analyze this", gatekeeper_block, lambda: self.fail("LLM called"))
            print("   ✅ Ghost Mode Active")
        except PermissionError:
            self.fail("Ghost Mode Failed")

        print("\n[Step 4] Waiting for TTL Expiry (3.1s)...")
        time.sleep(3.1)
        
        print("[Step 5] Call after Expiry (Should match Gatekeeper)")
        try:
            self.cache.resolve_request("gemini", "pro", self.test_symbol, "Analyze this", gatekeeper_block, self.mock_llm_call)
            self.fail("Should be blocked by Gatekeeper")
        except PermissionError:
            print("   ✅ Blocked correctly after TTL expiry")

if __name__ == '__main__':
    unittest.main()
