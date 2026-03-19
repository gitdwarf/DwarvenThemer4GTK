"""X cursor file parsing, xcursor format, cursor theme resolution."""
import os, struct, configparser
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib
from .constants import ICON_DIRS

def get_cursor_file_sizes(path):
    """Return sorted list of available sizes in an Xcursor file. Fast -- TOC only."""
    try:
        with open(path, 'rb') as f:
            data = f.read(16 + 12 * 256)  # header + up to 256 TOC entries
    except OSError:
        return []
    if len(data) < 16 or data[:4] != b'Xcur':
        return []
    _hsize, _version, ntoc = struct.unpack_from('<III', data, 4)
    CHUNK_IMAGE = 0xfffd0002
    sizes = set()
    off = 16
    for _ in range(min(ntoc, 256)):
        if off + 12 > len(data):
            break
        ctype, subtype, _pos = struct.unpack_from('<III', data, off)
        off += 12
        if ctype == CHUNK_IMAGE:
            sizes.add(subtype)
    return sorted(sizes)

def get_theme_native_size(theme_name, preferred_size):
    """Return the largest available cursor size in the theme <= preferred_size.
    Falls back to the smallest available if all are larger than preferred_size.
    Uses the 'default' cursor as representative -- all cursors in a theme
    typically share the same size set."""
    path = find_cursor_file(theme_name, 'default')
    if not path:
        # Try any cursor file we can find
        for d in ICON_DIRS:
            cursor_dir = os.path.join(d, theme_name, 'cursors')
            if not os.path.isdir(cursor_dir):
                continue
            for fname in os.listdir(cursor_dir):
                p = os.path.join(cursor_dir, fname)
                if os.path.isfile(p) and not os.path.islink(p):
                    sizes = get_cursor_file_sizes(p)
                    if sizes:
                        path = p
                        break
            if path:
                break
    if not path:
        return preferred_size

    sizes = get_cursor_file_sizes(path)
    if not sizes:
        return preferred_size

    # Largest size that fits within preferred_size
    candidates = [s for s in sizes if s <= preferred_size]
    if candidates:
        return max(candidates)
    # All sizes exceed preferred_size -- return smallest (slider is below theme min)
    return min(sizes)

def parse_xcursor_image(path, target_size=32):
    """Parse an X11 cursor file and return (width, height, bgra_bytes) or None."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return None

    if len(data) < 16 or data[:4] != b'Xcur':
        return None

    _hsize, _version, ntoc = struct.unpack_from('<III', data, 4)
    CHUNK_IMAGE = 0xfffd0002
    images = []
    off = 16
    for _ in range(ntoc):
        if off + 12 > len(data):
            break
        ctype, subtype, pos = struct.unpack_from('<III', data, off)
        off += 12
        if ctype == CHUNK_IMAGE:
            images.append((subtype, pos))

    if not images:
        return None

    images.sort(key=lambda x: abs(x[0] - target_size))
    _, pos = images[0]

    if pos + 36 > len(data):
        return None

    chunk = struct.unpack_from('<IIIIIIIII', data, pos)
    width, height = chunk[4], chunk[5]
    px_off = pos + 36
    px_end = px_off + width * height * 4
    if px_end > len(data):
        return None

    return width, height, data[px_off:px_end]


def xcursor_to_texture(path, target_size=32):
    """Load an X11 cursor file into a GdkTexture.
    Returns (texture, actual_width, actual_height) or None."""
    result = parse_xcursor_image(path, target_size)
    if result is None:
        return None
    width, height, bgra = result
    # X11 cursor pixels are BGRA -- convert to RGBA for GDK
    rgba = bytearray(len(bgra))
    for i in range(0, len(bgra), 4):
        rgba[i]   = bgra[i+2]   # R <- B
        rgba[i+1] = bgra[i+1]   # G
        rgba[i+2] = bgra[i]     # B <- R
        rgba[i+3] = bgra[i+3]   # A
    gbytes = GLib.Bytes.new(bytes(rgba))
    texture = Gdk.MemoryTexture.new(
        width, height,
        Gdk.MemoryFormat.R8G8B8A8,
        gbytes,
        width * 4)
    return texture, width, height



# Cursor name aliases -- many themes use legacy X11 names or alternative names
CURSOR_ALIASES = {
    'default':     ['default', 'left_ptr', 'arrow'],
    'pointer':     ['pointer', 'hand2', 'hand1', 'pointing_hand'],
    'text':        ['text', 'xterm', 'ibeam'],
    'crosshair':   ['crosshair', 'cross'],
    'move':        ['move', 'fleur', 'size_all'],
    'wait':        ['wait', 'watch', 'clock'],
    'progress':    ['progress', 'left_ptr_watch', 'half-busy'],
    'not-allowed': ['not-allowed', 'crossed_circle', 'forbidden'],
    'grab':        ['grab', 'openhand', 'hand1'],
    'zoom-in':     ['zoom-in', 'zoom_in'],
    'col-resize':  ['col-resize', 'sb_h_double_arrow', 'size_hor', 'e-resize', 'ew-resize'],
    'row-resize':  ['row-resize', 'sb_v_double_arrow', 'size_ver', 'n-resize', 'ns-resize'],
}

def _find_cursor_in_dir(cursor_dir, cursor_name):
    """Try cursor_name and all its aliases in a cursors/ directory."""
    aliases = CURSOR_ALIASES.get(cursor_name, [cursor_name])
    for name in aliases:
        path = os.path.join(cursor_dir, name)
        if os.path.exists(path):
            # Follow symlinks to get the real file
            real = os.path.realpath(path)
            if os.path.exists(real):
                return real
    return None

def _get_theme_inherits(theme_name):
    """Return list of parent theme names from index.theme Inherits field."""
    for d in ICON_DIRS:
        idx = os.path.join(d, theme_name, 'index.theme')
        if os.path.exists(idx):
            cfg = configparser.ConfigParser()
            cfg.read(idx)
            try:
                inherits = cfg['Icon Theme'].get('Inherits', '')
                if inherits:
                    return [t.strip() for t in inherits.split(',') if t.strip()]
            except KeyError:
                pass
    return []

def find_cursor_file(theme_name, cursor_name, _visited=None):
    """Find cursor file, following theme inheritance and name aliases."""
    if _visited is None:
        _visited = set()
    if theme_name in _visited:
        return None
    _visited.add(theme_name)

    # Look in all icon dirs for this theme
    for d in ICON_DIRS:
        cursor_dir = os.path.join(d, theme_name, 'cursors')
        if not os.path.isdir(cursor_dir):
            continue
        path = _find_cursor_in_dir(cursor_dir, cursor_name)
        if path:
            return path

    # Not found -- try inherited themes
    for parent in _get_theme_inherits(theme_name):
        path = find_cursor_file(parent, cursor_name, _visited)
        if path:
            return path

    return None

# ------------------------------------------------------------------ #
# INI helpers                                                         #
# ------------------------------------------------------------------ #

