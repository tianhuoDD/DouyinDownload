"""
B站视频上传脚本
基于 biliup 项目源码提取的独立上传工具

使用方法:
  1. 先登录，生成 cookies.json:
       python bilibili_upload.py login

  2. 上传视频:
       python bilibili_upload.py upload --file 视频.mp4 --title "视频标题" --tid 21 --tags 标签1 标签2

依赖安装:
  pip install requests aiohttp
"""

import asyncio
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field, InitVar
from os.path import splitext, basename
from typing import Optional, List, Any, Union

import aiohttp
import requests
import requests.utils
from requests.adapters import HTTPAdapter, Retry

# ──────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────

@dataclass
class Data:
    """投稿数据"""
    copyright: int = 1          # 1=自制, 2=转载
    source: str = ''            # 转载来源
    tid: int = 21               # 分区ID（21=日常）
    cover: str = ''             # 封面URL
    title: str = ''             # 标题
    desc_format_id: int = 0
    desc: str = ''              # 简介
    dynamic: str = ''           # 动态文字
    tag: Union[list, str] = ''  # 标签
    videos: list = field(default_factory=list)
    dtime: Any = None           # 定时发布时间戳
    open_subtitle: InitVar[bool] = False
    subtitle: dict = field(init=False)

    def __post_init__(self, open_subtitle):
        self.subtitle = {"open": int(open_subtitle), "lan": ""}
        if isinstance(self.tag, list):
            self.tag = ','.join(self.tag)

    def set_tag(self, tags: list):
        self.tag = ','.join(str(t) for t in tags)

    def append(self, video: dict):
        self.videos.append(video)


# ──────────────────────────────────────────────
# 核心上传类
# ──────────────────────────────────────────────

class BiliBili:
    APP_KEY = 'ae57252b0c09105d'
    APPSEC  = 'c75875c596a69eb55bd119e74b07cfe3'

    def __init__(self, video: Data):
        self.video = video
        self._auto_os = None
        self.__bili_jct = None
        self.cookies = None
        self.access_token = None
        self.__session = requests.Session()
        self.__session.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        self.__session.headers.update({
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/63.0.3239.108',
            'referer': 'https://www.bilibili.com/',
        })

    # ── 登录 ──────────────────────────────────

    def login(self, cookie_file='cookies.json'):
        """从 cookie 文件加载登录态，失败则扫码登录"""
        if os.path.isfile(cookie_file):
            print(f'[INFO] 读取 Cookie 文件: {cookie_file}')
            self._load(cookie_file)
            try:
                self._login_by_cookies(self.cookies)
                return
            except Exception as e:
                print(f'[WARN] Cookie 登录失败: {e}，尝试扫码登录')
        print('[INFO] 未找到有效 Cookie，启动扫码登录...')
        self._qrcode_login(cookie_file)

    def _load(self, cookie_file):
        with open(cookie_file) as f:
            self.cookies = json.load(f)
        token_info = self.cookies.get('token_info', {})
        self.access_token = token_info.get('access_token')

    def _store(self, cookie_file):
        with open(cookie_file, 'w') as f:
            json.dump(self.cookies, f, ensure_ascii=False, indent=2)
        print(f'[INFO] Cookie 已保存至 {cookie_file}')

    def _login_by_cookies(self, cookie: dict):
        cookies_list = cookie.get('cookie_info', {}).get('cookies', [])
        cookies_dict = {c['name']: c['value'] for c in cookies_list}
        requests.utils.add_dict_to_cookiejar(self.__session.cookies, cookies_dict)
        if 'bili_jct' in cookies_dict:
            self.__bili_jct = cookies_dict['bili_jct']
        r = self.__session.get('https://api.bilibili.com/x/web-interface/nav', timeout=5).json()
        if r['code'] != 0:
            raise Exception(r)
        uname = r.get('data', {}).get('uname', '未知')
        print(f'[INFO] 登录成功，用户: {uname}')

    def _qrcode_login(self, cookie_file='cookies.json'):
        """TV 端二维码登录"""
        params = {
            'appkey': '4409e2ce8ffd12b8',
            'local_id': '0',
            'ts': int(time.time()),
        }
        params['sign'] = hashlib.md5(
            f"{urllib.parse.urlencode(params)}59b43e04ad6965f34319062b478f83dd".encode()
        ).hexdigest()
        r = self.__session.post(
            'http://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code',
            data=params, timeout=5
        ).json()
        if r['code'] != 0:
            raise Exception(f'获取二维码失败: {r}')

        url = r['data']['url']
        print(f'\n请用 B 站 APP 扫描以下二维码登录:\n{url}\n')
        try:
            import qrcode
            qr = qrcode.QRCode()
            qr.add_data(url)
            qr.print_ascii(invert=True)
        except ImportError:
            print('（安装 qrcode 库可在终端显示二维码: pip install qrcode）')

        poll_params = {
            'appkey': '4409e2ce8ffd12b8',
            'auth_code': r['data']['auth_code'],
            'local_id': '0',
            'ts': int(time.time()),
        }
        poll_params['sign'] = hashlib.md5(
            f"{urllib.parse.urlencode(poll_params)}59b43e04ad6965f34319062b478f83dd".encode()
        ).hexdigest()

        for i in range(120):
            time.sleep(2)
            resp = self.__session.post(
                'http://passport.bilibili.com/x/passport-tv-login/qrcode/poll',
                data=poll_params, timeout=5
            ).json()
            if resp['code'] == 0:
                self.cookies = resp['data']
                self.access_token = resp['data']['token_info']['access_token']
                # 补充 cookie_info 格式供后续使用
                cookie_str = resp['data'].get('cookie_info', {})
                self.cookies = resp['data']
                self._store(cookie_file)
                # 重新加载以统一格式
                self._load(cookie_file)
                self._login_by_cookies(self.cookies)
                return
            if resp['code'] == 86038:
                raise Exception('二维码已过期')
            print(f'\r[INFO] 等待扫码... ({i*2}s)', end='', flush=True)
        raise Exception('扫码超时')

    # ── 探测上传线路 ──────────────────────────

    def probe(self):
        ret = self.__session.get('https://member.bilibili.com/preupload?r=probe', timeout=5).json()
        data, auto_os, min_cost = None, None, 0
        method = 'get' if ret['probe'].get('get') else 'post'
        if method == 'post':
            data = bytes(int(1024 * 0.1 * 1024))
        for line in ret['lines']:
            start = time.perf_counter()
            test = self.__session.request(method, f"https:{line['probe_url']}", data=data, timeout=30)
            cost = time.perf_counter() - start
            if test.status_code != 200:
                continue
            if not min_cost or min_cost > cost:
                auto_os = line
                min_cost = cost
        auto_os['cost'] = min_cost
        return auto_os

    # ── 文件上传 ──────────────────────────────

    def upload_file(self, filepath: str, lines='AUTO', tasks=3) -> dict:
        """上传单个视频文件，返回 {title, filename, desc}"""
        if not self._auto_os:
            line_map = {
                'bda':   'bda',  'bda2': 'bda2', 'ws': 'ws',
                'qn':    'qn',   'tx':   'tx',   'txa': 'txa',
            }
            cdn = line_map.get(lines)
            if cdn:
                self._auto_os = {
                    'os': 'upos',
                    'query': f'upcdn={cdn}&probe_version=20221109',
                    'probe_url': f'//upos-cs-upcdn{cdn}.bilivideo.com/OK',
                }
            else:
                print('[INFO] 自动探测最优线路...')
                self._auto_os = self.probe()
            print(f"[INFO] 上传线路: {self._auto_os['os']} | {self._auto_os['query']}")

        if self._auto_os['os'] != 'upos':
            raise NotImplementedError(f"暂不支持 {self._auto_os['os']} 线路")

        total_size = os.path.getsize(filepath)
        with open(filepath, 'rb') as f:
            query = {
                'r': 'upos',
                'profile': 'ugcupos/bup',
                'ssl': 0,
                'version': '2.8.12',
                'build': 2081200,
                'name': os.path.basename(f.name),
                'size': total_size,
            }
            resp = self.__session.get(
                f"https://member.bilibili.com/preupload?{self._auto_os['query']}",
                params=query, timeout=5
            )
            ret = resp.json()
            return asyncio.run(self._upos_upload(f, total_size, ret, tasks=tasks))

    async def _upos_upload(self, file, total_size, ret, tasks=3):
        filename  = file.name
        chunk_size = ret['chunk_size']
        auth       = ret['auth']
        endpoint   = ret['endpoint']
        biz_id     = ret['biz_id']
        upos_uri   = ret['upos_uri']
        url        = f"https:{endpoint}/{upos_uri.replace('upos://', '')}"
        headers    = {'X-Upos-Auth': auth}

        upload_id = self.__session.post(
            f'{url}?uploads&output=json', timeout=15, headers=headers
        ).json()['upload_id']

        parts  = []
        chunks = math.ceil(total_size / chunk_size)

        async def upload_chunk(session, data, params):
            async with session.put(url, params=params, data=data,
                                   headers=headers, raise_for_status=True):
                elapsed = time.perf_counter() - start
                parts.append({'partNumber': params['chunk'] + 1, 'eTag': 'etag'})
                sys.stdout.write(
                    f"\r[上传] {params['end']/1e6/elapsed:.2f} MB/s  "
                    f"{params['partNumber']}/{chunks} ({params['partNumber']/chunks:.0%})"
                )
                sys.stdout.flush()

        start = time.perf_counter()
        await self.__upload_worker(
            {'uploadId': upload_id, 'chunks': chunks, 'total': total_size},
            file, chunk_size, upload_chunk, tasks
        )
        cost = time.perf_counter() - start
        print()

        p = {
            'name': filename,
            'uploadId': upload_id,
            'biz_id': biz_id,
            'output': 'json',
            'profile': 'ugcupos/bup',
        }
        for attempt in range(6):
            try:
                r = self.__session.post(
                    url, params=p, json={'parts': parts}, headers=headers, timeout=15
                ).json()
                if r.get('OK') == 1:
                    print(f'[INFO] 上传完成: {total_size/1e6/cost:.2f} MB/s')
                    return {
                        'title': splitext(os.path.basename(filename))[0],
                        'filename': splitext(basename(upos_uri))[0],
                        'desc': '',
                    }
                raise IOError(r)
            except IOError:
                print(f'\n[WARN] 合并分片失败，重试 {attempt+1}/5...')
                time.sleep(15)
        raise Exception('上传失败：分片合并超过最大重试次数')

    @staticmethod
    async def __upload_worker(params, file, chunk_size, afunc, tasks=3):
        params['chunk'] = -1

        async def worker():
            while True:
                data = file.read(chunk_size)
                if not data:
                    return
                params['chunk'] += 1
                params['size']       = len(data)
                params['partNumber'] = params['chunk'] + 1
                params['start']      = params['chunk'] * chunk_size
                params['end']        = params['start'] + params['size']
                clone = params.copy()
                for i in range(10):
                    try:
                        await afunc(session, data, clone)
                        break
                    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                        print(f'\n[WARN] chunk{clone["chunk"]} 重试 {i+1}: {e}')

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[worker() for _ in range(tasks)])

    # ── 提交投稿 ──────────────────────────────

    def submit(self):
        if not self.video.title:
            self.video.title = self.video.videos[0]['title']
        self.__session.get('https://member.bilibili.com/x/geetest/pre/add', timeout=5)
        ret = self.__session.post(
            f'https://member.bilibili.com/x/vu/web/add?csrf={self.__bili_jct}',
            json=asdict(self.video), timeout=5
        ).json()
        if ret['code'] != 0:
            raise Exception(f'投稿失败: {ret}')
        return ret

    # ── context manager ───────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.__session.close()


# ──────────────────────────────────────────────
# 高级封装
# ──────────────────────────────────────────────

def upload_video(
    file_path: str,
    title: str,
    tid: int = 21,
    tags: Optional[List[str]] = None,
    desc: str = '',
    copyright: int = 1,
    source: str = '',
    cover_path: Optional[str] = None,
    lines: str = 'AUTO',
    threads: int = 3,
    cookie_file: str = 'cookies.json',
):
    """
    上传视频到 B 站

    :param file_path:   本地视频文件路径
    :param title:       视频标题（最多80字）
    :param tid:         分区ID，默认21（日常）
    :param tags:        标签列表
    :param desc:        视频简介
    :param copyright:   1=自制, 2=转载
    :param source:      转载来源（copyright=2 时填写）
    :param cover_path:  封面图片路径（可选）
    :param lines:       上传线路：AUTO/bda/bda2/ws/qn/tx/txa
    :param threads:     并发上传线程数
    :param cookie_file: Cookie 文件路径
    """
    video = Data()
    video.title     = title[:80]
    video.tid       = tid
    video.desc      = desc
    video.copyright = copyright
    video.source    = source
    if tags:
        video.set_tag(tags)

    with BiliBili(video) as bili:
        bili.login(cookie_file)

        print(f'[INFO] 开始上传: {file_path}')
        part = bili.upload_file(file_path, lines=lines, tasks=threads)
        part['title'] = part['title'][:80]
        video.append(part)

        if cover_path:
            print(f'[INFO] 上传封面: {cover_path}')
            video.cover = bili.cover_up(cover_path).replace('http:', '')

        print('[INFO] 提交投稿...')
        ret = bili.submit()
        bvid = ret.get('data', {}).get('bvid', '未知')
        print(f'[SUCCESS] 投稿成功！BV号: {bvid}')
        return ret


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description='B 站视频上传工具')
    sub = parser.add_subparsers(dest='cmd')

    # 登录子命令
    login_p = sub.add_parser('login', help='扫码登录并保存 Cookie')
    login_p.add_argument('--cookie', default='cookies.json', help='Cookie 保存路径')

    # 上传子命令
    up_p = sub.add_parser('upload', help='上传视频')
    up_p.add_argument('--file',    required=True, help='视频文件路径')
    up_p.add_argument('--title',   required=True, help='视频标题')
    up_p.add_argument('--tid',     type=int, default=21, help='分区ID（默认21=日常）')
    up_p.add_argument('--tags',    nargs='*', default=[], help='标签列表')
    up_p.add_argument('--desc',    default='',    help='视频简介')
    up_p.add_argument('--copyright', type=int, default=1, help='1=自制 2=转载')
    up_p.add_argument('--source',  default='',   help='转载来源')
    up_p.add_argument('--cover',   default=None, help='封面图片路径')
    up_p.add_argument('--lines',   default='AUTO', help='上传线路')
    up_p.add_argument('--threads', type=int, default=3, help='并发线程数')
    up_p.add_argument('--cookie',  default='cookies.json', help='Cookie 文件路径')

    args = parser.parse_args()

    if args.cmd == 'login':
        video = Data()
        with BiliBili(video) as bili:
            bili._qrcode_login(args.cookie)

    elif args.cmd == 'upload':
        if not os.path.isfile(args.file):
            print(f'[ERROR] 文件不存在: {args.file}')
            sys.exit(1)
        upload_video(
            file_path   = args.file,
            title       = args.title,
            tid         = args.tid,
            tags        = args.tags,
            desc        = args.desc,
            copyright   = args.copyright,
            source      = args.source,
            cover_path  = args.cover,
            lines       = args.lines,
            threads     = args.threads,
            cookie_file = args.cookie,
        )
    else:
        parser.print_help()


if __name__ == '__main__':
    main()