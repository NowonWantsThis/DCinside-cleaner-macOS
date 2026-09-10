from ..dcinside_cleaner import Cleaner
from PyQt5 import QtCore
from threading import Event


class CleanerThread(QtCore.QThread):
    event_signal = QtCore.pyqtSignal(dict)

    def __init__(self, captcha_signal):
        super().__init__()
        self.cleaner: Cleaner
        self.captcha_signal = captcha_signal
        self.del_list = []
        self.p_type = ''
        self.del_all = False

        self.captcha_resumed = Event()
        self.confirmation_resumed = Event()
        self.delete_confirmed = False
        self.posting_consent = False
        self.deleted_count = 0
        self.skipped_count = 0

        self.captcha_signal.connect(self.checkCaptcha)

    def setCleaner(self, cleaner):
        self.cleaner = cleaner

    def setDelInfo(self, del_list, p_type, del_all, posting_consent=False):
        self.del_list = list(del_list) if not del_all else []
        self.p_type = p_type
        self.del_all = del_all
        self.posting_consent = bool(posting_consent and p_type == 'posting')

    def checkCaptcha(self):
        self.captcha_resumed.set()

    def setDeleteConfirmation(self, confirmed):
        self.delete_confirmed = bool(confirmed)
        self.confirmation_resumed.set()

    def confirmDeletion(self, message, post_no):
        if self.p_type == 'posting' and self.posting_consent:
            return True
        self.delete_confirmed = False
        self.confirmation_resumed.clear()
        self.event_signal.emit({
            'type': 'confirmation', 'message': message, 'post_no': post_no,
        })
        self.confirmation_resumed.wait()
        return self.delete_confirmed

    def fail(self, event):
        failure = {
            'type': event['data'] if event['data'] in ('ipblocked', 'cancelled') else 'fail',
        }
        for key in ('message', 'post_no'):
            if key in event:
                failure[key] = event[key]
        self.event_signal.emit(failure)
        return False

    def delete(self, gno):
        self.event_signal.emit({'type': 'pages', 'data': self.cleaner.getPageCount(gno, self.p_type)})
        
        for i in self.cleaner.aggregatePosts(gno, self.p_type):
            if i['status'] is not True:
                return self.fail(i)
            self.event_signal.emit({'type': 'page_update', 'data': i['data']})

        self.event_signal.emit({'type': 'posts', 'data': len(self.cleaner.post_list)})
        

        for i in self.cleaner.deletePosts(self.p_type, confirm_deletion=self.confirmDeletion):
            if i['status'] is not True:
                if i['data'] == 'skipped':
                    self.skipped_count += 1
                    self.event_signal.emit({'type': 'post_skipped', 'data': {
                        'post_no': i['post_no'],
                        'message': i.get('message') or '이미 삭제되었거나 목록에 없는 항목입니다.',
                        'delay': i.get('delay', 0),
                    }})
                    continue
                if i['data'] == 'captcha':
                    # Clear before notifying the GUI so an immediate reply is retained.
                    self.captcha_resumed.clear()
                    self.event_signal.emit({'type': 'captcha'})
                    self.captcha_resumed.wait()
                    continue
                return self.fail(i)
            self.deleted_count += 1
            self.event_signal.emit({'type': 'post_update', 'data': i['data']})
        return True

    def run(self):
        self.deleted_count = 0
        self.skipped_count = 0
        try:
            galleries = [None] if self.del_all else self.del_list
            for gno in galleries:
                if not self.delete(gno):
                    return
        except Exception as exc:
            self.event_signal.emit({
                'type': 'fail',
                'message': f'삭제 작업 중 오류가 발생했습니다 ({type(exc).__name__}).\n잠시 후 다시 시도해 주세요.',
            })
            return
        finally:
            self.posting_consent = False

        self.event_signal.emit({'type': 'complete', 'data': {
            'deleted_count': self.deleted_count,
            'skipped_count': self.skipped_count,
        }})
