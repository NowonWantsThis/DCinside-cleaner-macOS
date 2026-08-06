from ..proxy_checker import ProxyChecker
from .utils import macos_control_style, resource_path
from datetime import datetime
from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import uic
import json

proxies_check_form = uic.loadUiType(resource_path('./resources/ui/ui_proxies_check_window.ui'))[0]
logo_ico = resource_path('./resources/icon/logo_icon.ico')

PROXY_CHECK_TIMEOUT = 5.0

class ProxyCheckWindow(QtWidgets.QDialog, proxies_check_form):
    available_proxy_list_signal  = QtCore.pyqtSignal(list)

    def __init__(self, proxy_list):
        super().__init__()
        self.setupUi(self)
        self.setStyleSheet(macos_control_style(self))
        self.setWindowIcon(QtGui.QIcon(logo_ico))

        self.check_thread = None

        self.proxy_list = proxy_list
        self.proxy_count = len(proxy_list)
        self.checked_count = 0

        self.available_list = []
        self.checkbox_list = []

        self.proxy_checker = ProxyChecker()
        self.proxy_checker.setCheckURL('https://www.dcinside.com/')
        self.label_help.setText(
            f'등록된 프록시가 DCInside에 연결되는지 확인합니다. '
            f'응답 제한 시간은 {PROXY_CHECK_TIMEOUT:g}초입니다.')

        self.btn_save_proxies.setEnabled(False)
        self.btn_save_proxies.clicked.connect(self.exportProxyList)
        
        self.btn_remove_excluded.setEnabled(False)
        self.btn_remove_excluded.clicked.connect(self.removeExcludedRows)

        self.btn_retest.setEnabled(False)
        self.btn_retest.clicked.connect(self.retest)

        self.initProxyTable()
        self.updateStatus('검사 중')

        self.runThread()

    def closeEvent(self, event):
        if self.check_thread:
            self.check_thread.stop()

        event.accept()

    def initProxyTable(self):
        table_labels = ['사용', 'IP', '포트', '지연', '상태']
        self.proxy_table.setColumnCount(len(table_labels))
        self.proxy_table.setHorizontalHeaderLabels(table_labels)
        self.proxy_table.setRowCount(self.proxy_count)
        self.proxy_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.proxy_table.setWordWrap(False)

        header = self.proxy_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Fixed)
        self.proxy_table.setColumnWidth(0, 56)
        self.proxy_table.setColumnWidth(2, 76)
        self.proxy_table.setColumnWidth(3, 82)
        self.proxy_table.setColumnWidth(4, 110)
        self.proxy_table.horizontalHeaderItem(1).setTextAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        for column in (0, 2, 3, 4):
            self.proxy_table.horizontalHeaderItem(column).setTextAlignment(
                QtCore.Qt.AlignCenter)
        self.proxy_table.verticalHeader().hide()
        self.proxy_table.verticalHeader().setDefaultSectionSize(32)

        for idx, proxy in enumerate(self.proxy_list):
            cell_widget = QtWidgets.QWidget()
            checkbox = QtWidgets.QCheckBox()
            layout = QtWidgets.QHBoxLayout(cell_widget)
            layout.addWidget(checkbox)
            layout.setAlignment(QtCore.Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            cell_widget.setLayout(layout)
            self.proxy_table.setCellWidget(idx, 0, cell_widget)
            self.checkbox_list.append(checkbox)

            ip, port = proxy.rsplit(':', 1)
            self.proxy_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(ip))
            self.proxy_table.setItem(idx, 2, self.centeredItem(port))
            self.proxy_table.setItem(idx, 3, self.centeredItem('-'))
            self.proxy_table.setItem(idx, 4, self.centeredItem('-'))

    @staticmethod
    def centeredItem(text):
        item = QtWidgets.QTableWidgetItem(text)
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        return item

    def updateStatus(self, status):
        self.label_status.setText(
            f'{status} · {self.checked_count}/{self.proxy_count}')
        self.label_summary.setText(f'사용 가능 {len(self.available_list)}개')

    def runThread(self):
        self.check_thread = ProxyThread(self.proxy_list)
        self.check_thread.proxy_info_signal.connect(self.checkProxy)
        self.check_thread.check_complete_signal.connect(self.completeCheck)
        self.check_thread.start()

    @QtCore.pyqtSlot(list)
    def checkProxy(self, result):
        idx, status, delay, proxy = result
        self.checked_count += 1

        if status:
            self.available_list.append(proxy)
            self.proxy_table.setItem(
                idx, 3, self.centeredItem(f'{delay:.1f}초'))
            self.checkbox_list[idx].setChecked(True)

        item = self.centeredItem('사용 가능' if status else '연결 실패')
        color = '#34c759' if status else '#ff453a'
        item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
        self.proxy_table.setItem(idx, 4, item)
        index = self.proxy_table.model().index(idx, 0)
        self.proxy_table.scrollTo(index)
        self.updateStatus('검사 중')

    @QtCore.pyqtSlot(bool)
    def completeCheck(self):
        self.updateStatus('검사 완료')
        self.available_proxy_list_signal.emit(self.available_list)
        self.btn_save_proxies.setEnabled(bool(self.available_list))
        self.btn_remove_excluded.setEnabled(bool(self.proxy_list))
        self.btn_retest.setEnabled(bool(self.proxy_list))

    def exportProxyList(self):
        time = str(datetime.today())
        export_content = {
            "title": "dcinside_cleaner_proxy_list",
            "create_date": time,
            "data": self.available_list
        }

        name = QtWidgets.QFileDialog.getSaveFileName(
            self, '프록시 목록 저장', './dcinside_cleaner_proxy_list.json',
            'JSON files (*.json)')[0]
        if not name:
            return

        try:
            with open(name, 'w', encoding='utf-8') as file:
                json.dump(export_content, file, ensure_ascii=False)
            QtWidgets.QMessageBox.information(self, '저장 완료', '파일 저장이 완료되었습니다.')
        except OSError:
            QtWidgets.QMessageBox.warning(self, '저장 실패', '파일을 저장하지 못했습니다.')

    def removeExcludedRows(self):
        new_checkbox_list = []
        new_proxy_list = []
        deleted = 0
        for i, checkbox in enumerate(self.checkbox_list):
            if not checkbox.isChecked():
                self.proxy_table.removeRow(i - deleted)
                deleted += 1
                continue
            new_checkbox_list.append(checkbox)
            new_proxy_list.append(self.proxy_list[i])

        self.checkbox_list = new_checkbox_list
        self.proxy_list = new_proxy_list
        self.available_list = new_proxy_list
        self.proxy_count = len(new_proxy_list)
        self.checked_count = self.proxy_count
        self.updateStatus('검사 완료')
        self.btn_save_proxies.setEnabled(bool(self.available_list))
        self.btn_remove_excluded.setEnabled(bool(self.proxy_list))
        self.btn_retest.setEnabled(bool(self.proxy_list))
        self.available_proxy_list_signal.emit(self.available_list)

    def retest(self):
        self.available_list = []
        self.checked_count = 0
        for i, checkbox in enumerate(self.checkbox_list):
            self.proxy_table.setItem(i, 3, self.centeredItem('-'))
            self.proxy_table.setItem(i, 4, self.centeredItem('-'))
            checkbox.setChecked(False)

        self.updateStatus('검사 중')
        self.btn_save_proxies.setEnabled(False)
        self.btn_remove_excluded.setEnabled(False)
        self.btn_retest.setEnabled(False)

        self.runThread()
        




class ProxyThread(QtCore.QThread):
    proxy_info_signal = QtCore.pyqtSignal(list)
    check_complete_signal = QtCore.pyqtSignal(bool)

    def __init__(self, proxy_list):
        super().__init__()
        self.proxy_list = proxy_list
        self.proxy_checker = ProxyChecker()
        self.proxy_checker.setCheckURL('https://www.dcinside.com/')
        self.working = False

    def run(self):
        self.working = True
        for idx, proxy in enumerate(self.proxy_list):
            if not self.working: return
            status, delay = self.proxy_checker.checkProxy(
                {'http': proxy, 'https': proxy}, PROXY_CHECK_TIMEOUT)
            self.proxy_info_signal.emit([idx, status, delay, proxy])

        self.check_complete_signal.emit(True)

    def stop(self):
        self.working = False
        self.quit()
        self.wait(5000)
