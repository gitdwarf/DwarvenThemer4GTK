"""DwarvenThemerApp -- application class and entry point."""
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk

from .constants import APP_ID, RESET_THEME_DIR
from .window import DwarvenThemer


class DwarvenThemerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.connect('activate', self._on_activate)

    def _on_activate(self, app):
        # Register app-wide CSS classes
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(
            b'.icon-preview-dark { background-color: #1e1e1e; }')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Add the bundled reset theme to XDG_DATA_DIRS so GTK finds DwarvenReset.
        # DwarvenReset is a minimal explicit-light theme shipped with the package.
        # Used as an intermediate when switching implicit-light themes to force
        # GTK to do a full style rebuild. Never written to disk at runtime.
        # RESET_THEME_DIR points to the parent of DwarvenReset/ inside the package.
        xdg = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share')
        if RESET_THEME_DIR not in xdg:
            os.environ['XDG_DATA_DIRS'] = RESET_THEME_DIR + ':' + xdg

        win = DwarvenThemer(app)
        win.connect('close-request', self._on_close)
        win.present()

    def _on_close(self, win):
        if win._changed:
            win._try_notify_settings_daemons()
        self.quit()
        return False

    def do_activate(self):
        pass


if __name__ == '__main__':
    DwarvenThemerApp().run()
