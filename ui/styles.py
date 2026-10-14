"""Estilo visual de la aplicación."""

STATUS_COLORS = {
    "PENDIENTE": "#6b7280", "EN_PROCESO": "#2563eb", "GUARDADA": "#d97706",
    "COMPLETADA": "#15803d", "ERROR": "#b91c1c", "REVISION": "#c2410c",
    "OMITIDA": "#9ca3af",
}

QSS = """
QWidget { font-family: "Segoe UI", Arial; font-size: 10pt; color: #1f2937; }
QMainWindow, QWidget#Page { background: #f4f6f9; }
QTabWidget::pane { border: 1px solid #d6dbe3; border-radius: 6px; background: #ffffff; top: -1px; }
QTabBar::tab { background: #e6eaf0; padding: 8px 16px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; color: #374151; }
QTabBar::tab:selected { background: #ffffff; color: #0f4c81; font-weight: 600; }
QGroupBox { border: 1px solid #d6dbe3; border-radius: 6px; margin-top: 14px; padding: 10px;
            background: #ffffff; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #0f4c81; }
QPushButton { background: #ffffff; border: 1px solid #c3cad6; border-radius: 5px; padding: 6px 12px; }
QPushButton:hover { background: #eef3fb; border-color: #0f4c81; }
QPushButton:disabled { color: #9ca3af; background: #f3f4f6; }
QPushButton#Primary { background: #0f4c81; color: white; border: none; font-weight: 600; }
QPushButton#Primary:hover { background: #0b3a63; }
QPushButton#Primary:disabled { background: #9db3c9; }
QPushButton#Danger { background: #b91c1c; color: white; border: none; font-weight: 600; }
QPushButton#Danger:disabled { background: #e3a5a5; }
QPushButton#Warn { background: #d97706; color: white; border: none; font-weight: 600; }
QPushButton#Warn:disabled { background: #f0c890; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {
    border: 1px solid #c3cad6; border-radius: 4px; padding: 4px; background: #ffffff; }
QTableWidget { gridline-color: #e5e7eb; background: #ffffff; alternate-background-color: #f8fafc;
               selection-background-color: #cfe0f5; selection-color: #111827; }
QHeaderView::section { background: #eef1f5; padding: 5px; border: none;
                       border-bottom: 1px solid #d6dbe3; font-weight: 600; }
QProgressBar { border: 1px solid #c3cad6; border-radius: 5px; text-align: center; height: 20px; }
QProgressBar::chunk { background: #15803d; border-radius: 4px; }
QLabel#Card { background: #ffffff; border: 1px solid #d6dbe3; border-radius: 8px; padding: 10px; }
QLabel#Title { font-size: 15pt; font-weight: 700; color: #0f4c81; }
QLabel#State { font-size: 12pt; font-weight: 600; padding: 8px; border-radius: 6px;
               background: #eef3fb; color: #0f4c81; }
QLabel#Hint { color: #6b7280; }
"""
