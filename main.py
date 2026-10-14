"""SisFaCon AutoFacturador — punto de entrada.

Ejecutar:  python main.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Permite ejecutar desde cualquier carpeta y desde el .exe de PyInstaller.
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app_context import AppContext
    from config import APP_NAME
    from ui.main_window import MainWindow, handle_interrupted
    from ui.styles import QSS

    if sys.platform.startswith("win"):
        try:  # coordenadas reales de pantalla con escalado de Windows (125 %, 150 %…)
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    qt = QApplication(sys.argv)
    qt.setApplicationName(APP_NAME)
    qt.setStyleSheet(QSS)

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        QMessageBox.critical(None, "Error inesperado", text[-3000:])

    sys.excepthook = excepthook

    ctx = AppContext.create()
    window = MainWindow(ctx)
    window.show()
    handle_interrupted(window)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
