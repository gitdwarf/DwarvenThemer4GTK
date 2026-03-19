"""GTK4 → GTK3/GTK2 theme downconverter.

Strategy:
- GTK3: @define-color variable names are IDENTICAL to GTK4 (verified).
  Write gtk-3.0/gtk.css that @imports base Adwaita GTK3 theme and overrides
  just the colour variables. Full fidelity -- inherits all GTK3 structural
  styling, just with custom colours on top.

- GTK2: Write gtk-color-scheme to ~/.gtkrc-2.0 mapping GTK4 colour variable
  names to GTK2's shorter colour names. GTK2 apps pick up colours via the
  gtk-color-scheme setting. Engine and structural styling inherited from
  whatever GTK2 theme is active.
"""

import os
import re

# GTK4 @define-color name → GTK2 gtk-color-scheme name
# GTK2 uses shorter names without the 'theme_' prefix
GTK4_TO_GTK2_COLOR_MAP = {
    'theme_bg_color':          'bg_color',
    'theme_fg_color':          'fg_color',
    'theme_base_color':        'base_color',
    'theme_text_color':        'text_color',
    'theme_selected_bg_color': 'selected_bg_color',
    'theme_selected_fg_color': 'selected_fg_color',
    'tooltip_background_color': 'tooltip_bg_color',
    'tooltip_foreground_color': 'tooltip_fg_color',
}

# GTK3 base theme to inherit from -- Adwaita is always available in libgtk3
GTK3_BASE_THEME = 'Adwaita'


def extract_colors_from_css(css_path):
    """Extract @define-color declarations from a gtk.css file.
    Returns dict of {name: value}."""
    colors = {}
    if not os.path.exists(css_path):
        return colors
    try:
        with open(css_path) as f:
            content = f.read()
    except OSError:
        return colors
    for m in re.finditer(r'@define-color\s+(\S+)\s+([^;]+);', content):
        colors[m.group(1)] = m.group(2).strip()
    return colors


def build_gtk3_css(color_overrides):
    """Build gtk-3.0/gtk.css content.

    Imports Adwaita GTK3 as the base theme, then overrides @define-color
    variables with custom values. Since GTK3 and GTK4 use identical variable
    names, this is a 1:1 mapping -- no translation needed.

    Args:
        color_overrides: dict of {gtk4_variable_name: hex_value}

    Returns:
        str: Complete gtk.css content for gtk-3.0/
    """
    lines = [
        '/* DwarvenThemer4GTK -- GTK3 theme generated from GTK4 colour settings */',
        '/* Base: Adwaita GTK3 (structural styling inherited intact)             */',
        '/* Colour overrides applied on top -- identical variable names GTK3/4   */',
        '',
        '@import url("resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained.css");',
        '',
        '/* Colour overrides from GTK4 theme */',
    ]

    for name, value in sorted(color_overrides.items()):
        lines.append(f'@define-color {name} {value};')

    return '\n'.join(lines) + '\n'


def build_gtk3_dark_css(color_overrides):
    """Build gtk-3.0/gtk-dark.css content (dark variant)."""
    lines = [
        '/* DwarvenThemer4GTK -- GTK3 dark theme generated from GTK4 colour settings */',
        '',
        '@import url("resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained-dark.css");',
        '',
        '/* Colour overrides from GTK4 dark theme */',
    ]
    for name, value in sorted(color_overrides.items()):
        lines.append(f'@define-color {name} {value};')
    return '\n'.join(lines) + '\n'


def build_gtk2_color_scheme(color_overrides):
    """Build gtk-color-scheme string for GTK2 gtkrc.

    Maps GTK4 @define-color names to GTK2 color scheme names.
    Only maps colours that have direct GTK2 equivalents.

    Args:
        color_overrides: dict of {gtk4_variable_name: hex_value}

    Returns:
        str: value for gtk-color-scheme setting, or None if no mappable colours
    """
    pairs = []
    for gtk4_name, gtk2_name in GTK4_TO_GTK2_COLOR_MAP.items():
        value = color_overrides.get(gtk4_name)
        if value and value.startswith('#'):
            pairs.append(f'{gtk2_name}:{value}')

    if not pairs:
        return None
    return '\\n'.join(pairs)


def write_gtk3_theme(theme_name, color_overrides, is_dark=False):
    """Write GTK3 theme files to ~/.local/share/themes/<theme_name>/gtk-3.0/.

    Creates a proper GTK3 theme directory that can be selected in any
    GTK3 theme manager. The theme inherits Adwaita structurally and
    applies colour overrides on top.

    Args:
        theme_name: name for the generated theme directory
        color_overrides: dict of {gtk4_variable_name: hex_value}
        is_dark: whether to use dark variant as base

    Returns:
        str: path to the created theme directory
    """
    theme_dir = os.path.join(
        os.path.expanduser('~/.local/share/themes'),
        theme_name, 'gtk-3.0')
    os.makedirs(theme_dir, exist_ok=True)

    # Write main gtk.css
    css = build_gtk3_dark_css(color_overrides) if is_dark else build_gtk3_css(color_overrides)
    with open(os.path.join(theme_dir, 'gtk.css'), 'w') as f:
        f.write(css)

    # Write gtk-dark.css variant (always provide both)
    dark_css = build_gtk3_dark_css(color_overrides)
    with open(os.path.join(theme_dir, 'gtk-dark.css'), 'w') as f:
        f.write(dark_css)

    return os.path.dirname(theme_dir)


def apply_gtk3_colors_to_settings(color_overrides, settings_path):
    """Write @define-color overrides to ~/.config/gtk-3.0/gtk.css.
    Writes clean -- no cruft, no appending, full replacement.

    Args:
        color_overrides: dict of {gtk4_variable_name: hex_value}
        settings_path: path to gtk-3.0/gtk.css
    """
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    with open(settings_path, 'w') as f:
        f.write('/* DwarvenThemer4GTK -- GTK3 colour overrides */\n')
        f.write('/* Generated on Apply -- do not edit manually */\n\n')
        for name, value in sorted(color_overrides.items()):
            f.write(f'@define-color {name} {value};\n')


def apply_gtk2_colors_to_gtkrc(color_overrides, gtkrc_path):
    """Write gtk-color-scheme to ~/.gtkrc-2.0.
    Writes clean -- no cruft, no appending, full replacement.

    Args:
        color_overrides: dict of {gtk4_variable_name: hex_value}
        gtkrc_path: path to .gtkrc-2.0
    """
    color_scheme = build_gtk2_color_scheme(color_overrides)
    if not color_scheme:
        return

    with open(gtkrc_path, 'w') as f:
        f.write('# DwarvenThemer4GTK -- GTK2 colour overrides\n')
        f.write('# Generated on Apply -- do not edit manually\n\n')
        f.write(f'gtk-color-scheme = "{color_scheme}"\n')


def downconvert_theme_gtk4_to_gtk3(theme_dir, out_dir):
    """Downconvert a GTK4 theme to GTK3 format.

    Reads @define-color declarations from theme's gtk-4.0/gtk.css,
    writes a gtk-3.0/gtk.css that imports Adwaita GTK3 as base and
    overrides the colour variables. Since GTK3 and GTK4 use identical
    @define-color variable names, this is a 1:1 colour mapping.

    Args:
        theme_dir: path to the source theme directory (contains gtk-4.0/)
        out_dir: path to write the GTK3 theme (will create gtk-3.0/ inside)

    Returns:
        (bool, str): (success, message)
    """
    import os

    gtk4_css = os.path.join(theme_dir, 'gtk-4.0', 'gtk.css')
    if not os.path.exists(gtk4_css):
        return False, f'No gtk-4.0/gtk.css found in {theme_dir}'

    # Extract colour variables from GTK4 theme
    colors = extract_colors_from_css(gtk4_css)

    # Also check for colors.css in the theme
    gtk4_colors = os.path.join(theme_dir, 'gtk-4.0', 'colors.css')
    if os.path.exists(gtk4_colors):
        colors.update(extract_colors_from_css(gtk4_colors))

    # Write GTK3 theme
    import shutil
    out_gtk3 = os.path.join(out_dir, 'gtk-3.0')
    # Wipe and recreate -- no cruft from previous runs
    if os.path.exists(out_gtk3):
        shutil.rmtree(out_gtk3)
    os.makedirs(out_gtk3)

    css = build_gtk3_css(colors)
    with open(os.path.join(out_gtk3, 'gtk.css'), 'w') as f:
        f.write(css)

    dark_css = build_gtk3_dark_css(colors)
    with open(os.path.join(out_gtk3, 'gtk-dark.css'), 'w') as f:
        f.write(dark_css)

    return True, f'GTK3 theme written to {out_gtk3}'


def downconvert_theme_gtk4_to_gtk2(theme_dir, gtkrc_path, extra_settings=None):
    """Downconvert a GTK4 theme's colours to GTK2 gtkrc format.

    Maps GTK4 @define-color colour variables to GTK2's gtk-color-scheme
    setting. The structural styling (engine, widget shapes) is inherited
    from whatever GTK2 theme is currently active.

    Args:
        theme_dir: path to the source theme directory (contains gtk-4.0/)
        gtkrc_path: path to write the GTK2 gtkrc file
        extra_settings: optional dict of additional gtk2 key=value settings

    Returns:
        (bool, str): (success, message)
    """
    import os

    gtk4_css = os.path.join(theme_dir, 'gtk-4.0', 'gtk.css')
    colors = {}
    if os.path.exists(gtk4_css):
        colors = extract_colors_from_css(gtk4_css)
        gtk4_colors = os.path.join(theme_dir, 'gtk-4.0', 'colors.css')
        if os.path.exists(gtk4_colors):
            colors.update(extract_colors_from_css(gtk4_colors))

    apply_gtk2_colors_to_gtkrc(colors, gtkrc_path)

    return True, f'GTK2 colours written to {gtkrc_path}'
