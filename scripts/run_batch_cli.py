import sys
import os

# -------------------------------------------------------------------
# Project Root Path Setup (Critical for imports)
# -------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# -------------------------------------------------------------------
# Imports (Real Engine Binding)
# -------------------------------------------------------------------
try:
    from src.shared.logger import logger
    from engine.orchestrator import SniperOrchestrator
except ImportError as e:
    print(f"::error::Critical Import Error: {e}")
    sys.exit(1)

# -------------------------------------------------------------------
# Main Entry
# -------------------------------------------------------------------
def main():
    """
    [Phase-4B] Sniper Batch CLI
    - Wraps real SniperOrchestrator with structured logging
    """

    # SECTION 1: System Initialization
    with logger.group("1. System Initialization"):
        try:
            logger.info("Bootstrapping Sniper Orchestrator...")
            orchestrator = SniperOrchestrator()
            logger.success("Orchestrator Initialized.")
        except Exception as e:
            logger.error("Initialization Failed", e)
            sys.exit(1)

    # SECTION 2: Batch Execution
    with logger.group("2. Batch Execution"):
        try:
            logger.info("Starting Orchestrator Pipeline...")
            orchestrator.run()
            logger.success("Pipeline Execution Completed.")
        except Exception as e:
            logger.error("Runtime Execution Failed", e)
            sys.exit(1)

    # SECTION 3: Shutdown
    with logger.group("3. Shutdown"):
        logger.info("System Shutdown Normal.")

# -------------------------------------------------------------------
if __name__ == "__main__":
    main()
