# Loggerimport logging
import os
import sys

class SystemLogger:
    def __init__(self, run_dir):
        # 로그 파일 경로 설정
        self.log_path = os.path.join(run_dir, "logs", "execution.log")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        
        # 기본 로거 설정 (파일 + 콘솔)
        logging.basicConfig(
            filename=self.log_path,
            level=logging.INFO,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S',
            force=True  # 핸들러 중복 방지
        )
        self.console = logging.StreamHandler(sys.stdout)
        self.console.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        logging.getLogger().addHandler(self.console)

    def log(self, msg, level="INFO"):
        """레벨별 로그 출력 및 저장"""
        if level == "INFO": logging.info(msg)
        elif level == "ERROR": logging.error(msg)
        elif level == "WARNING": logging.warning(msg)
        else: logging.info(msg)
