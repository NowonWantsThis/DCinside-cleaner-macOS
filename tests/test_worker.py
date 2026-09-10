import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtCore, QtWidgets

from dcinside_cleaner.gui.cleaner_thread import CleanerThread
from dcinside_cleaner.gui.cleaner_gui import MainWindow
from dcinside_cleaner.cli.cleaner_console import Console


def success(post_no='123'):
    return {'status': True, 'data': {
        'del_no': post_no, 'delay': 0.1, 'proxy': '', 'captcha_solved': False,
    }}


def skipped(post_no='123'):
    return {
        'status': False, 'data': 'skipped', 'post_no': post_no,
        'message': '올바르지 않은 번호입니다.', 'delay': 0.2,
    }


class SignalSource(QtCore.QObject):
    captcha = QtCore.pyqtSignal(bool)


class FakeCleaner:
    def __init__(self, events=None, collection_failure=None, confirm_count=0):
        self.events = [success()] if events is None else events
        self.collection_failure = collection_failure
        self.confirm_count = confirm_count
        self.post_list = ['123', '456']
        self.galleries = []
        self.confirmations = []

    def getPageCount(self, gno, post_type):
        return 1

    def aggregatePosts(self, gno, post_type):
        self.galleries.append(gno)
        if self.collection_failure:
            yield self.collection_failure
            return
        yield {'status': True, 'data': {'index': 1, 'delay': 0.1, 'proxy': ''}}

    def deletePosts(self, post_type, confirm_deletion=None):
        for index in range(self.confirm_count):
            accepted = confirm_deletion('삭제하면 갤러리에서 차단될 수 있습니다.', str(index))
            self.confirmations.append(accepted)
            if not accepted:
                yield {'status': False, 'data': 'cancelled', 'message': '삭제를 취소했습니다.'}
                return
        yield from self.events


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_worker(self, cleaner, post_type='posting', consent=False):
        self.signals = SignalSource()
        worker = CleanerThread(self.signals.captcha)
        worker.setCleaner(cleaner)
        worker.setDelInfo(['first', 'second'], post_type, False, posting_consent=consent)
        events = []
        worker.event_signal.connect(events.append)
        return worker, events

    def test_failure_stops_remaining_galleries_without_success_or_complete(self):
        cleaner = FakeCleaner(events=[{'status': False, 'data': 'failed', 'message': '실제 삭제가 확인되지 않았습니다.', 'post_no': '123'}])
        worker, events = self.make_worker(cleaner)
        worker.run()
        self.assertEqual(cleaner.galleries, ['first'])
        self.assertEqual(events[-1], {'type': 'fail', 'message': '실제 삭제가 확인되지 않았습니다.', 'post_no': '123'})
        self.assertFalse(any(event['type'] in ('post_update', 'complete') for event in events))

    def test_collection_failure_does_not_start_deletion(self):
        cleaner = FakeCleaner(collection_failure={'status': False, 'data': 'ipblocked'})
        worker, events = self.make_worker(cleaner)
        worker.run()
        self.assertEqual(cleaner.galleries, ['first'])
        self.assertEqual([event['type'] for event in events], ['pages', 'ipblocked'])

    def test_exception_emits_failure_without_complete(self):
        cleaner = FakeCleaner()
        cleaner.getPageCount = Mock(side_effect=RuntimeError('failure'))
        worker, events = self.make_worker(cleaner)
        worker.run()
        self.assertEqual([event['type'] for event in events], ['fail'])
        self.assertIn('RuntimeError', events[0]['message'])

    def test_captcha_immediate_reply_is_not_lost_or_counted(self):
        cleaner = FakeCleaner(events=[{'status': False, 'data': 'captcha'}, success()])
        worker, events = self.make_worker(cleaner, post_type='comment')
        worker.setDelInfo(['first'], 'comment', False)
        worker.event_signal.connect(lambda event: worker.checkCaptcha() if event['type'] == 'captcha' else None)
        worker.run()
        self.assertEqual([event['type'] for event in events].count('post_update'), 1)
        self.assertEqual(events[-1]['type'], 'complete')

    def test_prior_consent_covers_all_posts_and_clears_after_run(self):
        cleaner = FakeCleaner(confirm_count=2)
        worker, events = self.make_worker(cleaner, consent=True)
        worker.run()
        self.assertEqual(cleaner.confirmations, [True] * 4)
        self.assertFalse(any(event['type'] == 'confirmation' for event in events))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertFalse(worker.posting_consent)

    def test_next_run_does_not_inherit_consent(self):
        cleaner = FakeCleaner(confirm_count=1)
        worker, events = self.make_worker(cleaner, consent=True)
        worker.run()
        events.clear()
        worker.setDelInfo(['first'], 'posting', False)
        worker.event_signal.connect(lambda event: worker.setDeleteConfirmation(False) if event['type'] == 'confirmation' else None)
        worker.run()
        self.assertEqual(events[-1]['type'], 'cancelled')
        self.assertFalse(any(event['type'] in ('post_update', 'complete') for event in events))

    def test_comment_run_ignores_posting_consent_and_keeps_success_flow(self):
        worker, events = self.make_worker(FakeCleaner(), post_type='comment', consent=True)
        self.assertFalse(worker.posting_consent)
        worker.run()
        self.assertEqual([event['type'] for event in events].count('post_update'), 2)
        self.assertEqual(events[-1]['type'], 'complete')

    def test_skipped_after_captcha_continues_and_counts_across_galleries(self):
        cleaner = FakeCleaner(events=[{'status': False, 'data': 'captcha'}, skipped(), success('456')])
        worker, events = self.make_worker(cleaner, post_type='comment')
        worker.event_signal.connect(lambda event: worker.checkCaptcha() if event['type'] == 'captcha' else None)
        worker.run()
        self.assertEqual(cleaner.galleries, ['first', 'second'])
        self.assertEqual([event['type'] for event in events].count('post_skipped'), 2)
        self.assertEqual([event['type'] for event in events].count('post_update'), 2)
        self.assertFalse(any(event['type'] == 'fail' for event in events))
        self.assertEqual(events[-1], {'type': 'complete', 'data': {'deleted_count': 2, 'skipped_count': 2}})
        skipped_event = next(event for event in events if event['type'] == 'post_skipped')
        self.assertEqual(skipped_event['data'], {'post_no': '123', 'message': '올바르지 않은 번호입니다.', 'delay': 0.2})

    def test_failure_after_skipped_still_stops_without_counting_later_items(self):
        cleaner = FakeCleaner(events=[skipped(), {'status': False, 'data': 'failed'}, success('456')])
        worker, events = self.make_worker(cleaner)
        worker.run()
        self.assertEqual(cleaner.galleries, ['first'])
        self.assertEqual(worker.deleted_count, 0)
        self.assertEqual(worker.skipped_count, 1)
        self.assertEqual(events[-1]['type'], 'fail')
        self.assertFalse(any(event['type'] in ('post_update', 'complete') for event in events))

    def test_outcome_counts_reset_on_next_run(self):
        cleaner = FakeCleaner(events=[skipped()])
        worker, events = self.make_worker(cleaner)
        worker.run()
        self.assertEqual(events[-1]['data'], {'deleted_count': 0, 'skipped_count': 2})
        cleaner.events = [success()]
        worker.setDelInfo(['first'], 'posting', False)
        worker.run()
        self.assertEqual(events[-1]['data'], {'deleted_count': 1, 'skipped_count': 0})


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.cleaner_thread.start = Mock()
        self.window.updateUserInfo = Mock()
        self.window.cleaner.setProxyList = Mock()
        self.window.checkbox_gall_all.setChecked(True)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_posting_warns_once_per_start_and_new_run_warns_again(self):
        self.window.p_type = 'posting'
        with patch.object(self.window, 'askDeleteConfirmation', return_value=True) as confirm:
            self.window.delete()
            self.assertEqual(confirm.call_count, 1)
            self.assertTrue(self.window.cleaner_thread.posting_consent)
            self.window.cleaner_thread.finished.emit()
            self.window.p_type = 'posting'
            self.window.delete()
            self.assertEqual(confirm.call_count, 2)
        self.assertEqual(self.window.cleaner_thread.start.call_count, 2)

    def test_cancelled_warning_starts_no_deletion(self):
        self.window.p_type = 'posting'
        with patch.object(self.window, 'askDeleteConfirmation', return_value=False):
            self.window.delete()
        self.window.cleaner_thread.start.assert_not_called()

    def test_comments_start_without_posting_warning(self):
        self.window.p_type = 'comment'
        self.window.deleted_count = 5
        self.window.skipped_count = 3
        with patch.object(self.window, 'askDeleteConfirmation') as confirm:
            self.window.delete()
        confirm.assert_not_called()
        self.assertFalse(self.window.cleaner_thread.posting_consent)
        self.window.cleaner_thread.start.assert_called_once()
        self.assertEqual((self.window.deleted_count, self.window.skipped_count), (0, 0))

    def test_failure_preserves_count_and_unlocks_only_on_finished(self):
        self.window.setProgress('삭제 중', 1, 3)
        self.window.group_box_gall.setEnabled(False)
        self.window.btn_start.setEnabled(False)
        self.window.setProxyControlsBusy(True)
        with patch.object(QtWidgets.QMessageBox, 'warning') as warning:
            self.window.deleteEvent({'type': 'fail', 'message': '삭제가 확인되지 않았습니다.'})
        self.assertEqual(self.window.progress_cur, 1)
        self.assertEqual(self.window.progress_bar.value(), 33)
        self.assertFalse(self.window.btn_start.isEnabled())
        self.assertIn('삭제가 확인되지 않았습니다.', warning.call_args.args)
        self.window.cleaner_thread.finished.emit()
        self.assertTrue(self.window.btn_start.isEnabled())
        self.assertTrue(self.window.group_box_gall.isEnabled())
        self.assertFalse(self.window.proxy_controls_busy)
        self.assertEqual(self.window.progress_cur, 1)
        self.assertNotEqual(self.window.label_progress_status.text(), '완료')

    def test_warning_defaults_to_cancel_and_displays_plain_text(self):
        def inspect_dialog(dialog):
            self.assertIs(dialog.defaultButton(), dialog.button(QtWidgets.QMessageBox.Cancel))
            self.assertIs(dialog.escapeButton(), dialog.button(QtWidgets.QMessageBox.Cancel))
            self.assertEqual(dialog.textFormat(), QtCore.Qt.PlainText)
            self.assertEqual(dialog.button(QtWidgets.QMessageBox.Yes).text(), '동의하고 삭제')
            return QtWidgets.QMessageBox.Cancel

        with patch.object(QtWidgets.QMessageBox, 'exec_', inspect_dialog):
            self.assertFalse(self.window.askDeleteConfirmation('안내', '이번 작업에만 적용', '동의하고 삭제'))

    def test_skipped_advances_processing_only_and_completion_reports_both_counts(self):
        self.window.deleteEvent({'type': 'posts', 'data': 2})
        self.window.deleteEvent({'type': 'post_skipped', 'data': {
            'post_no': '123', 'message': '올바르지 않은 번호입니다.', 'delay': 0.2,
        }})
        self.assertEqual(self.window.progress_cur, 1)
        self.assertEqual((self.window.deleted_count, self.window.skipped_count), (0, 1))
        self.assertIn('123번 항목 건너뜀', self.window.box_log.toPlainText())
        self.assertNotIn('123번 글 삭제', self.window.box_log.toPlainText())
        self.window.deleteEvent({'type': 'post_update', 'data': success('456')['data']})
        self.assertEqual(self.window.progress_cur, 2)
        self.assertEqual((self.window.deleted_count, self.window.skipped_count), (1, 1))
        with patch.object(QtWidgets.QMessageBox, 'information') as information:
            self.window.deleteEvent({'type': 'complete', 'data': {'deleted_count': 1, 'skipped_count': 1}})
        self.assertIn('삭제: 1개\n건너뜀: 1개', information.call_args.args[2])
        self.assertIn('처리 완료: 삭제 1개, 건너뜀 1개', self.window.box_log.toPlainText())
        self.assertEqual(self.window.progress_bar.value(), 100)

    def test_gallery_change_preserves_outcome_counts(self):
        self.window.deleted_count = 3
        self.window.skipped_count = 2
        self.window.deleteEvent({'type': 'pages', 'data': 1})
        self.window.deleteEvent({'type': 'posts', 'data': 4})
        self.assertEqual((self.window.deleted_count, self.window.skipped_count), (3, 2))
        self.assertEqual(self.window.progress_cur, 0)

    def test_all_skipped_completion_does_not_claim_successful_deletions(self):
        with patch.object(QtWidgets.QMessageBox, 'information') as information:
            self.window.deleteEvent({'type': 'complete', 'data': {'deleted_count': 0, 'skipped_count': 2}})
        self.assertIn('삭제: 0개\n건너뜀: 2개', information.call_args.args[2])
        self.assertNotIn('삭제 완료', self.window.box_log.toPlainText())


class FakeProgress:
    def __init__(self, total):
        self.total = total
        self.count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def update(self, count):
        self.count += count


class ConsoleTests(unittest.TestCase):
    def make_console(self, cleaner):
        console = Console.__new__(Console)
        console.cleaner = cleaner
        console.posting_consent = False
        console.deleted_count = 0
        console.skipped_count = 0
        return console

    def test_failure_and_captcha_do_not_increment_deletion_progress(self):
        cleaner = FakeCleaner(events=[{'status': False, 'data': 'captcha'}, success(), {'status': False, 'data': 'failed'}])
        console = self.make_console(cleaner)
        progress = []

        def make_progress(total):
            result = FakeProgress(total)
            progress.append(result)
            return result

        with patch('dcinside_cleaner.cli.cleaner_console.tqdm', side_effect=make_progress), patch('builtins.print'), patch('builtins.input', return_value='') as prompt:
            self.assertFalse(console.delete('first', 'posting'))
        self.assertEqual(progress[1].count, 1)
        prompt.assert_called_once()

    def test_confirmation_is_cached_only_until_next_command(self):
        console = self.make_console(FakeCleaner())
        console.login_flag = True
        console.g_list = {'type': 'posting', 1: 'first', 2: 'second'}
        with patch('builtins.print'), patch('builtins.input', return_value='y') as prompt:
            self.assertTrue(console.confirmDeletion('안내', '123'))
            self.assertTrue(console.confirmDeletion('안내', '456'))
        prompt.assert_called_once()
        console.delete = Mock(return_value=False)
        console.parseAndExecute('del 1 2')
        self.assertFalse(console.posting_consent)
        console.delete.assert_called_once_with('first', 'posting')

    def test_skipped_counts_as_processed_but_not_deleted(self):
        console = self.make_console(FakeCleaner(events=[skipped(), success('456')]))
        progress = []

        def make_progress(total):
            result = FakeProgress(total)
            progress.append(result)
            return result

        with patch('dcinside_cleaner.cli.cleaner_console.tqdm', side_effect=make_progress), patch('builtins.print') as output:
            self.assertTrue(console.delete('first', 'comment'))
        self.assertEqual(progress[1].count, 2)
        self.assertEqual((console.deleted_count, console.skipped_count), (1, 1))
        self.assertTrue(any('123번 항목 건너뜀' in str(call) for call in output.call_args_list))

    def test_command_summary_accumulates_galleries_and_resets_next_command(self):
        console = self.make_console(FakeCleaner(events=[skipped(), success('456')]))
        console.login_flag = True
        console.g_list = {'type': 'comment', 1: 'first', 2: 'second'}
        with patch('dcinside_cleaner.cli.cleaner_console.tqdm', side_effect=lambda total: FakeProgress(total)), patch('builtins.print') as output:
            console.parseAndExecute('del 1 2')
            self.assertEqual((console.deleted_count, console.skipped_count), (2, 2))
            self.assertEqual(output.call_args.args, ('처리 완료: 삭제 2개, 건너뜀 2개',))
            console.parseAndExecute('del 1')
            self.assertEqual((console.deleted_count, console.skipped_count), (1, 1))
            self.assertEqual(output.call_args.args, ('처리 완료: 삭제 1개, 건너뜀 1개',))


if __name__ == '__main__':
    unittest.main()
