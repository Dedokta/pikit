"""Persistent settings stored in %APPDATA%\\PiKit\\settings.json."""
import json
import os

_APPDATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PiKit")
_PATH = os.path.join(_APPDATA, "settings.json")

DEFAULTS = {
    "default_image_folder":    os.path.join(os.path.expanduser("~"), "Pi Images"),
    "compression_level":       6,          # 1=fast, 9=best
    "verify_after_flash":      True,
    "removable_only":          True,
    "smart_backup":            True,       # stop at last partition boundary
    "shrink_before_compress":  True,
    "delete_intermediate":     True,       # delete .img after compressing to .gz
    "auto_name_with_date":     True,
    "wsl_distro":              "auto",
    "recent_images":           [],
    "window_geometry":         "1020x680",
}


class Settings:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(_PATH):
            try:
                with open(_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        os.makedirs(_APPDATA, exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, fallback=None):
        return self._data.get(key, DEFAULTS.get(key, fallback))

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def add_recent_image(self, path):
        recents = self._data.get("recent_images", [])
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        self._data["recent_images"] = recents[:10]
        self.save()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)
