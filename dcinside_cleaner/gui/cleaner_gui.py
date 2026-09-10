from .check_proxies import ProxyCheckWindow
from .get_proxies import ProxyInputWindow
from .cleaner_thread import CleanerThread
from ..dcinside_cleaner import Cleaner
from ..version import APP_VERSION
from .utils import macos_colors, macos_control_style, resource_path
from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import uic
import json
import sys
import os
import math
from collections import deque

main_form = uic.loadUiType(resource_path('./resources/ui/ui_main_window.ui'))[0]
about_dialog_form = uic.loadUiType(resource_path('./resources/ui/ui_about_dialog.ui'))[0]
logo_ico = resource_path('./resources/icon/logo_icon.ico')


class LoginSuccessDialog(QtWidgets.QDialog):
    DIALOG_SIZE = (320, 160)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('로그인 안내')
        self.setModal(True)
        self.setFixedSize(*self.DIALOG_SIZE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)
        layout.addStretch(1)

        self.label_message = QtWidgets.QLabel('로그인되었습니다', self)
        self.label_message.setObjectName('label_message')
        self.label_message.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.label_message)
        layout.addSpacing(20)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch(1)

        self.btn_confirm = QtWidgets.QPushButton('확인', self)
        self.btn_confirm.setObjectName('btn_confirm')
        self.btn_confirm.setFixedSize(112, 36)
        self.btn_confirm.setDefault(True)
        self.btn_confirm.setAutoDefault(True)
        self.btn_confirm.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.btn_confirm.setAttribute(QtCore.Qt.WA_MacShowFocusRect, False)
        self.btn_confirm.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_confirm)
        button_layout.addStretch(1)

        layout.addLayout(button_layout)
        layout.addStretch(1)
        self.applyAppearance()

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(
            0,
            lambda: self.btn_confirm.setFocus(QtCore.Qt.OtherFocusReason))

    def applyAppearance(self):
        colors = macos_colors(self)
        focus_border = '#64d2ff' if colors['window'] == '#1c1c1e' else '#5ac8fa'
        self.setStyleSheet(f'''
            QDialog {{
                background-color: {colors['window']};
            }}
            QLabel#label_message {{
                color: {colors['text']};
                font-size: 16px;
                font-weight: 600;
            }}
            QPushButton#btn_confirm {{
                background-color: {colors['accent']};
                color: #ffffff;
                border: 2px solid transparent;
                border-radius: 8px;
                padding: 0 16px;
                font-weight: 600;
            }}
            QPushButton#btn_confirm:hover {{
                background-color: {colors['accent_pressed']};
            }}
            QPushButton#btn_confirm:pressed {{
                background-color: {colors['accent_pressed']};
            }}
            QPushButton#btn_confirm:focus,
            QPushButton#btn_confirm:default {{
                border-color: {focus_border};
            }}
        ''')

class MainWindow(QtWidgets.QMainWindow, main_form):
    WINDOW_SIZE = (420, 640)
    p_type_dict = { 'p': 'posting', 'c': 'comment' }
    captcha_signal = QtCore.pyqtSignal(bool)
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(*self.WINDOW_SIZE)
        self.status_bar.hide()
        self.setWindowIcon(QtGui.QIcon(logo_ico))

        self.id = ''
        self.pw = ''
        self.p_type = '' # 'posting' | 'comment'
        self.twocaptcha_key = ''
        self.g_list = []
        self.proxy_list = []
        self.proxy_source = ''
        self.proxy_controls_busy = False
        
        self.about_dialog : AboutDialog

        self.progress_cur = 0
        self.progress_max = 0
        self.current_delay = 0
        self.recent_delays = deque(maxlen=30)
        self.current_task_type = None
        self.deleted_count = 0
        self.skipped_count = 0

        self.cleaner_thread = CleanerThread(self.captcha_signal)
        self.cleaner = Cleaner()
        self.cleaner_thread.setCleaner(self.cleaner)

        self.cleaner_thread.event_signal.connect(self.deleteEvent)
        self.cleaner_thread.finished.connect(self.deleteFinished)

        self.input_pw.returnPressed.connect(self.login)
        self.btn_login.clicked.connect(self.login)

        self.btn_captcha_key.clicked.connect(self.set2CaptchaKey)

        self.btn_get_posting.clicked.connect(lambda: self.getGallList('p'))
        self.btn_get_comment.clicked.connect(lambda: self.getGallList('c'))

        self.btn_start.clicked.connect(self.delete)

        self.action_add_proxy.triggered.connect(self.openProxyInputDialog)
        self.action_get_proxy.triggered.connect(self.getProxyList)
        self.action_about.triggered.connect(self.openAboutDialog)
        self.btn_add_proxy.clicked.connect(self.openProxyInputDialog)
        self.btn_load_proxy.clicked.connect(self.getProxyList)

        self.combo_box_gall.installEventFilter(self)
        self.updateGalleryComboMask()
        self.configureMainTabs()
        self.configureProgressBar()
        self.updateProxyControls()
        self.group_box_gall.setEnabled(False)

    def openAboutDialog(self):
        self.about_dialog = AboutDialog()
        self.about_dialog.show()

    def eventFilter(self, watched, event):
        if (watched is self.combo_box_gall
                and event.type() in (QtCore.QEvent.Show, QtCore.QEvent.Resize)):
            self.updateGalleryComboMask()
        return super().eventFilter(watched, event)

    def updateGalleryComboMask(self):
        rect = QtCore.QRectF(self.combo_box_gall.rect())
        if rect.isEmpty():
            return

        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        self.combo_box_gall.setMask(
            QtGui.QRegion(path.toFillPolygon().toPolygon()))

    def configureMainTabs(self):
        tab_bar = self.tab_widget.tabBar()
        self.tab_widget.setDocumentMode(False)
        tab_bar.setExpanding(True)
        tab_bar.setFixedWidth(240)
        tab_bar.setDrawBase(False)
        tab_bar.setFocusPolicy(QtCore.Qt.NoFocus)
        self.tab_work.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.tab_settings.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.tab_widget.currentChanged.connect(self.focusCurrentTabPage)
        self.applyMainAppearance()

    def applyMainAppearance(self):
        colors = macos_colors(self)
        self.tab_widget.setStyleSheet(f'''
            QTabWidget::pane {{
                border: 0;
                top: 8px;
            }}
            QTabWidget::tab-bar {{
                alignment: center;
            }}
            QTabBar {{
                background-color: {colors['control']};
                border: 1px solid {colors['separator']};
                border-radius: 8px;
                padding: 2px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {colors['secondary_text']};
                border: 0;
                border-radius: 6px;
                min-width: 92px;
                padding: 5px 12px;
                margin: 0;
            }}
            QTabBar::tab:selected {{
                background-color: {colors['selected']};
                color: {colors['text']};
                font-weight: 600;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {colors['control_hover']};
                color: {colors['text']};
            }}
        ''' + macos_control_style(self))

    def focusCurrentTabPage(self, index):
        QtCore.QTimer.singleShot(0, lambda: self._focusTabPage(index))

    def _focusTabPage(self, index):
        page = self.tab_widget.widget(index)
        if page is not None:
            page.setFocus(QtCore.Qt.OtherFocusReason)

    def configureProgressBar(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.styleProgressBar()
        self.label_progress_percent.setMinimumWidth(
            self.label_progress_percent.fontMetrics().horizontalAdvance('100%'))
        self.setProgress('대기 중', 0, 0)

    def styleProgressBar(self):
        colors = macos_colors(self)
        self.progress_bar.setStyleSheet(f'''
            QProgressBar {{
                background-color: {colors['field']};
                border: 0;
                border-radius: 4px;
                min-height: 16px;
                max-height: 16px;
            }}
            QProgressBar::chunk {{
                background-color: {colors['accent']};
                border-radius: 3px;
            }}
        ''')

    def setProgress(self, status, current, maximum):
        self.progress_max = max(int(maximum or 0), 0)
        self.progress_cur = max(int(current or 0), 0)

        if self.progress_max:
            percent = min(100, int((self.progress_cur / self.progress_max) * 100))
        else:
            percent = 0

        self.progress_bar.setValue(percent)
        self.label_progress_status.setText(status)
        self.label_progress_percent.setText(f'{percent}%')

    def advanceProgress(self):
        self.setProgress(
            self.label_progress_status.text(),
            self.progress_cur + 1,
            self.progress_max)

    def completeProgress(self):
        if self.progress_max:
            self.progress_cur = self.progress_max
        self.progress_bar.setValue(100)
        self.label_progress_status.setText('완료')
        self.label_progress_percent.setText('100%')

    def updateProxyControls(self):
        has_proxies = bool(self.proxy_list)
        controls_enabled = not self.proxy_controls_busy

        self.btn_add_proxy.setEnabled(controls_enabled)
        self.btn_load_proxy.setEnabled(controls_enabled)
        self.action_add_proxy.setEnabled(controls_enabled)
        self.action_get_proxy.setEnabled(controls_enabled)
        self.checkbox_proxy.setEnabled(controls_enabled and has_proxies)

        if has_proxies:
            self.checkbox_proxy.setText(f'프록시 사용 ({len(self.proxy_list)}개)')
            source = self.proxy_source or '확인된 목록'
            self.checkbox_proxy.setToolTip(f'{source}: 프록시 {len(self.proxy_list)}개')
        else:
            self.checkbox_proxy.setChecked(False)
            self.checkbox_proxy.setText('프록시 사용 (목록 없음)')
            self.checkbox_proxy.setToolTip('프록시를 추가하거나 불러오면 사용할 수 있습니다.')

    def setProxyControlsBusy(self, busy):
        self.proxy_controls_busy = busy
        self.updateProxyControls()

    def getProxyList(self):
        name = QtWidgets.QFileDialog.getOpenFileName(
            self, '프록시 파일 열기', './', 'JSON files (*.json)')[0]
        if not name:
            return

        try:
            with open(name, 'r', encoding='utf-8') as file:
                data = json.load(file)

            proxy_list = data.get('data') if isinstance(data, dict) else None
            if (not isinstance(data, dict)
                    or data.get('title') != 'dcinside_cleaner_proxy_list'
                    or not isinstance(proxy_list, list)):
                raise ValueError

            proxy_list = [proxy.strip() for proxy in proxy_list
                          if isinstance(proxy, str) and proxy.strip()]
            if not proxy_list:
                raise ValueError

            self.proxy_list = proxy_list
            self.proxy_source = os.path.basename(name)
            self.updateProxyControls()
            self.log(f'프록시 {len(self.proxy_list)}개를 불러왔습니다.')
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            QtWidgets.QMessageBox.warning(self, '파일 열기 실패', '올바른 파일이 아닙니다.')

    def calculateEstimatedTime(self, average_delay):
        if self.progress_max <= 0 or self.progress_cur >= self.progress_max:
            return "0초"
        
        remaining_items = self.progress_max - self.progress_cur
        total_seconds = math.ceil(remaining_items * average_delay)

        days = total_seconds // (24 * 3600)
        total_seconds = total_seconds % (24 * 3600)
        hours = total_seconds // 3600
        total_seconds %= 3600
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        time_parts = []
        if days > 0:
            time_parts.append(f"{days}일")
        if hours > 0:
            time_parts.append(f"{hours}시간")
        if minutes > 0:
            time_parts.append(f"{minutes}분")
        if seconds > 0 or not time_parts:
            time_parts.append(f"{seconds}초")
        
        return " ".join(time_parts) if time_parts else "0초"

    @QtCore.pyqtSlot(dict)
    def deleteEvent(self, event):
        if event['type'] == 'pages':
            self.log('글 목록 가져오는 중...')
            self.setProgress('목록 수집 중', 0, event['data'])
            self.current_task_type = None

        elif event['type'] == 'posts':
            self.log(f'글 개수는 {event["data"]}개 입니다')
            self.log('글 삭제하는 중...')
            self.setProgress('삭제 중', 0, event['data'])
            self.current_task_type = None

        elif event['type'] in ('page_update', 'post_update', 'post_skipped'):
            if event['type'] == 'post_update':
                self.deleted_count += 1
            elif event['type'] == 'post_skipped':
                self.skipped_count += 1
            self.advanceProgress()

            task_type = 'page_update' if event['type'] == 'page_update' else 'post_update'
            if self.current_task_type != task_type:
                self.recent_delays.clear()
                self.current_task_type = task_type

            if 'captcha_solved' in event['data'].keys() and event['data']['captcha_solved']:
                self.log(f"캡차가 자동 해제됨")

            if event['type'] == 'page_update':
                self.log(f"{event['data']['index'] + 1}번째 페이지 로딩...")
            elif event['type'] == 'post_skipped':
                self.log(f"{event['data']['post_no']}번 항목 건너뜀: {event['data']['message']}")
            else:
                self.log(f"{event['data']['del_no']}번 글 삭제")

            if task_type == 'post_update' and self.skipped_count:
                self.label_progress_status.setText(f'삭제 {self.deleted_count} · 건너뜀 {self.skipped_count}')
            
            current_event_delay = event['data']['delay']
            self.recent_delays.append(current_event_delay)
            
            if len(self.recent_delays) >= 4: 
                sorted_buffer = sorted(list(self.recent_delays))
                trimmed_buffer = sorted_buffer[1:-1]
                average_delay = sum(trimmed_buffer) / len(trimmed_buffer)
            else:
                average_delay = sum(self.recent_delays) / len(self.recent_delays)

            estimated_time_str = self.calculateEstimatedTime(average_delay)
                
            if event['type'] == 'post_skipped':
                self.log(f"딜레이: {current_event_delay:.1f}sec, ETA: {estimated_time_str}")
            else:
                self.log(f"프록시: {event['data']['proxy'] or 'X'}, 딜레이: {current_event_delay:.1f}sec, ETA: {estimated_time_str}")

        elif event['type'] == 'ipblocked':
            self.setProgress('삭제 중단', self.progress_cur, self.progress_max)
            self.log('IP 차단 감지')
            QtWidgets.QMessageBox.warning(self, '차단 안내', event.get('message') or 'IP가 차단되었습니다.')

        elif event['type'] == 'fail':
            self.setProgress('삭제 중단', self.progress_cur, self.progress_max)
            message = event.get('message') or '삭제에 실패했습니다.\n잠시 후 다시 시도해 보세요.'
            self.log(f'삭제 실패: {message}')
            QtWidgets.QMessageBox.warning(self, '실패 안내', message)

        elif event['type'] == 'cancelled':
            self.setProgress('삭제 취소', self.progress_cur, self.progress_max)
            self.log(event.get('message') or '삭제를 취소했습니다.')

        elif event['type'] == 'confirmation':
            confirmed = self.askDeleteConfirmation(
                event['message'], f"{event['post_no']}번 글의 삭제를 계속하시겠습니까?")
            self.cleaner_thread.setDeleteConfirmation(confirmed)

        elif event['type'] == 'captcha':
            self.log('캡차 감지')
            if not self.twocaptcha_key:
                QtWidgets.QMessageBox.information(self, '캡차 안내', '캡차가 감지되었습니다.\n갤로그에 접속해 캡차를 해제한 후 확인을 눌러주세요.')
            self.captcha_signal.emit(True)

        elif event['type'] == 'complete':
            summary = event.get('data', {})
            self.deleted_count = summary.get('deleted_count', self.deleted_count)
            self.skipped_count = summary.get('skipped_count', self.skipped_count)
            self.completeProgress()
            if self.skipped_count:
                self.label_progress_status.setText(f'완료 · 삭제 {self.deleted_count} · 건너뜀 {self.skipped_count}')
                self.log(f'처리 완료: 삭제 {self.deleted_count}개, 건너뜀 {self.skipped_count}개')
                QtWidgets.QMessageBox.information(
                    self, '완료', f'처리가 완료되었습니다.\n삭제: {self.deleted_count}개\n건너뜀: {self.skipped_count}개')
            else:
                self.log('삭제 완료')
                QtWidgets.QMessageBox.information(self, '완료', '삭제 작업이 완료되었습니다.')

    @QtCore.pyqtSlot()
    def deleteFinished(self):
        self.label_current_mode.setText('모드: 선택 전')
        self.group_box_gall.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.setProxyControlsBusy(False)
        self.combo_box_gall.clear()
        self.g_list = []
        self.p_type = ''
        self.updateUserInfo()

    def askDeleteConfirmation(self, message, detail, button_text='삭제'):
        dialog = QtWidgets.QMessageBox(self)
        dialog.setWindowTitle('작성글 삭제 확인')
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setTextFormat(QtCore.Qt.PlainText)
        dialog.setText(message)
        dialog.setInformativeText(detail)
        dialog.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        for label in dialog.findChildren(QtWidgets.QLabel):
            label.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
            label.setFocusPolicy(QtCore.Qt.NoFocus)
            label.setCursor(QtCore.Qt.ArrowCursor)
        dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        dialog.button(QtWidgets.QMessageBox.Yes).setText(button_text)
        dialog.button(QtWidgets.QMessageBox.Cancel).setText('취소')
        dialog.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        dialog.setEscapeButton(QtWidgets.QMessageBox.Cancel)
        dialog.button(QtWidgets.QMessageBox.Cancel).setFocus(QtCore.Qt.OtherFocusReason)
        return dialog.exec_() == QtWidgets.QMessageBox.Yes

    def log(self, text):
        self.box_log.append(text)
        self.statusBar().showMessage(text, 1500)

    def setCursorWait(self):
        QtGui.QGuiApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

    def restoreCursor(self):
        QtGui.QGuiApplication.restoreOverrideCursor()

    def login(self):
        self.id = self.input_id.text()
        self.pw = self.input_pw.text()
        self.log('로그인 중...')
        self.setCursorWait()
        try:
            res = self.cleaner.login(self.id, self.pw)
        except Exception as e:
            res = False
            self.log(f'로그인 오류: {e}')
        finally:
            self.restoreCursor()

        if res:
            self.log('로그인 성공')
            LoginSuccessDialog(self).exec_()
            self.group_box_login.setEnabled(False)
            self.updateUserInfo()
            self.group_box_gall.setEnabled(True)
        else:
            self.log('로그인 실패')
            QtWidgets.QMessageBox.warning(self, '로그인 안내', '로그인에 실패했습니다.')

    def updateUserInfo(self):
        try:
            result = self.cleaner.getUserInfo()
            self.label_nickname.setText('닉네임: ' + result['nickname'])
            self.label_article_num.setText('글: ' + result['article_num'])
            self.label_comment_num.setText('댓글: ' + result['comment_num'])
        except Exception as e:
            self.log(f'로그인 정보 갱신 실패: {e}')

    def getGallList(self, post_type):
        self.combo_box_gall.clear()

        self.g_list = []
        self.setCursorWait()
        self.p_type = self.p_type_dict[post_type]

        self.log('갤러리 목록 가져오는 중...')
        self.label_current_mode.setText('모드: ' + (post_type == 'p' and '글' or '댓글'))

        gall_list = self.cleaner.getGallList(self.p_type)
        idx = 0

        for gno in gall_list:
            self.g_list.append(gno)
            self.combo_box_gall.addItem(f'{idx + 1}. {gall_list[gno]}')
            idx += 1

        self.restoreCursor()

    def delete(self):
        del_all = self.checkbox_gall_all.isChecked()
        del_list = []

        if not self.p_type:
            return QtWidgets.QMessageBox.warning(self, '안내', '글 또는 댓글 불러오기를 하십시오.\n만약 목록이 비어있다면 전체삭제만 가능합니다.')
        
        if not del_all:
            idx = self.combo_box_gall.currentIndex()
            del_list = [self.g_list[idx]]

        posting_consent = False
        if self.p_type == 'posting':
            posting_consent = self.askDeleteConfirmation(
                "일부 갤러리에서 '질문' 등 삭제가 제한된 말머리의 글을 삭제하면 매니저에 의해 차단될 수 있습니다.",
                '동의하면 이번 작성글 삭제 작업에서 사이트가 요청하는 추가 확인에 자동으로 동의하고 삭제를 계속합니다.\n이 동의는 이번 작업에만 적용됩니다.',
                button_text='동의하고 삭제')
            if not posting_consent:
                return

        self.cleaner_thread.setDelInfo(del_list, self.p_type, del_all, posting_consent=posting_consent)
        
        if self.checkbox_proxy.isChecked():
            self.cleaner.setProxyList(self.proxy_list)
        else:
            self.cleaner.setProxyList([])

        self.deleted_count = 0
        self.skipped_count = 0
        self.setProgress('준비 중', 0, 0)
        self.group_box_gall.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.setProxyControlsBusy(True)
        self.cleaner_thread.start()

    def openProxyInputDialog(self):
        self.proxy_input_dialog = ProxyInputWindow()
        self.proxy_input_dialog.proxy_list_signal.connect(self.openProxyCheckDialog)
        self.proxy_input_dialog.show()
        
    @QtCore.pyqtSlot(list)
    def openProxyCheckDialog(self, proxy_list):
        self.proxy_check_dialog = ProxyCheckWindow(proxy_list)
        self.proxy_check_dialog.available_proxy_list_signal.connect(self.setAvailableProxyList)
        self.proxy_check_dialog.show()

    @QtCore.pyqtSlot(list)
    def setAvailableProxyList(self, available_list):
        self.proxy_list = list(available_list)
        self.proxy_source = '확인된 목록'
        self.updateProxyControls()

        if self.proxy_list:
            self.log(f'사용 가능한 프록시 {len(self.proxy_list)}개를 확인했습니다.')
        else:
            self.log('사용 가능한 프록시를 찾지 못했습니다.')

    def set2CaptchaKey(self):
        key = self.input_captcha_key.text()

        try:
            res = self.cleaner.set2CaptchaKey(key)
        except Exception as e:
            self.log(f'2Captcha 연결 오류: {e}')
            return QtWidgets.QMessageBox.warning(self, '안내', '2Captcha 연결에 실패했습니다.')

        if not res:
            return QtWidgets.QMessageBox.warning(self, '안내', '유효하지 않은 API 키입니다.')

        self.twocaptcha_key = key
        self.group_box_captcha.setEnabled(False)

        QtWidgets.QMessageBox.information(self, '안내', 'API 키가 등록되었습니다.')

class AboutDialog(QtWidgets.QDialog, about_dialog_form):

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowIcon(QtGui.QIcon(logo_ico))
        self.label_version.setText(f'버전 {APP_VERSION} macOS')

        colors = macos_colors(self)
        self.setStyleSheet(f'''
            QDialog {{
                background-color: {colors['window']};
            }}
            QLabel {{
                color: {colors['text']};
            }}
            QLabel#label_version, QLabel#label_author {{
                color: {colors['secondary_text']};
            }}
        ''')

def execute():
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    app.exec_()
