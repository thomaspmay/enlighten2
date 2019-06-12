import sys
from PyQt5 import QtWidgets
from windows.windows import WindowManager
from windows.main import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    window_manager = WindowManager()
    main_window = MainWindow(window_manager)

    main_window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()