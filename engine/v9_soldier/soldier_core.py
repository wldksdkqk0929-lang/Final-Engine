import json
import os
import sys
from datetime import datetime

class SoldierEngine:
    def __init__(self):
        self.input_file = "Target_Dossier.json"
        self.output_file = "Order_Book.json"
        self.capital_per_trade = 1000.0  # $1,000 per trade
        
    def execute_orders(self):
        print("⚔️ [Soldier] Receiving Dossier...")
        
        # 1. Dossier(지령서) 수신
        if not os.path.exists(self.input_file):
            print("❌ [Soldier] No Target Dossier found! Aborting.")
            return

        with open(self.input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        dossier = data.get("dossier", [])
        orders = []

        print(f"📋 [Soldier] Reviewing {len(dossier)} targets...")

        # 2. 실행 (Execution Loop)
        for target in dossier:
            symbol = target["symbol"]
            action = target["action"]
            
            # Soldier는 오직 "ENGAGE" 명령만 수행한다
            if action == "ENGAGE":
                print(f"   🔥 ENGAGING TARGET: {symbol}")
                
                # 주문서 작성 (가상 체결)
                order = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": symbol,
                    "type": "MARKET_BUY",
                    "amount_usd": self.capital_per_trade,
                    "reasoning_ref": target["thesis"]["summary"] # 근거 기록 (책임 소재)
                }
                orders.append(order)
            else:
                print(f"   zzz Skipping {symbol} (Action: {action})")

        # 3. 결과 보고 (Order Book)
        if orders:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(orders, f, indent=2)
            print(f"\n✅ [Soldier] Orders Executed. {len(orders)} trades recorded in {self.output_file}")
        else:
            print("\n💤 [Soldier] No targets to engage. Standing by.")

if __name__ == "__main__":
    soldier = SoldierEngine()
    soldier.execute_orders()
