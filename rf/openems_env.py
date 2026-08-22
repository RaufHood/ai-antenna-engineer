"""Call setup() before `import CSXCAD` / `import openEMS`.

Windows stopped searching PATH for an extension module's DLL dependencies
in Python 3.8 (os.add_dll_directory is now required); the openEMS wheels
need their sibling DLLs (CSXCAD.dll, openEMS.dll, the vtk*/boost*/Qt5*
runtime) made discoverable explicitly, or the import fails with a bare
"ImportError: DLL load failed" and no indication which DLL is missing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_INSTALL_PATH = Path(__file__).parent / "vendor" / "openEMS"


def setup(install_path: str | Path | None = None) -> Path:
    path = Path(install_path or os.environ.get("OPENEMS_INSTALL_PATH", DEFAULT_INSTALL_PATH))
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(path))
    return path


if __name__ == "__main__":
    p = setup()
    print(f"OPENEMS_INSTALL_PATH -> {p} (exists: {p.exists()})")
    import CSXCAD
    import openEMS
    print("CSXCAD OK:", CSXCAD.__file__)
    print("openEMS OK:", openEMS.__file__)
