import re

with open('todo_bird_app/services/world_clock_service.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_class = False

for i, line in enumerate(lines):
    if line.startswith("_SYSTEM_COUNTRY_CACHE"):
        new_lines.append("class WorldClockService:\n")
        new_lines.append("    CLOCK_STYLES = CLOCK_STYLES\n")
        new_lines.append("    DEFAULT_CLOCKS = DEFAULT_CLOCKS\n")
        new_lines.append("    POPULAR_PRESETS = POPULAR_PRESETS\n")
        new_lines.append("    SUPPORTED_TYPES = {'analog', 'digital'}\n")
        new_lines.append("    SUPPORTED_THEMES = {'minimal', 'luxury', 'cyberpunk', 'retro_lcd', 'solar'}\n\n")
        new_lines.append("    " + line)
        in_class = True
        continue
    
    if line.strip() == "@classmethod" and not in_class:
        # This shouldn't happen if we caught _SYSTEM_COUNTRY_CACHE but just in case
        pass
        
    if in_class:
        # We need to fix indentation for _system_tzdb_root and the rest
        # Wait, the rest is already indented by 4 spaces in the file!
        # Let's check the current indentation.
        pass

