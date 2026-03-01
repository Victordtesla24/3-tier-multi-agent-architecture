import sys
import shutil
import logging
from pathlib import Path

try:
    from ruamel.yaml import YAML
except ImportError:
    print("CRITICAL: ruamel.yaml not installed. Please run `uv sync`")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ConfigManager")

def merge_config_safely(config_path: str, new_settings: dict) -> None:
    """
    Safely merges new settings into the GEMINI config file using an atomic YAML parser.
    Backs up the existing config first to prevent catastrophic data loss and preserves comments.
    """
    target_file = Path(config_path)
    
    if not target_file.exists():
        logger.info(f"Configuration file {config_path} not found. Initializing new structure.")
        target_file.touch()

    # Create an atomic backup prior to destructive parsing
    backup_path = Path(f"{config_path}.bak")
    shutil.copy2(target_file, backup_path)
    logger.info(f"Atomic backup created at {backup_path}")

    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        with open(target_file, 'r') as f:
            data = yaml.load(f)
            if data is None:
                data = {}
                
        # Merge structurally
        for key, value in new_settings.items():
            data[key] = value
            
        with open(target_file, 'w') as f:
            yaml.dump(data, f)
            
        logger.info(f"Configuration merged and safely injected into {config_path}")

    except Exception as e:
        logger.error(f"FATAL parsing error in {config_path}. Restoring from backup. Exception: {e}")
        shutil.copy2(backup_path, target_file)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python config_manager.py <path_to_gemini_md>")
        sys.exit(1)
        
    gemini_conf = sys.argv[1]
    
    settingsToInject = {
        "orchestration_entry": ".agent/workflows/3-tier-orchestration.md",
        "default_model": "Gemini 3.1 Pro Preview",
        "startup_hook": ".agent/rules/system-verification-agent.md",
        "new_chat_hook": ".agent/rules/system-verification-agent.md"
    }

    logger.info(f"Applying robust architectural hooks via parsed YAML...")
    merge_config_safely(gemini_conf, settingsToInject)
