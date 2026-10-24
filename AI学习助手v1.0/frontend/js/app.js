/* ============================================================
   app.js —— 路由与页面装配
   路由用 # 锚点：#/learn  #/library  #/quiz  #/progress  #/report
   每个 Tab 对应功能需求文档里的一个功能，不多不少。
   ============================================================ */

/* ---------- 通用工具 ---------- */

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = function (n) { return String(n).padStart(2, '0'); };
  return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function formatSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1024 / 1024).toFixed(1) + ' MB';
}

/* ---------- 浮动提示 ---------- */

function showToast(message, type) {
  const host = document.getElementById('toastHost');
  if (!host) return;

  const el = document.createElement('div');
  el.className = 'toast toast--' + (type === 'err' ? 'err' : 'ok');
  el.textContent = message;
  host.appendChild(el);

  setTimeout(function () {
    el.classList.add('is-leaving');
    setTimeout(function () { el.remove(); }, 250);
  }, 3200);
}

/* ============================================================
   学习页（聊资料）
   ============================================================ */

const learnState = {
  sessions: [],
  currentSessionId: null,
  messages: [],
  materialId: null,
  sending: false
};

let learnEls = null;

function pageLearn() {
  return `
    <section class="learn">
      <aside class="learn__sidebar">
        <div class="learn__sidebar-head">
          <span class="learn__sidebar-title">历史对话</span>
        </div>
        <div class="session-list" id="sessionList"></div>
      </aside>

      <div class="learn__main">
        <div class="learn__toolbar">
          <select class="select" id="materialSelect" title="选择要对话的资料"></select>
          <button class="btn btn--ghost" type="button" id="newChatBtn">新对话</button>
        </div>

        <div class="chat__messages" id="chatMessages"></div>

        <div class="chat__error" id="chatError" hidden></div>

        <form class="chat__composer" id="chatComposer">
          <textarea class="textarea" id="chatInput" rows="2"
                    placeholder="输入问题，回车发送，Shift + 回车换行"></textarea>
          <button class="btn btn--primary" type="submit" id="sendBtn">发送</button>
        </form>
      </div>
    </section>
  `;
}

function mountLearn() {
  learnEls = {
    select:   document.getElementById('materialSelect'),
    newBtn:   document.getElementById('newChatBtn'),
    list:     document.getElementById('sessionList'),
    messages: document.getElementById('chatMessages'),
    error:    document.getElementById('chatError'),
    form:     document.getElementById('chatComposer'),
    input:    document.getElementById('chatInput'),
    send:     document.getElementById('sendBtn')
  };

  learnState.sessions = [];
  learnState.currentSessionId = null;
  learnState.messages = [];
  learnState.materialId = null;
  learnState.sending = false;

  renderEmptyState();
  renderSessionList();

  learnEls.newBtn.addEventListener('click', onNewChat);
  learnEls.form.addEventListener('submit', onSubmit);
  learnEls.input.addEventListener('keydown', onInputKeydown);
  learnEls.select.addEventListener('change', onScopeChange);
  learnEls.list.addEventListener('click', onSessionClick);
  learnEls.messages.addEventListener('click', onRefsToggle);

  loadMaterialOptions();
  loadSessions();
}

/* ---------- 资料下拉框 ---------- */

async function loadMaterialOptions() {
  const select = learnEls.select;
  select.innerHTML = '';
  select.appendChild(new Option('普通对话（不引用资料）', ''));

  try {
    const data = await api.get('/materials');
    const ready = (data.items || []).filter(function (m) { return m.status === 'ready'; });
    ready.forEach(function (m) {
      select.appendChild(new Option(m.name, String(m.id)));
    });
  } catch (err) {
    const opt = new Option('（资料加载失败）', '');
    opt.disabled = true;
    select.appendChild(opt);
  }

  select.value = '';
  learnState.materialId = null;
}

function onScopeChange() {
  const value = learnEls.select.value;
  learnState.materialId = value ? Number(value) : null;
}

/* 把历史会话的资料范围回填到下拉框 */
function applySessionScope(session) {
  const ids = (session && session.material_ids) || [];
  const target = ids.length ? String(ids[0]) : '';
  const select = learnEls.select;
  const exists = Array.prototype.some.call(select.options, function (o) {
    return o.value === target && !o.disabled;
  });

  select.value = exists ? target : '';
  learnState.materialId = select.value ? Number(select.value) : null;
}

/* ---------- 历史对话 ---------- */

async function loadSessions() {
  try {
    const data = await api.get('/chat/sessions');
    learnState.sessions = data.items || [];
  } catch (err) {
    learnState.sessions = [];
  }
  renderSessionList();
}

function renderSessionList() {
  const list = learnEls.list;
  const items = learnState.sessions;

  if (!items.length) {
    list.innerHTML = '<div class="empty empty--sidebar">还没有历史对话</div>';
    return;
  }

  list.innerHTML = items.map(function (s) {
    const active = s.id === learnState.currentSessionId ? ' is-active' : '';
    return '<button class="session-item' + active + '" type="button" data-id="' + s.id + '">'
         +   '<span class="session-item__title">' + escapeHtml(s.title || '未命名对话') + '</span>'
         +   '<span class="session-item__meta">' + formatTime(s.created_at) + '</span>'
         + '</button>';
  }).join('');
}

async function onSessionClick(e) {
  const btn = e.target.closest('.session-item');
  if (!btn) return;

  const id = Number(btn.dataset.id);
  if (id === learnState.currentSessionId) return;

  learnState.currentSessionId = id;
  learnState.messages = [];
  hideError();
  renderSessionList();
  learnEls.messages.innerHTML = '<div class="empty">正在载入对话…</div>';

  try {
    const data = await api.get('/chat/sessions/' + id);
    learnState.messages = data.messages || [];
    const session = learnState.sessions.filter(function (s) { return s.id === id; })[0];
    applySessionScope(session);
  } catch (err) {
    learnState.messages = [];
    showError('历史对话加载失败：' + err.message);
  }

  renderMessages();
}

/* ---------- 消息渲染 ---------- */

function renderMessages() {
  if (!learnState.messages.length) {
    renderEmptyState();
    return;
  }
  learnEls.messages.innerHTML = learnState.messages.map(renderMessage).join('');
  scrollToBottom();
}

function renderMessage(m) {
  if (m.role === 'user') {
    return '<div class="msg msg--user">'
         +   '<div class="msg__body">'
         +     '<div class="msg__content">' + escapeHtml(m.content).replace(/\n/g, '<br>') + '</div>'
         +   '</div>'
         + '</div>';
  }

  return '<div class="msg msg--assistant">'
       +   '<div class="msg__body">'
       +     '<div class="msg__content">' + renderMarkdown(m.content) + '</div>'
       +     renderRefs(m.references || [])
       +   '</div>'
       + '</div>';
}

function renderRefs(refs) {
  if (!refs.length) return '';

  const items = refs.map(function (r) {
    const seq = (Number(r.chunk_index) || 0) + 1;
    return '<div class="refs__item">'
         +   '<div class="refs__source">' + escapeHtml(r.material_name || '') + ' · 第 ' + seq + ' 段</div>'
         +   '<div class="refs__snippet">' + escapeHtml(r.snippet || '') + '</div>'
         + '</div>';
  }).join('');

  return '<button class="refs-toggle" type="button" data-refs>'
       +   '<span class="refs-toggle__arrow"></span>引用了 ' + refs.length + ' 段资料'
       + '</button>'
       + '<div class="refs" hidden>' + items + '</div>';
}

function onRefsToggle(e) {
  const btn = e.target.closest('[data-refs]');
  if (!btn) return;

  const panel = btn.nextElementSibling;
  const willOpen = panel.hasAttribute('hidden');

  if (willOpen) {
    panel.removeAttribute('hidden');
  } else {
    panel.setAttribute('hidden', '');
  }
  btn.classList.toggle('is-open', willOpen);
}

/* ---------- 空状态 / 思考中 / 错误 ---------- */

function renderEmptyState() {
  learnEls.messages.innerHTML = `
    <div class="chat__empty">
      <svg class="chat__empty-icon" viewBox="0 0 48 48" fill="none" stroke="currentColor"
           stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M8 11a3 3 0 0 1 3-3h26a3 3 0 0 1 3 3v16a3 3 0 0 1-3 3H21l-9 8v-8h-1a3 3 0 0 1-3-3z"/>
        <path d="M16 17h16"/>
        <path d="M16 23h10"/>
      </svg>
      <div class="chat__empty-title">选一份资料，开始提问</div>
      <div class="chat__empty-hint">从上方下拉框选择资料，回答将严格基于资料内容；不选则是普通对话。</div>
    </div>
  `;
}

function showThinking() {
  const el = document.createElement('div');
  el.className = 'msg msg--assistant';
  el.id = 'thinkingMsg';
  el.innerHTML = '<div class="msg__body">'
               +   '<div class="msg__content thinking">'
               +     '<span>正在思考</span>'
               +     '<span class="thinking__dots"><i></i><i></i><i></i></span>'
               +   '</div>'
               + '</div>';
  learnEls.messages.appendChild(el);
  scrollToBottom();
}

function removeThinking() {
  const el = document.getElementById('thinkingMsg');
  if (el) el.remove();
}

function showError(message) {
  learnEls.error.textContent = message;
  learnEls.error.hidden = false;
}

function hideError() {
  learnEls.error.hidden = true;
}

function scrollToBottom() {
  const box = learnEls.messages;
  box.scrollTop = box.scrollHeight;
}

/* ---------- 发送 ---------- */

function setSending(flag) {
  learnState.sending = flag;
  learnEls.input.disabled = flag;
  learnEls.send.disabled = flag;
}

function onInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    learnEls.form.requestSubmit();
  }
}

async function onSubmit(e) {
  e.preventDefault();
  if (learnState.sending) return;

  const input = learnEls.input;
  const question = input.value.trim();
  if (!question) return;

  hideError();
  input.value = '';
  setSending(true);

  learnState.messages.push({ role: 'user', content: question });
  renderMessages();
  showThinking();

  const payload = { question: question };
  if (learnState.currentSessionId) payload.session_id = learnState.currentSessionId;
  if (learnState.materialId) payload.material_ids = [learnState.materialId];

  try {
    // 要走大模型，用长超时（见 api.js 的 LLM_TIMEOUT）
    const data = await api.post('/chat', payload, { llm: true });

    learnState.currentSessionId = data.session_id;
    learnState.messages.push({
      role: 'assistant',
      content: data.answer,
      references: data.references || [],
      created_at: data.created_at
    });

    removeThinking();
    renderMessages();
    loadSessions();
  } catch (err) {
    removeThinking();
    learnState.messages.pop();          /* 撤回未送达的提问，让用户可以重发 */
    renderMessages();
    showError('发送失败：' + err.message);
    input.value = question;
  } finally {
    setSending(false);
    input.focus();
  }
}

function onNewChat() {
  if (learnState.sending) return;

  learnState.currentSessionId = null;
  learnState.messages = [];
  hideError();
  renderMessages();
  renderSessionList();
  learnEls.input.focus();
}

/* ============================================================
   资料库页（传资料）
   ============================================================ */

const MATERIAL_ACCEPT = ['pdf', 'ppt', 'pptx', 'doc', 'docx', 'md', 'markdown', 'txt'];

const MATERIAL_TYPE_TEXT = {
  pdf: 'PDF',
  ppt: 'PPT',
  pptx: 'PPT',
  doc: 'Word',
  docx: 'Word',
  md: 'Markdown',
  markdown: 'Markdown',
  txt: 'TXT'
};

const MATERIAL_STATUS = {
  pending:    { text: '解析中', cls: 'is-pending' },
  processing: { text: '解析中', cls: 'is-pending' },
  ready:      { text: '完成',   cls: 'is-ready' },
  failed:     { text: '失败',   cls: 'is-failed' }
};

const libraryState = {
  items: [],
  pollTimer: null
};

let libraryEls = null;

function pageLibrary() {
  return `
    <section class="page">
      <header class="page__header">
        <h1 class="page__title">资料库</h1>
        <p class="page__desc">上传 PDF、PPT、Word、Markdown、TXT 资料，供学习与测评使用。</p>
      </header>

      <div class="dropzone" id="dropzone">
        <div class="dropzone__title">拖拽文件到此处，或点击选择</div>
        <div class="dropzone__hint">支持 PDF、PPT、Word、Markdown、TXT · 单个文件最大 ${CONFIG.MAX_UPLOAD_MB} MB</div>
        <input id="fileInput" type="file" multiple hidden
               accept=".pdf,.ppt,.pptx,.doc,.docx,.md,.markdown,.txt">
      </div>

      <div class="panel panel--flush">
        <div class="panel__head">
          <span class="panel__title">已上传资料</span>
          <span class="panel__hint" id="materialCount">0 份</span>
        </div>
        <div id="materialList"></div>
      </div>
    </section>
  `;
}

function mountLibrary() {
  libraryEls = {
    dropzone: document.getElementById('dropzone'),
    input:    document.getElementById('fileInput'),
    list:     document.getElementById('materialList'),
    count:    document.getElementById('materialCount')
  };

  libraryState.items = [];

  renderMaterialList();
  refreshLibraryMaterials();

  libraryEls.dropzone.addEventListener('click', function () { libraryEls.input.click(); });
  libraryEls.input.addEventListener('change', function () {
    uploadFiles(libraryEls.input.files);
    libraryEls.input.value = '';   /* 允许重复选择同一个文件 */
  });

  libraryEls.dropzone.addEventListener('dragover', function (e) {
    e.preventDefault();
    libraryEls.dropzone.classList.add('is-dragover');
  });

  libraryEls.dropzone.addEventListener('dragleave', function (e) {
    if (!libraryEls.dropzone.contains(e.relatedTarget)) {
      libraryEls.dropzone.classList.remove('is-dragover');
    }
  });

  libraryEls.dropzone.addEventListener('drop', function (e) {
    e.preventDefault();
    libraryEls.dropzone.classList.remove('is-dragover');
    uploadFiles(e.dataTransfer.files);
  });

  libraryEls.list.addEventListener('click', onMaterialAction);
}

function unmountLibrary() {
  stopPolling();
}

/* ---------- 上传 ---------- */

async function uploadFiles(fileList) {
  const files = Array.prototype.slice.call(fileList || []);
  if (!files.length) return;

  const accepted = [];
  const rejected = [];
  const oversized = [];
  const maxBytes = CONFIG.MAX_UPLOAD_MB * 1024 * 1024;

  files.forEach(function (f) {
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    if (MATERIAL_ACCEPT.indexOf(ext) < 0) {
      rejected.push(f);
    } else if (f.size > maxBytes) {
      oversized.push(f);
    } else {
      accepted.push(f);
    }
  });

  rejected.forEach(function (f) {
    showToast('「' + f.name + '」格式不支持，已跳过', 'err');
  });

  oversized.forEach(function (f) {
    showToast('「' + f.name + '」有 ' + formatSize(f.size) +
              '，超过 ' + CONFIG.MAX_UPLOAD_MB + ' MB 上限，已跳过', 'err');
  });

  for (let i = 0; i < accepted.length; i++) {
    const file = accepted[i];
    const form = new FormData();
    form.append('file', file);

    try {
      await api.upload('/materials', form);
      showToast('「' + file.name + '」上传成功，正在解析', 'ok');
    } catch (err) {
      showToast('「' + file.name + '」上传失败：' + err.message, 'err');
    }
  }

  if (accepted.length) refreshLibraryMaterials();
}

/* ---------- 列表 ---------- */

async function loadLibraryMaterials() {
  try {
    const data = await api.get('/materials');
    libraryState.items = data.items || [];
    renderMaterialList();
  } catch (err) {
    libraryState.items = [];
    renderMaterialList('资料列表加载失败：' + err.message);
  }
}

async function refreshLibraryMaterials() {
  await loadLibraryMaterials();
  syncPolling();
}

function renderMaterialList(errorMessage) {
  const box = libraryEls.list;
  const items = libraryState.items;

  libraryEls.count.textContent = items.length + ' 份';

  if (errorMessage) {
    box.innerHTML = '<div class="empty">' + escapeHtml(errorMessage) + '</div>';
    return;
  }

  if (!items.length) {
    box.innerHTML = '<div class="empty">还没有资料。上传第一份开始学习。</div>';
    return;
  }

  box.innerHTML = items.map(renderMaterialRow).join('');
}

function renderMaterialRow(m) {
  const status = MATERIAL_STATUS[m.status] || { text: m.status || '未知', cls: 'is-pending' };
  const type = MATERIAL_TYPE_TEXT[m.file_type] || String(m.file_type || '').toUpperCase();
  const name = escapeHtml(m.name);

  return '<div class="material" data-id="' + m.id + '">'
       +   '<div class="material__name" title="' + name + '">' + name + '</div>'
       +   '<div class="material__type">' + escapeHtml(type) + '</div>'
       +   '<div class="material__size">' + formatSize(m.file_size) + '</div>'
       +   '<div class="material__status ' + status.cls + '">' + status.text + '</div>'
       +   '<div class="material__actions">'
       +     (m.status === 'failed'
                ? '<button class="btn btn--ghost btn--sm" type="button" data-action="retry">重试</button>'
                : '')
       +     '<button class="btn btn--ghost btn--sm" type="button" data-action="delete">删除</button>'
       +   '</div>'
       + '</div>';
}

async function onMaterialAction(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;

  const row = btn.closest('.material');
  const id = Number(row.dataset.id);
  const item = libraryState.items.filter(function (m) { return m.id === id; })[0];
  if (!item) return;

  const action = btn.dataset.action;

  if (action === 'delete') {
    if (!window.confirm('确定删除「' + item.name + '」？该资料及其解析内容会一并删除。')) return;

    btn.disabled = true;
    try {
      await api.del('/materials/' + id);
      showToast('已删除「' + item.name + '」', 'ok');
      refreshLibraryMaterials();
    } catch (err) {
      btn.disabled = false;
      showToast('删除失败：' + err.message, 'err');
    }
    return;
  }

  if (action === 'retry') {
    btn.disabled = true;
    try {
      await api.post('/materials/' + id + '/retry');
      showToast('已重新提交「' + item.name + '」', 'ok');
      refreshLibraryMaterials();
    } catch (err) {
      btn.disabled = false;
      showToast('重试失败：' + err.message, 'err');
    }
  }
}

/* ---------- 解析中的轮询 ---------- */

function hasPending() {
  return libraryState.items.some(function (m) {
    return m.status === 'pending' || m.status === 'processing';
  });
}

function stopPolling() {
  if (libraryState.pollTimer) {
    clearInterval(libraryState.pollTimer);
    libraryState.pollTimer = null;
  }
}

function syncPolling() {
  if (hasPending()) {
    if (!libraryState.pollTimer) {
      libraryState.pollTimer = setInterval(refreshLibraryMaterials, 2000);
    }
  } else {
    stopPolling();
  }
}

/* ============================================================
   测评页（做测评）
   三个阶段：setup 开始前 → answering 答题中 → result 看结果
   ============================================================ */

const QUIZ_COUNTS = [5, 8, 10, 15];

const QUESTION_TYPE_TEXT = {
  choice: '选择题',
  judge:  '判断题',
  short:  '简答题'
};

const DIFFICULTY_TEXT = {
  easy:   '简单',
  medium: '中等',
  hard:   '困难'
};

const SCORE_RING_R = 52;
const SCORE_RING_C = 2 * Math.PI * SCORE_RING_R;

const quizState = {
  phase: 'setup',
  materials: [],
  materialId: '',
  questionCount: 5,
  generating: false,
  submitting: false,
  quiz: null,
  answers: {},
  result: null,
  history: [],
  startedAt: 0,
  elapsed: 0,
  timerId: null
};

let quizEls = null;

function pageQuiz() {
  return '<section class="page" id="quizRoot"></section>';
}

function mountQuiz() {
  quizEls = { root: document.getElementById('quizRoot') };

  quizState.phase = 'setup';
  quizState.materialId = '';
  quizState.questionCount = 5;
  quizState.generating = false;
  quizState.submitting = false;
  quizState.quiz = null;
  quizState.answers = {};
  quizState.result = null;
  quizState.elapsed = 0;
  stopQuizTimer();

  /* 监听挂在 root 上，各阶段只换 innerHTML，避免重复绑定 */
  quizEls.root.addEventListener('click', onQuizClick);
  quizEls.root.addEventListener('change', onQuizChange);
  quizEls.root.addEventListener('input', onQuizInput);

  renderQuiz();
  loadQuizMaterials();
  /* 进来就要把历史记录拉出来，否则要等做完一次测评才显示 */
  loadQuizHistory();
}

function unmountQuiz() {
  stopQuizTimer();
}

/* ---------- 阶段切换 ---------- */

function renderQuiz() {
  if (quizState.phase === 'setup') {
    renderQuizSetup();
  } else if (quizState.phase === 'answering') {
    renderQuizAnswering();
  } else {
    renderQuizResult();
  }
}

/* ---------- 第一步：开始前 ---------- */

function renderQuizSetup() {
  const counts = QUIZ_COUNTS.map(function (n) {
    const active = n === quizState.questionCount ? ' is-active' : '';
    return '<button class="segmented__item' + active + '" type="button" data-count="' + n + '">' + n + ' 道</button>';
  }).join('');

  quizEls.root.innerHTML = `
    <header class="page__header">
      <h1 class="page__title">测评</h1>
      <p class="page__desc">基于资料自动出题，做完告诉你哪些知识点没掌握。</p>
    </header>

    <div class="panel quiz-setup">
      <div class="field">
        <label class="field__label" for="quizMaterial">测试资料</label>
        <select class="select" id="quizMaterial">
          <option value="">全部资料</option>
        </select>
      </div>

      <div class="field">
        <span class="field__label">题目数量</span>
        <div class="segmented" id="quizCount">${counts}</div>
      </div>

      <button class="btn btn--primary quiz-setup__start" type="button" id="startQuizBtn">开始测试</button>

      <div class="working" id="quizWorking" hidden>
        <span>正在生成测试题</span>
        <span class="thinking__dots"><i></i><i></i><i></i></span>
      </div>
    </div>

    ${renderHistoryPanel()}
  `;
}

async function loadQuizMaterials() {
  const select = document.getElementById('quizMaterial');
  if (!select) return;

  select.innerHTML = '';
  select.appendChild(new Option('全部资料', ''));

  try {
    const data = await api.get('/materials');
    quizState.materials = (data.items || []).filter(function (m) { return m.status === 'ready'; });
    quizState.materials.forEach(function (m) {
      select.appendChild(new Option(m.name, String(m.id)));
    });
  } catch (err) {
    quizState.materials = [];
    const opt = new Option('（资料加载失败）', '');
    opt.disabled = true;
    select.appendChild(opt);
  }

  select.value = quizState.materialId;
}

async function onStartQuiz() {
  if (quizState.generating) return;

  setQuizGenerating(true);

  const payload = {
    question_count: quizState.questionCount,
    material_ids: quizState.materialId
      ? [Number(quizState.materialId)]
      : quizState.materials.map(function (m) { return m.id; })
  };

  try {
    // 出题要等模型生成，用长超时
    const data = await api.post('/quizzes', payload, { llm: true });
    quizState.quiz = data;
    quizState.answers = {};
    quizState.phase = 'answering';
    startQuizTimer();
    renderQuiz();
  } catch (err) {
    setQuizGenerating(false);
    showToast('生成测试题失败：' + err.message, 'err');
  }
}

function setQuizGenerating(flag) {
  quizState.generating = flag;

  const btn = document.getElementById('startQuizBtn');
  const box = document.getElementById('quizWorking');
  if (btn) btn.disabled = flag;
  if (box) box.hidden = !flag;
}

/* ---------- 第二步：答题中 ---------- */

function renderQuizAnswering() {
  const questions = (quizState.quiz && quizState.quiz.questions) || [];

  quizEls.root.innerHTML = `
    <div class="quiz-bar">
      <span>已作答 <b id="answeredCount">${countAnswered()}</b> / ${questions.length}</span>
      <span>用时 <b id="quizTimer">${formatDuration(quizState.elapsed)}</b></span>
    </div>

    <div class="quiz-list">${questions.map(renderQuestionCard).join('')}</div>

    <div class="quiz-actions">
      <button class="btn btn--ghost" type="button" id="abandonQuizBtn">放弃</button>
      <button class="btn btn--primary" type="button" id="submitQuizBtn">提交</button>
    </div>

    <div class="working" id="quizWorking" hidden>
      <span>正在出结果</span>
      <span class="thinking__dots"><i></i><i></i><i></i></span>
    </div>
  `;
}

function renderQuestionCard(q, index) {
  const typeText = QUESTION_TYPE_TEXT[q.type] || q.type;
  const diffText = DIFFICULTY_TEXT[q.difficulty];
  const seq = q.seq || index + 1;

  return '<div class="question">'
       +   '<div class="question__head">'
       +     '<span class="question__seq">第 ' + seq + ' 题</span>'
       +     '<span class="qtag qtag--type">' + escapeHtml(typeText) + '</span>'
       +     (diffText ? '<span class="qtag qtag--' + escapeHtml(q.difficulty) + '">' + diffText + '</span>' : '')
       +   '</div>'
       +   '<div class="question__text">' + escapeHtml(q.question) + '</div>'
       +   renderQuestionInput(q)
       + '</div>';
}

/* 判断题的选项是固定的，后端没给就自己兜底 */
const JUDGE_OPTIONS = { A: '正确', B: '错误' };

/* 把后端给的选项统一成 [{key, text}]。
   后端可能给对象 {"A": "文本"}，也可能给数组 ["A. 文本", ...]，
   甚至是 JSON 字符串 —— 三种都要能吃下，前端不该猜格式。 */
function normalizeOptions(raw) {
  let source = raw;

  if (typeof source === 'string') {
    try {
      source = JSON.parse(source);
    } catch (err) {
      source = String(source).split(/\r?\n/);
    }
  }

  if (Array.isArray(source)) {
    const mapped = {};
    source.forEach(function (item, index) {
      const text = String(item === null || item === undefined ? '' : item).trim();
      if (!text) return;

      const matched = text.match(/^([A-Za-z])\s*[.、)．:：]\s*(.+)$/);
      if (matched) {
        mapped[matched[1].toUpperCase()] = matched[2].trim();
      } else {
        mapped[String.fromCharCode(65 + index)] = text;
      }
    });
    source = mapped;
  }

  if (!source || typeof source !== 'object') return [];

  return Object.keys(source)
    .filter(function (key) { return String(source[key]).trim() !== ''; })
    .sort()
    .map(function (key) {
      return { key: key.toUpperCase(), text: String(source[key]).trim() };
    });
}

function renderQuestionInput(q) {
  if (q.type === 'short') {
    return '<textarea class="option-text" data-question="' + q.id + '"'
         +        ' placeholder="在这里作答…">' + escapeHtml(quizState.answers[String(q.id)] || '') + '</textarea>';
  }

  const isJudge = q.type === 'judge';
  let options = normalizeOptions(q.options);

  // 判断题的选项固定，后端没给或给坏了都用兜底值
  if (isJudge && !options.length) {
    options = normalizeOptions(JUDGE_OPTIONS);
  }

  if (!options.length) {
    return '<div class="empty">这道题没有可用选项，跳过即可。</div>';
  }

  const current = quizState.answers[String(q.id)];

  return '<div class="options">'
       + options.map(function (option, index) {
           const picked = current === option.key ? ' is-picked' : '';
           const glyph = isJudge ? (index === 0 ? '✓' : '✗') : option.key;
           return '<button class="option' + picked + '" type="button"'
                +        ' data-question="' + q.id + '" data-value="' + option.key + '">'
                +   '<span class="option__key">' + glyph + '</span>'
                +   '<span class="option__text">' + escapeHtml(option.text) + '</span>'
                + '</button>';
         }).join('')
       + '</div>';
}

function countAnswered() {
  const questions = (quizState.quiz && quizState.quiz.questions) || [];
  return questions.filter(function (q) {
    const value = quizState.answers[String(q.id)];
    return value !== undefined && String(value).trim() !== '';
  }).length;
}

function updateAnsweredCount() {
  const el = document.getElementById('answeredCount');
  if (el) el.textContent = String(countAnswered());
}

function onQuizClick(e) {
  const countBtn = e.target.closest('[data-count]');
  if (countBtn) {
    quizState.questionCount = Number(countBtn.dataset.count);
    quizEls.root.querySelectorAll('.segmented__item').forEach(function (b) {
      b.classList.toggle('is-active', b === countBtn);
    });
    return;
  }

  const option = e.target.closest('.option[data-question]');
  if (option) {
    quizState.answers[String(option.dataset.question)] = option.dataset.value;
    option.parentNode.querySelectorAll('.option').forEach(function (o) {
      o.classList.toggle('is-picked', o === option);
    });
    updateAnsweredCount();
    return;
  }

  if (e.target.closest('#startQuizBtn'))   return onStartQuiz();
  if (e.target.closest('#submitQuizBtn'))  return onSubmitQuiz();
  if (e.target.closest('#abandonQuizBtn')) return onAbandonQuiz();
  if (e.target.closest('#restartQuizBtn')) return backToSetup();
}

function onQuizChange(e) {
  if (e.target.id === 'quizMaterial') {
    quizState.materialId = e.target.value;
  }
}

function onQuizInput(e) {
  const textarea = e.target.closest('.option-text[data-question]');
  if (!textarea) return;

  quizState.answers[String(textarea.dataset.question)] = textarea.value;
  updateAnsweredCount();
}

/* ---------- 计时 ---------- */

function startQuizTimer() {
  stopQuizTimer();
  quizState.startedAt = Date.now();
  quizState.elapsed = 0;

  quizState.timerId = setInterval(function () {
    quizState.elapsed = Math.floor((Date.now() - quizState.startedAt) / 1000);
    const el = document.getElementById('quizTimer');
    if (el) el.textContent = formatDuration(quizState.elapsed);
  }, 1000);
}

function stopQuizTimer() {
  if (quizState.timerId) {
    clearInterval(quizState.timerId);
    quizState.timerId = null;
  }
}

function formatDuration(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const pad = function (n) { return String(n).padStart(2, '0'); };
  return pad(Math.floor(s / 60)) + ':' + pad(s % 60);
}

function formatScore(n) {
  return (Number(n) || 0).toFixed(1);
}

/* ---------- 提交 ---------- */

function buildAnswerPayload() {
  const questions = (quizState.quiz && quizState.quiz.questions) || [];

  return questions.map(function (q) {
    let value = quizState.answers[String(q.id)];
    if (value === undefined || String(value).trim() === '') {
      value = null;
    } else if (q.type === 'judge') {
      // 界面上判断题也是 A/B 两个选项，但标准答案是布尔，这里换回来
      value = (String(value).toUpperCase() === 'A');
    }
    return { question_id: q.id, user_answer: value };
  });
}

async function onSubmitQuiz() {
  if (quizState.submitting) return;

  setQuizSubmitting(true);

  try {
    const data = await api.post('/quizzes/' + quizState.quiz.quiz_id + '/submit', {
      answers: buildAnswerPayload(),
      duration_seconds: quizState.elapsed
    }, { llm: true });

    stopQuizTimer();
    quizState.result = data;
    quizState.phase = 'result';
    renderQuiz();
    loadQuizHistory();
  } catch (err) {
    setQuizSubmitting(false);
    showToast('提交失败：' + err.message, 'err');
  }
}

function setQuizSubmitting(flag) {
  quizState.submitting = flag;

  const submitBtn = document.getElementById('submitQuizBtn');
  const abandonBtn = document.getElementById('abandonQuizBtn');
  const box = document.getElementById('quizWorking');

  if (submitBtn) submitBtn.disabled = flag;
  if (abandonBtn) abandonBtn.disabled = flag;
  if (box) box.hidden = !flag;
}

function onAbandonQuiz() {
  if (quizState.submitting) return;
  if (!window.confirm('确定放弃本次测评？已作答的内容不会保存。')) return;
  backToSetup();
}

function backToSetup() {
  stopQuizTimer();

  quizState.phase = 'setup';
  quizState.generating = false;
  quizState.submitting = false;
  quizState.quiz = null;
  quizState.answers = {};
  quizState.result = null;
  quizState.elapsed = 0;

  renderQuiz();
  loadQuizMaterials();
}

/* ---------- 第三步：看结果 ---------- */

function renderQuizResult() {
  const result = quizState.result;
  const details = result.details || [];
  const fullScore = Number(result.full_score) || 0;
  const totalScore = Number(result.total_score) || 0;
  const rate = fullScore > 0 ? totalScore / fullScore : 0;

  const rightCount = details.filter(function (d) { return d.is_correct; }).length;
  const wrongCount = details.length - rightCount;
  const duration = result.duration_seconds === undefined ? quizState.elapsed : result.duration_seconds;

  const questions = questionMap();

  const reviews = details.map(function (d) {
    return renderReviewItem(d, questions[String(d.question_id)]);
  }).join('');

  quizEls.root.innerHTML = `
    <div class="panel quiz-score">
      <div class="score-ring-wrap">
        <svg class="score-ring" viewBox="0 0 120 120" aria-hidden="true">
          <circle class="score-ring__track" cx="60" cy="60" r="${SCORE_RING_R}"></circle>
          <circle class="score-ring__fill" id="scoreRingFill" cx="60" cy="60" r="${SCORE_RING_R}"></circle>
        </svg>
        <div class="score-ring__center">
          <div class="score-ring__value" id="scoreRingValue">0.0</div>
          <div class="score-ring__unit">/ ${formatScore(fullScore)}</div>
        </div>
      </div>
      <div class="quiz-score__caption">本次得分</div>
    </div>

    <div class="grid-cards">
      <div class="stat">
        <div class="stat__label">答对</div>
        <div class="stat__value stat__value--ok">${rightCount} 道</div>
      </div>
      <div class="stat">
        <div class="stat__label">答错</div>
        <div class="stat__value stat__value--err">${wrongCount} 道</div>
      </div>
      <div class="stat">
        <div class="stat__label">用时</div>
        <div class="stat__value">${formatDuration(duration)}</div>
      </div>
    </div>

    <div class="panel panel--flush">
      <div class="panel__head">
        <span class="panel__title">逐题回顾</span>
        <span class="panel__hint">点开看答案与点评</span>
      </div>
      ${reviews}
    </div>

    ${renderHistoryPanel()}

    <div class="quiz-actions">
      <button class="btn btn--primary" type="button" id="restartQuizBtn">重新测评</button>
    </div>
  `;

  animateScoreRing(rate, totalScore);
}

function questionMap() {
  const map = {};
  ((quizState.quiz && quizState.quiz.questions) || []).forEach(function (q) {
    map[String(q.id)] = q;
  });
  return map;
}

function animateScoreRing(rate, totalScore) {
  const fill = document.getElementById('scoreRingFill');
  const valueEl = document.getElementById('scoreRingValue');
  const safeRate = Math.max(0, Math.min(1, rate));

  requestAnimationFrame(function () {
    if (fill) fill.style.strokeDashoffset = String(SCORE_RING_C * (1 - safeRate));
  });

  const duration = 1100;
  const start = performance.now();

  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);

    if (valueEl) valueEl.textContent = (totalScore * eased).toFixed(1);
    if (t < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

function renderReviewItem(d, q) {
  const typeText = QUESTION_TYPE_TEXT[d.type] || d.type;
  const cls = d.is_correct ? 'is-right' : 'is-wrong';
  const mark = d.is_correct ? '✓' : '✗';

  return '<details class="review">'
       +   '<summary class="review__head">'
       +     '<span class="review__seq">第 ' + (q ? (q.seq || '') : '') + ' 题</span>'
       +     '<span class="qtag qtag--type">' + escapeHtml(typeText) + '</span>'
       +     '<span class="review__score ' + cls + '">' + mark + ' '
       +       formatScore(d.score) + ' / ' + formatScore(d.full_score) + '</span>'
       +   '</summary>'
       +   '<div class="review__body">'
       +     (q ? '<div class="review__question">' + escapeHtml(q.question) + '</div>' : '')
       +     reviewRow('正确答案', escapeHtml(formatAnswer(d.correct_answer, d.type)))
       +     reviewRow('你的答案', escapeHtml(formatAnswer(d.user_answer, d.type)))
       +     reviewRow('点评', renderMarkdown(d.reason || '—'))
       +     (d.knowledge_point ? reviewRow('知识点', escapeHtml(d.knowledge_point)) : '')
       +   '</div>'
       + '</details>';
}

function reviewRow(label, valueHtml) {
  return '<div class="review__row">'
       +   '<span class="review__label">' + escapeHtml(label) + '</span>'
       +   '<div class="review__value">' + valueHtml + '</div>'
       + '</div>';
}

function formatAnswer(value, type) {
  if (value === null || value === undefined || value === '') return '未作答';
  if (type === 'judge') return (value === true || value === 'true') ? '正确' : '错误';
  return String(value);
}

async function loadQuizHistory() {
  try {
    const data = await api.get('/quizzes');
    quizState.history = data.items || [];
  } catch (err) {
    quizState.history = [];
  }
  renderQuizHistory();
}

/* 历史测评记录的渲染。抽成公共函数是因为 setup（刚进页面）和 result（交卷后）
   两个阶段都要显示 —— 只在结果页显示的话，用户刚进来看不到之前做过什么。 */
function historyRowsHTML() {
  const items = quizState.history || [];

  if (!items.length) {
    return '<div class="empty">还没有测评记录。</div>';
  }

  return items.map(function (it) {
    return '<div class="history-row">'
         +   '<span class="history-row__date">' + formatTime(it.submitted_at) + '</span>'
         +   '<span class="history-row__meta">' + (it.question_count || 0) + ' 道</span>'
         +   '<span class="history-row__meta">' + formatDuration(it.duration_seconds) + '</span>'
         +   '<span class="history-row__score">'
         +     formatScore(it.score) + ' / ' + formatScore(it.full_score)
         +   '</span>'
         + '</div>';
  }).join('');
}

function renderHistoryPanel() {
  return '<div class="panel panel--flush">'
       +   '<div class="panel__head">'
       +     '<span class="panel__title">历史测评记录</span>'
       +   '</div>'
       +   '<div id="quizHistory">' + historyRowsHTML() + '</div>'
       + '</div>';
}

/* 数据加载完后只换列表内容，不动外层面板 */
function renderQuizHistory() {
  const box = document.getElementById('quizHistory');
  if (box) box.innerHTML = historyRowsHTML();
}

/* ============================================================
   进度页（看进度）
   ============================================================ */

/* 掌握度等级：按知识点累计得分率划分 */
const KNOWLEDGE_LEVELS = [
  { min: 0.9, name: '已掌握', cls: 'is-mastered' },
  { min: 0.7, name: '熟练',   cls: 'is-familiar' },
  { min: 0.4, name: '待加强', cls: 'is-shaky' },
  { min: 0,   name: '薄弱',   cls: 'is-poor' }
];

/* 低于此得分率计入薄弱知识点 */
const WEAK_THRESHOLD = 0.7;

/* 笔记缩略滑块：行高与上下内边距必须与 .note-input 的 CSS 一致 */
const NOTE_LINE_HEIGHT = 22;
const NOTE_PADDING = 24;
const NOTE_MIN_LINES = 4;
const NOTE_SAVE_DELAY = 1200;

const progressState = {
  overview: null,
  knowledge: [],
  materials: [],
  saveTimers: {},
  loading: true,
  error: ''
};

let progressEls = null;

function pageProgress() {
  return '<section class="page" id="progressRoot"></section>';
}

function mountProgress() {
  progressEls = { root: document.getElementById('progressRoot') };

  progressState.overview = null;
  progressState.knowledge = [];
  progressState.materials = [];
  progressState.saveTimers = {};
  progressState.loading = true;
  progressState.error = '';

  progressEls.root.addEventListener('input', onProgressInput);

  renderProgress();
  loadProgressData();
}

function unmountProgress() {
  flushNotes();
}

/* ---------- 数据 ---------- */

async function loadProgressData() {
  progressState.loading = true;
  renderProgress();

  const results = await Promise.all([
    api.get('/progress/overview').catch(function (e) { return { __error: e.message }; }),
    api.get('/progress/knowledge').catch(function (e) { return { __error: e.message }; }),
    api.get('/materials').catch(function (e) { return { __error: e.message }; })
  ]);

  const [overview, knowledge, materials] = results;

  if (overview.__error) {
    progressState.error = '学习数据加载失败：' + overview.__error;
  } else {
    progressState.overview = overview;
  }

  progressState.knowledge = knowledge.__error ? [] : (knowledge.items || []);
  progressState.materials = materials.__error ? [] : (materials.items || []);

  progressState.loading = false;
  renderProgress();

  /* 首屏渲染后测量笔记高度，决定要不要出缩略滑块 */
  progressState.materials.forEach(function (m) { syncNoteSlider(String(m.id)); });
}

function renderProgress() {
  if (progressState.loading) {
    progressEls.root.innerHTML = '<div class="empty">正在载入学习数据…</div>';
    return;
  }

  if (progressState.error) {
    progressEls.root.innerHTML = '<div class="empty">' + escapeHtml(progressState.error) + '</div>';
    return;
  }

  const overview = progressState.overview || {};
  const knowledge = progressState.knowledge;
  const weakPoints = knowledge
    .filter(function (k) { return k.score_rate < WEAK_THRESHOLD; })
    .sort(function (a, b) { return a.score_rate - b.score_rate; });

  progressEls.root.innerHTML = `
    <header class="page__header">
      <h1 class="page__title">进度</h1>
      <p class="page__desc">资料学习情况与知识点掌握度。</p>
    </header>

    <div class="grid-cards">
      ${statCard('资料总数', overview.materials_total, ' 份', '')}
      ${statCard('已掌握', overview.materials_mastered, ' 份', 'ok')}
      ${statCard('学习次数', overview.study_count, ' 次', '')}
      ${statCard('平均分', formatRate(overview.avg_score_rate), '', '')}
      ${statCard('薄弱点', weakPoints.length, ' 个', weakPoints.length ? 'err' : '')}
    </div>

    <div class="progress-grid">
      <div class="panel">
        <div class="panel__head">
          <span class="panel__title">知识点掌握度</span>
          <span class="panel__hint">${knowledge.length} 个知识点</span>
        </div>
        <div class="radar-wrap">${renderRadar(knowledge)}</div>
      </div>

      <div class="panel panel--flush">
        <div class="panel__head">
          <span class="panel__title">知识点明细</span>
        </div>
        <div class="kp-list">${renderKnowledgeList(knowledge)}</div>
      </div>
    </div>

    <div class="panel panel--flush">
      <div class="panel__head">
        <span class="panel__title">薄弱知识点</span>
        <span class="panel__hint">${weakPoints.length} 个</span>
      </div>
      <div class="kp-list">${renderWeakList(weakPoints)}</div>
    </div>

    <div class="panel panel--flush">
      <div class="panel__head">
        <span class="panel__title">资料详情与笔记</span>
        <span class="panel__hint">输入后自动保存</span>
      </div>
      <div id="materialNotes">${renderMaterialNotes(progressState.materials)}</div>
    </div>
  `;
}

function statCard(label, value, unit, tone) {
  const hasValue = value !== null && value !== undefined && value !== '';
  const cls = 'stat__value' + (hasValue ? (tone ? ' stat__value--' + tone : '') : ' stat__value--muted');
  return '<div class="stat">'
       +   '<div class="stat__label">' + escapeHtml(label) + '</div>'
       +   '<div class="' + cls + '">' + (hasValue ? escapeHtml(String(value)) + unit : '—') + '</div>'
       + '</div>';
}

function formatRate(rate) {
  if (rate === null || rate === undefined || rate === '') return null;
  return Math.round(Number(rate) * 100) + '%';
}

/* ---------- 雷达图 ---------- */

function renderRadar(items) {
  if (items.length < 3) {
    return '<div class="empty">知识点少于 3 个，画不出雷达图。先去「测评」做一次测试。</div>';
  }

  const W = 400;
  const H = 330;
  const cx = W / 2;
  const cy = H / 2;
  const R = 100;
  const labelR = 120;
  const n = items.length;

  function pointAt(index, ratio) {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / n;
    return {
      x: cx + R * ratio * Math.cos(angle),
      y: cy + R * ratio * Math.sin(angle),
      angle: angle
    };
  }

  let grid = '';
  [0.25, 0.5, 0.75, 1].forEach(function (level) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const p = pointAt(i, level);
      pts.push(p.x.toFixed(1) + ',' + p.y.toFixed(1));
    }
    grid += '<polygon class="radar__grid" points="' + pts.join(' ') + '"></polygon>';
  });

  let axes = '';
  for (let i = 0; i < n; i++) {
    const p = pointAt(i, 1);
    axes += '<line class="radar__axis" x1="' + cx + '" y1="' + cy + '"'
          + ' x2="' + p.x.toFixed(1) + '" y2="' + p.y.toFixed(1) + '"></line>';
  }

  const rates = items.map(function (it) { return clamp01(it.score_rate); });

  const areaPoints = rates.map(function (rate, i) {
    const p = pointAt(i, rate);
    return p.x.toFixed(1) + ',' + p.y.toFixed(1);
  }).join(' ');

  const dots = rates.map(function (rate, i) {
    const p = pointAt(i, rate);
    return '<circle class="radar__dot" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="2.6"></circle>';
  }).join('');

  const labels = items.map(function (it, i) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const lx = cx + labelR * Math.cos(angle);
    const ly = cy + labelR * Math.sin(angle);
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const anchor = Math.abs(cos) < 0.3 ? 'middle' : (cos > 0 ? 'start' : 'end');
    const dy = sin > 0.5 ? '0.8em' : (sin < -0.5 ? '0' : '0.32em');

    return '<text class="radar__label" x="' + lx.toFixed(1) + '" y="' + ly.toFixed(1) + '"'
         +      ' text-anchor="' + anchor + '" dy="' + dy + '">'
         +   escapeHtml(truncateText(it.knowledge_point, 6))
         + '</text>';
  }).join('');

  return '<svg class="radar" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="知识点掌握度雷达图">'
       +   grid + axes
       +   '<polygon class="radar__area" points="' + areaPoints + '"></polygon>'
       +   dots + labels
       + '</svg>';
}

function clamp01(value) {
  const n = Number(value);
  if (isNaN(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function truncateText(text, max) {
  const s = String(text === null || text === undefined ? '' : text);
  return s.length > max ? s.slice(0, max) + '…' : s;
}

/* ---------- 知识点列表 ---------- */

function renderKnowledgeList(items) {
  if (!items.length) {
    return '<div class="empty">还没有测评记录。完成一次测评后，这里会显示各知识点的掌握度。</div>';
  }

  return items.map(function (k) {
    const level = levelOf(k.score_rate);
    const pct = Math.round(clamp01(k.score_rate) * 100);

    return '<div class="kp-row">'
         +   '<div class="kp-row__head">'
         +     '<span class="kp-row__name">' + escapeHtml(k.knowledge_point) + '</span>'
         +     '<span class="kp-row__rate">' + pct + '%</span>'
         +     '<span class="qtag kp-row__level ' + level.cls + '">' + level.name + '</span>'
         +   '</div>'
         +   '<div class="kp-row__bar"><i class="kp-row__fill ' + level.cls + '" style="width:' + pct + '%"></i></div>'
         + '</div>';
  }).join('');
}

function renderWeakList(items) {
  if (!items.length) {
    return '<div class="empty">没有薄弱知识点，保持住。</div>';
  }

  return items.map(function (k) {
    const level = levelOf(k.score_rate);
    const pct = Math.round(clamp01(k.score_rate) * 100);

    return '<div class="kp-row">'
         +   '<div class="kp-row__head">'
         +     '<span class="kp-row__name">' + escapeHtml(k.knowledge_point) + '</span>'
         +     '<span class="kp-row__meta">答对 ' + (k.correct || 0) + ' / ' + (k.total || 0) + ' 题</span>'
         +     '<span class="kp-row__rate">' + pct + '%</span>'
         +     '<span class="qtag kp-row__level ' + level.cls + '">' + level.name + '</span>'
         +   '</div>'
         +   '<div class="kp-row__bar"><i class="kp-row__fill ' + level.cls + '" style="width:' + pct + '%"></i></div>'
         + '</div>';
  }).join('');
}

function levelOf(rate) {
  const r = clamp01(rate);
  for (let i = 0; i < KNOWLEDGE_LEVELS.length; i++) {
    if (r >= KNOWLEDGE_LEVELS[i].min) return KNOWLEDGE_LEVELS[i];
  }
  return KNOWLEDGE_LEVELS[KNOWLEDGE_LEVELS.length - 1];
}

/* ---------- 资料详情与笔记 ---------- */

function renderMaterialNotes(items) {
  if (!items.length) {
    return '<div class="empty">还没有资料。先去「资料库」上传。</div>';
  }

  return items.map(function (m) {
    const typeText = MATERIAL_TYPE_TEXT[m.file_type] || String(m.file_type || '').toUpperCase();

    return '<div class="note-block">'
         +   '<div class="note-block__head">'
         +     '<span class="note-block__name" title="' + escapeHtml(m.name) + '">' + escapeHtml(m.name) + '</span>'
         +     '<span class="qtag">' + escapeHtml(typeText) + '</span>'
         +     '<span class="note-status" data-status="' + m.id + '"></span>'
         +   '</div>'
         +   '<textarea class="note-input" data-material="' + m.id + '"'
         +     ' placeholder="记录这份资料的学习笔记，停笔后自动保存…">'
         +     escapeHtml(m.note || '')
         +   '</textarea>'
         +   '<div class="note-slider" data-slider="' + m.id + '" hidden>'
         +     '<span class="note-slider__end">缩略</span>'
         +     '<input type="range" min="' + NOTE_MIN_LINES + '" max="' + NOTE_MIN_LINES + '" value="' + NOTE_MIN_LINES + '"'
         +       ' data-slider-for="' + m.id + '" aria-label="笔记显示行数">'
         +     '<span class="note-slider__end">完整</span>'
         +     '<span class="note-slider__count"></span>'
         +   '</div>'
         + '</div>';
  }).join('');
}

function onProgressInput(e) {
  const slider = e.target.closest('.note-slider input[type="range"]');
  if (slider) {
    applyNoteSlider(slider.dataset.sliderFor, Number(slider.value));
    return;
  }

  const textarea = e.target.closest('.note-input');
  if (textarea) {
    onNoteInput(textarea);
  }
}

function onNoteInput(textarea) {
  const id = textarea.dataset.material;
  const item = progressState.materials.filter(function (m) { return String(m.id) === id; })[0];
  if (item) item.note = textarea.value;

  setNoteStatus(id, '编辑中…', 'is-editing');

  clearTimeout(progressState.saveTimers[id]);
  progressState.saveTimers[id] = setTimeout(function () {
    progressState.saveTimers[id] = null;
    if (item) persistNote(id, item.note);
  }, NOTE_SAVE_DELAY);

  syncNoteSlider(id);
}

async function persistNote(id, note) {
  try {
    const data = await api.put('/materials/' + id + '/note', { note: note });
    setNoteStatus(id, '已保存 ' + formatTime(data && data.updated_at), 'is-saved');
  } catch (err) {
    setNoteStatus(id, '保存失败：' + err.message, 'is-error');
  }
}

/* 离开页面时把没到点的自动保存立刻发出去，避免丢笔记 */
function flushNotes() {
  Object.keys(progressState.saveTimers).forEach(function (id) {
    if (!progressState.saveTimers[id]) return;
    clearTimeout(progressState.saveTimers[id]);
    progressState.saveTimers[id] = null;

    const item = progressState.materials.filter(function (m) { return String(m.id) === id; })[0];
    if (item) persistNote(id, item.note);
  });
}

function setNoteStatus(id, text, cls) {
  const el = document.querySelector('.note-status[data-status="' + id + '"]');
  if (!el) return;
  el.textContent = text;
  el.className = 'note-status ' + (cls || '');
}

/* ---------- 笔记缩略滑块 ---------- */

function noteTextarea(id) {
  return document.querySelector('.note-input[data-material="' + id + '"]');
}

function measureNoteLines(textarea) {
  const prevHeight = textarea.style.height;
  const prevOverflow = textarea.style.overflowY;

  textarea.style.height = 'auto';
  textarea.style.overflowY = 'hidden';
  const natural = textarea.scrollHeight;

  textarea.style.height = prevHeight;
  textarea.style.overflowY = prevOverflow;

  return Math.max(1, Math.round((natural - NOTE_PADDING) / NOTE_LINE_HEIGHT));
}

function syncNoteSlider(id) {
  const textarea = noteTextarea(id);
  if (!textarea) return;

  const wrap = document.querySelector('.note-slider[data-slider="' + id + '"]');
  if (!wrap) return;

  const range = wrap.querySelector('input[type="range"]');
  const lines = measureNoteLines(textarea);

  if (lines <= NOTE_MIN_LINES) {
    wrap.hidden = true;
    textarea.style.height = (NOTE_MIN_LINES * NOTE_LINE_HEIGHT + NOTE_PADDING) + 'px';
    textarea.style.overflowY = 'hidden';
    return;
  }

  wrap.hidden = false;
  range.max = String(lines);

  let value = Number(range.value) || NOTE_MIN_LINES;
  if (value > lines) value = lines;
  if (value < NOTE_MIN_LINES) value = NOTE_MIN_LINES;
  range.value = String(value);

  applyNoteSlider(id, value);
}

function applyNoteSlider(id, lines) {
  const textarea = noteTextarea(id);
  if (!textarea) return;

  const value = Math.max(NOTE_MIN_LINES, Number(lines) || NOTE_MIN_LINES);

  textarea.style.height = (value * NOTE_LINE_HEIGHT + NOTE_PADDING) + 'px';
  textarea.style.overflowY = 'auto';

  const wrap = document.querySelector('.note-slider[data-slider="' + id + '"]');
  if (!wrap) return;

  const range = wrap.querySelector('input[type="range"]');
  const count = wrap.querySelector('.note-slider__count');
  if (count) count.textContent = value + ' / ' + range.max + ' 行';
}

/* ============================================================
   报告页（出周报）
   ============================================================ */

const reportState = {
  mode: 'week',        /* week 本周 / custom 自定义 */
  startDate: '',
  endDate: '',
  generating: false,
  report: null,        /* 当前展示的报告 */
  history: []
};

let reportEls = null;

function pageReport() {
  return '<section class="page" id="reportRoot"></section>';
}

function mountReport() {
  reportEls = { root: document.getElementById('reportRoot') };

  const range = weekRange();
  reportState.mode = 'week';
  reportState.startDate = range.start;
  reportState.endDate = range.end;
  reportState.generating = false;
  reportState.report = null;
  reportState.history = [];

  reportEls.root.addEventListener('click', onReportClick);
  reportEls.root.addEventListener('change', onReportChange);

  renderReportPage();
  loadReportHistory();
}

/* ---------- 日期范围 ---------- */

function toDateValue(date) {
  const pad = function (n) { return String(n).padStart(2, '0'); };
  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
}

/* 本周 = 周一 至 周日 */
function weekRange() {
  const now = new Date();
  const mondayOffset = (now.getDay() + 6) % 7;   /* 周日 getDay()=0，回退 6 天 */
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - mondayOffset);
  const sunday = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
  return { start: toDateValue(monday), end: toDateValue(sunday) };
}

/* ---------- 渲染 ---------- */

function renderReportPage() {
  const isWeek = reportState.mode === 'week';

  reportEls.root.innerHTML = `
    <header class="page__header">
      <h1 class="page__title">报告</h1>
      <p class="page__desc">按日期范围汇总学习数据与薄弱知识点。</p>
    </header>

    <div class="panel">
      <div class="report-toolbar">
        <div class="field report-toolbar__mode">
          <span class="field__label">范围</span>
          <div class="segmented">
            <button class="segmented__item${isWeek ? ' is-active' : ''}" type="button" data-mode="week">本周</button>
            <button class="segmented__item${isWeek ? '' : ' is-active'}" type="button" data-mode="custom">自定义</button>
          </div>
        </div>

        <div class="field">
          <label class="field__label" for="reportStart">开始</label>
          <input class="input" type="date" id="reportStart"
                 value="${escapeHtml(reportState.startDate)}"${isWeek ? ' disabled' : ''}>
        </div>

        <div class="field">
          <label class="field__label" for="reportEnd">结束</label>
          <input class="input" type="date" id="reportEnd"
                 value="${escapeHtml(reportState.endDate)}"${isWeek ? ' disabled' : ''}>
        </div>

        <button class="btn btn--primary" type="button" id="generateReportBtn">生成周报</button>
      </div>

      <div class="working" id="reportWorking" hidden>
        <span>正在生成周报</span>
        <span class="thinking__dots"><i></i><i></i><i></i></span>
      </div>
    </div>

    ${renderReportView()}

    <div class="panel panel--flush">
      <div class="panel__head">
        <span class="panel__title">历史报告</span>
        <span class="panel__hint" id="reportHistoryCount">${reportState.history.length} 份</span>
      </div>
      <div id="reportHistory">${renderReportHistory()}</div>
    </div>
  `;
}

function renderReportView() {
  const r = reportState.report;

  if (!r) {
    return '<div class="panel"><div class="empty">选好日期范围，点「生成周报」，AI 会汇总这段时间的学习情况。</div></div>';
  }

  const stats = r.stats || {};

  return `
    <div class="panel panel--flush">
      <div class="panel__head">
        <span class="panel__title">${escapeHtml(r.start_date)} ~ ${escapeHtml(r.end_date)}</span>
        <span class="report-head__right">
          ${r.created_at ? '<span class="panel__hint">生成于 ' + formatTime(r.created_at) + '</span>' : ''}
          <button class="btn btn--ghost btn--sm" type="button" id="downloadReportBtn">下载</button>
        </span>
      </div>

      <div class="report-stats">
        ${reportStat('新增资料', stats.new_materials, ' 份')}
        ${reportStat('对话次数', stats.chat_count, ' 次')}
        ${reportStat('测评次数', stats.quiz_count, ' 次')}
        ${reportStat('平均得分率', formatRate(stats.avg_score_rate), '')}
      </div>

      <div class="report-body">${renderMarkdown(r.content || '')}</div>
    </div>
  `;
}

function reportStat(label, value, unit) {
  const hasValue = value !== null && value !== undefined && value !== '';
  return '<div class="report-stat">'
       +   '<div class="report-stat__label">' + escapeHtml(label) + '</div>'
       +   '<div class="report-stat__value">'
       +     (hasValue ? escapeHtml(String(value)) + unit : '—')
       +   '</div>'
       + '</div>';
}

function renderReportHistory() {
  const items = reportState.history;

  if (!items.length) {
    return '<div class="empty">还没有生成过报告。</div>';
  }

  const currentId = reportState.report ? reportState.report.id : null;

  return items.map(function (it) {
    const active = it.id === currentId ? ' is-active' : '';
    return '<button class="report-row' + active + '" type="button" data-report="' + it.id + '">'
         +   '<span class="report-row__range">'
         +     escapeHtml(it.start_date) + ' ~ ' + escapeHtml(it.end_date)
         +   '</span>'
         +   '<span class="report-row__meta">生成于 ' + formatTime(it.created_at) + '</span>'
         + '</button>';
  }).join('');
}

/* ---------- 交互 ---------- */

function onReportClick(e) {
  const modeBtn = e.target.closest('[data-mode]');
  if (modeBtn) return setReportMode(modeBtn.dataset.mode);

  const row = e.target.closest('[data-report]');
  if (row) return loadReport(Number(row.dataset.report));

  if (e.target.closest('#generateReportBtn')) return onGenerateReport();
  if (e.target.closest('#downloadReportBtn')) return downloadReport();
}

function onReportChange(e) {
  if (e.target.id === 'reportStart') reportState.startDate = e.target.value;
  if (e.target.id === 'reportEnd') reportState.endDate = e.target.value;
}

/* 只更新受影响的控件，不整页重渲染，避免报告内容闪烁 */
function setReportMode(mode) {
  reportState.mode = mode;

  if (mode === 'week') {
    const range = weekRange();
    reportState.startDate = range.start;
    reportState.endDate = range.end;
  }

  const startInput = document.getElementById('reportStart');
  const endInput = document.getElementById('reportEnd');
  const isWeek = mode === 'week';

  if (startInput) {
    startInput.value = reportState.startDate;
    startInput.disabled = isWeek;
  }
  if (endInput) {
    endInput.value = reportState.endDate;
    endInput.disabled = isWeek;
  }

  reportEls.root.querySelectorAll('[data-mode]').forEach(function (btn) {
    btn.classList.toggle('is-active', btn.dataset.mode === mode);
  });
}

async function onGenerateReport() {
  if (reportState.generating) return;

  const start = document.getElementById('reportStart').value;
  const end = document.getElementById('reportEnd').value;

  if (!start || !end) {
    showToast('请选择完整的日期范围', 'err');
    return;
  }
  if (start > end) {
    showToast('开始日期不能晚于结束日期', 'err');
    return;
  }

  reportState.startDate = start;
  reportState.endDate = end;
  setReportGenerating(true);

  try {
    // 写周报也要等模型生成
    const data = await api.post('/reports',
      { start_date: start, end_date: end }, { llm: true });
    reportState.generating = false;
    reportState.report = data;
    renderReportPage();
    loadReportHistory();
  } catch (err) {
    setReportGenerating(false);
    showToast('生成周报失败：' + err.message, 'err');
  }
}

function setReportGenerating(flag) {
  reportState.generating = flag;

  const btn = document.getElementById('generateReportBtn');
  const box = document.getElementById('reportWorking');
  if (btn) btn.disabled = flag;
  if (box) box.hidden = !flag;
}

async function loadReportHistory() {
  try {
    const data = await api.get('/reports');
    reportState.history = data.items || [];
  } catch (err) {
    reportState.history = [];
  }

  const box = document.getElementById('reportHistory');
  if (box) box.innerHTML = renderReportHistory();

  const count = document.getElementById('reportHistoryCount');
  if (count) count.textContent = reportState.history.length + ' 份';
}

async function loadReport(id) {
  try {
    const data = await api.get('/reports/' + id);
    reportState.report = data;
    renderReportPage();
    window.scrollTo(0, 0);
  } catch (err) {
    showToast('报告加载失败：' + err.message, 'err');
  }
}

/* ---------- 下载 ---------- */

function downloadReport() {
  const r = reportState.report;
  if (!r) return;

  const blob = new Blob([buildReportFile(r)], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = '学习周报_' + r.start_date + '_' + r.end_date + '.md';
  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}

function buildReportFile(r) {
  const stats = r.stats || {};
  const rate = formatRate(stats.avg_score_rate);

  return [
    '# 学习周报（' + r.start_date + ' ~ ' + r.end_date + '）',
    '',
    '- 新增资料：' + (stats.new_materials || 0) + ' 份',
    '- 对话次数：' + (stats.chat_count || 0) + ' 次',
    '- 测评次数：' + (stats.quiz_count || 0) + ' 次',
    '- 平均得分率：' + (rate === null ? '—' : rate),
    '',
    '---',
    '',
    r.content || ''
  ].join('\n');
}

/* ============================================================
   其余页面（静态骨架，待接入）
   ============================================================ */

/* ---------- 路由表 ---------- */

const ROUTES = {
  '#/learn':    { render: pageLearn,    mount: mountLearn },
  '#/library':  { render: pageLibrary,  mount: mountLibrary,  unmount: unmountLibrary },
  '#/quiz':     { render: pageQuiz,     mount: mountQuiz,     unmount: unmountQuiz },
  '#/progress': { render: pageProgress, mount: mountProgress, unmount: unmountProgress },
  '#/report':   { render: pageReport,   mount: mountReport }
};

const DEFAULT_ROUTE = '#/learn';

const appEl = document.getElementById('app');
const navEl = document.getElementById('nav');

let mountedPage = null;

function currentRoute() {
  return ROUTES[location.hash] ? location.hash : DEFAULT_ROUTE;
}

function render() {
  const route = currentRoute();
  const page = ROUTES[route];

  if (mountedPage && mountedPage.unmount) mountedPage.unmount();

  appEl.innerHTML = page.render();

  navEl.querySelectorAll('.nav-tab').forEach(function (tab) {
    tab.classList.toggle('is-active', tab.dataset.route === route);
  });

  window.scrollTo(0, 0);

  if (page.mount) page.mount();
  mountedPage = page;
}

function initRouter() {
  window.addEventListener('hashchange', render);
  render();
}

/* ---------- 后台连接状态点 ---------- */

const dotEl = document.getElementById('statusDot');

async function refreshStatus() {
  const online = await api.checkHealth();

  dotEl.classList.toggle('is-online', online);
  dotEl.classList.toggle('is-offline', !online);
  dotEl.title = online ? '后台已连接' : '后台未连接';
}

function initStatus() {
  refreshStatus();
  setInterval(refreshStatus, CONFIG.HEALTH_INTERVAL);
}

/* ---------- 启动 ---------- */

/* 拖到页面其他地方时，阻止浏览器直接打开文件 */
document.addEventListener('dragover', function (e) { e.preventDefault(); });
document.addEventListener('drop', function (e) { e.preventDefault(); });

initRouter();
initStatus();
