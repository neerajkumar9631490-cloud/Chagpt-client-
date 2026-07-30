import json
import random
import time
import uuid
import hashlib
import base64
import re
from typing import AsyncGenerator, Dict, Optional
import httpx
from httpx_sse import aconnect_sse

# Global cache for speed
_CACHED_CONFIG = None
_CACHED_UA = None
_CACHED_DEVICE_ID = None

class ChatGPTClient:
    def __init__(self):
        global _CACHED_CONFIG, _CACHED_UA, _CACHED_DEVICE_ID

        self.base_url = "https://chatgpt.com"
        self.cookies = {}

        # Reuse device ID across instances
        if _CACHED_DEVICE_ID is None:
            _CACHED_DEVICE_ID = str(uuid.uuid4())
        self.device_id = _CACHED_DEVICE_ID

        self.conversation_id = None
        self.parent_message_id = str(uuid.uuid4())
        self.oai_version = None

        # Reuse UA and config
        if _CACHED_UA is None:
            _CACHED_UA = self._pick_user_agent()
        self.ua = _CACHED_UA

        if _CACHED_CONFIG is None:
            _CACHED_CONFIG = self._generate_config()
        self.config = _CACHED_CONFIG.copy()

    def _pick(self, arr):
        return arr[random.randint(0, len(arr) - 1)]

    def _pick_user_agent(self):
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        ]
        return self._pick(user_agents)

    def _generate_config(self):
        screen_sizes = [
            [1920, 1080], [2560, 1440], [1366, 768],
            [1536, 864], [1440, 900], [3840, 2160]
        ]
        cpu_cores = [8, 12, 16, 24, 32]
        timezones = [
            'Eastern Standard Time', 'Central Standard Time',
            'Mountain Standard Time', 'Pacific Standard Time'
        ]
        offsets = ['-0500', '-0600', '-0700', '-0800']

        screen = self._pick(screen_sizes)
        perf_counter = round(random.random() * 450 + 50 * 100) / 100
        cores = self._pick(cpu_cores)

        t = time.gmtime()
        tz = self._pick(timezones)
        offset = self._pick(offsets)
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        time_str = f"{days[t.tm_wday]} {months[t.tm_mon]} {str(t.tm_mday).zfill(2)} {t.tm_year} {str(t.tm_hour).zfill(2)}:{str(t.tm_min).zfill(2)}:{str(t.tm_sec).zfill(2)} GMT{offset} ({tz})"

        navigator_keys = [
            'vendor-Google Inc.', 'vendor-', 'vendorSub-',
            'productSub-20030107', 'productSub-20100101'
        ]
        document_keys = [
            '_reactListeningo743lnnpvdg', '_reactListeningzw72ump40ol',
            '_reactListeningtm3ymhhlwsk', '__reactEvents$abcdef123456'
        ]
        window_keys = [
            'fetch', 'localStorage', 'sessionStorage',
            'crypto', 'performance', 'navigator', 'location'
        ]

        config = [
            screen[0] + screen[1],
            time_str,
            4294705152,
            0,
            self.ua,
            '',
            '',
            'en-US',
            'en-US,en',
            0,
            self._pick(navigator_keys),
            self._pick(document_keys),
            self._pick(window_keys),
            perf_counter,
            str(uuid.uuid4()),
            '',
            cores,
            round(time.time() - perf_counter * 1000)
        ]
        return config

    def _get_headers(self, extra: Dict = None) -> Dict:
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'oai-device-id': self.device_id,
            'oai-language': 'en-US',
            'origin': 'https://chatgpt.com',
            'referer': 'https://chatgpt.com/',
            'sec-ch-ua': '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.ua,
        }
        if self.oai_version:
            headers['oai-client-version'] = self.oai_version
        if extra:
            headers.update(extra)
        return headers

    def _get_cookie_header(self) -> str:
        return '; '.join([f"{k}={v}" for k, v in self.cookies.items()])

    def _parse_cookies(self, set_cookie_headers):
        if not set_cookie_headers:
            return
        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]
        for header in set_cookie_headers:
            if ';' in header:
                pair = header.split(';')[0]
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    self.cookies[name.strip()] = value.strip()

    def _solve_proof_of_work(self, seed: str, difficulty: str) -> str:
        diff_len = len(difficulty) // 2
        seed_buf = seed.encode('utf-8')
        target = bytes.fromhex(difficulty)

        prefix = json.dumps(self.config[:3])[:-1] + ','
        mid = ',' + json.dumps(self.config[4:9])[1:-1] + ','
        suffix = ',' + json.dumps(self.config[10:])[1:]

        prefix_buf = prefix.encode('utf-8')
        mid_buf = mid.encode('utf-8')
        suffix_buf = suffix.encode('utf-8')

        # FASTER: Reduced from 500000 to 50000 (10x speedup)
        for i in range(50000):
            i_buf = str(i).encode('utf-8')
            j_buf = str(i >> 1).encode('utf-8')
            final = prefix_buf + i_buf + mid_buf + j_buf + suffix_buf
            encoded = base64.b64encode(final).decode('utf-8')

            hash_obj = hashlib.sha3_512()
            hash_obj.update(seed_buf)
            hash_obj.update(encoded.encode('utf-8'))
            hash_digest = hash_obj.digest()

            if hash_digest[:diff_len] <= target[:diff_len]:
                return 'gAAAAAB' + encoded

        fallback = 'wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D' + base64.b64encode(f'"{seed}"'.encode('utf-8')).decode('utf-8')
        return 'gAAAAAB' + fallback

    def _get_requirements_token(self) -> str:
        seed = str(random.random())
        difficulty = '0fffff'
        diff_len = len(difficulty) // 2
        seed_buf = seed.encode('utf-8')
        target = bytes.fromhex(difficulty)

        prefix = json.dumps(self.config[:3])[:-1] + ','
        mid = ',' + json.dumps(self.config[4:9])[1:-1] + ','
        suffix = ',' + json.dumps(self.config[10:])[1:]

        prefix_buf = prefix.encode('utf-8')
        mid_buf = mid.encode('utf-8')
        suffix_buf = suffix.encode('utf-8')

        # FASTER: Reduced from 500000 to 50000
        for i in range(50000):
            i_buf = str(i).encode('utf-8')
            j_buf = str(i >> 1).encode('utf-8')
            final = prefix_buf + i_buf + mid_buf + j_buf + suffix_buf
            encoded = base64.b64encode(final).decode('utf-8')

            hash_obj = hashlib.sha3_512()
            hash_obj.update(seed_buf)
            hash_obj.update(encoded.encode('utf-8'))
            hash_digest = hash_obj.digest()

            if hash_digest[:diff_len] <= target[:diff_len]:
                return 'gAAAAAC' + encoded

        return 'gAAAAAC' + base64.b64encode(f'"{seed}"'.encode('utf-8')).decode('utf-8')

    def _solve_turnstile(self, dx: str, p: str) -> str:
        if not dx or not p:
            return ''
        try:
            dx_bytes = base64.b64decode(dx)
            key_bytes = p.encode('utf-8')
            result = bytearray()
            for i in range(len(dx_bytes)):
                result.append(dx_bytes[i] ^ key_bytes[i % len(key_bytes)])
            decrypted = result.decode('utf-8')
            instructions = json.loads(decrypted)
            return self._execute_turnstile_vm(instructions)
        except:
            return ''

    def _execute_turnstile_vm(self, instructions) -> str:
        variables = {}
        result = ''

        for inst in instructions:
            if not inst or len(inst) == 0:
                continue
            op = inst[0]
            args = inst[1:]

            if op == 1:
                if len(args) >= 2:
                    a = str(variables.get(args[0], args[0]))
                    b = str(variables.get(args[1], args[1]))
                    res = ''
                    for i in range(len(a)):
                        res += chr(ord(a[i]) ^ ord(b[i % len(b)]))
                    variables[args[0]] = res
            elif op == 2:
                if len(args) >= 2:
                    variables[args[0]] = args[1]
            elif op == 3:
                if len(args) >= 1:
                    val = variables.get(args[0], args[0])
                    result = base64.b64encode(str(val).encode('utf-8')).decode('utf-8')
            elif op == 5:
                if len(args) >= 2:
                    a = variables.get(args[0], '')
                    b = variables.get(args[1], args[1])
                    variables[args[0]] = str(a) + str(b)
            elif op == 6:
                if len(args) >= 3:
                    obj = variables.get(args[1], {})
                    key = args[2]
                    if isinstance(obj, dict):
                        variables[args[0]] = obj.get(key, '')
            elif op == 7:
                pass
            elif op == 14:
                if len(args) >= 2:
                    val = variables.get(args[1], args[1])
                    if isinstance(val, str):
                        try:
                            variables[args[0]] = json.loads(val)
                        except:
                            pass
            elif op == 15:
                if len(args) >= 2:
                    val = variables.get(args[1], args[1])
                    variables[args[0]] = json.dumps(val)
        return result

    async def init(self):
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.base_url,
                headers={
                    'user-agent': self.ua,
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
            )
            text = response.text
            match = re.search(r'data-build="([^"]+)"', text)
            if match:
                self.oai_version = match.group(1)

            set_cookie = response.headers.get('set-cookie')
            if set_cookie:
                self._parse_cookies(set_cookie)

            if 'oai-did' in self.cookies:
                self.device_id = self.cookies['oai-did']

    async def _get_requirements(self) -> Dict:
        headers = self._get_headers()
        cookie = self._get_cookie_header()
        if cookie:
            headers['cookie'] = cookie

        p_token = self._get_requirements_token()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/backend-anon/sentinel/chat-requirements",
                headers=headers,
                json={'p': p_token}
            )
            set_cookie = response.headers.get('set-cookie')
            if set_cookie:
                self._parse_cookies(set_cookie)
            return response.json()

    def _solve_challenges(self, requirements: Dict) -> Dict:
        tokens = {'chat_token': '', 'proof_token': '', 'turnstile_token': ''}
        tokens['chat_token'] = requirements.get('token', '')

        pow_data = requirements.get('proofofwork', {})
        if pow_data.get('required', False):
            seed = pow_data.get('seed')
            difficulty = pow_data.get('difficulty')
            if seed and difficulty:
                tokens['proof_token'] = self._solve_proof_of_work(seed, difficulty)

        turnstile = requirements.get('turnstile', {})
        if turnstile.get('required', False):
            dx = turnstile.get('dx', '')
            p = turnstile.get('p', '')
            if dx and p:
                tokens['turnstile_token'] = self._solve_turnstile(dx, p)

        return tokens

    async def chat(self, message: str) -> AsyncGenerator[str, None]:
        requirements = await self._get_requirements()
        tokens = self._solve_challenges(requirements)

        headers = self._get_headers({
            'accept': 'text/event-stream',
            'openai-sentinel-chat-requirements-token': tokens['chat_token'],
        })
        if tokens['proof_token']:
            headers['openai-sentinel-proof-token'] = tokens['proof_token']
        if tokens['turnstile_token']:
            headers['openai-sentinel-turnstile-token'] = tokens['turnstile_token']

        cookie = self._get_cookie_header()
        if cookie:
            headers['cookie'] = cookie

        msg_id = str(uuid.uuid4())
        body = {
            'action': 'next',
            'messages': [{
                'id': msg_id,
                'author': {'role': 'user'},
                'content': {'content_type': 'text', 'parts': [message]},
                'metadata': {}
            }],
            'parent_message_id': self.parent_message_id,
            'model': 'auto',
            'timezone_offset_min': -300,
            'history_and_training_disabled': True,
            'conversation_mode': {'kind': 'primary_assistant'},
            'force_paragen': False,
            'force_paragen_model_slug': '',
            'force_nulligen': False,
            'force_rate_limit': False,
            'reset_rate_limits': False,
            'websocket_request_id': str(uuid.uuid4()),
        }
        if self.conversation_id:
            body['conversation_id'] = self.conversation_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with aconnect_sse(
                client, 'POST', f"{self.base_url}/backend-anon/conversation",
                headers=headers, json=body
            ) as event_source:
                last_len = 0
                async for event in event_source.aiter_sse():
                    data_str = event.data
                    if data_str == '[DONE]':
                        break

                    try:
                        data = json.loads(data_str)
                    except:
                        continue

                    if 'conversation_id' in data:
                        self.conversation_id = data['conversation_id']

                    message_data = data.get('message')
                    if message_data:
                        author = message_data.get('author')
                        if author and author.get('role') == 'assistant':
                            content = message_data.get('content', {})
                            parts = content.get('parts', [])
                            if parts and content.get('content_type') == 'text':
                                text = parts[0]
                                if len(text) > last_len:
                                    yield text[last_len:]
                                    last_len = len(text)
                            if 'id' in message_data:
                                self.parent_message_id = message_data['id']

    def reset(self):
        self.conversation_id = None
        self.parent_message_id = str(uuid.uuid4())
