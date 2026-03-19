"""DwarvenThemer main application window."""
import os, subprocess, configparser
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango

try:
    gi.require_version("GdkWayland", "4.0")
    from gi.repository import GdkWayland
    _HAS_WAYLAND = True
except (ValueError, ImportError):
    GdkWayland = None
    _HAS_WAYLAND = False

try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
    _HAS_X11 = True
except (ValueError, ImportError):
    GdkX11 = None
    _HAS_X11 = False

from .constants import (
    USER_ICON_DIR, APP_NAME,
    CFG_GTK4, CFG_GTK3, CFG_GTK2, GTK4_CSS, GTK3_CSS,
    COLORS_GTK4, COLORS_GTK3, CURSOR_CFG,
    ICON_DIRS, MANAGED_COLORS, MANAGED_KEYS,
    PREVIEW_CURSORS,
)
from .config import (
    read_ini, write_ini, write_gtk4_settings, write_dwarven_suite_settings,
    write_gtk2_key, gset,
    read_colors_css, write_colors_css, ensure_css_imports_colors,
)
from .theme_detect import detect_theme_dark, adwaita_fallback_theme
from .theme_find import (
    find_widget_themes, find_icon_themes, find_cursor_themes,
    current,
)
from .cursor import (
    get_theme_native_size, xcursor_to_texture, find_cursor_file,
)
from .ui_helpers import (
    make_scrolled_listbox, make_install_bar, make_listbox_row,
    make_section_frame_columns,
    make_combo_row, make_check_row, make_fallback_label,
)
from .icon_names import ICON_LEGACY_NAMES
from .downconvert import (
    downconvert_theme_gtk4_to_gtk2, downconvert_theme_gtk4_to_gtk3,
    apply_gtk3_colors_to_settings, apply_gtk2_colors_to_gtkrc,
)

class DwarvenThemer(Gtk.ApplicationWindow):

    SAMPLE_ICONS = [
        'folder', 'folder-open', 'user-home', 'user-desktop', 'user-trash',
        'document-new', 'document-open', 'document-save',
        'edit-copy', 'edit-cut', 'edit-paste', 'edit-undo',
        'go-home', 'go-up', 'go-previous', 'go-next', 'view-refresh',
        'preferences-system', 'help-about', 'application-exit',
        'image-x-generic', 'text-x-generic', 'application-x-executable',
    ]

    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(780, 540)
        self.set_icon_name('preferences-desktop-theme')
        self._changed  = False
        self._suppress = False     # suppress signal re-entrancy
        self._cursor_fallbacks = {}  # {theme_name: set(cursor_names that used fallback)}
        self._icon_fallbacks   = {}  # {theme_name: set(icon_names that used fallback)}


        self._load_current()

        # Focus tracking: preview cursor lives only on our surfaces
        self.connect('notify::is-active', self._on_focus_changed)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(outer)

        self._nb = Gtk.Notebook()
        self._nb.set_vexpand(True)
        outer.append(self._nb)

        self._build_widget_tab()
        self._build_color_tab()
        self._build_icon_tab()
        self._build_cursor_tab()
        self._build_font_tab()
        self._build_wm_tab()
        self._build_other_tab()

        # Bottom bar -- fixed height so long status messages never resize the window
        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_margin_start(8); bar.set_margin_end(8)
        bar.set_margin_top(6);   bar.set_margin_bottom(6)
        bar.set_size_request(-1, 52)  # enough for 3 lines, never grows

        self._status = Gtk.Label(label='')
        self._status.set_hexpand(True)
        self._status.set_halign(Gtk.Align.START)
        self._status.set_valign(Gtk.Align.START)
        self._status.set_wrap(True)
        self._status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._status.set_max_width_chars(60)
        self._status.set_size_request(-1, -1)  # natural size within fixed bar
        bar.append(self._status)

        self._chk_gtk3 = Gtk.CheckButton(label='Apply to GTK3')
        self._chk_gtk2 = Gtk.CheckButton(label='Apply to GTK2')
        bar.append(self._chk_gtk3)
        bar.append(self._chk_gtk2)

        btn_revert = Gtk.Button(label='Revert')
        btn_revert.connect('clicked', self._on_revert)
        bar.append(btn_revert)

        btn_apply = Gtk.Button(label='Apply')
        btn_apply.add_css_class('suggested-action')
        btn_apply.connect('clicked', self._on_apply)
        bar.append(btn_apply)

        outer.append(bar)

    # ---- state ---------------------------------------------------- #

    def _load_current(self):
        self._widget_theme = current('gtk-theme-name', 'Adwaita')
        self._icon_theme   = current('gtk-icon-theme-name', 'hicolor')
        self._cursor_theme = current('gtk-cursor-theme-name', '')
        self._cursor_size  = int(current('gtk-cursor-theme-size', '24') or '24')
        self._font_name    = current('gtk-font-name', 'Sans 10')
        self._antialias    = current('gtk-xft-antialias',  '1') == '1'
        self._hinting      = current('gtk-xft-hinting',   '1') == '1'
        self._hint_style   = current('gtk-xft-hintstyle', 'hintslight')
        self._rgba         = current('gtk-xft-rgba', 'rgb')
        # Dark mode -- read from gsettings color-scheme first (authoritative),
        # fall back to gtk-application-prefer-dark-theme
        try:
            import subprocess
            r = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'],
                capture_output=True, text=True, timeout=2)
            scheme = r.stdout.strip().strip("'")
            if scheme == 'prefer-dark':
                self._dark_mode = True
            elif scheme == 'prefer-light':
                self._dark_mode = False
            else:  # 'default' -- fall back to theme detection
                self._dark_mode = detect_theme_dark(self._widget_theme, False)
        except Exception:
            self._dark_mode = current('gtk-application-prefer-dark-theme', 'false') == 'true'
        # Decoration layout -- dconf takes priority for GNOME apps,
        # fall back to GTK settings.ini
        try:
            import subprocess
            r = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.wm.preferences', 'button-layout'],
                capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout.strip():
                self._deco_layout = r.stdout.strip().strip("'")
            else:
                self._deco_layout = current('gtk-decoration-layout', 'icon:minimize,maximize,close')
        except Exception:
            self._deco_layout  = current('gtk-decoration-layout', 'icon:minimize,maximize,close')
        self._colors       = read_colors_css(COLORS_GTK4)
        TB_STYLE_MAP = {
            'GTK_TOOLBAR_ICONS':      2,
            'GTK_TOOLBAR_TEXT':       3,
            'GTK_TOOLBAR_BOTH':       4,
            'GTK_TOOLBAR_BOTH_HORIZ': 3,
        }
        TB_SIZE_MAP = {
            'GTK_ICON_SIZE_MENU':          1,
            'GTK_ICON_SIZE_SMALL_TOOLBAR': 2,
            'GTK_ICON_SIZE_LARGE_TOOLBAR': 3,
            'GTK_ICON_SIZE_BUTTON':        4,
            'GTK_ICON_SIZE_DND':           5,
            'GTK_ICON_SIZE_DIALOG':        6,
        }
        def _read_gtk3_only(key, default):
            # Legacy GTK3 settings -- read from [X-DwarvenSuite] in settings.ini,
            # falling back to GTK3 config for migration from pre-DwarvenSuite setups
            return (read_ini(CFG_GTK4, 'X-DwarvenSuite', key, '')
                    or read_ini(CFG_GTK3, 'Settings', key, default))

        def _read_gtk4_or_gtk3(key, default):
            # Valid GTK4 GtkSettings properties -- GTK4 is source of truth
            return current(key, '') or read_ini(CFG_GTK3, 'Settings', key, default)

        raw_style = _read_gtk3_only('gtk-toolbar-style',    '3')
        raw_size  = _read_gtk3_only('gtk-toolbar-icon-size', '3')
        self._tb_style     = TB_STYLE_MAP.get(raw_style) or (int(raw_style) if raw_style.isdigit() else 3)
        self._tb_icon_size = TB_SIZE_MAP.get(raw_size)   or (int(raw_size)  if raw_size.isdigit()  else 3)
        self._btn_images   = _read_gtk3_only('gtk-button-images', 'false').lower() == 'true'
        self._menu_images  = _read_gtk3_only('gtk-menu-images',   'false').lower() == 'true'
        self._event_sounds   = _read_gtk4_or_gtk3('gtk-enable-event-sounds',          '0') == '1'
        self._input_sounds   = _read_gtk4_or_gtk3('gtk-enable-input-feedback-sounds', '0') == '1'
        self._a11y           = _read_gtk4_or_gtk3('gtk-enable-accels',      'true').lower() == 'true'
        # GTK4-native settings (new in GTK4 or always valid)
        self._animations     = current('gtk-enable-animations',   'true').lower()  == 'true'
        self._overlay_scroll = current('gtk-overlay-scrolling',   'true').lower()  == 'true'
        self._cursor_blink   = current('gtk-cursor-blink',        'true').lower()  == 'true'
        self._cursor_blink_time = int(current('gtk-cursor-blink-time', '1200') or '1200')
        self._dialogs_header = current('gtk-dialogs-use-header',  'true').lower()  == 'true'
        self._error_bell     = current('gtk-error-bell',          'true').lower()  == 'true'
        self._hint_metrics   = current('gtk-hint-font-metrics',   'false').lower() == 'true'
        self._sound_theme    = current('gtk-sound-theme-name',    'freedesktop')
        self._wm_theme       = ''   # selection from WM tab list (informational only)

    def _set(self, attr, val):
        """Set attribute and mark changed."""
        setattr(self, attr, val)
        self._mark_changed()

    def _mark_changed(self):
        self._changed = True
        self._status.set_text('Unsaved changes')

    # ---- Tab 1: Widget -------------------------------------------- #

    def _build_widget_tab(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_margin_start(8); paned.set_margin_end(8)
        paned.set_margin_top(8);   paned.set_margin_bottom(8)

        left, lb, rows, _ = make_scrolled_listbox(self._on_widget_selected)
        self._widget_lb   = lb
        self._widget_rows = rows

        for name in find_widget_themes():
            row = make_listbox_row(name, name)
            lb.append(row)
            rows[name] = row

        paned.set_start_child(left)
        paned.set_position(200)
        self._widget_paned = paned
        paned.set_end_child(self._make_widget_preview())
        self._nb.append_page(paned, Gtk.Label(label='Main Theme'))

        self._suppress = True
        if self._widget_theme in rows:
            lb.select_row(rows[self._widget_theme])
        self._suppress = False

    def _refresh_widget_preview(self):
        """Destroy and recreate the preview widget."""
        old = self._widget_paned.get_end_child()
        if old:
            self._widget_paned.set_end_child(None)
        self._widget_paned.set_end_child(self._make_widget_preview())

    def _recreate_window(self):
        """Recreate the entire window so all widgets read fresh GtkSettings.
        Preserves current tab, window size, and suppresses _load_current
        re-reading from disk by immediately restoring in-memory state."""
        app = self.get_application()

        # Save everything we need to restore
        current_tab   = self._nb.get_current_page()
        width, height = self.get_width(), self.get_height()
        widget_theme  = self._widget_theme
        dark_mode     = self._dark_mode

        # Close without triggering quit
        self.disconnect_by_func(app._on_close)
        self.close()

        # Fresh window -- all widgets read current GtkSettings from scratch
        new_win = DwarvenThemer(app)
        new_win.connect('close-request', app._on_close)
        new_win.set_default_size(width, height)
        new_win.present()

        # Restore in-memory state so listbox shows the correct selection
        new_win._suppress = True
        if widget_theme in new_win._widget_rows:
            new_win._widget_lb.select_row(new_win._widget_rows[widget_theme])
        new_win._dark_cb.set_active(dark_mode)
        new_win._suppress = False
        new_win._nb.set_current_page(current_tab)
        new_win._changed = True
        new_win._status.set_text('Unsaved changes')

        return False

    def _make_widget_preview(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(12);   box.set_margin_bottom(12)

        hdr = Gtk.Label()
        hdr.set_markup('<b>Live preview</b>')
        hdr.set_halign(Gtk.Align.START)
        box.append(hdr)

        frame = Gtk.Frame()
        grid  = Gtk.Grid()
        grid.set_row_spacing(8); grid.set_column_spacing(8)
        grid.set_margin_start(10); grid.set_margin_end(10)
        grid.set_margin_top(10);  grid.set_margin_bottom(10)
        frame.set_child(grid)

        grid.attach(Gtk.Button(label='Normal'), 0, 0, 1, 1)
        b_sug = Gtk.Button(label='Suggested')
        b_sug.add_css_class('suggested-action')
        grid.attach(b_sug, 1, 0, 1, 1)
        b_des = Gtk.Button(label='Destructive')
        b_des.add_css_class('destructive-action')
        grid.attach(b_des, 2, 0, 1, 1)

        entry = Gtk.Entry()
        entry.set_placeholder_text('Text entry…')
        entry.set_hexpand(True)
        grid.attach(entry, 0, 1, 2, 1)
        sp = Gtk.Spinner()
        sp.start()
        grid.attach(sp, 2, 1, 1, 1)

        grid.attach(Gtk.CheckButton(label='Checkbox'), 0, 2, 1, 1)
        sw = Gtk.Switch()
        sw.set_active(True)
        sw.set_halign(Gtk.Align.START)
        grid.attach(sw, 1, 2, 1, 1)
        pb = Gtk.ProgressBar()
        pb.set_fraction(0.65)
        pb.set_hexpand(True)
        grid.attach(pb, 2, 2, 1, 1)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_value(40)
        scale.set_hexpand(True)
        grid.attach(scale, 0, 3, 3, 1)

        rb1 = Gtk.CheckButton(label='Option A')
        rb2 = Gtk.CheckButton(label='Option B')
        rb2.set_group(rb1)
        rb2.set_active(True)
        rb3 = Gtk.CheckButton(label='Option C')
        rb3.set_group(rb1)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hb.append(rb1); hb.append(rb2); hb.append(rb3)
        grid.attach(hb, 0, 4, 3, 1)

        box.append(frame)

        self._dark_cb = Gtk.CheckButton(label='Invert light/dark')
        self._dark_cb.set_margin_top(4)
        self._dark_cb.set_active(self._dark_mode)
        self._dark_cb.set_tooltip_text(
            'Unchecked: theme displays in its natural light/dark state.\n'
            'Checked: inverts -- a light theme goes dark, a dark theme goes light.')
        self._dark_cb.connect('toggled', self._on_dark_mode)
        box.append(self._dark_cb)

        return box

    def _on_widget_selected(self, _lb, row):
        if self._suppress or row is None:
            return
        self._widget_theme = row.theme_name
        theme_is_dark = detect_theme_dark(self._widget_theme, False)
        self._dark_mode = theme_is_dark

        # Preview: process-local GtkSettings only.
        # DwarvenReset is the reference reset theme -- always use it as the
        # intermediate to force a full GTK style rebuild. No special cases.
        # Use a genuinely different base theme as intermediate.
        # HighContrast and Adwaita are different bases -- GTK must do full rebuild.
        # For HighContrast-base themes, use Adwaita. For everything else, use HighContrast.
        hc_base = {'HighContrast', 'HighContrastInverse'}
        if self._widget_theme in hc_base:
            # HC variants share a base -- use Adwaita:dark as intermediate
            # (different enough from both HC variants to force full rebuild)
            intermediate = 'Adwaita:dark' if not theme_is_dark else 'Adwaita'
        else:
            intermediate = 'HighContrast'
        gset().set_property('gtk-application-prefer-dark-theme', theme_is_dark)
        gset().set_property('gtk-theme-name', intermediate)
        gset().set_property('gtk-theme-name', self._widget_theme)
        for win in self.get_application().get_windows():
            win.queue_draw()

        # Reset invert checkbox without triggering _on_dark_mode
        self._suppress = True
        self._dark_cb.set_active(False)
        self._suppress = False
        self._mark_changed()

    def _on_dark_mode(self, cb):
        if self._suppress:
            return
        theme_is_dark = detect_theme_dark(self._widget_theme, False)
        inverted = not theme_is_dark if cb.get_active() else theme_is_dark
        self._dark_mode = inverted
        hc_base = {'HighContrast', 'HighContrastInverse'}
        if self._widget_theme in hc_base:
            # For HC themes, swap to the explicit opposite theme name rather than
            # using the prefer-dark flag -- GTK caches prefer-dark+HC as HCInverse
            # and skips the rebuild. Explicit name swap forces it.
            target = 'HighContrastInverse' if inverted else 'HighContrast'
            gset().set_property('gtk-application-prefer-dark-theme', inverted)
            gset().set_property('gtk-theme-name', 'Adwaita')
            gset().set_property('gtk-theme-name', target)
            self._widget_theme = target
        else:
            gset().set_property('gtk-application-prefer-dark-theme', inverted)
            gset().set_property('gtk-theme-name', 'HighContrast')
            gset().set_property('gtk-theme-name', self._widget_theme)
        for win in self.get_application().get_windows():
            win.queue_draw()
        self._mark_changed()

    # ---- Tab 2: Colors -------------------------------------------- #

    def _build_color_tab(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_start(12); outer.set_margin_end(12)
        outer.set_margin_top(12);   outer.set_margin_bottom(12)

        info = Gtk.Label()
        info.set_markup(
            'Color overrides are written to <tt>~/.config/gtk-4.0/colors.css</tt>.\n'
            'These override the active theme palette without modifying theme files.')
        info.set_halign(Gtk.Align.START)
        info.set_wrap(True)
        outer.append(info)

        self._enable_colors = Gtk.CheckButton(label='Enable custom color overrides')
        self._enable_colors.set_active(
            bool(self._colors) and
            any(k in self._colors for k in MANAGED_KEYS))
        self._enable_colors.connect('toggled', self._on_colors_toggled)
        outer.append(self._enable_colors)

        self._color_buttons = {}

        self._color_grid_box = Gtk.Box()
        outer.append(self._color_grid_box)

        # Pairs: (bg, fg)
        pairs = [
            (MANAGED_COLORS[0], MANAGED_COLORS[1], 'Window'),
            (MANAGED_COLORS[2], MANAGED_COLORS[3], 'Text area'),
            (MANAGED_COLORS[4], MANAGED_COLORS[5], 'Selection'),
            (MANAGED_COLORS[6], MANAGED_COLORS[7], 'Tooltip'),
        ]

        def make_color_btn(key, default):
            btn = Gtk.ColorDialogButton()
            btn.set_dialog(Gtk.ColorDialog())
            rgba = Gdk.RGBA()
            if not rgba.parse(self._colors.get(key, default)):
                rgba.parse(default)
            btn.set_rgba(rgba)
            btn.connect('notify::rgba', self._on_color_changed, key)
            self._color_buttons[key] = btn
            return btn

        # Pre-build all buttons once
        for (bg_key, _bl, bg_def), (fg_key, _fl, fg_def), _name in pairs:
            if bg_key not in self._color_buttons:
                make_color_btn(bg_key, bg_def)
            if fg_key not in self._color_buttons:
                make_color_btn(fg_key, fg_def)

        def build_color_grid():
            # Unparent colour buttons before removing old grid
            for btn in self._color_buttons.values():
                parent = btn.get_parent()
                if parent:
                    parent.remove(btn)
            # Remove old grid
            child = self._color_grid_box.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                self._color_grid_box.remove(child)
                child = nxt

            g = Gtk.Grid()
            g.set_row_spacing(10)
            g.set_column_spacing(16)

            # col0: row label  col1: bg btn  col2: fg btn
            bg_hdr = Gtk.Label(); bg_hdr.set_markup('<b>Background</b>')
            fg_hdr = Gtk.Label(); fg_hdr.set_markup('<b>Foreground</b>')
            bg_hdr.set_halign(Gtk.Align.START)
            fg_hdr.set_halign(Gtk.Align.START)
            g.attach(bg_hdr, 1, 0, 1, 1)
            g.attach(fg_hdr, 2, 0, 1, 1)
            for row, ((bg_key, _bl, _bd), (fg_key, _fl, _fd), name) in enumerate(pairs):
                lbl = Gtk.Label(label=name + ':')
                lbl.set_halign(Gtk.Align.START)
                g.attach(lbl,                              0, row+1, 1, 1)
                g.attach(self._color_buttons[bg_key],      1, row+1, 1, 1)
                g.attach(self._color_buttons[fg_key],      2, row+1, 1, 1)


            self._color_grid_box.append(g)
            self._color_grid = g

        build_color_grid()

        # Set initial sensitivity on individual buttons
        enabled = bool(self._colors) and any(k in self._colors for k in MANAGED_KEYS)
        for b in self._color_buttons.values():
            b.set_sensitive(enabled)

        btn_reset = Gtk.Button(label='Reset to theme defaults')
        btn_reset.connect('clicked', self._on_colors_reset)
        outer.append(btn_reset)

        self._nb.append_page(outer, Gtk.Label(label='Colors'))

    def _on_colors_toggled(self, btn):
        active = btn.get_active()
        for b in self._color_buttons.values():
            b.set_sensitive(active)
        self._mark_changed()

    def _on_color_changed(self, btn, _param, key):
        rgba = btn.get_rgba()
        r, g, b = int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255)
        self._colors[key] = f'#{r:02x}{g:02x}{b:02x}'
        self._apply_colors_live()
        self._mark_changed()

    def _apply_colors_live(self):
        """Apply colour overrides as process-local CSS provider.
        Only affects DT4GTK process. Zero system impact, crash-safe."""
        if not self._colors:
            if hasattr(self, '_colors_provider'):
                Gtk.StyleContext.remove_provider_for_display(
                    self.get_display(), self._colors_provider)
                del self._colors_provider
            return

        def safe_hex(val):
            if val and val.startswith('#') and len(val) in (4, 7):
                return val
            return None

        bg     = safe_hex(self._colors.get('theme_bg_color'))
        fg     = safe_hex(self._colors.get('theme_fg_color'))
        base   = safe_hex(self._colors.get('theme_base_color'))
        text   = safe_hex(self._colors.get('theme_text_color'))
        sel_bg = safe_hex(self._colors.get('theme_selected_bg_color'))
        sel_fg = safe_hex(self._colors.get('theme_selected_fg_color'))
        tip_bg = safe_hex(self._colors.get('tooltip_background_color'))
        tip_fg = safe_hex(self._colors.get('tooltip_foreground_color'))

        parts = []

        if bg or fg:
            p = ('background-color: ' + bg + '; ' if bg else '') + ('color: ' + fg + ';' if fg else '')
            # Buttons use background-image gradient -- must clear it to show background-color
            bp = ('background-image: none; background-color: ' + bg + '; ' if bg else '') + ('color: ' + fg + ';' if fg else '')
            parts.append(f'.background, window, widget {{ {p} }}')
            parts.append(f'headerbar, .titlebar {{ {p} }}')
            parts.append(f'notebook, stack, box, paned {{ {p} }}')
            parts.append(f'button, button:hover, button:active, button:checked {{ {bp} }}')
            parts.append(f'label {{ {"color: " + fg + ";" if fg else ""} }}')
            parts.append(f'checkbutton, radiobutton {{ {"color: " + fg + ";" if fg else ""} }}')
            parts.append(f'scale, progressbar, levelbar {{ {p} }}')
            parts.append(f'frame {{ {p} }}')
            parts.append(f'scrollbar {{ {p} }}')

        if base or text:
            p = ('background-color: ' + base + '; ' if base else '') + ('color: ' + text + ';' if text else '')
            parts.append(f'.view, iconview, textview > text, entry, entry > text {{ {p} }}')
            parts.append(f'spinbutton > text, spinbutton {{ {p} }}')
            parts.append(f'listview, listbox, treeview {{ {p} }}')
            parts.append(f'combobox, dropdown {{ {p} }}')

        if sel_bg or sel_fg:
            p = ('background-color: ' + sel_bg + '; ' if sel_bg else '') + ('color: ' + sel_fg + ';' if sel_fg else '')
            parts.append(f'*:selected, selection {{ {p} }}')
            parts.append(f'row:selected, listbox row:selected {{ {p} }}')

        if tip_bg or tip_fg:
            p = ('background-color: ' + tip_bg + '; ' if tip_bg else '') + ('color: ' + tip_fg + ';' if tip_fg else '')
            parts.append(f'tooltip, tooltip label {{ {p} }}')

        css = '\n'.join(parts)
        if not hasattr(self, '_colors_provider'):
            self._colors_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(), self._colors_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._colors_provider.load_from_data(css.encode())

    def _on_colors_reset(self, _btn):
        self._colors = {}
        for key, _label, default in MANAGED_COLORS:
            rgba = Gdk.RGBA()
            rgba.parse(default)
            self._color_buttons[key].set_rgba(rgba)
        self._apply_colors_live()
        self._mark_changed()

    # ---- Tab 3: Icons --------------------------------------------- #

    def _build_icon_tab(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_margin_start(8); paned.set_margin_end(8)
        paned.set_margin_top(8);   paned.set_margin_bottom(8)

        left_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left, lb, rows, _ = make_scrolled_listbox(self._on_icon_selected)
        self._icon_lb   = lb
        self._icon_rows = rows
        left_outer.append(left)

        for name, disp in find_icon_themes():
            row = make_listbox_row(name, disp)
            lb.append(row)
            rows[name] = row

        left_outer.append(make_install_bar(
            self, USER_ICON_DIR,
            lambda ok, n: self._theme_installed(ok, n, 'icon'),
            lambda ok, n: self._theme_removed(ok, n, 'icon'),
            lambda: getattr(self._icon_lb.get_selected_row(), 'theme_name', None),
        ))
        paned.set_start_child(left_outer)
        paned.set_position(200)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_margin_start(8); right.set_margin_top(8)
        lbl = Gtk.Label(label='Sample icons from selected theme:')
        lbl.set_halign(Gtk.Align.START)
        right.append(lbl)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self._icon_scroll = scroll  # keep ref for dark bg updates
        self._icon_flow = Gtk.FlowBox()
        self._icon_flow.set_max_children_per_line(6)
        self._icon_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._icon_flow.set_row_spacing(4)
        self._icon_flow.set_column_spacing(4)
        scroll.set_child(self._icon_flow)
        right.append(scroll)
        paned.set_end_child(right)

        self._nb.append_page(paned, Gtk.Label(label='Icons'))

        self._suppress = True
        if self._icon_theme in rows:
            lb.select_row(rows[self._icon_theme])
        self._suppress = False
        self._refresh_icon_preview()

    def _get_icon_theme_checker(self, theme_name):
        """Return a GtkIconTheme instance for the given theme name.
        Cached per-theme -- creating GtkIconTheme is cheap but not free."""
        if not hasattr(self, '_icon_theme_checkers'):
            self._icon_theme_checkers = {}
        if theme_name not in self._icon_theme_checkers:
            t = Gtk.IconTheme.new()
            t.set_search_path(ICON_DIRS)
            t.set_theme_name(theme_name)
            self._icon_theme_checkers[theme_name] = t
        return self._icon_theme_checkers[theme_name]

    def _icon_exists_in_theme(self, theme_name, icon_name):
        """Check if an icon exists in the given theme.
        Returns (found: bool, actual_name: str, is_legacy: bool).
        Lookup order: XDG canonical -> symbolic variant -> GTK3/GTK2 legacy names.
        Falls back to (True, icon_name, False) on error -- no false positives."""
        if not theme_name:
            return False, icon_name, False
        try:
            checker = self._get_icon_theme_checker(theme_name)

            # 1. XDG canonical name
            if checker.has_icon(icon_name):
                return True, icon_name, False

            # 2. Symbolic variant of canonical name
            sym = icon_name + '-symbolic'
            if checker.has_icon(sym):
                return True, sym, False

            # 3. Legacy GTK3/GTK2 names
            for legacy in ICON_LEGACY_NAMES.get(icon_name, []):
                if checker.has_icon(legacy):
                    return True, legacy, True  # found but under legacy name

            # 4. Live display theme as tiebreaker (different search paths)
            try:
                live = Gtk.IconTheme.get_for_display(self.get_display())
                if live and live.get_theme_name() == theme_name:
                    if live.has_icon(icon_name) or live.has_icon(sym):
                        return True, icon_name, False
            except Exception:
                pass

            return False, icon_name, False
        except Exception:
            return True, icon_name, False  # assume exists on error

    def _refresh_icon_preview(self):
        """Populate icon preview, tracking any icons missing from the theme.
        Sets a dark background when the icon theme is dark so symbolic
        icons (white-on-transparent) are visible."""
        child = self._icon_flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._icon_flow.remove(child)
            child = nxt

        # Dark themes use white/light symbolic icons -- need dark preview bg
        is_dark = detect_theme_dark(self._widget_theme, self._dark_mode)
        if is_dark:
            self._icon_scroll.add_css_class('icon-preview-dark')
        else:
            self._icon_scroll.remove_css_class('icon-preview-dark')

        # Reset icon fallback tracking for current theme
        if self._icon_theme:
            self._icon_fallbacks[self._icon_theme] = set()

        # Get Adwaita checker for explicit fallback icon loading
        adwaita_checker = self._get_icon_theme_checker('Adwaita')

        for name in self.SAMPLE_ICONS:
            found, actual_name, is_legacy = self._icon_exists_in_theme(
                self._icon_theme, name)

            # Only flag as Adwaita fallback if truly missing AND Adwaita has it
            used_adwaita = (not found
                            and self._icon_theme not in ('', 'Adwaita')
                            and (adwaita_checker.has_icon(name)
                                 or adwaita_checker.has_icon(name + '-symbolic')))

            if used_adwaita:
                self._icon_fallbacks.setdefault(self._icon_theme, set()).add(name)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

            if used_adwaita:
                if adwaita_checker.has_icon(name):
                    adwaita_name = name
                elif adwaita_checker.has_icon(name + '-symbolic'):
                    adwaita_name = name + '-symbolic'
                else:
                    adwaita_name = 'image-missing'
                # Must load from Adwaita explicitly -- new_from_icon_name uses current theme
                paintable = adwaita_checker.lookup_icon(
                    adwaita_name, None, 32, 1,
                    Gtk.TextDirection.NONE, Gtk.IconLookupFlags(0))
                img = Gtk.Image.new_from_paintable(paintable)
            else:
                img = Gtk.Image.new_from_icon_name(actual_name)

            img.set_pixel_size(32)
            img.set_tooltip_text(name)

            lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            lbl = Gtk.Label(label=name.split("-")[-1][:8])
            lbl.set_max_width_chars(8)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl_box.append(lbl)
            if used_adwaita:
                lbl_box.append(make_fallback_label())

            vbox.append(img)
            vbox.append(lbl_box)
            self._icon_flow.append(vbox)

    def _on_icon_selected(self, _lb, row):
        if self._suppress or row is None:
            return
        self._icon_theme = row.theme_name
        # Invalidate checker cache for fresh lookup
        if hasattr(self, '_icon_theme_checkers'):
            self._icon_theme_checkers.pop(self._icon_theme, None)
        gset().set_property('gtk-icon-theme-name', self._icon_theme)
        GLib.idle_add(self._refresh_icon_preview)
        self._mark_changed()

    # ---- Tab 4: Cursors ------------------------------------------- #

    def _build_cursor_tab(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_margin_start(8); paned.set_margin_end(8)
        paned.set_margin_top(8);   paned.set_margin_bottom(8)

        left_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left, lb, rows, _ = make_scrolled_listbox(self._on_cursor_selected)
        self._cursor_lb   = lb
        self._cursor_rows = rows
        left_outer.append(left)

        for name, disp in find_cursor_themes():
            row = make_listbox_row(name, disp)
            lb.append(row)
            rows[name] = row

        left_outer.append(make_install_bar(
            self, USER_ICON_DIR,
            lambda ok, n: self._theme_installed(ok, n, 'cursor'),
            lambda ok, n: self._theme_removed(ok, n, 'cursor'),
            lambda: getattr(self._cursor_lb.get_selected_row(), 'theme_name', None),
        ))
        paned.set_start_child(left_outer)
        paned.set_position(200)

        # Right side: size slider + cursor preview grid
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right.set_margin_start(12); right.set_margin_top(12)
        right.set_margin_end(8)

        size_lbl = Gtk.Label(label='Cursor size:')
        size_lbl.set_halign(Gtk.Align.START)
        right.append(size_lbl)

        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        size_box.append(Gtk.Label(label='Smaller'))
        self._cursor_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 8, 128, 2)
        self._cursor_scale.set_value(self._cursor_size)
        self._cursor_scale.set_hexpand(True)
        self._cursor_scale.set_digits(0)
        self._cursor_scale.connect('value-changed', self._on_cursor_size)
        size_box.append(self._cursor_scale)
        size_box.append(Gtk.Label(label='Bigger'))
        right.append(size_box)

        # Cursor preview: toggle bar + stack
        prev_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        prev_hdr.set_margin_top(8)
        prev_lbl = Gtk.Label(label='Preview:')
        prev_lbl.set_halign(Gtk.Align.START)
        prev_lbl.set_hexpand(True)
        prev_hdr.append(prev_lbl)

        # Grid/List toggle buttons
        toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        toggle_box.add_css_class('linked')
        self._cursor_view_grid_btn = Gtk.ToggleButton()
        self._cursor_view_grid_btn.set_icon_name('view-grid-symbolic')
        self._cursor_view_grid_btn.set_tooltip_text('Grid view')
        self._cursor_view_grid_btn.set_active(True)
        self._cursor_view_list_btn = Gtk.ToggleButton()
        self._cursor_view_list_btn.set_icon_name('view-list-symbolic')
        self._cursor_view_list_btn.set_tooltip_text('List view')
        self._cursor_view_list_btn.set_group(self._cursor_view_grid_btn)
        toggle_box.append(self._cursor_view_grid_btn)
        toggle_box.append(self._cursor_view_list_btn)
        prev_hdr.append(toggle_box)
        right.append(prev_hdr)

        # Stack: grid view + list view
        self._cursor_preview_stack = Gtk.Stack()
        self._cursor_preview_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._cursor_preview_stack.set_vexpand(True)

        # --- Grid view ---
        scroll_grid = Gtk.ScrolledWindow()
        scroll_grid.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._cursor_preview_flowbox = Gtk.FlowBox()
        self._cursor_preview_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._cursor_preview_flowbox.set_max_children_per_line(4)
        self._cursor_preview_flowbox.set_min_children_per_line(2)
        self._cursor_preview_flowbox.set_row_spacing(8)
        self._cursor_preview_flowbox.set_column_spacing(8)
        self._cursor_preview_flowbox.set_margin_top(4)
        scroll_grid.set_child(self._cursor_preview_flowbox)
        self._cursor_preview_stack.add_named(scroll_grid, 'grid')

        # --- List view ---
        scroll_list = Gtk.ScrolledWindow()
        scroll_list.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._cursor_preview_listgrid = Gtk.Grid()
        self._cursor_preview_listgrid.set_row_spacing(6)
        self._cursor_preview_listgrid.set_column_spacing(12)
        self._cursor_preview_listgrid.set_margin_top(4)
        scroll_list.set_child(self._cursor_preview_listgrid)
        self._cursor_preview_stack.add_named(scroll_list, 'list')

        right.append(self._cursor_preview_stack)

        # Wire toggle
        self._cursor_view_grid_btn.connect(
            'toggled', self._on_cursor_view_toggle)

        note = Gtk.Label()
        note.set_markup(
            '<i>Cursor theme changes take full effect at next login.\n'
            'Running applications may not update immediately.</i>')
        note.set_wrap(True)
        note.set_halign(Gtk.Align.START)
        note.set_margin_top(4)
        right.append(note)

        paned.set_end_child(right)
        self._nb.append_page(paned, Gtk.Label(label='Cursors'))

        self._suppress = True
        if self._cursor_theme in rows:
            lb.select_row(rows[self._cursor_theme])
        self._suppress = False
        self._refresh_cursor_preview(self._cursor_theme)

    def _on_cursor_view_toggle(self, btn):
        if btn.get_active():
            self._cursor_preview_stack.set_visible_child_name('grid')
        else:
            self._cursor_preview_stack.set_visible_child_name('list')

    def _refresh_cursor_preview(self, theme_name):
        """Populate both grid and list cursor previews.
        Tracks which cursors used Adwaita fallback for this theme."""
        # Reset fallback tracking for this theme
        if theme_name:
            self._cursor_fallbacks[theme_name] = set()
        self._refresh_cursor_grid(theme_name)
        self._refresh_cursor_list(theme_name)

    def _clear_widget(self, widget):
        child = widget.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            widget.remove(child)
            child = nxt

    def _make_cursor_image(self, theme_name, cursor_name, size=None):
        """Returns (img_widget, used_fallback: bool).
        If the theme lacks the cursor, falls back to Adwaita silently.
        Effective size is soft-capped at the theme's native max size so:
        - Slider can go to 96px but a 24px-max theme still shows at 24px
        - Adwaita fallback cursors are fetched at the same effective size
          as the theme's own cursors -- visually consistent grid."""
        if size is None:
            size = self._cursor_size
        used_fallback = False

        # Soft-cap: find the largest size this theme actually has <= requested
        effective_size = get_theme_native_size(theme_name, size)

        path   = find_cursor_file(theme_name, cursor_name)
        result = xcursor_to_texture(path, effective_size) if path else None

        if not result and theme_name != 'Adwaita':
            # Theme missing this cursor -- fetch Adwaita at SAME effective_size
            # so fallback icons match the theme's own cursor sizes visually
            path   = find_cursor_file('Adwaita', cursor_name)
            result = xcursor_to_texture(path, effective_size) if path else None
            if result:
                used_fallback = True

        if result:
            texture, actual_w, actual_h = result
            img = Gtk.Picture.new_for_paintable(texture)
            # SCALE_DOWN: never upscale, only shrink if somehow oversized
            img.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
            img.set_halign(Gtk.Align.CENTER)
            img.set_valign(Gtk.Align.CENTER)
            img.set_size_request(actual_w, actual_h)
        else:
            # Nothing found even in Adwaita
            img = Gtk.Image.new_from_icon_name('image-missing')
            img.set_pixel_size(max(16, effective_size // 2))
            img.set_halign(Gtk.Align.CENTER)
            img.set_valign(Gtk.Align.CENTER)
            img.set_size_request(effective_size, effective_size)

        return img, used_fallback

    def _refresh_cursor_grid(self, theme_name):
        fb = self._cursor_preview_flowbox
        self._clear_widget(fb)
        if not theme_name:
            return
        for cursor_name, label in PREVIEW_CURSORS:
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            cell.set_halign(Gtk.Align.CENTER)
            img, used_fallback = self._make_cursor_image(theme_name, cursor_name)
            if used_fallback and theme_name:
                self._cursor_fallbacks.setdefault(theme_name, set()).add(cursor_name)

            lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            name_lbl = Gtk.Label(label=label)
            name_lbl.set_halign(Gtk.Align.CENTER)
            name_lbl.set_max_width_chars(12)
            name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl_box.append(name_lbl)
            if used_fallback:
                lbl_box.append(make_fallback_label())

            cell.append(img)
            cell.append(lbl_box)
            fb.append(cell)

    def _refresh_cursor_list(self, theme_name):
        grid = self._cursor_preview_listgrid
        self._clear_widget(grid)
        if not theme_name:
            return
        for row_idx, (cursor_name, label) in enumerate(PREVIEW_CURSORS):
            img, used_fallback = self._make_cursor_image(theme_name, cursor_name)
            if used_fallback and theme_name:
                self._cursor_fallbacks.setdefault(theme_name, set()).add(cursor_name)

            name_lbl = Gtk.Label(label=label)
            name_lbl.set_halign(Gtk.Align.START)
            name_lbl.set_valign(Gtk.Align.CENTER)

            if used_fallback:
                lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                lbl_box.append(name_lbl)
                lbl_box.append(make_fallback_label())
                grid.attach(img,     0, row_idx, 1, 1)
                grid.attach(lbl_box, 1, row_idx, 1, 1)
            else:
                grid.attach(img,     0, row_idx, 1, 1)
                grid.attach(name_lbl,1, row_idx, 1, 1)

    def _apply_live_cursor(self, theme_name):
        """Set preview cursor on DwarvenThemer's own surfaces ONLY.
        Never touches GtkSettings, env vars, or any system-wide state.
        When our window loses focus, system cursor resumes automatically.
        Dirty close is a non-issue -- preview was never system-wide."""
        if not self.get_surface():
            return False

        if theme_name:
            # Build cursor from our parsed texture for exact size match
            path   = find_cursor_file(theme_name, 'default')
            result = xcursor_to_texture(path, self._cursor_size) if path else None
            if result:
                texture, _w, _h = result
                cursor = Gdk.Cursor.new_from_texture(texture, 0, 0, None)
            else:
                cursor = Gdk.Cursor.new_from_name('default', None)
        else:
            cursor = None

        # Only set on our own surfaces -- system cursor unchanged
        for win in self.get_application().get_windows():
            surface = win.get_surface()
            if surface:
                surface.set_cursor(cursor)

        return False

    def _restore_system_cursor(self):
        """Remove our preview cursor -- surfaces revert to system cursor."""
        for win in self.get_application().get_windows():
            surface = win.get_surface()
            if surface:
                surface.set_cursor(None)

    def _on_focus_changed(self, win, _param):
        """When we gain focus: show preview cursor.
        When we lose focus: system cursor resumes automatically via set_cursor(None)."""
        if win.is_active():
            if self._cursor_theme:
                self._apply_live_cursor(self._cursor_theme)
        else:
            self._restore_system_cursor()



    def _on_cursor_selected(self, _lb, row):
        if self._suppress or row is None:
            return
        self._cursor_theme = row.theme_name
        gset().set_property('gtk-cursor-theme-name', self._cursor_theme)
        self._refresh_cursor_preview(self._cursor_theme)
        GLib.idle_add(self._apply_live_cursor, self._cursor_theme)
        self._mark_changed()

    def _on_cursor_size(self, scale):
        self._cursor_size = int(scale.get_value())
        gset().set_property('gtk-cursor-theme-size', self._cursor_size)
        self._refresh_cursor_preview(self._cursor_theme)
        GLib.idle_add(self._apply_live_cursor, self._cursor_theme)
        self._mark_changed()

    def _build_font_tab(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_start(16); outer.set_margin_end(16)
        outer.set_margin_top(16);   outer.set_margin_bottom(16)

        # ---- Font selector row ----
        font_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label='Default font:')
        lbl.set_halign(Gtk.Align.START)
        font_row.append(lbl)

        self._font_btn = Gtk.FontDialogButton()
        self._font_btn.set_dialog(Gtk.FontDialog())
        desc = Pango.FontDescription.from_string(self._font_name)
        self._font_btn.set_font_desc(desc)
        self._font_btn.set_hexpand(False)
        self._font_btn.set_halign(Gtk.Align.START)
        # Calculate min width from longest installed font name
        try:
            gi.require_version('PangoCairo', '1.0')
            from gi.repository import PangoCairo
            ctx = PangoCairo.font_map_get_default().create_context()
            families = PangoCairo.font_map_get_default().list_families()
            longest = max(
                (f'{f.get_name()} {face.get_face_name()}'
                 for f in families for face in f.list_faces()),
                key=len, default='Sans Regular')
            layout = Pango.Layout(ctx)
            layout.set_text(longest + ' 10', -1)
            pw, _ph = layout.get_pixel_size()
            min_w = pw + 80
        except Exception:
            min_w = 320
        self._font_btn.set_size_request(min_w, -1)
        self._font_btn.connect('notify::font-desc', self._on_font_changed)
        font_row.append(self._font_btn)
        outer.append(font_row)

        # ---- Preview ----
        self._font_preview = Gtk.Label(
            label='The quick brown fox jumps over the lazy dog. 0123456789')
        self._font_preview.set_wrap(True)
        self._font_preview.set_halign(Gtk.Align.START)
        self._update_font_preview(desc)
        outer.append(self._font_preview)

        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # ---- Antialiasing + Hinting checkboxes side by side ----
        check_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self._aa_check = Gtk.CheckButton(label='Enable antialiasing')
        self._aa_check.set_active(self._antialias)
        self._aa_check.connect('toggled', lambda b: self._set('_antialias', b.get_active()))
        self._hint_check = Gtk.CheckButton(label='Enable hinting')
        self._hint_check.set_active(self._hinting)
        self._hint_check.connect('toggled', lambda b: self._set('_hinting', b.get_active()))
        check_row.append(self._aa_check)
        check_row.append(self._hint_check)
        outer.append(check_row)

        # ---- Hinting style + Sub-pixel geometry side by side ----
        render_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        hint_lbl = Gtk.Label(label='Hinting style:')
        hint_lbl.set_halign(Gtk.Align.START)
        self._hint_combo = Gtk.DropDown.new_from_strings(
            ['None', 'Slight', 'Medium', 'Full'])
        hint_map = {'hintnone': 0, 'hintslight': 1, 'hintmedium': 2, 'hintfull': 3}
        self._hint_combo.set_selected(hint_map.get(self._hint_style, 1))
        self._hint_combo.set_hexpand(False)
        self._hint_combo.connect('notify::selected', self._on_hint_style)

        rgba_lbl = Gtk.Label(label='Sub-pixel geometry:')
        rgba_lbl.set_halign(Gtk.Align.START)
        self._rgba_combo = Gtk.DropDown.new_from_strings(
            ['None', 'RGB', 'BGR', 'VRGB', 'VBGR'])
        rgba_map = {'none': 0, 'rgb': 1, 'bgr': 2, 'vrgb': 3, 'vbgr': 4}
        self._rgba_combo.set_selected(rgba_map.get(self._rgba.lower(), 1))
        self._rgba_combo.set_hexpand(False)
        self._rgba_combo.connect('notify::selected', self._on_rgba)

        render_row.append(hint_lbl)
        render_row.append(self._hint_combo)
        render_row.append(rgba_lbl)
        render_row.append(self._rgba_combo)
        outer.append(render_row)

        self._nb.append_page(outer, Gtk.Label(label='Font'))

    def _update_font_preview(self, desc):
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_font_desc_new(desc))
        self._font_preview.set_attributes(attrs)

    def _on_font_changed(self, btn, _param):
        desc = btn.get_font_desc()
        if desc:
            self._font_name = desc.to_string()
            gset().set_property('gtk-font-name', self._font_name)
            self._update_font_preview(desc)
            self._mark_changed()

    def _on_hint_style(self, combo, _param):
        styles = ['hintnone', 'hintslight', 'hintmedium', 'hintfull']
        self._hint_style = styles[combo.get_selected()]
        self._mark_changed()

    def _on_rgba(self, combo, _param):
        modes = ['none', 'rgb', 'bgr', 'vrgb', 'vbgr']
        self._rgba = modes[combo.get_selected()]
        self._mark_changed()

    # ---- Tab 6: Window Border ------------------------------------- #

    # Button tokens and their display labels
    DECO_TOKENS = {
        'close':    'Close  ✕',
        'minimize': 'Minimize  ─',
        'maximize': 'Maximize  □',
        'icon':     'App Icon',
        'menu':     'Menu',
        'spacer':   'Spacer  |',
    }

    def _parse_deco_layout(self, layout):
        """Parse 'left:right' into ([left tokens], [right tokens])."""
        parts = layout.split(':') if ':' in layout else ['', layout]
        def tokens(s):
            return [t.strip() for t in s.split(',') if t.strip()]
        return tokens(parts[0]), tokens(parts[1] if len(parts) > 1 else '')

    def _build_deco_layout(self, left, right):
        """Build 'left:right' string from token lists."""
        return ','.join(left) + ':' + ','.join(right)

    def _build_wm_tab(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_start(16); outer.set_margin_end(16)
        outer.set_margin_top(16);   outer.set_margin_bottom(16)

        # Explanation
        info = Gtk.Label()
        info.set_markup(
'<b>GTK4 Headerbar Button Layout</b>\n'
            'Sets button layout for GTK4 apps using client-side decorations (headerbars).\n'
            'DwarvenSuite apps honour this fully. Some apps may hardcode their own layout.\n'
            'Changes take effect when apps are next launched.')
        info.set_halign(Gtk.Align.START)
        info.set_wrap(True)
        outer.append(info)

        # Preview bar -- looks like an actual headerbar
        preview_frame = Gtk.Frame()
        preview_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        preview_box.set_margin_start(8); preview_box.set_margin_end(8)
        preview_box.set_margin_top(6);   preview_box.set_margin_bottom(6)
        preview_box.add_css_class('deco-preview')
        self._deco_left_preview  = Gtk.Box(spacing=4)
        self._deco_title_preview = Gtk.Label(label='App Title')
        self._deco_title_preview.set_hexpand(True)
        self._deco_title_preview.set_halign(Gtk.Align.CENTER)
        self._deco_right_preview = Gtk.Box(spacing=4)
        self._deco_right_preview.set_halign(Gtk.Align.END)
        preview_box.append(self._deco_left_preview)
        preview_box.append(self._deco_title_preview)
        preview_box.append(self._deco_right_preview)
        preview_frame.set_child(preview_box)
        outer.append(preview_frame)

        # Left side editor
        left_lbl = Gtk.Label()
        left_lbl.set_markup('<b>Left side</b>')
        left_lbl.set_halign(Gtk.Align.START)
        outer.append(left_lbl)
        self._deco_left_box = Gtk.Box(spacing=6)
        outer.append(self._deco_left_box)

        # Right side editor
        right_lbl = Gtk.Label()
        right_lbl.set_markup('<b>Right side</b>')
        right_lbl.set_halign(Gtk.Align.START)
        outer.append(right_lbl)
        self._deco_right_box = Gtk.Box(spacing=6)
        outer.append(self._deco_right_box)

        # Available buttons pool
        pool_lbl = Gtk.Label()
        pool_lbl.set_markup('<b>Available buttons</b>  (click to add)')
        pool_lbl.set_halign(Gtk.Align.START)
        outer.append(pool_lbl)
        pool_box = Gtk.Box(spacing=6)
        outer.append(pool_box)

        for token, label in self.DECO_TOKENS.items():
            btn = Gtk.Button(label=label)
            btn.connect('clicked', self._on_deco_pool_add, token)
            pool_box.append(btn)

        # Preset buttons
        preset_lbl = Gtk.Label()
        preset_lbl.set_markup('<b>Presets</b>')
        preset_lbl.set_halign(Gtk.Align.START)
        outer.append(preset_lbl)
        preset_box = Gtk.Box(spacing=6)
        presets = [
            ('GNOME',       'icon:minimize,maximize,close'),
            ('macOS style', 'close,minimize,maximize:'),
            ('Right only',  ':minimize,maximize,close'),
            ('Minimal',     ':close'),
        ]
        for name, layout in presets:
            btn = Gtk.Button(label=name)
            btn.connect('clicked', lambda b, l=layout: self._apply_deco_layout(l))
            preset_box.append(btn)
        outer.append(preset_box)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(outer)
        self._nb.append_page(scroll, Gtk.Label(label='Window Border'))

        # Initial render
        self._refresh_deco_editor()

    def _make_deco_token_button(self, token, side):
        """Create a button representing a token in left/right editor."""
        box = Gtk.Box(spacing=4)
        lbl = Gtk.Label(label=self.DECO_TOKENS.get(token, token))
        rm  = Gtk.Button(label='✕')
        rm.set_has_frame(False)
        rm.add_css_class('flat')
        rm.connect('clicked', self._on_deco_remove, token, side)
        box.append(lbl)
        box.append(rm)
        frame = Gtk.Frame()
        frame.set_child(box)
        return frame

    def _refresh_deco_editor(self):
        left_tokens, right_tokens = self._parse_deco_layout(self._deco_layout)

        # Clear and rebuild left editor
        child = self._deco_left_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._deco_left_box.remove(child)
            child = nxt
        for token in left_tokens:
            self._deco_left_box.append(self._make_deco_token_button(token, 'left'))
        add_l = Gtk.Button(label='+ Add')
        add_l.connect('clicked', self._on_deco_add_left)
        self._deco_left_box.append(add_l)

        # Clear and rebuild right editor
        child = self._deco_right_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._deco_right_box.remove(child)
            child = nxt
        for token in right_tokens:
            self._deco_right_box.append(self._make_deco_token_button(token, 'right'))
        add_r = Gtk.Button(label='+ Add')
        add_r.connect('clicked', self._on_deco_add_right)
        self._deco_right_box.append(add_r)

        # Rebuild preview
        child = self._deco_left_preview.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._deco_left_preview.remove(child)
            child = nxt
        child = self._deco_right_preview.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._deco_right_preview.remove(child)
            child = nxt

        for token in left_tokens:
            lbl = Gtk.Label(label=self.DECO_TOKENS.get(token, token))
            lbl.set_margin_end(4)
            self._deco_left_preview.append(lbl)
        for token in right_tokens:
            lbl = Gtk.Label(label=self.DECO_TOKENS.get(token, token))
            lbl.set_margin_start(4)
            self._deco_right_preview.append(lbl)

    def _apply_deco_layout(self, layout):
        self._deco_layout = layout
        self._set('_deco_layout', layout)
        gset().set_property('gtk-decoration-layout', layout)
        self._refresh_deco_editor()

    def _on_deco_remove(self, _btn, token, side):
        left, right = self._parse_deco_layout(self._deco_layout)
        if side == 'left' and token in left:
            left.remove(token)
        elif side == 'right' and token in right:
            right.remove(token)
        self._apply_deco_layout(self._build_deco_layout(left, right))

    def _on_deco_pool_add(self, _btn, token):
        """Add token to right side by default."""
        left, right = self._parse_deco_layout(self._deco_layout)
        right.append(token)
        self._apply_deco_layout(self._build_deco_layout(left, right))

    def _on_deco_add_left(self, _btn):
        self._show_deco_picker('left')

    def _on_deco_add_right(self, _btn):
        self._show_deco_picker('right')

    def _show_deco_picker(self, side):
        """Popover picker for adding a token to left or right."""
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(8); box.set_margin_end(8)
        box.set_margin_top(8);   box.set_margin_bottom(8)
        for token, label in self.DECO_TOKENS.items():
            btn = Gtk.Button(label=label)
            btn.connect('clicked', self._on_deco_pick, token, side, popover)
            box.append(btn)
        popover.set_child(box)
        if side == 'left':
            popover.set_parent(self._deco_left_box)
        else:
            popover.set_parent(self._deco_right_box)
        popover.popup()

    def _on_deco_pick(self, _btn, token, side, popover):
        popover.popdown()
        left, right = self._parse_deco_layout(self._deco_layout)
        if side == 'left':
            left.append(token)
        else:
            right.append(token)
        self._apply_deco_layout(self._build_deco_layout(left, right))

    # ---- Tab 7: Other --------------------------------------------- #

    def _build_other_tab(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_start(16); outer.set_margin_end(16)
        outer.set_margin_top(16);   outer.set_margin_bottom(16)
        scroll.set_child(outer)

        self._other_sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.append(self._other_sections)

        def rebuild_sections(cols):
            self._other_cols = cols
            child = self._other_sections.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                self._other_sections.remove(child)
                child = nxt
            sf = lambda t, w: make_section_frame_columns(t, w, cols)

            self._other_sections.append(sf('Behaviour', [
                make_check_row('Enable animations',
                    self._animations,
                    lambda b: self._set('_animations', b.get_active())),
                make_check_row('Overlay scrollbars',
                    self._overlay_scroll,
                    lambda b: self._set('_overlay_scroll', b.get_active())),
                make_check_row('Dialogs use header bars',
                    self._dialogs_header,
                    lambda b: self._set('_dialogs_header', b.get_active())),
                make_check_row('Error bell',
                    self._error_bell,
                    lambda b: self._set('_error_bell', b.get_active())),
                make_check_row('Hint font metrics',
                    self._hint_metrics,
                    lambda b: self._set('_hint_metrics', b.get_active())),
            ]))

            self._other_sections.append(sf('Cursor', [
                make_check_row('Blink cursor',
                    self._cursor_blink,
                    lambda b: self._set('_cursor_blink', b.get_active())),
                make_combo_row('Blink speed:',
                    ['Slow (1800ms)', 'Normal (1200ms)', 'Fast (600ms)'],
                    {1800: 0, 1200: 1, 600: 2}.get(self._cursor_blink_time, 1),
                    lambda c, _p: self._set('_cursor_blink_time',
                                            [1800, 1200, 600][c.get_selected()])),
            ]))

            self._other_sections.append(make_section_frame_columns('Sound', [
                make_check_row('Play event sounds',
                    self._event_sounds,
                    lambda b: self._set('_event_sounds', b.get_active())),
                make_check_row('Play input feedback sounds',
                    self._input_sounds,
                    lambda b: self._set('_input_sounds', b.get_active())),
            ], cols=2))

            self._other_sections.append(make_section_frame_columns('Accessibility', [
                make_check_row('Enable keyboard accelerators',
                    self._a11y,
                    lambda b: self._set('_a11y', b.get_active())),
            ], cols=1))

            self._other_sections.append(sf('Legacy GTK3 (DwarvenSuite soft defaults)', [
                make_combo_row('Toolbar style:',
                    ['Icons only', 'Text only', 'Text below icons', 'Text beside icons'],
                    max(0, self._tb_style - 2),
                    lambda c, _p: self._set('_tb_style', c.get_selected() + 2)),
                make_combo_row('Toolbar icon size:',
                    ['Same as menu', 'Small toolbar', 'Large toolbar', 'Button', 'DnD', 'Dialog'],
                    max(0, self._tb_icon_size - 1),
                    lambda c, _p: self._set('_tb_icon_size', c.get_selected() + 1)),
                make_check_row('Show images in buttons',
                    self._btn_images,
                    lambda b: self._set('_btn_images', b.get_active())),
                make_check_row('Show images in menus',
                    self._menu_images,
                    lambda b: self._set('_menu_images', b.get_active())),
            ]))

        def make_other_frame(title, content_widget):
            f = Gtk.Frame()
            hdr = Gtk.Label()
            hdr.set_markup(f'<b>{title}</b>')
            f.set_label_widget(hdr)
            f.set_label_align(0.0)
            f.set_child(content_widget)
            return f

        # One SizeGroup per column position -- enforces identical width
        # across all sections so column boundaries align globally
        col_groups = [Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
                      for _ in range(3)]

        def make_cols():
            """3 equal columns sharing a SizeGroup -- column boundaries
            align across all sections on the tab."""
            outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            outer.set_hexpand(True)
            outer.set_margin_start(12); outer.set_margin_end(8)
            outer.set_margin_top(6);    outer.set_margin_bottom(8)
            cols = []
            for i in range(3):
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                col.set_hexpand(True)
                col.set_halign(Gtk.Align.FILL)
                col_groups[i].add_widget(col)
                outer.append(col)
                cols.append(col)
            return outer, cols

        def make_check(label, attr):
            cb = Gtk.CheckButton(label=label)
            cb.set_active(getattr(self, attr))
            cb.set_hexpand(True)
            cb.connect('toggled', lambda b, a=attr: self._set(a, b.get_active()))
            return cb

        def make_drop(options, attr, offset=0, values=None):
            dd = Gtk.DropDown.new_from_strings(options)
            cur = getattr(self, attr)
            if values:
                dd.set_selected(values.index(cur) if cur in values else 0)
                dd.connect('notify::selected',
                    lambda c, _p, v=values, a=attr: self._set(a, v[c.get_selected()]))
            else:
                dd.set_selected(max(0, cur - offset))
                dd.connect('notify::selected',
                    lambda c, _p, o=offset, a=attr: self._set(a, c.get_selected() + o))
            dd.set_hexpand(False)
            dd.set_halign(Gtk.Align.START)
            return dd

        def olbl(text):
            l = Gtk.Label(label=text)
            l.set_halign(Gtk.Align.START)
            return l

        def build_sections():
            child = self._other_sections.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                self._other_sections.remove(child)
                child = nxt

            # Behaviour
            # col0               col1                  col2
            # X animations       X overlay scroll      X dialogs header
            # X error bell       X hint metrics
            outer, c = make_cols()
            c[0].append(make_check('Enable animations',       '_animations'))
            c[0].append(make_check('Error bell',              '_error_bell'))
            c[1].append(make_check('Overlay scrollbars',      '_overlay_scroll'))
            c[1].append(make_check('Hint font metrics',       '_hint_metrics'))
            c[2].append(make_check('Dialogs use header bars', '_dialogs_header'))
            self._other_sections.append(make_other_frame('Behaviour', outer))

            # Cursor
            # col0          col1              col2
            # X blink       Blink speed:      (empty)
            #               [dropdown]
            outer, c = make_cols()
            c[0].append(make_check('Blink cursor', '_cursor_blink'))
            c[1].append(olbl('Blink speed:'))
            c[1].append(make_drop(['Slow (1800ms)', 'Normal (1200ms)', 'Fast (600ms)'],
                                  '_cursor_blink_time', values=[1800, 1200, 600]))
            self._other_sections.append(make_other_frame('Cursor', outer))

            # Sound
            # col0              col1                   col2
            # X play event      X play input           (empty)
            outer, c = make_cols()
            c[0].append(make_check('Play event sounds',          '_event_sounds'))
            c[1].append(make_check('Play input feedback sounds', '_input_sounds'))
            self._other_sections.append(make_other_frame('Sound', outer))

            # Accessibility
            # col0         col1    col2
            # X accels
            outer, c = make_cols()
            c[0].append(make_check('Enable keyboard accelerators', '_a11y'))
            self._other_sections.append(make_other_frame('Accessibility', outer))

            # Legacy GTK3
            # col0              col1               col2
            # X img buttons     Toolbar style:     Toolbar icon size:
            # X img menus       [dropdown]         [dropdown]
            outer, c = make_cols()
            c[0].append(make_check('Show images in buttons', '_btn_images'))
            c[0].append(make_check('Show images in menus',   '_menu_images'))
            c[1].append(olbl('Toolbar style:'))
            c[1].append(make_drop(['Icons only', 'Text only',
                                   'Text below icons', 'Text beside icons'],
                                  '_tb_style', offset=2))
            c[2].append(olbl('Toolbar icon size:'))
            c[2].append(make_drop(['Same as menu', 'Small toolbar',
                                   'Large toolbar', 'Button', 'DnD', 'Dialog'],
                                  '_tb_icon_size', offset=1))
            self._other_sections.append(make_other_frame(
                'Legacy GTK3 (DwarvenSuite soft defaults)', outer))

        build_sections()

        self._nb.append_page(scroll, Gtk.Label(label='Other'))

    # ---- Install / remove callbacks ------------------------------- #

    def _theme_installed(self, ok, name, kind):
        self._status.set_text(f'Installed: {name}' if ok else f'Install failed: {name}')
        if ok:
            self._reload_list(kind)

    def _theme_removed(self, ok, name, kind):
        self._status.set_text(
            f'Removed: {name}' if ok
            else f'Cannot remove system theme: {name}')
        if ok:
            self._reload_list(kind)

    def _reload_list(self, kind):
        if kind == 'icon':
            self._repopulate(self._icon_lb, self._icon_rows,
                             find_icon_themes(), pairs=True)
        elif kind == 'cursor':
            self._repopulate(self._cursor_lb, self._cursor_rows,
                             find_cursor_themes(), pairs=True)

    def _repopulate(self, lb, rows, themes, pairs=False):
        child = lb.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            lb.remove(child)
            child = nxt
        rows.clear()
        for item in themes:
            name, disp = item if pairs else (item, item)
            row = make_listbox_row(name, disp)
            lb.append(row)
            rows[name] = row

    # ---- Apply / Revert ------------------------------------------- #

    def _on_apply(self, _btn):
        sync3 = self._chk_gtk3.get_active()
        sync2 = self._chk_gtk2.get_active()

        write_gtk4_settings({
            'gtk-theme-name':                     self._widget_theme,
            'gtk-icon-theme-name':                self._icon_theme,
            'gtk-cursor-theme-name':              self._cursor_theme,
            'gtk-cursor-theme-size':              str(self._cursor_size),
            'gtk-font-name':                      self._font_name,
            'gtk-xft-antialias':                  '1' if self._antialias else '0',
            'gtk-xft-hinting':                    '1' if self._hinting   else '0',
            'gtk-xft-hintstyle':                  self._hint_style,
            'gtk-xft-rgba':                       self._rgba,
            'gtk-application-prefer-dark-theme':  'true' if self._dark_mode else 'false',
            'gtk-decoration-layout':              self._deco_layout,
            # Valid GTK4 GtkSettings properties
            'gtk-enable-event-sounds':            '1' if self._event_sounds else '0',
            'gtk-enable-input-feedback-sounds':   '1' if self._input_sounds else '0',
            'gtk-enable-accels':                  'true' if self._a11y else 'false',
            'gtk-enable-animations':              'true' if self._animations else 'false',
            'gtk-overlay-scrolling':              'true' if self._overlay_scroll else 'false',
            'gtk-cursor-blink':                   'true' if self._cursor_blink else 'false',
            'gtk-cursor-blink-time':              str(self._cursor_blink_time),
            'gtk-dialogs-use-header':             'true' if self._dialogs_header else 'false',
            'gtk-error-bell':                     'true' if self._error_bell else 'false',
            'gtk-hint-font-metrics':              'true' if self._hint_metrics else 'false',
            'gtk-sound-theme-name':               self._sound_theme,
        })

        if self._enable_colors.get_active() and self._colors:
            write_colors_css(COLORS_GTK4, self._colors)
            ensure_css_imports_colors(GTK4_CSS)
            if sync3:
                write_colors_css(COLORS_GTK3, self._colors)
                ensure_css_imports_colors(GTK3_CSS)
        elif not self._enable_colors.get_active():
            write_colors_css(COLORS_GTK4, {k: None for k in MANAGED_KEYS})
            # Remove @import from gtk.css so colors.css isn't loaded at all
            for css_path in (GTK4_CSS, GTK3_CSS):
                if os.path.exists(css_path):
                    with open(css_path) as f:
                        lines = f.readlines()
                    lines = [l for l in lines if "colors.css" not in l]
                    with open(css_path, 'w') as f:
                        f.writelines(lines)

        # Persist legacy GTK3 settings to [X-DwarvenSuite] in settings.ini.
        # GTK4 ignores unknown sections -- DwarvenSuite apps read them as soft defaults.
        write_dwarven_suite_settings({
            'gtk-toolbar-style':     str(self._tb_style),
            'gtk-toolbar-icon-size': str(self._tb_icon_size),
            'gtk-button-images':     'true' if self._btn_images else 'false',
            'gtk-menu-images':       'true' if self._menu_images else 'false',
        })

        if sync3:
            for key, val in [
                ('gtk-theme-name',                        self._widget_theme),
                ('gtk-icon-theme-name',                   self._icon_theme),
                ('gtk-cursor-theme-name',                 self._cursor_theme),
                ('gtk-cursor-theme-size',                 str(self._cursor_size)),
                ('gtk-font-name',                         self._font_name),
                ('gtk-xft-antialias',                     '1' if self._antialias else '0'),
                ('gtk-xft-hinting',                       '1' if self._hinting   else '0'),
                ('gtk-xft-hintstyle',                     self._hint_style),
                ('gtk-xft-rgba',                          self._rgba),
                ('gtk-toolbar-style',                     str(self._tb_style)),
                ('gtk-toolbar-icon-size',                 str(self._tb_icon_size)),
                ('gtk-button-images',                     'true' if self._btn_images else 'false'),
                ('gtk-menu-images',                       'true' if self._menu_images else 'false'),
                ('gtk-enable-event-sounds',               '1' if self._event_sounds else '0'),
                ('gtk-enable-input-feedback-sounds',      '1' if self._input_sounds else '0'),
                ('gtk-decoration-layout',                 self._deco_layout),
            ]:
                write_ini(CFG_GTK3, 'Settings', key, val)

        if sync2:
            write_gtk2_key('gtk-theme-name',        self._widget_theme)
            write_gtk2_key('gtk-icon-theme-name',   self._icon_theme)
            write_gtk2_key('gtk-cursor-theme-name', self._cursor_theme)
            write_gtk2_key('gtk-cursor-theme-size', str(self._cursor_size), quoted=False)
            write_gtk2_key('gtk-font-name',         self._font_name)

        # Downconvert GTK4 theme CSS to GTK3/2 formats
        # Find the theme directory for the selected widget theme
        from .constants import THEME_DIRS, USER_THEME_DIR
        theme_dir = None
        for d in THEME_DIRS:
            candidate = os.path.join(d, self._widget_theme)
            if os.path.isdir(os.path.join(candidate, 'gtk-4.0')):
                theme_dir = candidate
                break

        if theme_dir:
            if sync3:
                # Always downconvert to ~/.local/share/themes/ --
                # this creates/updates a GTK3 theme that inherits Adwaita
                # structurally and overrides colour variables from the GTK4 theme.
                out_dir = os.path.join(USER_THEME_DIR, self._widget_theme)
                ok, msg = downconvert_theme_gtk4_to_gtk3(theme_dir, out_dir)
                if not ok:
                    self._status.set_text(f'GTK3 downconvert: {msg}')

            if sync2:
                # Write GTK2 colour scheme to ~/.local/share/themes/<theme>/gtk-2.0/gtkrc
                gtkrc_path = os.path.join(
                    USER_THEME_DIR, self._widget_theme, 'gtk-2.0', 'gtkrc')
                os.makedirs(os.path.dirname(gtkrc_path), exist_ok=True)
                ok, msg = downconvert_theme_gtk4_to_gtk2(theme_dir, gtkrc_path)
                if not ok:
                    self._status.set_text(f'GTK2 downconvert: {msg}')

        # Apply colour overrides to GTK3/2 config directly (simpler path)
        if sync3 and self._enable_colors.get_active() and self._colors:
            apply_gtk3_colors_to_settings(self._colors, GTK3_CSS)
        if sync2 and self._enable_colors.get_active() and self._colors:
            apply_gtk2_colors_to_gtkrc(self._colors, CFG_GTK2)

        os.makedirs(os.path.dirname(CURSOR_CFG), exist_ok=True)
        with open(CURSOR_CFG, 'w') as f:
            f.write(f'[Icon Theme]\nInherits={self._cursor_theme}\n')

        # Write color-scheme to gsettings -- affects all GTK3/4 apps system-wide.
        # Only done on explicit Apply, never during preview.
        color_scheme = 'prefer-dark' if self._dark_mode else 'prefer-light'
        try:
            import subprocess
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.interface',
                 'color-scheme', color_scheme],
                capture_output=True, timeout=2)
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.wm.preferences',
                 'button-layout', self._deco_layout],
                capture_output=True, timeout=2)
        except Exception:
            pass

        self._try_notify_settings_daemons()


        # Patch any themes with missing icons/cursors -- XDG Inherits fallback
        is_dark = detect_theme_dark(self._widget_theme, self._dark_mode)
        fallback = adwaita_fallback_theme(is_dark)
        cursor_patched = self._write_cursor_theme_patch(self._cursor_theme)
        icon_patched   = self._write_icon_theme_patch(self._icon_theme)

        self._changed = False
        parts = ['Settings applied.']
        if cursor_patched:
            n = len(self._cursor_fallbacks.get(self._cursor_theme, set()))
            parts.append(f'Patched {n} cursor(s) in {self._cursor_theme}.')
        if icon_patched:
            n = len(self._icon_fallbacks.get(self._icon_theme, set()))
            parts.append(f'Patched {n} icon(s) in {self._icon_theme}.')
        if (cursor_patched or icon_patched):
            theme_type = 'dark' if is_dark else 'light'
            parts.append(f'Fallback: {fallback} ({theme_type} theme detected).')
        self._status.set_text(' '.join(parts))

    def _on_revert(self, _btn):
        self._load_current()
        self._suppress = True
        gset().set_property('gtk-theme-name',       self._widget_theme)
        gset().set_property('gtk-icon-theme-name',  self._icon_theme)
        gset().set_property('gtk-cursor-theme-name', self._cursor_theme)
        gset().set_property('gtk-font-name',        self._font_name)
        gset().set_property('gtk-application-prefer-dark-theme', self._dark_mode)
        gset().set_property('gtk-decoration-layout', self._deco_layout)
        for lb, rows, theme in [
            (self._widget_lb,  self._widget_rows,  self._widget_theme),
            (self._icon_lb,    self._icon_rows,    self._icon_theme),
            (self._cursor_lb,  self._cursor_rows,  self._cursor_theme),
        ]:
            if theme in rows:
                lb.select_row(rows[theme])
        self._dark_cb.set_active(self._dark_mode)
        self._cursor_scale.set_value(self._cursor_size)
        self._refresh_deco_editor()
        self._suppress = False
        self._changed = False
        self._status.set_text('Reverted')

    def _patch_icon_theme(self, theme_name, patched_set_key, note_key):
        """Write ~/.icons/<theme>/index.theme with Inherits=Adwaita.
        100% XDG spec. Works for both cursor themes and icon themes.
        Every cursor loader, GTK4, Qt, Wayland compositor honours Inherits.
        Only writes user-local copy -- system themes untouched."""
        if not theme_name or theme_name in ('Adwaita', 'Adwaita:dark'):
            return False
        fallbacks = getattr(self, patched_set_key, {}).get(theme_name, set())
        if not fallbacks:
            return False

        # Detect light/dark for accurate reporting
        is_dark = detect_theme_dark(self._widget_theme, self._dark_mode)
        fallback_name = adwaita_fallback_theme(is_dark)

        theme_dir = os.path.join(os.path.expanduser('~/.icons'), theme_name)
        idx_path  = os.path.join(theme_dir, 'index.theme')
        os.makedirs(theme_dir, exist_ok=True)

        cfg = configparser.ConfigParser()
        if os.path.exists(idx_path):
            cfg.read(idx_path)
        if 'Icon Theme' not in cfg:
            cfg['Icon Theme'] = {}
        section = cfg['Icon Theme']

        # Add fallback theme to Inherits -- spec-compliant inheritance chain
        inherits = [t.strip() for t in section.get('Inherits', '').split(',') if t.strip()]
        if fallback_name not in inherits:
            inherits.append(fallback_name)
            section['Inherits'] = ','.join(inherits)
        if 'Name' not in section:
            section['Name'] = theme_name

        # Record what was patched and with what -- informational
        section[note_key] = ','.join(sorted(fallbacks))
        section['X-DwarvenThemer-FallbackTheme'] = fallback_name
        section['X-DwarvenThemer-ThemeType'] = 'dark' if is_dark else 'light'

        with open(idx_path, 'w') as f:
            cfg.write(f)
        return True

    def _write_cursor_theme_patch(self, theme_name):
        return self._patch_icon_theme(
            theme_name, '_cursor_fallbacks', 'X-DwarvenThemer-PatchedCursors')

    def _write_icon_theme_patch(self, theme_name):
        return self._patch_icon_theme(
            theme_name, '_icon_fallbacks', 'X-DwarvenThemer-PatchedIcons')

        return True

    def _try_notify_settings_daemons(self):
        """Notify running settings daemons to reload.
        Handles both X11 (xsettingsd) and Wayland (xsettings-daemon, gsettings).
        Safe to call on either session type — silently skips what isn't running."""
        # X11: xsettingsd — SIGHUP to reload
        # Wayland: xsettings-daemon (if running under XWayland compat layer)
        for daemon in ('xsettingsd', 'xsettings-daemon'):
            try:
                result = subprocess.run(
                    ['pidof', daemon], capture_output=True, text=True)
                pid = result.stdout.strip()
                if pid:
                    subprocess.run(['kill', '-HUP', pid], check=False)
            except OSError:
                pass

        # Wayland / GNOME portal: GSettings propagates immediately since we
        # wrote to ~/.config/gtk-4.0/settings.ini which GTK re-reads on
        # next Gtk.Settings.reset_property() or app restart.
        # Nothing to explicitly signal here — file write is sufficient.


# ------------------------------------------------------------------ #
# Application                                                          #
# ------------------------------------------------------------------ #

