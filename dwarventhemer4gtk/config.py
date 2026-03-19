"""Read/write GTK settings, colors.css, gtkrc, dconf helpers."""
import os, configparser
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from .constants import (CFG_GTK4, CFG_GTK2)

def read_ini(path, section, key, default=''):
    cfg = configparser.ConfigParser()
    if os.path.exists(path):
        cfg.read(path)
    try:
        return cfg[section][key]
    except KeyError:
        return default

def write_ini(path, section, key, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cfg = configparser.ConfigParser()
    if os.path.exists(path):
        cfg.read(path)
    if section not in cfg:
        cfg[section] = {}
    cfg[section][key] = value
    with open(path, 'w') as f:
        cfg.write(f)

def write_gtk4_settings(settings):
    """Write GTK4 [Settings] section to settings.ini.
    Preserves other sections (e.g. [X-DwarvenSuite]) -- GTK4 ignores them,
    DwarvenSuite apps read them as soft-default legacy settings."""
    os.makedirs(os.path.dirname(CFG_GTK4), exist_ok=True)
    cfg = configparser.ConfigParser()
    # Read existing file to preserve non-Settings sections
    if os.path.exists(CFG_GTK4):
        cfg.read(CFG_GTK4)
    # Replace Settings section entirely -- no stale GTK4 keys survive
    cfg['Settings'] = settings
    with open(CFG_GTK4, 'w') as f:
        cfg.write(f)

def write_dwarven_suite_settings(settings):
    """Write [X-DwarvenSuite] section to ~/.config/gtk-4.0/settings.ini.
    Stores legacy/deprecated GTK3 settings that DwarvenSuite apps honour
    as soft defaults. GTK4 itself silently ignores unknown sections."""
    os.makedirs(os.path.dirname(CFG_GTK4), exist_ok=True)
    cfg = configparser.ConfigParser()
    if os.path.exists(CFG_GTK4):
        cfg.read(CFG_GTK4)
    cfg['X-DwarvenSuite'] = settings
    with open(CFG_GTK4, 'w') as f:
        cfg.write(f)

def read_dwarven_suite_setting(key, default=''):
    """Read a value from [X-DwarvenSuite] in settings.ini."""
    return read_ini(CFG_GTK4, 'X-DwarvenSuite', key, default)

def write_gtk2_key(key, value, quoted=True):
    lines = []
    if os.path.exists(CFG_GTK2):
        with open(CFG_GTK2) as f:
            lines = [l for l in f if not l.startswith(key + '=')]
    val = f'"{value}"' if quoted else str(value)
    lines.insert(0, f'{key}={val}\n')
    with open(CFG_GTK2, 'w') as f:
        f.writelines(lines)

def gset():
    return Gtk.Settings.get_default()

# ------------------------------------------------------------------ #
# CSS color scheme                                                     #
# ------------------------------------------------------------------ #


def read_colors_css(path):
    colors = {}
    if not os.path.exists(path):
        return colors
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('@define-color'):
                parts = line.rstrip(';').split(None, 2)
                if len(parts) == 3:
                    colors[parts[1]] = parts[2]
    return colors

def write_colors_css(path, colors):
    """Merge colors into existing css file. None value = remove that key."""
    existing = {}
    other_lines = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('@define-color'):
                    parts = stripped.rstrip(';').split(None, 2)
                    if len(parts) == 3:
                        existing[parts[1]] = parts[2]
                        continue
                other_lines.append(line)
    for k, v in colors.items():
        if v is None:
            existing.pop(k, None)
        else:
            existing[k] = v
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        for line in other_lines:
            f.write(line)
        for name, value in sorted(existing.items()):
            f.write(f'@define-color {name} {value};\n')

def ensure_css_imports_colors(css_path, colors_filename='colors.css'):
    import_line = f"@import '{colors_filename}';\n"
    if os.path.exists(css_path):
        with open(css_path) as f:
            if import_line.strip() in f.read():
                return
        with open(css_path, 'r+') as f:
            content = f.read()
            f.seek(0)
            f.write(import_line + content)
    else:
        os.makedirs(os.path.dirname(css_path), exist_ok=True)
        with open(css_path, 'w') as f:
            f.write(import_line)

# ------------------------------------------------------------------ #
# Theme discovery                                                      #
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# Theme darkness detection                                            #
# ------------------------------------------------------------------ #

