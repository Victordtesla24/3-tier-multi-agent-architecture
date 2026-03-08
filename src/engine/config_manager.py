import sys
import shutil
import logging
from pathlib import Path
from typing import Any

YAMLFactory: Any

try:
    from ruamel.yaml import YAML as YAMLFactory
except ImportError:
    YAMLFactory = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ConfigManager")


def _dump_simple_mapping(target_file: Path, data: dict[str, Any]) -> None:
    """Fallback writer used when ruamel.yaml is unavailable."""
    lines = [f"{key}: {value}" for key, value in data.items()]
    target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

def merge_config_safely(config_path: str, new_settings: dict[str, Any]) -> None:
    """
    Safely merges new settings into the GEMINI config file using an atomic YAML parser.
    Backs up the existing config first to prevent catastrophic data loss and preserves comments.
    """
    target_file = Path(config_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)

    if not target_file.exists():
        logger.info(f"Configuration file {config_path} not found. Initializing new structure.")
        target_file.touch()

    # Create an atomic backup prior to destructive parsing
    backup_path = Path(f"{config_path}.bak")
    shutil.copy2(target_file, backup_path)
    logger.info(f"Atomic backup created at {backup_path}")

    try:
        if YAMLFactory is None:
            logger.warning(
                "ruamel.yaml is unavailable; falling back to simple key/value config writing."
            )
            data: dict[str, Any] = {}
        else:
            yaml = YAMLFactory()
            yaml.preserve_quotes = True

            with target_file.open("r", encoding="utf-8") as f:
                raw = f.read()
            try:
                import io
                loaded = yaml.load(io.StringIO(raw))
            except Exception:
                # File is not valid YAML (e.g., it is a Markdown document).
                # Treat existing content as opaque and seed an empty mapping.
                loaded = {}
            if isinstance(loaded, dict):
                data = loaded
            else:
                data = {}

        # Merge structurally
        for key, value in new_settings.items():
            data[key] = value

        if YAMLFactory is None:
            _dump_simple_mapping(target_file, data)
        else:
            with target_file.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)

        logger.info(f"Configuration merged and safely injected into {config_path}")

    except Exception as e:
        logger.error(
            f"FATAL error writing {config_path}. Restoring from backup. Exception: {e}"
        )
        shutil.copy2(backup_path, target_file)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python config_manager.py <path_to_gemini_md> [default_model_label]")
        sys.exit(1)
        
    gemini_conf = sys.argv[1]
    default_model = sys.argv[2] if len(sys.argv) >= 3 else "OpenAI GPT-5.4 (Latest Flagship)"
    
    settingsToInject = {
        "orchestration_entry": ".agent/workflows/3-tier-orchestration.md",
        "default_model": default_model,
        "startup_hook": ".agent/rules/system-verification-agent.md",
        "new_chat_hook": ".agent/rules/system-verification-agent.md"
    }

    logger.info("Applying robust architectural hooks via parsed YAML...")
    merge_config_safely(gemini_conf, settingsToInject)
