"""Entry point: python -m dwarventhemer4gtk  OR  python __main__.py"""
import sys
import os

# Handle both 'python -m dwarventhemer4gtk' and 'python __main__.py' directly
if __package__ is None or __package__ == '':
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, pkg_dir)
    from dwarventhemer4gtk.constants import RESET_THEME_DIR
else:
    from .constants import RESET_THEME_DIR

# Set XDG_DATA_DIRS BEFORE any GTK import so GTK finds DwarvenReset at startup
xdg = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share')
if RESET_THEME_DIR not in xdg:
    os.environ['XDG_DATA_DIRS'] = RESET_THEME_DIR + ':' + xdg

# Suppress GDK portal warnings -- we don't use screenshot/screencast portals
# GDK_DEBUG=no-portals prevents GDK from querying portal interfaces on startup
os.environ.setdefault('GDK_DEBUG', 'no-portals')

# Now safe to import GTK-dependent modules
if __package__ is None or __package__ == '':
    from dwarventhemer4gtk.app import DwarvenThemerApp
else:
    from .app import DwarvenThemerApp


def main():
    app = DwarvenThemerApp()
    sys.exit(app.run(sys.argv))

if __name__ == '__main__':
    main()
