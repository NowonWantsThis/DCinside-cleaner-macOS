import os
import socket
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtWidgets
from PyQt5.QtTest import QSignalSpy

from dcinside_cleaner.gui.cleaner_gui import MainWindow


class DeletionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network disabled in tests'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.sleep = patch('dcinside_cleaner.dcinside_cleaner.time.sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.window = MainWindow()
        self.window.updateUserInfo = Mock()
        self.window.askDeleteConfirmation = Mock(return_value=True)
        self.window.checkbox_gall_all.setChecked(True)
        cleaner = self.window.cleaner
        cleaner.user_id = 'test-user'
        cleaner.delay = 0
        cleaner.getPageCount = Mock(return_value=1)
        cleaner.getPostList = Mock(return_value=['101', '102'])
        cleaner.session = Mock()
        cleaner.session.cookies.get_dict.return_value = {'ci_c': 'test-csrf'}
        cleaner.session.get.return_value = Mock(status_code=200, text='<body></body>')
        self.events = []
        self.window.cleaner_thread.event_signal.connect(self.events.append)

    def tearDown(self):
        self.assertFalse(self.window.cleaner_thread.isRunning())
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def run_deletion(self, mode, payloads, post_list=None):
        self.window.p_type = mode
        if post_list is not None:
            self.window.cleaner.getPostList.return_value = post_list
        self.window.cleaner.session.post.side_effect = [
            Mock(status_code=200, json=Mock(return_value=data)) for data in payloads
        ]
        finished = QSignalSpy(self.window.cleaner_thread.finished)
        with patch.object(QtWidgets.QMessageBox, 'information'), patch.object(QtWidgets.QMessageBox, 'warning'):
            self.window.delete()
            self.assertTrue(finished.wait(3000), 'Deletion worker did not finish')
            self.app.processEvents()

    def test_posting_warns_once_and_confirms_each_restricted_post(self):
        self.run_deletion('posting', [
            {'result': 'confirm', 'msg': "'일반' 말머리의 글 삭제 시, 매니저에 의해 차단됩니다."},
            {'result': 'success'},
            {'result': 'confirm', 'msg': '삭제 시 차단됩니다.'},
            {'result': 'success'},
        ])
        self.window.askDeleteConfirmation.assert_called_once()
        calls = self.window.cleaner.session.post.call_args_list
        self.assertEqual([call.kwargs['data']['no'] for call in calls], ['101', '101', '102', '102'])
        self.assertEqual([call.kwargs['data'].get('del_limit_ok') for call in calls], [None, '1', None, '1'])
        self.assertEqual([event['type'] for event in self.events].count('post_update'), 2)
        self.assertEqual(self.events[-1]['type'], 'complete')
        self.assertEqual(self.window.progress_cur, 2)
        self.assertFalse(self.window.cleaner_thread.posting_consent)

    def test_comment_success_needs_no_posting_warning_or_confirmation(self):
        self.run_deletion('comment', [{'result': 'success'}, {'result': 'success'}])
        self.window.askDeleteConfirmation.assert_not_called()
        self.assertEqual(self.window.cleaner.session.post.call_count, 2)
        self.assertEqual(self.window.progress_cur, 2)
        self.assertEqual(self.events[-1]['type'], 'complete')

    def test_failure_after_one_success_preserves_count_without_complete(self):
        self.run_deletion('posting', [{'result': 'success'}, {'result': 'fail', 'msg': '삭제가 거절되었습니다.'}])
        self.assertEqual(self.window.progress_cur, 1)
        self.assertEqual(self.window.progress_bar.value(), 50)
        self.assertEqual(self.window.cleaner.post_list, ['102'])
        self.assertEqual(self.events[-1]['type'], 'fail')
        self.assertFalse(any(event['type'] == 'complete' for event in self.events))
        self.assertTrue(self.window.btn_start.isEnabled())

    def test_captcha_then_manually_deleted_later_item_continues_in_both_modes(self):
        for mode in ('posting', 'comment'):
            with self.subTest(mode=mode):
                self.events.clear()
                self.run_deletion(mode, [
                    {'result': 'captcha'},
                    {'result': 'success'},
                    {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'},
                    {'result': 'success'},
                ], post_list=['101', '102', '103'])
                self.assertEqual([event['type'] for event in self.events].count('post_update'), 2)
                skipped = [event for event in self.events if event['type'] == 'post_skipped']
                self.assertEqual(len(skipped), 1)
                self.assertEqual(skipped[0]['data']['post_no'], '102')
                self.assertEqual(self.events[-1], {'type': 'complete', 'data': {'deleted_count': 2, 'skipped_count': 1}})
                self.assertEqual(self.window.progress_cur, 3)
                self.assertEqual(self.window.progress_bar.value(), 100)
                self.assertEqual(self.window.cleaner.post_list, [])
                self.assertIn('삭제 2개', self.window.box_log.toPlainText())
                self.assertIn('건너뜀 1개', self.window.box_log.toPlainText())

    def test_all_missing_items_complete_with_zero_deletions(self):
        self.run_deletion('comment', [
            {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'},
            {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'},
        ])
        self.assertFalse(any(event['type'] == 'post_update' for event in self.events))
        self.assertEqual(self.events[-1], {'type': 'complete', 'data': {'deleted_count': 0, 'skipped_count': 2}})
        self.assertEqual(self.window.progress_bar.value(), 100)
        self.assertIn('삭제 0개', self.window.box_log.toPlainText())
        self.assertIn('건너뜀 2개', self.window.box_log.toPlainText())

    def test_permission_failure_after_skipped_item_still_stops(self):
        self.run_deletion('posting', [
            {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'},
            {'result': 'fail', 'msg': '삭제 권한이 없습니다.'},
        ], post_list=['101', '102', '103'])
        self.assertEqual([event['type'] for event in self.events].count('post_skipped'), 1)
        self.assertFalse(any(event['type'] in ('post_update', 'complete') for event in self.events))
        self.assertEqual(self.events[-1]['type'], 'fail')
        self.assertEqual(self.window.cleaner.post_list, ['102', '103'])
        self.assertEqual(self.window.progress_cur, 1)
        self.assertTrue(self.window.btn_start.isEnabled())


if __name__ == '__main__':
    unittest.main()
