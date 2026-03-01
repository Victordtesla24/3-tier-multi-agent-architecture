import os
import sys
import shutil

def merge_config(config_path, new_settings):
    """
    Safely merges new settings into the GEMINI config file.
    Backs up the existing config first to prevent data loss.
    """
    if not os.path.exists(config_path):
        # Create empty if it doesn't exist
        open(config_path, 'w').close()
    
    # Backup
    backup_path = f"{config_path}.bak"
    shutil.copy2(config_path, backup_path)
    print(f"  ↳ Backup created at {backup_path}")

    # Read existing lines
    with open(config_path, 'r') as f:
        lines = f.readlines()

    # Apply changes
    merged_settings = {}
    out_lines = []
    
    # Process existing lines, updating values if keys match
    for line in lines:
        if ':' in line and not line.strip().startswith('#'):
            key = line.split(':', 1)[0].strip()
            if key in new_settings:
                out_lines.append(f"{key}: {new_settings[key]}\n")
                merged_settings[key] = True
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)

    # Append new keys that weren't in the file
    for key, value in new_settings.items():
        if key not in merged_settings:
            # Ensure proper separation
            if out_lines and not out_lines[-1].endswith('\n\n'):
                if not out_lines[-1].endswith('\n'):
                    out_lines.append('\n')
            
            out_lines.append(f"{key}: {value}\n")

    # Write back
    with open(config_path, 'w') as f:
        f.writelines(out_lines)
    
    print(f"  ↳ Configuration merged safely into {config_path}")


if __name__ == "__main__":
    gemini_conf = sys.argv[1]
    
    settings = {
        "orchestration_entry": ".agent/workflows/3-tier-orchestration.md",
        "default_model": "Gemini 3.1 Pro Preview",
        "startup_hook": ".agent/rules/system-verification-agent.md",
        "new_chat_hook": ".agent/rules/system-verification-agent.md"
    }

    print(f"Applying robust configuration merging...")
    merge_config(gemini_conf, settings)
