"""Reusable GTK4 UI component factories."""
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, GLib, Gio, Pango
from .theme_find import install_theme_archive, remove_theme

def make_scrolled_listbox(on_select):
    """Returns (outer_box, listbox, rows_dict, search_entry)."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

    search = Gtk.SearchEntry()
    search.set_placeholder_text('Filter…')
    search.set_margin_start(4); search.set_margin_end(4)
    search.set_margin_top(4);   search.set_margin_bottom(4)
    outer.append(search)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)
    scroll.set_min_content_width(180)
    outer.append(scroll)

    lb = Gtk.ListBox()
    lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
    lb.connect('row-selected', on_select)
    scroll.set_child(lb)

    rows = {}

    def on_search(entry):
        text = entry.get_text().lower()
        lb.set_filter_func(
            lambda row: not text or text in getattr(row, '_label', '').lower())
    search.connect('search-changed', on_search)

    return outer, lb, rows, search


def make_install_bar(parent_win, dest_dir, on_installed, on_removed, get_selected):
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    bar.set_margin_top(4)

    btn_install = Gtk.Button(label='Install…')
    btn_remove  = Gtk.Button(label='Remove')
    bar.append(btn_install)
    bar.append(btn_remove)

    def do_install(_btn):
        dlg = Gtk.FileDialog()
        dlg.set_title('Select theme archive')
        dlg.set_initial_folder(Gio.File.new_for_path(os.path.expanduser('~')))
        dlg.open(parent_win, None, _file_chosen)

    def _file_chosen(dlg, result):
        try:
            gfile = dlg.open_finish(result)
        except GLib.Error:
            return
        ok, name = install_theme_archive(gfile.get_path(), dest_dir)
        on_installed(ok, name)

    def do_remove(_btn):
        name = get_selected()
        if name:
            on_removed(remove_theme(name, [dest_dir]), name)

    btn_install.connect('clicked', do_install)
    btn_remove.connect('clicked', do_remove)
    return bar


def make_listbox_row(name, display):
    row = Gtk.ListBoxRow()
    lbl = Gtk.Label(label=display)
    lbl.set_halign(Gtk.Align.START)
    lbl.set_margin_start(8); lbl.set_margin_top(4); lbl.set_margin_bottom(4)
    row.set_child(lbl)
    row._label     = display
    row.theme_name = name
    return row


def make_section_frame(title, widgets):
    frame = Gtk.Frame()
    hdr = Gtk.Label()
    hdr.set_markup(f'<b>{title}</b>')
    frame.set_label_widget(hdr)
    frame.set_label_align(0.0)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_margin_start(12); box.set_margin_end(8)
    box.set_margin_top(6);    box.set_margin_bottom(8)
    for w in widgets:
        box.append(w)
    frame.set_child(box)
    return frame

def make_section_frame_columns(title, widgets, cols=2):
    """Like make_section_frame but arranges widgets in cols columns.
    Combos and non-check widgets always span full width."""
    frame = Gtk.Frame()
    hdr = Gtk.Label()
    hdr.set_markup(f'<b>{title}</b>')
    frame.set_label_widget(hdr)
    frame.set_label_align(0.0)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    outer.set_margin_start(12); outer.set_margin_end(8)
    outer.set_margin_top(6);    outer.set_margin_bottom(8)

    # Split into check widgets (go in grid) and others (full width)
    checks = [w for w in widgets if isinstance(w, Gtk.CheckButton)]
    others = [w for w in widgets if not isinstance(w, Gtk.CheckButton)]

    if checks:
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(4)
        grid.set_column_homogeneous(True)
        grid.set_hexpand(True)
        for i, w in enumerate(checks):
            grid.attach(w, i % cols, i // cols, 1, 1)
            w.set_hexpand(True)
        outer.append(grid)

    for w in others:
        outer.append(w)

    frame.set_child(outer)
    return frame


def make_combo_row(label, options, selected, on_change):
    hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    if label:
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        hb.append(lbl)
    combo = Gtk.DropDown.new_from_strings(options)
    combo.set_selected(selected)
    combo.set_hexpand(not label)  # expand to fill if no label
    combo.connect('notify::selected', on_change)
    hb.append(combo)
    return hb


def make_check_row(label, active, on_toggle):
    cb = Gtk.CheckButton(label=label)
    cb.set_active(active)
    cb.connect('toggled', on_toggle)
    return cb

def make_fallback_label(text='(Adwaita fallback)'):
    """Small dimmed subtitle label for Adwaita fallback indicators.
    Used in Icons, Cursors, and any future tab that shows fallback icons."""
    lbl = Gtk.Label(label=text)
    lbl.set_halign(Gtk.Align.CENTER)
    lbl.set_max_width_chars(14)
    lbl.set_ellipsize(Pango.EllipsizeMode.END)
    lbl.add_css_class('caption')
    lbl.set_opacity(0.6)
    return lbl

# ------------------------------------------------------------------ #
# Main window                                                          #
# ------------------------------------------------------------------ #

# Legacy icon name aliases -- complete authoritative GTK2/pre-XDG mapping.
# Source: /usr/share/icon-naming-utils/legacy-icon-mapping.xml (freedesktop.org spec).
# Lookup order: XDG canonical -> symbolic variant -> legacy names -> Adwaita fallback.
