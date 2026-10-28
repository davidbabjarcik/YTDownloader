import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, paths
from app.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.ui.widgets import NoWheelChange


def main() -> int:
    logging.basicConfig(filename=str(paths.log_file()), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    settings = Settings.load()
    apply_theme(app, settings.theme)
    no_wheel = NoWheelChange(app)
    app.installEventFilter(no_wheel)

    def hook(exc_type, exc, tb):
        logging.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, APP_NAME, f"Unexpected error (the app keeps running):\n{exc}\n\n"
                                             f"Details: {paths.log_file()}")
    sys.excepthook = hook

    win = MainWindow(settings)
    win.show()
    QTimer.singleShot(300, win.check_dependencies)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
