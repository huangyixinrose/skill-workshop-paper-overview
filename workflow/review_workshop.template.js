// 并行精读 + 主题综合 + 议题对照 的编排模板（Claude Code Workflow 工具）。
// 用法：把 ▼FILL▼ 各处（BASE / CATS / PAPERS / RECOVER / AUDIENCE）按本次 manifest 填好，
//      再用 Workflow 工具以 {script: <填好的内容>} 运行（在背景跑，完成会通知）。
// 注意：经验上 Workflow 的 args 传参易被字符串化，所以把清单"写死"进脚本最稳（见下）。
// 完成后 result 里有 { digests, sections, recovery, critic, crosscut }；落盘到 data/ 后用 build_report.py 组装。
//   crosscut 落到 data/crosscut.json。
// 全程便宜模型即可：批判这一层的定位是"系统性对照扫描 → 给人的核查提示"，深度判断由人读原文完成。

export const meta = {
  name: 'review-workshop-run',
  description: 'Read papers into digests, recover missing, per-theme syntheses + critic, then issue×paper cross-cut scan',
  phases: [
    { title: 'Read', detail: 'one reader subagent per paper (cheap model) + 1 recovery agent' },
    { title: 'Synthesize', detail: 'one writer per theme + 1 completeness critic' },
    { title: 'CrossCut', detail: 'issue×paper matrix + common problems + central papers + white space (cheap model)' },
  ],
}

// ▼FILL▼ 1：抽好的文本目录
const BASE = '/ABS/PATH/TO/<workdir>/txt/'
// ▼FILL▼ 2：关口2确认后的主线类目
const CATS = ['主线A', '主线B', '主线C', '其他']
// ▼FILL▼ 3：manifest 里成功抽到文本的论文
const PAPERS = [
  { id: 'p01', track: 'archival',     title: '...' },
  // ...
]
// ▼FILL▼ 4：缺失/撤稿论文标题（交给 recovery 检索；没有就留空数组）
const RECOVER = ['Some Withheld Title ...']
// ▼FILL▼ 5：目标读者，用于贯穿提示词
const AUDIENCE = '（如：做实时交互视频世界模型的创业者）'

const DIGEST_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    id: { type: 'string' }, title: { type: 'string' },
    team: { type: 'string' }, track: { type: 'string' },
    category: { type: 'string', enum: CATS },
    problem: { type: 'string' }, method: { type: 'string' },
    key_results: { type: 'string' }, limitations: { type: 'string' },
    relevance: { type: 'string' },
    appraisal: { type: 'string' },     // 批判核查提示（按其范式看证据/构念清晰度/隐含前提），供人核实非定论
    future_calls: { type: 'string' },  // 论文自陈的局限/未来工作呼吁（现成 gap 候选）
    card_zh: { type: 'string' },
    code_url: { type: 'string' },
    figure_essential: { type: 'boolean' },
    figure_ref: { type: 'string' }, figure_caption: { type: 'string' },
  },
  required: ['id', 'title', 'category', 'problem', 'method', 'key_results', 'relevance', 'card_zh', 'figure_essential'],
}

phase('Read')
const readTasks = PAPERS.map(p => () => agent(
  `你在精读一篇论文，为 ${AUDIENCE} 做结构化提要。\n` +
  `论文 id：${p.id}\n标题：${p.title}\n赛道：${p.track}\n全文文本文件：${BASE}${p.id}.txt\n` +
  `请用 Read 读取（聚焦正文，附录略读），按 schema 返回。要求：id/track 原样回填；` +
  `category 从这些里选最贴切原文照填：${CATS.join(' / ')}；文本中文、含数字、不编造、读不到写"未报告"；` +
  `team 识别机构、code_url 有则填；figure_essential 仅当有一张原图能显著辅助理解才 true 并填 figure_ref+figure_caption；` +
  `card_zh 120-180 字；` +
  `appraisal=按该工作"自身范式"给人的批判核查提示（证据是否扎实、核心构念/指标是否清晰且与同领域一致、有何隐含前提）——是供人核实的线索而非定论，无明显问题写"未见明显问题"；` +
  `future_calls=论文自陈的局限或对未来工作的呼吁，无则写"无"。`,
  { label: 'read:' + p.id, phase: 'Read', model: 'sonnet', schema: DIGEST_SCHEMA }
))
const recTask = () => agent(
  `以下论文未公开全文，只有标题，请用 WebSearch 尽量找 arXiv/Scholar 预印本，逐篇中文返回：标题、是否找到、链接、据标题推断的一句话核心贡献（找不到也要标"仅据标题推断"）：\n` +
  RECOVER.map((t, i) => (i + 1) + '. ' + t).join('\n'),
  { label: 'recover', phase: 'Read', model: 'sonnet' }
)
const readResults = await parallel(RECOVER.length ? [...readTasks, recTask] : readTasks)
const recovery = RECOVER.length ? readResults.pop() : ''
const digests = readResults.filter(Boolean)
log('digests=' + digests.length + '/' + PAPERS.length + ' output_tokens=' + budget.spent())

phase('Synthesize')
const byCat = {}; CATS.forEach(c => byCat[c] = [])
digests.forEach(d => (byCat[d.category] || (byCat[d.category] = [])).push(d))
const sections = await parallel(CATS.map(cat => () => agent(
  `为面向 ${AUDIENCE} 的综述写主线"${cat}"。相关提要 JSON（可能为空）：\n` +
  JSON.stringify(byCat[cat] || []) +
  `\n写 600-1000 字中文：核心进展；点名代表作并串起取向与分歧；可落地启发；若很少/空则指出留白。` +
  `用"评价"语气而非平铺直叙，按各自范式判断优劣（优点缺点都讲）。不要用"不是X而是Y"句式。返回纯文本可用小标题。`,
  { label: 'theme:' + cat.slice(0, 4), phase: 'Synthesize', model: 'sonnet' }
)))
const critic = await agent(
  `综述草稿查漏（结果是给人的核查清单，逐条标明依据）。提要(精简)：\n` +
  JSON.stringify(digests.map(d => ({ id: d.id, title: d.title, category: d.category, key: d.key_results, appraisal: d.appraisal }))) +
  `\n各主线草稿：\n` + JSON.stringify(sections) +
  `\n中文列点：①归错类/遗漏；②结论缺支撑/不可比数字并排/绝对值写成相对值/以偏概全；` +
  `③系统性找 gap：核心构念定义或度量在各篇间是否不一致、跨论文结论是否矛盾、结论是否受限于单一基准/语境、各篇 future_calls 能否汇成方向；④缺哪些跨主线视角。`,
  { label: 'critic', phase: 'Synthesize', model: 'sonnet' }
)

phase('CrossCut')
const CROSSCUT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    issues: { type: 'array', items: { type: 'object', additionalProperties: false,
      properties: { name: { type: 'string' }, papers: { type: 'array', items: { type: 'string' } }, note: { type: 'string' } },
      required: ['name', 'papers'] } },
    common_problems: { type: 'array', items: { type: 'object', additionalProperties: false,
      properties: { problem: { type: 'string' }, papers: { type: 'array', items: { type: 'string' } }, why: { type: 'string' } },
      required: ['problem', 'papers'] } },
    central_papers: { type: 'array', items: { type: 'object', additionalProperties: false,
      properties: { id: { type: 'string' }, issues: { type: 'array', items: { type: 'string' } }, why: { type: 'string' } },
      required: ['id', 'why'] } },
    white_space: { type: 'array', items: { type: 'object', additionalProperties: false,
      properties: { gap: { type: 'string' }, note: { type: 'string' } }, required: ['gap'] } },
    human_note: { type: 'string' },
  },
  required: ['issues', 'common_problems', 'central_papers', 'white_space'],
}
const crosscut = await agent(
  `你在为面向 ${AUDIENCE} 的综述做"议题×论文对照扫描"。这是给人看的批判性核查清单——你只做系统性扫描、列候选与线索，最终判断由人读原文完成，措辞克制、默认"待人核查"。\n` +
  `全部论文提要(JSON)：\n` +
  JSON.stringify(digests.map(d => ({ id: d.id, title: d.title, category: d.category, problem: d.problem, key_results: d.key_results, limitations: d.limitations, appraisal: d.appraisal, future_calls: d.future_calls }))) +
  `\n按 schema 输出（全部中文）：issues=从各篇抽出的跨论文议题/子概念及涉及论文 id；common_problems=多篇共同的痛点或未解问题（共性问题候选）+涉及论文+为何值得注意；central_papers=覆盖议题最多、最该优先二次深读的论文 id+所涉议题+理由；white_space=少有人触及的方向/研究空白。`,
  { label: 'crosscut', phase: 'CrossCut', model: 'sonnet', schema: CROSSCUT_SCHEMA }
)

return { digests, categories: CATS, sections, recovery, critic, crosscut }
