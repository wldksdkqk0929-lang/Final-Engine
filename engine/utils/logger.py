from datetime import datetime

class SniperLogger:
    def __init__(self, name="SNIPER"):
        self.name = name

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{self.name} | {timestamp}] {message}")
