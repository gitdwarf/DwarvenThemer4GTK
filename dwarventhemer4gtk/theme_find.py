"""Find installed GTK widget, icon, cursor, WM themes. Install/remove archives."""
import os, shutil, tarfile, zipfile, configparser
from .constants import THEME_DIRS, ICON_DIRS, CFG_GTK4
from .config import read_ini

def find_widget_themes():
    # GTK4 built-ins -- always available regardless of installed themes
    built_ins = ['Adwaita', 'Adwaita:dark', 'HighContrast', 'HighContrastInverse']
    seen = set(built_ins)
    themes = list(built_ins)
    for d in THEME_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name in seen:
                continue
            path = os.path.join(d, name)
            # Only include themes with a gtk-4.0 subdir -- GTK4 themes only
            if os.path.isdir(os.path.join(path, 'gtk-4.0')):
                seen.add(name)
                themes.append(name)
    return themes

def find_icon_themes():
    seen = set()
    themes = []
    for d in ICON_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name in seen or name == 'default':
                continue
            idx = os.path.join(d, name, 'index.theme')
            if not os.path.exists(idx):
                continue
            cfg = configparser.ConfigParser()
            cfg.read(idx)
            try:
                section = cfg['Icon Theme']
                if section.get('Hidden', 'false').lower() == 'true':
                    continue
                if 'Directories' not in section and 'directories' not in section:
                    continue
                disp = section.get('Name', name)
                seen.add(name)
                themes.append((name, disp))
            except KeyError:
                continue
    return sorted(themes, key=lambda x: x[1].lower())

def find_cursor_themes():
    seen = set()
    themes = []
    for d in ICON_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name in seen:
                continue
            if not os.path.isdir(os.path.join(d, name, 'cursors')):
                continue
            idx = os.path.join(d, name, 'index.theme')
            cfg = configparser.ConfigParser()
            disp = name
            if os.path.exists(idx):
                cfg.read(idx)
                try:
                    disp = cfg['Icon Theme'].get('Name', name)
                except KeyError:
                    pass
            seen.add(name)
            themes.append((name, disp))
    return sorted(themes, key=lambda x: x[1].lower())

def find_wm_themes():
    seen = set()
    themes = []
    wm_subdirs = ('openbox-3', 'metacity-1', 'xfwm4', 'fluxbox')
    for d in THEME_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name in seen:
                continue
            path = os.path.join(d, name)
            if any(os.path.isdir(os.path.join(path, sub)) for sub in wm_subdirs):
                seen.add(name)
                themes.append(name)
    return sorted(themes)

# ------------------------------------------------------------------ #
# Theme install / remove                                               #
# ------------------------------------------------------------------ #

def install_theme_archive(path, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    try:
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as tf:
                top = set(m.split('/')[0] for m in tf.getnames() if m)
                tf.extractall(dest_dir)
                return True, ', '.join(sorted(top))
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                top = set(m.split('/')[0] for m in zf.namelist() if m)
                zf.extractall(dest_dir)
                return True, ', '.join(sorted(top))
        return False, 'Unrecognised archive format'
    except Exception as e:
        return False, str(e)

def remove_theme(name, dirs):
    for d in dirs:
        if not d.startswith(os.path.expanduser('~')):
            continue
        target = os.path.join(d, name)
        if os.path.isdir(target):
            shutil.rmtree(target)
            return True
    return False

# ------------------------------------------------------------------ #
# Current settings shorthand                                          #
# ------------------------------------------------------------------ #

def current(key, default=''):
    return read_ini(CFG_GTK4, 'Settings', key, default)

# ------------------------------------------------------------------ #
# Reusable UI components                                               #
# ------------------------------------------------------------------ #

