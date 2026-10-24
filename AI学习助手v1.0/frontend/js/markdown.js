/* ============================================================
   markdown.js —— 文本渲染工具
   1) escapeHtml      转义成安全 HTML
   2) renderMarkdown  把 AI 回复渲染成带排版的 HTML
   只支持聊天里真正会出现的语法：标题、列表、代码块、行内代码、粗体、斜体。
   ============================================================ */

const MD_ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };

function escapeHtml(text) {
  return String(text === null || text === undefined ? '' : text)
    .replace(/[&<>"]/g, function (ch) { return MD_ESCAPE_MAP[ch]; });
}

/* ---------- 行内语法 ---------- */

function inlineMarkdown(text) {
  /* 先把行内代码抽出来占位，避免其中的 * 被当成粗体 */
  const codes = [];

  let out = escapeHtml(text).replace(/`([^`]+)`/g, function (m, code) {
    codes.push(code);
    return '\u0000' + (codes.length - 1) + '\u0000';
  });

  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/(^|[^*\w])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  out = out.replace(/\n/g, '<br>');

  return out.replace(/\u0000(\d+)\u0000/g, function (m, idx) {
    return '<code class="md-inline-code">' + codes[Number(idx)] + '</code>';
  });
}

/* ---------- 块级语法 ---------- */

function renderMarkdown(src) {
  const lines = String(src === null || src === undefined ? '' : src)
    .replace(/\r\n/g, '\n')
    .split('\n');

  let html = '';
  let listTag = null;   /* 当前打开的列表标签：ul / ol */

  function closeList() {
    if (listTag) {
      html += '</' + listTag + '>';
      listTag = null;
    }
  }

  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    /* 代码块 ```lang */
    const fence = line.match(/^\s*```(\S*)\s*$/);
    if (fence) {
      closeList();
      const lang = fence[1] || 'code';
      const buf = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
        buf.push(lines[i]);
        i++;
      }
      i++;   /* 跳过收尾围栏 */
      html += '<div class="md-code">'
            +   '<div class="md-code__lang">' + escapeHtml(lang) + '</div>'
            +   '<pre><code>' + escapeHtml(buf.join('\n')) + '</code></pre>'
            + '</div>';
      continue;
    }

    /* 标题：# ~ ######，映射到 h3 ~ h6，避免盖过页面层级 */
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      html += '<h' + level + ' class="md-h md-h' + level + '">'
            + inlineMarkdown(heading[2])
            + '</h' + level + '>';
      i++;
      continue;
    }

    /* 无序列表 */
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (bullet) {
      if (listTag !== 'ul') {
        closeList();
        html += '<ul class="md-list">';
        listTag = 'ul';
      }
      html += '<li>' + inlineMarkdown(bullet[1]) + '</li>';
      i++;
      continue;
    }

    /* 有序列表 */
    const ordered = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ordered) {
      if (listTag !== 'ol') {
        closeList();
        html += '<ol class="md-list">';
        listTag = 'ol';
      }
      html += '<li>' + inlineMarkdown(ordered[1]) + '</li>';
      i++;
      continue;
    }

    /* 空行 */
    if (!line.trim()) {
      closeList();
      i++;
      continue;
    }

    /* 段落：连续普通行合并，行内换行保留 */
    closeList();
    const para = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*```/.test(lines[i]) &&
      !/^#{1,6}\s/.test(lines[i]) &&
      !/^\s*[-*+]\s/.test(lines[i]) &&
      !/^\s*\d+\.\s/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    html += '<p class="md-p">' + inlineMarkdown(para.join('\n')) + '</p>';
  }

  closeList();
  return html;
}
