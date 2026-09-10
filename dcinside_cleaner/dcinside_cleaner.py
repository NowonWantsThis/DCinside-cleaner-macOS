from requests.exceptions import ConnectTimeout
from requests.exceptions import ProxyError
from twocaptcha import TwoCaptcha
from bs4 import BeautifulSoup
from typing import Union
from urllib.parse import urljoin
import requests
import urllib3
import time

MAX_DELAY = 0.9
MAX_ATTEMPT = 5

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Cleaner:
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    login_url = 'https://sign.dcinside.com/login?s_url=https%3A%2F%2Fwww.dcinside.com%2F'
    login_headers = {
        "Referer": "https://www.dcinside.com/",
        'User-Agent': user_agent
    }

    delete_headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Host': 'gallog.dcinside.com',
        'Origin': 'https://gallog.dcinside.com',
        'Referer': '',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': user_agent
    }

    dcinside_site_key = '6LcJyr4UAAAAAOy9Q_e9sDWPSHJ_aXus4UnYLfgL'

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({'User-Agent': self.user_agent})
        self.post_list = []
        self.proxy_list = []
        self.twocaptcha_key = ''
        self.solver : TwoCaptcha
        self.delay = MAX_DELAY

    def updateDelay(self):
        self.delay = round(MAX_DELAY / (len(self.proxy_list) or 1), 1)

    def _handleProxyError(func):
        def wrapper(self, *args, **kwargs):
            result = None
            while True:
                try:
                    result = func(self, *args, **kwargs)
                except (ProxyError, ConnectTimeout):
                    self.proxy_list.pop()
                    self.updateDelay()
                else:
                    return result

        return wrapper

    def serializeForm(self, input_elements):
        form = {}
        for element in input_elements:
            name = element.get('name')
            if name:
                form[name] = element.get('value', '')
        return form

    def isLoginFailureResponse(self, response) -> bool:
        text = response.text or ''
        failure_keywords = (
            'history.back()',
            '식별 코드 또는 비밀번호',
            '자동입력 방지코드',
            '비밀번호를 확인',
            '로그인에 실패',
        )
        return any(keyword in text for keyword in failure_keywords)

    def getUserId(self) -> str:
        return self.user_id

    def setUserId(self, user_id: str) -> None:
        self.user_id = user_id

    def setProxyList(self, proxy_list: list) -> None:
        self.proxy_list = list(proxy_list)
        self.updateDelay()

    def set2CaptchaKey(self, key) -> bool:
        twocaptcha_url = f'https://2captcha.com/in.php?key={key}'

        res = requests.get(twocaptcha_url)

        if res.text in ('ERROR_KEY_DOES_NOT_EXIST', 'ERROR_WRONG_USER_KEY'):
            return False
        
        self.twocaptcha_key = key

        self.solver = TwoCaptcha(key)
        
        return True

    def getCookies(self) -> dict:
        return self.session.cookies.get_dict()

    def loginFromCookies(self, cookies: dict) -> bool:
        self.session.cookies.update(cookies)
        res = self.session.get('https://www.dcinside.com/')
        if not BeautifulSoup(res.text, 'html.parser').select('.logout'):
            return False
        return True

    def login(self, user_id: str, user_pw: str) -> bool:
        self.user_id = user_id.lower().strip()
        self.session.headers.update(self.login_headers)

        res = self.session.get(self.login_url)
        soup = BeautifulSoup(res.text, 'html.parser')
        login_form = soup.select_one('form[name=login]') or soup.select_one('form[action*="member_check"]')
        if not login_form:
            return False

        input_elements = login_form.select('input')
        login_data = self.serializeForm(input_elements)
        login_data['ci_t'] = self.session.cookies.get('ci_c', login_data.get('ci_t', ''))
        login_data['user_id'] = user_id
        login_data['pw'] = user_pw

        action_url = urljoin(res.url, login_form.get('action') or '/login/member_check')
        post_headers = {
            'Origin': 'https://sign.dcinside.com',
            'Referer': res.url,
            'User-Agent': self.user_agent,
        }
        res = self.session.post(action_url, data=login_data, headers=post_headers)
        if self.isLoginFailureResponse(res):
            return False

        # Warm the main domain with the newly issued SSO cookies.
        self.session.get('https://www.dcinside.com/')
        return True

    def getUserInfo(self) -> dict:
        self.session.headers.update(self.login_headers)
        res = self.session.get(f'https://gallog.dcinside.com/{self.user_id}')
        soup = BeautifulSoup(res.text, 'html.parser')
        nickname = soup.select_one('#top_bg > div.galler_info > strong').get_text()
        article_num = soup.select_one('#container > article > div > div.wrap_right > section > section:nth-child(2) > div > header > div > h2 > span').get_text()
        comment_num = soup.select_one('#container > article > div > div.wrap_right > section > section:nth-child(3) > div > header > div > h2 > span').get_text()

        remove_bracket = lambda x: x[1:-1]

        return {
            'nickname': nickname,
            'article_num': remove_bracket(article_num),
            'comment_num': remove_bracket(comment_num)
        }

    @_handleProxyError
    def deletePost(self, post_no: str, post_type: str, solve_captcha: bool,
                   confirm_delete: bool = False) -> dict:
        gallog_url = f'https://gallog.dcinside.com/{self.user_id}/{post_type}'

        proxy = self.getProxy()

        self.session.headers.update({'User-Agent': self.user_agent})
        res = self.session.get(gallog_url, proxies=proxy)

        if res.status_code != 200 or not BeautifulSoup(res.text, 'html.parser').select_one('body'):
            return {'result': 'fail', 'msg': '갤로그 페이지를 불러오지 못했습니다. 로그인 상태와 연결을 확인해 주세요.'}
        
        captcha = { 'g-recaptcha-response': self.solveCaptcha(gallog_url) if solve_captcha else 'undefined' }

        csrf_token = self.session.cookies.get_dict().get('ci_c')
        if not csrf_token:
            return {'result': 'fail', 'msg': '로그인 확인 정보가 없습니다. 다시 로그인해 주세요.'}

        form_data = {
            'ci_t': csrf_token,
            'no': post_no,
            'service_code': 'undefined',
            **(captcha if solve_captcha else {})
        }
        if post_type == 'posting':
            form_data['c_k_v'] = 'dzk'
        if confirm_delete:
            form_data['del_limit_ok'] = '1'

        headers = {**self.delete_headers, 'Referer': gallog_url}

        res = self.session.post(
            f'https://gallog.dcinside.com/{self.user_id}/ajax/log_list_ajax/delete',
            data=form_data, proxies=proxy, headers=headers)
        if res.status_code != 200:
            return {'result': 'fail', 'msg': f'삭제 요청에 HTTP {res.status_code} 오류가 발생했습니다. 삭제 여부를 확인해 주세요.'}

        try:
            data = res.json()
        except ValueError:
            # An unrecognized response does not prove that deletion succeeded.
            return {'result': 'fail', 'msg': '삭제 결과를 확인할 수 없는 응답입니다. 갤로그에서 삭제 여부를 확인해 주세요.'}

        if not isinstance(data, dict) or not isinstance(data.get('result'), str):
            return {'result': 'fail', 'msg': '삭제 결과 형식을 확인할 수 없습니다. 갤로그에서 삭제 여부를 확인해 주세요.'}
        if data['result'] == 'success':
            return {}
        return data

    def deletePosts(self, post_type: str, confirm_deletion=None):
        solve_captcha = False
        confirm_delete = False
        captcha_attempts = 0

        while self.post_list:
            post_no = self.post_list[0]

            a = time.time()
            time.sleep(self.delay)
            data = self.deletePost(post_no, post_type, solve_captcha,
                                   confirm_delete=confirm_delete)
            delay = time.time() - a

            if data == 'BLOCKED':
                yield {
                    'status': False,
                    'data': 'ipblocked'
                }
                return

            result = data.get('result', '') if isinstance(data, dict) else ''
            message = data.get('msg', '') if isinstance(data, dict) else ''
            result = result if isinstance(result, str) else ''
            message = message if isinstance(message, str) else ''

            if self.isMissingPostResponse(data):
                # A queued item may have been removed manually during CAPTCHA.
                # Consume only this stale number, without emitting delete success.
                self.post_list.pop(0)
                solve_captcha = False
                confirm_delete = False
                captcha_attempts = 0
                yield {'status': False, 'data': 'skipped', 'post_no': post_no,
                       'message': message, 'delay': round(delay, 1)}
                continue

            if result == 'confirm':
                if confirm_delete:
                    yield {'status': False, 'data': 'failed', 'post_no': post_no,
                           'message': message or '추가 확인 후에도 사이트가 삭제를 승인하지 않았습니다.'}
                    return
                if confirm_deletion is None:
                    yield {'status': False, 'data': 'failed', 'post_no': post_no,
                           'message': message or '사이트에서 삭제 전 추가 확인을 요구했습니다.'}
                    return
                if not confirm_deletion(message or '사이트에서 이 글의 삭제 전 추가 확인을 요구했습니다. 계속하시겠습니까?', post_no):
                    yield {'status': False, 'data': 'cancelled', 'post_no': post_no,
                           'message': '추가 삭제 확인을 취소하여 작업을 중단했습니다.'}
                    return
                confirm_delete = True
                continue

            if 'captcha' in result or ('fail' in result and 'g-recaptcha error!' in message):
                captcha_attempts += 1
                if self.twocaptcha_key and captcha_attempts < MAX_ATTEMPT:
                    solve_captcha = True
                    continue
                if self.twocaptcha_key:
                    yield {'status': False, 'data': 'failed', 'post_no': post_no,
                           'message': '캡차 인증이 반복해서 실패했습니다. 갤로그에서 인증 상태를 확인해 주세요.'}
                    return

                yield {
                    'status': False,
                    'data': 'captcha'
                }
                continue

            # Only deletePost's explicit success sentinel may consume an item.
            if not isinstance(data, dict) or data != {}:
                yield {'status': False, 'data': 'failed', 'post_no': post_no,
                       'message': message or '사이트에서 삭제 성공을 확인하지 못했습니다. 남은 항목은 유지됩니다.'}
                return

            captcha_solved = solve_captcha

            solve_captcha = False
            confirm_delete = False
            captcha_attempts = 0
            self.post_list.pop(0)

            yield {
                'status': True,
                'data': {
                    'proxy': self.proxy_list and self.proxy_list[-1] or '',
                    'del_no': post_no,
                    'delay': round(delay, 1),
                    'captcha_solved': captcha_solved
                }
            }

    @staticmethod
    def isMissingPostResponse(data) -> bool:
        if not isinstance(data, dict) or data.get('result') not in ('fail', 'error'):
            return False
        message = data.get('msg')
        if not isinstance(message, str):
            return False
        normalized = ''.join(message.split()).rstrip('.!。')
        return normalized in ('올바르지않은번호', '올바르지않은번호입니다')

    @_handleProxyError
    def getPageCount(self, gno: str, post_type: str) -> int:
        gallog_url = f'https://gallog.dcinside.com/{self.user_id}/{post_type}/index?{ "cno=" + str(gno) + "&" if gno else "" }p=%s'
        self.session.headers.update({'User-Agent': self.user_agent})

        res = self.session.get(gallog_url % 1, proxies=self.getProxy())
        soup = BeautifulSoup(res.text, 'html.parser')
        pages = 1
        paging_elements = soup.select('.bottom_paging_box > a')

        try:
            if paging_elements:
                if paging_elements[-1].text == '끝':
                    pages = paging_elements[-1]['href'].split('&p=')[-1]
                else:
                    pages = int(paging_elements[-1].text)
            elif soup.select_one('.bottom_paging_box > em').text == '1':
                pass
        except:
            return 0

        return int(pages)

    @_handleProxyError
    def getPostList(self, gno: str, post_type: str, idx: int) -> Union[list, str]:
        gallog_url = f'https://gallog.dcinside.com/{self.user_id}/{post_type}/index?{ "cno=" + str(gno) + "&" if gno else "" }p=%s'
        self.session.headers.update({'User-Agent': self.user_agent})

        res = self.session.get(gallog_url % idx, proxies=self.getProxy())

        soup = BeautifulSoup(res.text, 'html.parser')
        if not soup.select_one('body'):
            return 'BLOCKED'
        post_list_elements = soup.select('.cont_listbox > li')

        if len(post_list_elements) < 1:
            return []

        l = []
        for post_list_element in reversed(post_list_elements):
            post_no = post_list_element['data-no']
            l.append(post_no)

        return l

    def aggregatePosts(self, gno: str, post_type: str) -> None:
        pages = self.getPageCount(gno, post_type)
        self.post_list = []

        for idx in range(pages, 0, -1):
            a = time.time()
            time.sleep(self.delay)
            res = self.getPostList(gno, post_type, idx)
            delay = time.time() - a

            if res == 'BLOCKED':
                yield {
                    'status': False,
                    'data': 'ipblocked'
                }
                return

            self.post_list += res

            yield {
                'status': True,
                'data': {
                    'index': idx,
                    'proxy': self.proxy_list and self.proxy_list[-1] or '',
                    'delay': round(delay, 1)
                }
            }

    @_handleProxyError
    def getGallList(self, post_type: str) -> Union[dict, str]:
        res = self.session.get(
            f'https://gallog.dcinside.com/{self.user_id}/{post_type}', proxies=self.getProxy())

        soup = BeautifulSoup(res.text, 'html.parser')

        if not soup.select_one('body'):
            return 'BLOCKED'

        gall_list_elements = soup.select(
            'div.option_sort.gallog > div > ul > li')

        if len(gall_list_elements) <= 1:
            return {}

        gall_list = {}

        for gall_list_element in gall_list_elements[1:]:
            gno = gall_list_element['data-value']
            gname = gall_list_element.text
            gall_list[gno] = gname
        return gall_list

    def getProxy(self) -> dict:
        if self.proxy_list:
            proxy = self.proxy_list.pop(0)
            self.proxy_list.append(proxy)
            return {
                'http': proxy,
                'https': proxy
            }

        return {}
    
    def solveCaptcha(self, page_url) -> str:
        result = self.solver.recaptcha(sitekey=self.dcinside_site_key, url=page_url)

        return result['code']
