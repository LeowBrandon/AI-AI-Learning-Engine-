"""从资料里挑出与问题相关的段落，拼成给模型的上下文。

不用向量模型、不做 RAG：这里靠的是关键词重合度（英文按单词、中文按 2~4 字滑窗），
把命中的段落按相关度排序后凑到字符上限。够用，且没有任何外部依赖。

出题场景没有「问题」可依据，改用等间隔抽样，保证题目覆盖整份资料而不是只取开头。
"""

import re

from models import Material

# 中文里这些词到处都是，当关键词会命中一大片，先滤掉
STOPWORDS = {
    '什么', '怎么', '为什', '哪些', '哪个', '这个', '那个', '我们', '你们', '它们',
    '可以', '是否', '请问', '如何', '以及', '但是', '因为', '所以', '如果', '还是',
    '就是', '一个', '一下', '这些', '那些', '不能', '不会', '没有', '不是', '有的',
    '怎样', '介绍', '说明', '解释', '一下', '意思', '内容', '问题', '一下',
}

CJK_RUN = re.compile(r'[\u4e00-\u9fff]+')
LATIN_WORD = re.compile(r'[a-z][a-z0-9_\-\.]{1,}')


def load_materials(material_ids=None):
    """取出可用的资料。不传 material_ids 就是全部可用资料。"""
    query = Material.query.filter(Material.status == 'ready')

    if material_ids:
        query = query.filter(Material.id.in_(list(material_ids)))

    return query.order_by(Material.id).all()


def extract_terms(text):
    """抽出用于匹配的词，权重取词长 —— 越长越具体，命中越有分量。"""
    terms = {}
    lowered = (text or '').lower()

    for word in LATIN_WORD.findall(lowered):
        terms[word] = max(terms.get(word, 0), len(word))

    for run in CJK_RUN.findall(lowered):
        for size in (2, 3, 4):
            for start in range(len(run) - size + 1):
                term = run[start:start + size]
                if term in STOPWORDS:
                    continue
                terms[term] = max(terms.get(term, 0), size)

    return terms


def _score(content, terms):
    lowered = content.lower()
    total = 0
    for term, weight in terms.items():
        count = lowered.count(term)
        if count:
            # 同一个词出现太多次不再加分，避免长段落靠堆词胜出
            total += weight * min(count, 5)
    return total


def select_relevant(materials, question, limit_chars):
    """按关键词重合度挑段落，返回 [(material, chunk), ...]，按资料与段号排序。"""
    pairs = [(m, c) for m in materials for c in m.chunks]
    if not pairs:
        return []

    terms = extract_terms(question)
    hits = []
    for material, chunk in pairs:
        score = _score(chunk.content, terms)
        if score > 0:
            hits.append((score, material, chunk))

    hits.sort(key=lambda item: -item[0])

    picked = []
    used = 0
    for _score_value, material, chunk in hits:
        size = len(chunk.content)
        if used + size > limit_chars:
            continue
        picked.append((material, chunk))
        used += size

    if not picked:
        # 一个词都没命中（比如「总结一下这份资料」）。退化成按顺序取前面的段落，
        # 至少让模型有东西可看；资料确实没覆盖时，提示词里的兜底规则会兜住。
        for material, chunk in pairs:
            size = len(chunk.content)
            if used + size > limit_chars:
                break
            picked.append((material, chunk))
            used += size

    picked.sort(key=lambda pair: (pair[0].id, pair[1].chunk_index))
    return picked


def select_for_generation(materials, limit_chars):
    """出题用：等间隔抽样，让题目覆盖整份资料。"""
    pairs = [(m, c) for m in materials for c in m.chunks]
    if not pairs:
        return []

    total = sum(len(chunk.content) for _m, chunk in pairs)
    if total <= limit_chars:
        return pairs

    keep = max(1, int(len(pairs) * limit_chars / total))
    if keep >= len(pairs):
        return pairs

    step = len(pairs) / keep
    picked = []
    for index in range(keep):
        picked.append(pairs[min(len(pairs) - 1, int(index * step))])

    # 抽样可能取到重复项，去重后保持原顺序
    seen = set()
    unique = []
    for material, chunk in picked:
        key = (material.id, chunk.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        unique.append((material, chunk))

    return unique


def format_context(pairs, with_material_id=False):
    """拼成提示词里的「参考资料」。段号用 chunk_index + 1，与前端显示一致。

    with_material_id=True 时额外标出资料编号，用于出题 ——
    模型要把它原样回填到每道题的 material_id 字段，这样题目才能挂到具体资料上。
    """
    blocks = []
    for material, chunk in pairs:
        label = '《%s》第 %d 段' % (material.name, chunk.chunk_index + 1)
        if with_material_id:
            label = '【资料 %d】%s' % (material.id, label)
        blocks.append('%s：\n%s' % (label, chunk.content))
    return '\n\n'.join(blocks)


def build_references(pairs, snippet_length=150):
    """给前端的引用列表，字段与需求文档 B1 的 references 一致。"""
    return [
        {
            'material_id': material.id,
            'material_name': material.name,
            'chunk_index': chunk.chunk_index,
            'snippet': chunk.content[:snippet_length],
        }
        for material, chunk in pairs
    ]
