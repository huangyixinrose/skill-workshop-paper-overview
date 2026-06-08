// 并行精读 + 主题综合 的编排模板（Claude Code Workflow 工具）。
// 用法：把 ▼FILL▼ 三处（BASE / CATS / PAPERS）按本次 manifest 填好，
//      再用 Workflow 工具以 {script: <填好的内容>} 运行（在背景跑，完成会通知）。
// 注意：经验上 Workflow 的 args 传参易被字符串化，所以把清单"写死"进脚本最稳（见下）。
// 完成后 result 里有 { digests, sections, recovery, critic }；落盘到 data/ 后用 build_report.py 组装。

export const meta = {
  name: 'review-workshop-run',
  description: 'Read all papers into structured digests, recover missing ones, then per-theme syntheses + completeness critic',
  phases: [
    { title: 'Read', detail: 'one reader subagent per paper (cheap model) + 1 recovery agent' },
    { title: 'Synthesize', detail: 'one writer per theme + 1 completeness critic' },
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
    relevance: { type: 'string' }, card_zh: { type: 'string' },
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
  `card_zh 120-180 字。`,
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
  `不要用"不是X而是Y"句式。返回纯文本可用小标题。`,
  { label: 'theme:' + cat.slice(0, 4), phase: 'Synthesize', model: 'sonnet' }
)))
const critic = await agent(
  `综述草稿查漏。提要(精简)：\n` +
  JSON.stringify(digests.map(d => ({ id: d.id, title: d.title, category: d.category, key: d.key_results }))) +
  `\n各主线草稿：\n` + JSON.stringify(sections) +
  `\n中文列点：①归错类/遗漏；②结论缺支撑/不可比数字并排/绝对值写成相对值/以偏概全；③缺哪些跨主线视角。`,
  { label: 'critic', phase: 'Synthesize', model: 'sonnet' }
)

return { digests, categories: CATS, sections, recovery, critic }
