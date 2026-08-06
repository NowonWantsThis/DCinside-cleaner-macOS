from .utils import macos_control_style, resource_path
from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import uic
import ipaddress

proxies_input_form = uic.loadUiType(resource_path('./resources/ui/ui_proxies_input_window.ui'))[0]
logo_ico = resource_path('./resources/icon/logo_icon.ico')

class ProxyInputWindow(QtWidgets.QDialog, proxies_input_form):
    proxy_list_signal = QtCore.pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setStyleSheet(macos_control_style(self))
        self.setWindowIcon(QtGui.QIcon(logo_ico))

        self.btn_complete.clicked.connect(self.getProxyList)
        self.proxies_input.textChanged.connect(
            lambda: self.label_validation.setVisible(False))
        self.proxies_input.setFocus()

        error_palette = self.label_validation.palette()
        error_palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor('#ff453a'))
        self.label_validation.setPalette(error_palette)

    @staticmethod
    def parseProxyList(text):
        proxy_list = []
        seen = set()

        for raw_proxy in text.splitlines():
            raw_proxy = raw_proxy.strip()
            if not raw_proxy:
                continue

            try:
                ip, raw_port = raw_proxy.rsplit(':', 1)
                ip = str(ipaddress.IPv4Address(ip.strip()))
                port = int(raw_port)
                if not 1 <= port <= 65535:
                    raise ValueError
            except (ipaddress.AddressValueError, ValueError):
                continue

            proxy = f'{ip}:{port}'
            if proxy not in seen:
                seen.add(proxy)
                proxy_list.append(proxy)

        return proxy_list

    def getProxyList(self):
        valid_proxy_list = self.parseProxyList(self.proxies_input.toPlainText())

        if not valid_proxy_list:
            self.label_validation.setVisible(True)
            return

        self.proxy_list_signal.emit(valid_proxy_list)
        self.close()
