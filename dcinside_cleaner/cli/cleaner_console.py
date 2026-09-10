from ..dcinside_cleaner import Cleaner
from getpass import getpass
from tqdm import tqdm
import json
import re

class Console:
    p_type_dict = {'-p': 'posting', '-c': 'comment'}
    def __init__(self):
        self.cleaner = Cleaner()
        self.login_flag = False
        self.g_list = {'type':  None}
        self.posting_consent = False
        self.deleted_count = 0
        self.skipped_count = 0
        self.getCommand()
        self.articles = 0

    def parseAndExecute(self, cmd : str) -> None:
        cmd = cmd.split()

        if cmd[0] == 'help':
            print('login (-saved) - 로그인합니다. "-saved" 옵션은 저장된 파일을 통해 로그인합니다.')
            print('export login - 로그인 정보를 dcinside-cleaner-login.json으로 내보냅니다.')
            print('getglist -p | -c - 갤러리 리스트를 가져옵니다. "-p"는 글, "-c"는 댓글입니다.')
            print('del all | 1 2 3 4 ... | 1 ~ 4 - 선택한 갤러리에 대해 삭제를 수행합니다.')
            print('logout - 로그아웃합니다.')
            print('help - 도움말을 봅니다.')
            print('exit - 종료합니다.')
            return

        elif cmd[0] == 'login':
            if self.login_flag:
                print('이미 로그인되었습니다.')
                return 0
            if len(cmd) > 1 and cmd[1] == '-saved':
                with open('dcinside-cleaner-login.json', 'r') as f:
                    data = json.load(f)
                    res = self.cleaner.loginFromCookies(data['cookies'])
                    if res:
                        print('로그인되었습니다.')
                    else:
                        print('로그인에 실패하였습니다.')
                        return 0
                    self.cleaner.setUserId(data['user_id'])
                self.login_flag = True
                return
            self.user_id = input('ID >> ')
            self.user_pw = getpass('PW >> ')
            res = self.cleaner.login(self.user_id, self.user_pw)
            if res:
                print('로그인되었습니다.')
                self.login_flag = True
            else:
                print('로그인에 실패하였습니다.')
                return

        if not self.login_flag: print('로그인해 주십시오.')

        elif cmd[0] == 'export':
            data = {
                'cookies': self.cleaner.getCookies(),
                'user_id': self.cleaner.getUserId()
            }
            with open('dcinside-cleaner-login.json', 'wt', encoding='utf-8') as f:
                f.write(json.dumps(data))

        elif cmd[0] == 'getglist':
            if len(cmd) < 2:
                print('옵션을 입력하십시오.')
                return
            if not cmd[1] in self.p_type_dict:
                print('옵션이 올바르지 않습니다.')
                return
            post_type = self.p_type_dict[cmd[1]]
            g_list = self.cleaner.getGallList(post_type)
            if g_list == 'BLOCKED':
                print('IP 차단이 감지되었습니다.')
                return
            if not self.g_list:
                print('갤러리 리스트가 없습니다.')
                return
            self.g_list = {'type': post_type}
            idx = 1
            for k in g_list:
                gno = k
                gname = g_list[k]
                self.g_list[idx] = gno
                print(f'{idx}. {gname}')
                idx += 1

        elif cmd[0] == 'del':
            self.posting_consent = False
            self.deleted_count = 0
            self.skipped_count = 0
            if self.g_list['type'] == None:
                print('갤러리 리스트를 선택하지 않았습니다.')
            del_list = []
            if cmd[1] == 'all':
                del_list = map(str, self.g_list.keys())
            elif '~' in cmd:
                cmd = ''.join(cmd[1:]).replace(',', ' ')
                regex = re.compile(r'(\d+)~(\d+)')
                numbers = regex.findall(cmd)
                for number in numbers:
                    a, b = map(int, number)
                    del_list += [str(i) for i in range(a, b+1)]
            else:
                del_list = cmd[1:]
            del_list = sorted(list(set(del_list)))
            for del_no in del_list:
                if del_no.isdigit():
                    gno = self.g_list[int(del_no)]
                    post_type = self.g_list['type']
                    if self.delete(gno, post_type) is False:
                        if self.skipped_count:
                            print(f'처리 중단: 삭제 {self.deleted_count}개, 건너뜀 {self.skipped_count}개')
                        return
            if self.skipped_count:
                print(f'처리 완료: 삭제 {self.deleted_count}개, 건너뜀 {self.skipped_count}개')

        elif cmd[0] == 'logout':
            self.login_flag = False
            self.user_id, self.user_pw = ''

    
    def confirmDeletion(self, message, post_no):
        if self.posting_consent:
            return True
        print(message)
        print('동의하면 이번 삭제 작업에서 사이트가 요청하는 추가 확인에 자동으로 동의합니다.')
        self.posting_consent = input(f'{post_no}번 글부터 삭제를 계속하시겠습니까? [y/N] >> ').strip().lower() in ('y', 'yes', '예')
        return self.posting_consent

    def delete(self, gno, post_type):
        print('글 목록 가져오는 중...')
        with tqdm(total=self.cleaner.getPageCount(gno, post_type)) as pbar:
            for i in self.cleaner.aggregatePosts(gno, post_type):
                if i['status'] is not True:
                    message = 'IP 차단이 감지되었습니다.' if i['data'] == 'ipblocked' else '글 목록을 가져오지 못했습니다.'
                    print(i.get('message') or message)
                    return False
                pbar.update(1)

        print('글 지우는 중...')
        with tqdm(total=len(self.cleaner.post_list)) as pbar:
            for i in self.cleaner.deletePosts(post_type, confirm_deletion=self.confirmDeletion):
                if i['status'] is not True:
                    if i['data'] == 'skipped':
                        self.skipped_count += 1
                        print(f"{i['post_no']}번 항목 건너뜀: {i.get('message') or '이미 삭제되었거나 목록에 없는 항목입니다.'}")
                        pbar.update(1)
                        continue
                    if i['data'] == 'captcha':
                        print('reCAPTCHA Detected!')
                        input('캡차를 해제한 후 엔터키를 눌러주십시오.')
                        continue
                    message = {
                        'ipblocked': 'IP 차단이 감지되었습니다.',
                        'cancelled': '삭제를 취소했습니다.',
                    }.get(i['data'], '삭제에 실패했습니다.')
                    print(i.get('message') or message)
                    return False
                self.deleted_count += 1
                pbar.update(1)
        return True

    def getCommand(self):
        print('dcinside cleaner')
        print('사용법은 help를 입력하세요.')
        while True:
            cmd = input('>> ')
            if cmd == 'exit':
                break
            try:
                self.parseAndExecute(cmd)
            except Exception as e:
                print(e)
                print('문제가 발생하였습니다.')
