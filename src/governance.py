import logging
import time
import json
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class SystemStatus(Enum):
    GREEN = "NORMAL"      # 정상 (1.0x Delay)
    YELLOW = "WARNING"    # 주의 (2.0x Delay - Soft Throttle)
    RED = "STOPPED"       # 차단 (Kill-Switch Active)


@dataclass
class SafetyLimits:
    MAX_DAILY_COST: float = 2.0
    COST_WARNING_THRESHOLD: float = 0.7
    MAX_CONSECUTIVE_ERRORS: int = 5
    MIN_INTERVAL_SEC: float = 1.0

    # Gemini 비용 (보수적)
    COST_PER_1M_INPUT_TOKENS: float = 0.10
    COST_PER_1M_OUTPUT_TOKENS: float = 0.40


class GovernanceManager:
    def __init__(self, limits: SafetyLimits = SafetyLimits()):
        self.limits = limits
        self.current_status = SystemStatus.GREEN

        self.total_cost = 0.0
        self.consecutive_errors = 0
        self.total_requests = 0
        self.last_call_time = 0.0
        self.last_reset_date = datetime.now().date()

        self.status_file = "system_status.json"
        self._update_status_file()

    # -------------------------
    # Daily Reset
    # -------------------------
    def _check_daily_reset(self):
        current_date = datetime.now().date()
        if current_date > self.last_reset_date:
            logging.info(f"🔄 Daily Reset: {self.last_reset_date} → {current_date}")
            self.total_cost = 0.0
            self.consecutive_errors = 0
            self.total_requests = 0
            self.last_reset_date = current_date
            self.current_status = SystemStatus.GREEN
            self._update_status_file()

    # -------------------------
    # Gatekeeper
    # -------------------------
    def check_status(self) -> bool:
        self._check_daily_reset()

        if self.current_status == SystemStatus.RED:
            logging.critical("🚨 SYSTEM HALTED (Kill-Switch Active)")
            return False

        # YELLOW 진입
        if self.total_cost >= (self.limits.MAX_DAILY_COST * self.limits.COST_WARNING_THRESHOLD):
            if self.current_status != SystemStatus.YELLOW:
                self.current_status = SystemStatus.YELLOW
                logging.warning("⚠️ Status → YELLOW (Cost Warning)")
                self._update_status_file()

        # RED 진입 조건
        if self.total_cost >= self.limits.MAX_DAILY_COST:
            self._trigger_kill_switch("Daily cost limit exceeded")
            return False

        if self.consecutive_errors >= self.limits.MAX_CONSECUTIVE_ERRORS:
            self._trigger_kill_switch("Too many consecutive errors")
            return False

        return True

    # -------------------------
    # Throttling
    # -------------------------
    def wait_for_slot(self):
        elapsed = time.time() - self.last_call_time
        base_interval = self.limits.MIN_INTERVAL_SEC

        if self.current_status == SystemStatus.YELLOW:
            base_interval *= 2.0

        if elapsed < base_interval:
            time.sleep(base_interval - elapsed)

    # -------------------------
    # Success / Failure
    # -------------------------
    def record_success(self, input_tokens: int, output_tokens: int):
        input_cost = (input_tokens / 1_000_000) * self.limits.COST_PER_1M_INPUT_TOKENS
        output_cost = (output_tokens / 1_000_000) * self.limits.COST_PER_1M_OUTPUT_TOKENS
        tx_cost = input_cost + output_cost

        self.consecutive_errors = 0
        self.total_cost += tx_cost
        self.total_requests += 1
        self.last_call_time = time.time()

        logging.info(f"💰 Cost +${tx_cost:.6f} | Total=${self.total_cost:.4f}")

    def record_failure(self):
        self.consecutive_errors += 1
        self.last_call_time = time.time()
        logging.warning(f"❌ Error Count {self.consecutive_errors}/{self.limits.MAX_CONSECUTIVE_ERRORS}")

    # -------------------------
    # Kill Switch
    # -------------------------
    def _trigger_kill_switch(self, reason: str):
        self.current_status = SystemStatus.RED
        logging.critical(f"🔥 KILL-SWITCH TRIGGERED: {reason}")
        self._update_status_file(reason)

    # -------------------------
    # External Hook
    # -------------------------
    def _update_status_file(self, reason: str = None):
        payload = {
            "status": self.current_status.value,
            "total_cost": self.total_cost,
            "errors": self.consecutive_errors,
            "last_updated": str(datetime.now()),
            "reason": reason,
        }
        try:
            with open(self.status_file, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to write status file: {e}")
