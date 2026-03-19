# DwarvenThemer4GTK

**GTK4 Appearance Manager - Takes the Crown from lxappearance. Python3 + GTK4. No apologies.**

A pure GTK4 appearance manager with live preview, full system-theme compliance, and automatic GTK3/2 downconversion. No GTK2/3 library dependency. Runs natively on X11 and Wayland.

## What Makes It Different

lxappearance was the go-to GTK appearance manager for years. It is GTK3-based, has no live preview, and cannot handle GTK4 themes. DwarvenThemer4GTK is its GTK4 successor:

- **Pure GTK4** - no GTK2/3 library dependency anywhere in the stack
- **Live preview** - theme, colour, cursor, and font changes reflected immediately in the app itself
- **GTK3/2 downconversion** - apply a GTK4 theme and it automatically generates compatible GTK3/2 versions
- **100% XDG spec compliant** - writes only to `~/.config/gtk-<version>/` and `~/.icons/`
- **Fixes what theme authors broke** - automatic Adwaita fallback patching for missing icons and cursors
- **Native X11 and Wayland** - no XWayland fallback needed

## Features

### Main Theme Tab
- GTK4-only theme list (no GTK3-only clutter)
- Live preview with real GTK4 widgets (buttons, entry, checkbox, switch, progress bar, scale, radio buttons)
- Auto-detects whether a theme is light or dark
- Invert light/dark toggle for any theme
- Filter box for large theme collections

### Colours Tab
- Override individual GTK colour variables without modifying theme files
- Live colour preview in the app itself
- Writes to `~/.config/gtk-4.0/colors.css` on Apply
- Background/Foreground paired layout, same as lxappearance

### Icons Tab
- Full icon theme browser with live preview grid
- Adwaita fallback detection -- shows which icons are missing from a theme
- Fallback icons loaded directly from Adwaita, clearly labelled
- Automatic `Inherits=Adwaita` patch written to `~/.icons/<theme>/index.theme` on Apply

### Cursors Tab
- Cursor theme browser with live preview of all standard cursor shapes
- Surface-local preview -- cursor changes are visible in the app without affecting the system until Apply
- Native size detection from xcursor files
- Adwaita fallback detection and patching

### Font Tab
- GTK4 FontDialogButton integration
- Live preview sentence in the selected font
- Font button width calculated from longest installed font name
- Antialiasing, hinting style, and sub-pixel geometry controls

### Window Border Tab
- Visual GTK4 headerbar button layout editor
- Left/right zone assignment for button tokens
- One-click presets (GNOME, macOS style, minimal)
- Writes to both `settings.ini` and dconf

### Other Tab
- GTK4-native settings: animations, overlay scrolling, cursor blink, dialog headers, error bell, font hint metrics
- Legacy GTK3 settings stored in `[X-DwarvenSuite]` section of `settings.ini` -- GTK4 ignores unknown sections; DwarvenSuite apps read them as informational soft-defaults only

### GTK3/2 Downconversion
- GTK3 and GTK4 use identical `@define-color` variable names (36 variables, verified)
- On Apply with "Apply to GTK3" checked: generates `gtk-3.0/gtk.css` that imports Adwaita GTK3 structurally and overrides colour variables. Full fidelity -- inherits all of GTK3 Adwaita's widget styling with custom colours on top
- On Apply with "Apply to GTK2" checked: writes `gtk-color-scheme` to `~/.local/share/themes/<n>/gtk-2.0/gtkrc` with mapped colour variables
- Clean write every time -- no cruft, no stale entries

## Installation

    pip install dwarventhemer4gtk

## Requirements

- Python 3.9+
- GTK4 (`python3-gi`, `gir1.2-gtk-4.0`)
- PyGObject (`python3-gi-cairo`)

On Debian/Ubuntu:

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0

On Slackware:

    # PyGObject and GTK4 are included in a full Slackware64-current install

## Running

    dwarventhemer4gtk

Or directly from the source directory:

    python3 dwarventhemer4gtk/__main__.py

## Architecture

DwarvenThemer4GTK follows strict separation of concerns:

| Module | Responsibility |
|--------|---------------|
| `constants.py` | Path constants, colour variable definitions, app identity |
| `config.py` | Read/write GTK settings.ini, colors.css, gtkrc |
| `theme_detect.py` | Dark/light detection via CSS luminance and explicit maps |
| `theme_find.py` | Discover installed GTK widget, icon, cursor themes |
| `cursor.py` | XCursor file parsing, size detection, theme resolution |
| `icon_names.py` | Freedesktop icon name legacy mapping for fallback detection |
| `ui_helpers.py` | Reusable GTK4 widget factories |
| `downconvert.py` | GTK4 to GTK3/2 theme downconversion |
| `window.py` | Main application window (DwarvenThemer class) |
| `app.py` | Application class and startup |

The bundled `reset_theme_data/themes/DwarvenReset/` is a complete GTK4 light theme sourced from `libgtk Default-light.css`. It is used internally as a clean intermediate state when switching themes to force GTK4 to fully rebuild its style pipeline. It never appears in the user-visible theme list.

## Design Philosophy

- **Only writes to `~/.config/gtk-<version>/` and `~/.icons/`** -- no system file modification, ever
- **Preview is process-local** -- cursor and colour previews never affect other running apps
- **Apply is explicit** -- nothing is committed to disk until the user clicks Apply
- **Clean writes** -- every Apply is a full replacement, no appended cruft
- **Modularity is life** -- each module has a single clear responsibility

## Other DwarvenSuite Projects

- **pip-search-ex** -- Modern PyPI package search. Fast, smart, beautiful. A complete replacement for the discontinued `pip search` command with unified search architecture, interactive TUI, and 20+ themes.

      pip install pip-search-ex

## Author

thedwarf -- gitdwarf

## Support / Tip Jar

If you find DwarvenThemer4GTK useful, you can support the project:

[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue?logo=paypal)](https://www.paypal.com/paypalme/gitdwarf)

## License

GPL-2.0-or-later -- see LICENSE file for details
