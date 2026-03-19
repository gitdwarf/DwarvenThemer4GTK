"""Theme darkness detection via CSS luminance, name heuristics, built-in map."""
import os
from .constants import THEME_DIRS

def _hex_to_luminance(hex_color):
    """Return perceived luminance 0.0-1.0 for a #rrggbb colour string."""
    hex_color = hex_color.strip().lstrip('#')
    if len(hex_color) not in (3, 6):
        return 0.5  # unknown, assume mid
    if len(hex_color) == 3:
        hex_color = ''.join(c*2 for c in hex_color)
    try:
        r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 0.5
    # Relative luminance (sRGB)
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

def _css_bg_luminance(css_path):
    """Parse a CSS/colors.css file and return luminance of the background colour.
    Tries multiple declaration styles used by different theme authors."""
    if not os.path.exists(css_path):
        return None
    import re
    try:
        with open(css_path) as f:
            content = f.read()
    except OSError:
        return None

    # 1. @define-color declarations (modern GTK4 themes)
    for key in ('window_bg_color', 'theme_bg_color', 'theme_base_color'):
        m = re.search(r'@define-color\s+' + key + r'\s+(#[0-9a-fA-F]{3,6})', content)
        if m:
            return _hex_to_luminance(m.group(1))

    # 2. .background { background-color: #xxxxxx } (older GTK3/4 themes, Adwaita style)
    m = re.search(r'\.background\s*\{[^}]*background-color:\s*(#[0-9a-fA-F]{3,6})', content)
    if m:
        return _hex_to_luminance(m.group(1))

    # 3. color-scheme: light/dark (CSS spec, some modern themes)
    m = re.search(r'color-scheme:\s*(light|dark)', content, re.IGNORECASE)
    if m:
        return 0.9 if m.group(1).lower() == 'light' else 0.1

    return None


# Built-in GTK4 themes -- explicit light/dark map
# These are baked into libgtk, no CSS files on disk to parse
_BUILTIN_DARK_THEMES  = frozenset(['adwaita:dark', 'highcontrastinverse',
                                    'default-dark', 'default-hc-dark'])
_BUILTIN_LIGHT_THEMES = frozenset(['adwaita', 'highcontrast',
                                    'default', 'default-hc'])

def detect_theme_dark(widget_theme_name, settings_dark_mode=False):
    """Return True if the theme is dark.
    Checks (in order):
    1. gtk-application-prefer-dark-theme setting
    2. Built-in theme explicit map (Adwaita, HighContrast etc)
    3. Theme name heuristics
    4. Theme CSS background colour luminance
    Falls back to False (assume light) if undetermined."""

    # 1. Explicit dark mode setting
    if settings_dark_mode:
        return True

    name_lower = widget_theme_name.lower()

    # 2. Built-in theme map -- definitive, no heuristics needed
    if name_lower in _BUILTIN_DARK_THEMES:
        return True
    if name_lower in _BUILTIN_LIGHT_THEMES:
        return False

    # 3. Name heuristics
    dark_words = ('dark', 'black', 'night', 'dim', 'dracula',
                  'monokai', 'solarized-dark', 'nord', 'gruvbox-dark')
    if any(w in name_lower for w in dark_words):
        return True

    # 4. Theme CSS background colour luminance
    for d in THEME_DIRS:
        for sub in ('gtk-4.0', 'gtk-3.0'):
            css    = os.path.join(d, widget_theme_name, sub, 'gtk.css')
            colors = os.path.join(d, widget_theme_name, sub, 'colors.css')
            for path in (colors, css):
                lum = _css_bg_luminance(path)
                if lum is not None:
                    return lum < 0.4

    return False  # assume light

def adwaita_fallback_theme(is_dark):
    """Return the appropriate Adwaita fallback theme name.
    For cursors: always Adwaita (no dark cursor variant in spec).
    For icons: Adwaita scalable SVGs are theme-agnostic (currentColor).
    is_dark is retained for future use with PNG-only fallback scenarios."""
    return 'Adwaita'

def adwaita_symbolic_dirs():
    """Return all Adwaita symbolic icon subdirs for search path injection.
    Symbolic icons recolour via CSS -- always appropriate for any theme."""
    dirs = []
    xdg = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share')
    for base in xdg.split(':'):
        for sub in ('actions', 'apps', 'categories', 'devices',
                    'emblems', 'mimetypes', 'places', 'status', 'ui'):
            p = os.path.join(base.strip(), 'icons', 'Adwaita', 'symbolic', sub)
            if os.path.isdir(p):
                dirs.append(p)
        # Also add flat symbolic dir (some distros)
        p = os.path.join(base.strip(), 'icons', 'Adwaita', 'symbolic')
        if os.path.isdir(p):
            dirs.append(p)
    return dirs

