/* ============================================================
   api.js —— 请求封装
   所有后端交互都从这里走，页面里不出现 fetch。
   接口地址与参数见《功能需求文档.md》第二节。
   ============================================================ */

/* 后端地址。默认 127.0.0.1:8765（见 backend/config.py 的 PORT）。
   写 127.0.0.1 而不是 localhost：后者可能被解析成 IPv6 的 ::1，而后端只监听 IPv4。
   临时换端口不用改代码，在页面地址后加 ?api=http://127.0.0.1:9000/api 即可。 */
const API_OVERRIDE = new URLSearchParams(location.search).get('api');

const CONFIG = {
  BASE_URL: API_OVERRIDE || 'http://127.0.0.1:8765/api',

  /* 普通请求超时（毫秒）。读写数据库的接口都很快，15 秒足够。 */
  TIMEOUT: 15000,

  /* 走大模型的请求超时（毫秒）。
     聊天、出题、改卷、周报都要等模型生成，出 15 道题可能要几十秒，
     后端失败还会重试，所以给足时间 —— 否则会看到
     「signal is aborted without reason」这种看不懂的报错。 */
  LLM_TIMEOUT: 240000,

  /* 后台连接状态轮询间隔（毫秒） */
  HEALTH_INTERVAL: 8000,

  /* 健康检查超时，要短，避免状态点迟迟不亮 */
  HEALTH_TIMEOUT: 3000,

  /* 单文件大小上限（MB），与后端 backend/.env 的 MAX_UPLOAD_MB 保持一致。
     前端先拦一道：超限的文件直接提示，不用等浏览器传一半再被后端掐断
     （超大请求被后端拒绝时，浏览器往往只看到连接中断，看不到后端给的提示）。 */
  MAX_UPLOAD_MB: 200
};

/* ---------- 基础请求 ---------- */

async function request(path, options = {}) {
  const {
    method = 'GET',
    body,
    isForm = false,
    llm = false,
    timeout = llm ? CONFIG.LLM_TIMEOUT : CONFIG.TIMEOUT
  } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  const headers = {};
  let payload;

  if (isForm) {
    /* multipart/form-data 交给浏览器自己带 boundary，不要手写 Content-Type */
    payload = body;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(CONFIG.BASE_URL + path, {
      method,
      headers,
      body: payload,
      signal: controller.signal
    });
  } catch (err) {
    /* 超时被 abort 时，浏览器给的消息是 "signal is aborted without reason"，
       对用户毫无意义，换成能看懂的说法。 */
    if (err && err.name === 'AbortError') {
      throw new Error('请求超时（等待 ' + Math.round(timeout / 1000) + ' 秒）。' +
                      '模型响应较慢时会出现，请重试一次。');
    }
    throw new Error('连不上后端服务，请确认后端已启动（start_backend）。');
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();

  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (err) {
      /* 开发模式下 Flask 出错会返回一整个 HTML 报错页，不是 JSON。
         直接说清楚，比抛一句 SyntaxError 有用。 */
      if (/^\s*</.test(text)) {
        throw new Error('后端出错（HTTP ' + res.status + '）。' +
                        '后端窗口里有详细的报错信息。');
      }
      throw new Error('后端返回的不是 JSON（HTTP ' + res.status + '）：' + text.slice(0, 120));
    }
  }

  if (!res.ok) {
    const message = data && data.error ? data.error.message : '请求失败（HTTP ' + res.status + '）';
    throw new Error(message);
  }

  return data;
}

/* ---------- 对外方法 ---------- */

const api = {
  get(path, options) {
    return request(path, Object.assign({ method: 'GET' }, options));
  },

  post(path, body, options) {
    return request(path, Object.assign({ method: 'POST', body: body }, options));
  },

  put(path, body, options) {
    return request(path, Object.assign({ method: 'PUT', body: body }, options));
  },

  del(path, options) {
    return request(path, Object.assign({ method: 'DELETE' }, options));
  },

  /* 上传资料：A1 POST /api/materials。
     大文件上传会慢，但用 LLM_TIMEOUT 又太长，单独给 60 秒。 */
  upload(path, formData) {
    return request(path, { method: 'POST', body: formData, isForm: true, timeout: 60000 });
  },

  /* ---------- 健康检查（供状态点使用） ---------- */

  async checkHealth() {
    try {
      await request('/health', { method: 'GET', timeout: CONFIG.HEALTH_TIMEOUT });
      return true;
    } catch (err) {
      return false;
    }
  }
};
