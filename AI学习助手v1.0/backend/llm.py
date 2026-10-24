"""大模型客户端。

地址、密钥、模型名三者互相独立，全部从配置读（见 config.py / .env.example），
所以换成任意 OpenAI 兼容的服务只改 .env，不动代码。

包含三件事：
1. 调用 /chat/completions（OpenAI 兼容）
2. 失败自动重试（网络问题、5xx、429 才重试；4xx 参数错误重试没意义）
3. 把模型返回的 JSON 剥出来 —— 它经常在 JSON 外面包一层 ```json```
"""

import json
import logging
import re
import time
import warnings

# requests 启动时会找编码探测库（charset_normalizer / chardet），找不到就打一条
# RequestsDependencyWarning。那两个库带编译扩展，在本项目的长路径下加载不了
# （实测 271 字符，超过 Windows 260 上限），所以没装。我们只用它读 JSON，
# 不需要编码探测，这条警告纯属噪音，在 import requests 之前先静默掉。
warnings.filterwarnings('ignore', message='.*character detection dependency.*')

import requests  # noqa: E402
from flask import current_app

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """调用大模型失败。调用方捕获后转成 502 返回给前端。

    retryable 为 True 时，chat() / chat_json() 会自动重试。
    """

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def _settings():
    cfg = current_app.config
    return {
        'base_url': (cfg.get('LLM_BASE_URL') or '').rstrip('/'),
        'api_key': cfg.get('LLM_API_KEY') or '',
        'model': cfg.get('LLM_MODEL'),
        'temperature': cfg.get('LLM_TEMPERATURE', 0.3),
        'timeout': cfg.get('LLM_TIMEOUT', 120),
        'max_retries': cfg.get('LLM_MAX_RETRIES', 3),
        'retry_delay': cfg.get('LLM_RETRY_DELAY', 1.5),
    }


def _chat_once(messages, temperature, timeout):
    """单次调用，不做重试。"""
    conf = _settings()

    if not conf['api_key']:
        raise LLMError('未配置 LLM_API_KEY，请在 backend/.env 中填写后重启服务')
    if not conf['base_url']:
        raise LLMError('未配置 LLM_BASE_URL')

    payload = {
        'model': conf['model'],
        'messages': messages,
        'temperature': conf['temperature'] if temperature is None else temperature,
    }

    try:
        response = requests.post(
            conf['base_url'] + '/chat/completions',
            headers={
                'Authorization': 'Bearer ' + conf['api_key'],
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=timeout or conf['timeout'],
        )
    except requests.RequestException as exc:
        # 连不上、超时、DNS 失败 —— 典型的「网不好」，值得重试
        raise LLMError('无法连接大模型服务：%s' % exc, retryable=True) from exc

    if response.status_code != 200:
        # 429 限流和 5xx 服务端问题可以重试；4xx 是请求本身有问题，重试没用
        retryable = response.status_code == 429 or response.status_code >= 500
        raise LLMError(
            '大模型返回 HTTP %s：%s' % (response.status_code, response.text[:300]),
            retryable=retryable,
        )

    try:
        data = response.json()
        content = data['choices'][0]['message']['content']
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError('无法解析大模型响应：%s' % response.text[:300], retryable=True) from exc

    if not content or not content.strip():
        raise LLMError('大模型返回了空内容', retryable=True)

    return content


def _with_retry(attempt_fn):
    """统一的「失败自动重试」外壳。"""
    conf = _settings()
    total = 1 + max(0, conf['max_retries'])
    last_error = None

    for attempt in range(1, total + 1):
        try:
            return attempt_fn()
        except LLMError as exc:
            last_error = exc
            if not exc.retryable or attempt >= total:
                raise
            wait = conf['retry_delay'] * attempt
            logger.warning('大模型调用失败（第 %d/%d 次），%.1fs 后重试：%s',
                           attempt, total, wait, exc)
            time.sleep(wait)

    raise last_error


def chat(messages, temperature=None, timeout=None):
    """调用模型，返回纯文本（用于聊天与周报这类 Markdown 输出）。"""
    return _with_retry(lambda: _chat_once(messages, temperature, timeout))


def extract_json(text):
    """把模型返回内容里的 JSON 剥出来。

    模型常见的三种毛病，逐个处理：
    1. 整个包在 ```json ... ``` 里
    2. 围栏外还有解释文字
    3. 什么都没有，直接是 JSON
    """
    if not text or not text.strip():
        raise LLMError('模型返回了空内容')

    raw = text.strip()

    fenced = re.search(r'```(?:json|JSON)?\s*(.+?)\s*```', raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    else:
        # 没有围栏但前后有废话：截第一个 { 或 [ 到最后一个 } 或 ]
        starts = [i for i in (raw.find('{'), raw.find('[')) if i != -1]
        if starts:
            start = min(starts)
            end = max(raw.rfind('}'), raw.rfind(']'))
            if end > start:
                raw = raw[start:end + 1]

    try:
        return json.loads(raw)
    except ValueError as exc:
        raise LLMError('模型返回的不是合法 JSON：%s' % raw[:200], retryable=True) from exc


def chat_json(messages, temperature=None, timeout=None):
    """调用模型并把结果解析成 JSON。

    JSON 解析失败也算一次失败，一起计入重试预算 ——
    模型偶尔会多写一句解释或漏个括号，再问一次通常就好了。
    """
    def attempt():
        return extract_json(_chat_once(messages, temperature, timeout))

    return _with_retry(attempt)
