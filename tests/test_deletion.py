import socket
import unittest
from unittest.mock import Mock, patch

from dcinside_cleaner.dcinside_cleaner import Cleaner, MAX_ATTEMPT


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network disabled in tests'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.sleep = patch('dcinside_cleaner.dcinside_cleaner.time.sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.cleaner = Cleaner()
        self.cleaner.user_id = 'test-user'
        self.cleaner.post_list = ['101', '102']
        self.cleaner.session = Mock()
        self.cleaner.session.cookies.get_dict.return_value = {'ci_c': 'test-csrf'}
        self.cleaner.session.get.return_value = Mock(status_code=200, text='<html><body></body></html>')

    def response(self, payload, status=200):
        response = Mock(status_code=status)
        response.json.return_value = payload
        self.cleaner.session.post.return_value = response
        return response

    def test_comment_request_retains_existing_payload(self):
        self.response({'result': 'success'})
        self.assertEqual(self.cleaner.deletePost('101', 'comment', False), {})
        request = self.cleaner.session.post.call_args
        self.assertEqual(request.args[0], 'https://gallog.dcinside.com/test-user/ajax/log_list_ajax/delete')
        self.assertEqual(request.kwargs['data'], {'ci_t': 'test-csrf', 'no': '101', 'service_code': 'undefined'})
        self.assertEqual(request.kwargs['headers']['Referer'], 'https://gallog.dcinside.com/test-user/comment')
        self.assertNotIn('Host', self.cleaner.session.headers.update.call_args.args[0])

    def test_posting_acknowledgement_only_when_approved(self):
        self.response({'result': 'confirm', 'msg': '삭제하면 차단됩니다.'})
        self.assertEqual(self.cleaner.deletePost('101', 'posting', False)['result'], 'confirm')
        self.assertEqual(self.cleaner.session.post.call_args.kwargs['data']['c_k_v'], 'dzk')
        self.assertNotIn('del_limit_ok', self.cleaner.session.post.call_args.kwargs['data'])
        self.response({'result': 'success'})
        self.assertEqual(self.cleaner.deletePost('101', 'posting', False, confirm_delete=True), {})
        self.assertEqual(self.cleaner.session.post.call_args.kwargs['data']['del_limit_ok'], '1')

    def test_unrecognized_responses_never_return_success(self):
        for payload in ({}, None, [], False, {'result': None}, {'result': 'error'}, {'result': 'fail', 'msg': '추가 절차 필요'}):
            with self.subTest(payload=payload):
                self.response(payload)
                self.assertNotEqual(self.cleaner.deletePost('101', 'posting', False), {})

    def test_http_error_cannot_be_success(self):
        self.response({'result': 'success'}, status=500)
        self.assertNotEqual(self.cleaner.deletePost('101', 'posting', False), {})

    def test_invalid_json_stops_without_reposting(self):
        response = self.response(None)
        response.json.side_effect = ValueError('HTML response')
        self.assertNotEqual(self.cleaner.deletePost('101', 'posting', False), {})
        self.cleaner.session.post.assert_called_once()

    def test_missing_csrf_or_unavailable_page_does_not_post(self):
        self.cleaner.session.cookies.get_dict.return_value = {}
        self.assertNotEqual(self.cleaner.deletePost('101', 'posting', False), {})
        self.cleaner.session.post.assert_not_called()
        self.cleaner.session.get.return_value.status_code = 403
        self.assertNotEqual(self.cleaner.deletePost('101', 'posting', False), {})
        self.cleaner.session.post.assert_not_called()

    def test_failures_keep_queue_and_never_yield_success(self):
        for payload in (False, None, 'FAILED', 'BLOCKED', [], {'result': 'fail', 'msg': '추가 확인 필요'}, {'result': 'unknown'}, {'result': None}):
            with self.subTest(payload=payload):
                self.cleaner.deletePost = Mock(return_value=payload)
                events = list(self.cleaner.deletePosts('posting'))
                self.assertEqual(len(events), 1)
                self.assertFalse(events[0]['status'])
                self.assertEqual(self.cleaner.post_list, ['101', '102'])

    def test_success_is_counted_once_per_item_for_both_modes(self):
        for mode in ('posting', 'comment'):
            with self.subTest(mode=mode):
                self.cleaner.post_list = ['101', '102']
                self.cleaner.deletePost = Mock(return_value={})
                events = list(self.cleaner.deletePosts(mode))
                self.assertEqual([event['data']['del_no'] for event in events], ['101', '102'])
                self.assertTrue(all(event['status'] for event in events))
                self.assertEqual(self.cleaner.post_list, [])

    def test_confirm_retries_same_item_and_resets_ack_for_next(self):
        self.cleaner.deletePost = Mock(side_effect=[{'result': 'confirm', 'msg': '삭제 시 차단됩니다.'}, {}, {}])
        confirmation = Mock(return_value=True)
        events = list(self.cleaner.deletePosts('posting', confirm_deletion=confirmation))
        confirmation.assert_called_once_with('삭제 시 차단됩니다.', '101')
        self.assertEqual([event['data']['del_no'] for event in events], ['101', '102'])
        calls = self.cleaner.deletePost.call_args_list
        self.assertEqual([call.args[0] for call in calls], ['101', '101', '102'])
        self.assertEqual([call.kwargs['confirm_delete'] for call in calls], [False, True, False])

    def test_declined_confirmation_does_not_delete_or_count(self):
        self.cleaner.deletePost = Mock(return_value={'result': 'confirm', 'msg': '차단 안내'})
        events = list(self.cleaner.deletePosts('posting', confirm_deletion=lambda *_: False))
        self.assertEqual(events[0]['data'], 'cancelled')
        self.assertFalse(events[0]['status'])
        self.assertEqual(self.cleaner.post_list, ['101', '102'])
        self.cleaner.deletePost.assert_called_once()

    def test_missing_confirmation_handler_stops(self):
        self.cleaner.deletePost = Mock(return_value={'result': 'confirm', 'msg': '차단 안내'})
        events = list(self.cleaner.deletePosts('posting'))
        self.assertFalse(events[0]['status'])
        self.assertEqual(self.cleaner.post_list, ['101', '102'])
        self.cleaner.deletePost.assert_called_once()

    def test_repeated_confirmation_after_approval_stops(self):
        self.cleaner.deletePost = Mock(return_value={'result': 'confirm', 'msg': '차단 안내'})
        confirmation = Mock(return_value=True)
        events = list(self.cleaner.deletePosts('posting', confirm_deletion=confirmation))
        self.assertEqual(events[0]['data'], 'failed')
        self.assertEqual(self.cleaner.deletePost.call_count, 2)
        confirmation.assert_called_once()
        self.assertEqual(self.cleaner.post_list, ['101', '102'])

    def test_manual_captcha_retries_without_popping_item(self):
        self.cleaner.deletePost = Mock(side_effect=[{'result': 'captcha'}, {}, {}])
        events = self.cleaner.deletePosts('comment')
        self.assertEqual(next(events), {'status': False, 'data': 'captcha'})
        self.assertEqual(self.cleaner.post_list, ['101', '102'])
        successes = list(events)
        self.assertEqual([event['data']['del_no'] for event in successes], ['101', '102'])
        self.assertEqual([call.args[0] for call in self.cleaner.deletePost.call_args_list], ['101', '101', '102'])

    def test_automatic_captcha_retries_are_bounded(self):
        self.cleaner.twocaptcha_key = 'fake-key'
        self.cleaner.deletePost = Mock(return_value={'result': 'captcha'})
        events = list(self.cleaner.deletePosts('posting'))
        self.assertEqual(events[0]['data'], 'failed')
        self.assertEqual(self.cleaner.deletePost.call_count, MAX_ATTEMPT)
        self.assertEqual(self.cleaner.post_list, ['101', '102'])

    def test_blocked_collection_stops_without_appending_error_text(self):
        self.cleaner.getPageCount = Mock(return_value=1)
        self.cleaner.getPostList = Mock(return_value='BLOCKED')
        events = list(self.cleaner.aggregatePosts(None, 'posting'))
        self.assertEqual(events, [{'status': False, 'data': 'ipblocked'}])
        self.assertEqual(self.cleaner.post_list, [])

    def test_missing_item_skips_only_that_number_in_both_modes(self):
        for mode in ('posting', 'comment'):
            with self.subTest(mode=mode):
                self.cleaner.post_list = ['101', '102', '103']
                self.cleaner.deletePost = Mock(side_effect=[{}, {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'}, {}])
                events = list(self.cleaner.deletePosts(mode))
                self.assertEqual([event['status'] for event in events], [True, False, True])
                self.assertEqual(events[1]['data'], 'skipped')
                self.assertEqual(events[1]['post_no'], '102')
                self.assertEqual([event['data']['del_no'] for event in events if event['status']], ['101', '103'])
                self.assertEqual(self.cleaner.post_list, [])

    def test_known_invalid_number_response_variants(self):
        for message in ('올바르지 않은 번호', '올바르지 않은 번호입니다.', '\n 올바르지 않은 번호 입니다. \n', '올바르지 않은\n번호입니다!'):
            for result in ('fail', 'error'):
                with self.subTest(message=message, result=result):
                    self.assertTrue(Cleaner.isMissingPostResponse({'result': result, 'msg': message}))

    def test_other_errors_are_not_missing_items(self):
        for message in ('올바르지 않은 접근입니다.', '올바르지 않은 인증 번호입니다.', '로그인 후 이용해 주세요.', '삭제 권한이 없습니다.', '올바르지 않은 번호입니다. 다시 로그인해 주세요.', '잘못된 요청입니다.', '', None):
            with self.subTest(message=message):
                self.assertFalse(Cleaner.isMissingPostResponse({'result': 'fail', 'msg': message}))
        for result in ('success', 'confirm', 'captcha', 'unknown', None):
            with self.subTest(result=result):
                self.assertFalse(Cleaner.isMissingPostResponse({'result': result, 'msg': '올바르지 않은 번호입니다.'}))

    def test_manual_deletion_of_later_item_during_captcha_does_not_stop_queue(self):
        self.cleaner.post_list = ['101', '102', '103']
        self.cleaner.deletePost = Mock(side_effect=[{'result': 'captcha'}, {}, {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'}, {}])
        iterator = self.cleaner.deletePosts('comment')
        self.assertEqual(next(iterator), {'status': False, 'data': 'captcha'})
        self.assertEqual(self.cleaner.post_list, ['101', '102', '103'])
        events = list(iterator)
        self.assertEqual([event['status'] for event in events], [True, False, True])
        self.assertEqual(events[1]['post_no'], '102')
        self.assertEqual(events[1]['data'], 'skipped')
        self.assertEqual([call.args[0] for call in self.cleaner.deletePost.call_args_list], ['101', '101', '102', '103'])
        self.assertEqual(self.cleaner.post_list, [])

    def test_manual_deletion_of_current_item_during_captcha_retries_then_skips(self):
        self.cleaner.deletePost = Mock(side_effect=[{'result': 'captcha'}, {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'}, {}])
        events = list(self.cleaner.deletePosts('posting'))
        self.assertEqual([event['data'] if not event['status'] else 'success' for event in events], ['captcha', 'skipped', 'success'])
        self.assertEqual(events[1]['post_no'], '101')
        self.assertEqual(events[2]['data']['del_no'], '102')
        self.assertEqual(self.cleaner.post_list, [])

    def test_skipping_resets_confirmation_and_captcha_state_for_next_item(self):
        self.cleaner.twocaptcha_key = 'fake-key'
        self.cleaner.deletePost = Mock(side_effect=[{'result': 'confirm', 'msg': '차단 안내'}, {'result': 'captcha'}, {'result': 'fail', 'msg': '올바르지 않은 번호입니다.'}, {}])
        events = list(self.cleaner.deletePosts('posting', confirm_deletion=lambda *_: True))
        self.assertEqual(events[0]['data'], 'skipped')
        self.assertEqual(events[1]['data']['del_no'], '102')
        calls = self.cleaner.deletePost.call_args_list
        self.assertEqual([call.kwargs['confirm_delete'] for call in calls], [False, True, True, False])
        self.assertEqual([call.args[2] for call in calls], [False, False, True, False])
        self.assertFalse(events[1]['data']['captcha_solved'])

    def test_real_failure_after_skipped_item_still_stops_with_queue_preserved(self):
        self.cleaner.post_list = ['101', '102', '103']
        self.cleaner.deletePost = Mock(side_effect=[{'result': 'fail', 'msg': '올바르지 않은 번호입니다.'}, {'result': 'fail', 'msg': '로그인이 필요합니다.'}])
        events = list(self.cleaner.deletePosts('posting'))
        self.assertEqual([event['data'] for event in events], ['skipped', 'failed'])
        self.assertTrue(all(event['status'] is False for event in events))
        self.assertEqual(self.cleaner.post_list, ['102', '103'])

    def test_all_missing_items_finish_without_any_delete_success(self):
        self.cleaner.deletePost = Mock(return_value={'result': 'fail', 'msg': '올바르지 않은 번호입니다.'})
        events = list(self.cleaner.deletePosts('comment'))
        self.assertEqual([event['data'] for event in events], ['skipped', 'skipped'])
        self.assertTrue(all(event['status'] is False for event in events))
        self.assertEqual(self.cleaner.post_list, [])


if __name__ == '__main__':
    unittest.main()
