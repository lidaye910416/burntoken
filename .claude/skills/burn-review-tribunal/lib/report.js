// .claude/skills/burn-review-tribunal/lib/report.js

const SEVERITY_EMOJI = {
  critical: '🔴',
  major:    '🟠',
  minor:    '🟡',
  nit:      '⚪',
}

/**
 * Group findings by file path.
 */
export function groupByFile(findings) {
  const groups = {}
  for (const f of findings) {
    (groups[f.file] ?? (groups[f.file] = [])).push(f)
  }
  return groups
}

/**
 * Render confirmed findings as a Markdown report.
 */
export function renderMarkdown({ confirmed, rounds, totalTokens, target, startedAt }) {
  const groups = groupByFile(confirmed)
  const bySeverity = countBy(confirmed, 'severity')
  const byLens = countBy(confirmed, 'lens')

  const lines = []
  lines.push('# burn 审判团代码审查报告')
  lines.push('')
  lines.push(`- **时间**: ${startedAt}`)
  lines.push(`- **目标**: ${target}`)
  lines.push(`- **轮数**: ${rounds}`)
  lines.push(`- **Token 消耗**: ~${(totalTokens / 1000).toFixed(0)}k`)
  lines.push(`- **确认问题数**: ${confirmed.length}`)
  lines.push('')
  lines.push('## 严重程度分布')
  lines.push('')
  lines.push('| Severity | Count |')
  lines.push('|----------|-------|')
  for (const sev of ['critical', 'major', 'minor', 'nit']) {
    lines.push(`| ${sev} | ${bySeverity[sev] || 0} |`)
  }
  lines.push('')
  lines.push('## Lens 命中分布')
  lines.push('')
  lines.push('| Lens | Count |')
  lines.push('|------|-------|')
  for (const [lens, count] of Object.entries(byLens)) {
    lines.push(`| ${lens} | ${count} |`)
  }
  lines.push('')
  lines.push('## 确认问题（按文件分组）')
  lines.push('')
  for (const [file, items] of Object.entries(groups).sort()) {
    lines.push(`### ${file}`)
    lines.push('')
    for (const f of items) {
      const emoji = SEVERITY_EMOJI[f.severity] || '⚪'
      lines.push(`#### ${emoji} [${f.lens}][${f.severity}] ${f.title}`)
      lines.push(`- **行**: ${f.line}`)
      lines.push(`- **证据**: \`\`\`\n${f.evidence}\n\`\`\``)
      lines.push(`- **解释**: ${f.rationale}`)
      if (f.votes && Object.keys(f.votes).length) {
        const summary = Object.entries(f.votes)
          .map(([k, v]) => `${k}: ${v.verdict} (${v.confidence?.toFixed(2) ?? '?'})`)
          .join(', ')
        lines.push(`- **投票**: ${summary}`)
      }
      lines.push('')
    }
  }
  return lines.join('\n')
}

/**
 * Render as a structured JSON object (compatible with burn run.jsonl).
 */
export function renderJson({ confirmed, rounds, totalTokens, target, startedAt }) {
  const byLens = countBy(confirmed, 'lens')
  const bySeverity = countBy(confirmed, 'severity')
  return {
    workflow: 'burn-review-tribunal',
    version: '1.0',
    target,
    started_at: startedAt,
    rounds,
    total_tokens: totalTokens,
    estimated_cost_usd: totalTokens > 0 ? Number((totalTokens / 1000 * 0.01).toFixed(4)) : 0,
    confirmed_count: confirmed.length,
    findings: confirmed,
    by_lens: byLens,
    by_severity: bySeverity,
    raw_calls: [],
  }
}

function countBy(arr, key) {
  const result = {}
  for (const item of arr) {
    const k = item[key]
    result[k] = (result[k] || 0) + 1
  }
  return result
}
