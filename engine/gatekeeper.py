import os
import json
import logging
import fcntl  # Linux/Unix Standard for File Locking
import time
from datetime import datetime

class LLMGatekeeper:
    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.state_dir = os.path.join(base_dir, "state")
        self.log_dir = os.path.join(base_dir, "logs")
        self.state_file = os.path.join(self.state_dir, "llm_cap.json")
        self.audit_log_file = os.path.join(self.log_dir, "llm_cap_audit.log")
        self.lock_file = os.path.join(self.state_dir, "llm_cap.lock") # Lock file path
        
        # Initialize Directories
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create empty lock file if not exists
        if not os.path.exists(self.lock_file):
            with open(self.lock_file, 'w') as f:
                f.write("")

        # Setup Logger (Prevent Duplication Fix)
        self.logger = logging.getLogger("LLM_Audit")
        self.logger.setLevel(logging.INFO)
        
        # Check if FileHandler already exists to avoid duplication
        has_file_handler = any(isinstance(h, logging.FileHandler) for h in self.logger.handlers)
        
        if not has_file_handler:
            handler = logging.FileHandler(self.audit_log_file)
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _load_state(self):
        # Default State
        default_state = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "call_count": 0,
            "cap_limit": 50,
            "kill_switch": False,
            "updated_at": datetime.now().isoformat()
        }

        if not os.path.exists(self.state_file):
            return default_state
            
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            # [Fix 2] Corrupt State Recovery (Conservative)
            default_state["updated_at"] = f"RECOVERED_FROM_CORRUPTION_{datetime.now().isoformat()}"
            # Log this critical error to audit
            self._append_log_internal("SYSTEM_ERROR", "SYSTEM", default_state, reason=f"State File Corrupted: {str(e)}")
            return default_state

    def _save_state(self, state):
        state["updated_at"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _append_log_internal(self, event, symbol, state, reason="", request_id=None):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id or "N/A", # [Fix 3] Request ID Added
            "symbol": symbol,
            "event": event,
            "call_count_snapshot": state.get("call_count", -1),
            "cap_limit": state.get("cap_limit", -1),
            "reason": reason
        }
        self.logger.info(json.dumps(log_entry))

    def check_access(self, symbol: str, request_id: str = None, cap_override: int = None, date_override: str = None) -> dict:
        """
        Thread-Safe Gatekeeper Check
        """
        # [Fix 1] Critical Section with File Lock
        with open(self.lock_file, 'r') as lock_f:
            try:
                # Exclusive Lock (Blocking)
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                
                # --- CRITICAL SECTION START ---
                state = self._load_state()
                
                # [Fix 4] Cap Override Logic (Memory Only)
                effective_cap = cap_override if cap_override is not None else state["cap_limit"]
                
                today = date_override if date_override else datetime.now().strftime("%Y-%m-%d")

                # 1. Date Reset Check
                if state["date"] != today:
                    old_date = state["date"]
                    state["date"] = today
                    state["call_count"] = 0
                    state["kill_switch"] = False
                    self._save_state(state)
                    self._append_log_internal("RESET", "SYSTEM", state, reason=f"New Day: {old_date} -> {today}", request_id=request_id)

                # 2. Kill Switch Check
                if state["kill_switch"]:
                    # No save needed
                    self._append_log_internal("REJECT", symbol, state, reason="KILL_SWITCH_ACTIVE", request_id=request_id)
                    return {"allowed": False, "reason": "KILL_SWITCH_ACTIVE"}

                # 3. Cap Limit Check (Using effective_cap)
                if state["call_count"] >= effective_cap:
                    state["kill_switch"] = True
                    self._save_state(state) # Persist Kill Switch
                    self._append_log_internal("KILL_SWITCH_ON", symbol, state, reason="DAILY_CAP_EXCEEDED", request_id=request_id)
                    return {"allowed": False, "reason": "DAILY_CAP_EXCEEDED"}

                # 4. Allow & Increment
                state["call_count"] += 1
                self._save_state(state)
                self._append_log_internal("ALLOW", symbol, state, reason="UNDER_CAP", request_id=request_id)
                
                return {"allowed": True, "reason": "OK"}
                # --- CRITICAL SECTION END ---

            finally:
                # Release Lock
                fcntl.flock(lock_f, fcntl.LOCK_UN)