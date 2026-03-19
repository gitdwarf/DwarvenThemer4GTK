"""Path constants, app identity, managed colours, reset CSS path."""
import os

APP_ID      = 'com.dwarven.themer4gtk'
APP_VERSION = '0.1.0'
APP_NAME    = 'DwarvenThemer4GTK'

CFG_GTK4    = os.path.expanduser('~/.config/gtk-4.0/settings.ini')
CFG_GTK3    = os.path.expanduser('~/.config/gtk-3.0/settings.ini')
CFG_GTK2    = os.path.expanduser('~/.gtkrc-2.0')
COLORS_GTK4 = os.path.expanduser('~/.config/gtk-4.0/colors.css')
COLORS_GTK3 = os.path.expanduser('~/.config/gtk-3.0/colors.css')
GTK4_CSS    = os.path.expanduser('~/.config/gtk-4.0/gtk.css')
GTK3_CSS    = os.path.expanduser('~/.config/gtk-3.0/gtk.css')
CURSOR_CFG  = os.path.expanduser('~/.icons/default/index.theme')

USER_THEME_DIR  = os.path.expanduser('~/.local/share/themes')
USER_ICON_DIR   = os.path.expanduser('~/.local/share/icons')

# Path to the bundled DwarvenReset theme (shipped with package)
# Parent dir containing themes/DwarvenReset/gtk-4.0/gtk.css
# Added to XDG_DATA_DIRS at startup so GTK finds DwarvenReset as a real theme.
RESET_THEME_DIR = os.path.join(os.path.dirname(__file__), 'reset_theme_data')
RESET_THEME_NAME = 'Default'

MANAGED_COLORS = [
    ('theme_bg_color',           'Window background',    '#f0f0f0'),
    ('theme_fg_color',           'Window foreground',    '#2e2e2e'),
    ('theme_base_color',         'Text area background', '#ffffff'),
    ('theme_text_color',         'Text area foreground', '#1a1a1a'),
    ('theme_selected_bg_color',  'Selection background', '#4a90d9'),
    ('theme_selected_fg_color',  'Selection foreground', '#ffffff'),
    ('tooltip_background_color', 'Tooltip background',   '#1a1a1a'),
    ('tooltip_foreground_color', 'Tooltip foreground',   '#e8e8e8'),
]
MANAGED_KEYS = {k for k, _, _ in MANAGED_COLORS}

PREVIEW_CURSORS = [
    ('default',        'Default'),
    ('pointer',        'Pointer'),
    ('text',           'Text'),
    ('crosshair',      'Crosshair'),
    ('move',           'Move'),
    ('wait',           'Wait'),
    ('progress',       'Progress'),
    ('not-allowed',    'Blocked'),
    ('grab',           'Grab'),
    ('zoom-in',        'Zoom in'),
    ('col-resize',     'Col resize'),
    ('row-resize',     'Row resize'),
]

def _build_icon_dirs():
    dirs = []
    xdg = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share')
    for base in xdg.split(':'):
        d = os.path.join(base, 'icons')
        if os.path.isdir(d):
            dirs.append(d)
    for extra in [
        os.path.expanduser('~/.icons'),
        os.path.expanduser('~/.local/share/icons'),
        '/usr/share/pixmaps',
    ]:
        if os.path.isdir(extra) and extra not in dirs:
            dirs.append(extra)
    # KDE paths
    for kde in ['/usr/share/plasma/desktoptheme', '/usr/share/kde4/apps/cursor']:
        if os.path.isdir(kde) and kde not in dirs:
            dirs.append(kde)
    return dirs

ICON_DIRS  = _build_icon_dirs()
THEME_DIRS = [
    os.path.expanduser('~/.themes'),
    os.path.expanduser('~/.local/share/themes'),
    '/usr/share/themes',
    '/usr/local/share/themes',
]
