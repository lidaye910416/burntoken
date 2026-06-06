// .claude/skills/burn-review-tribunal/lib/estimate.js
import { getAvgTokens } from './calibration.js'

const DEFAULT_LENS_TOKENS = 2000
const DEFAULT_JUDGE_TOKENS = 500

/**
 * Estimate tokens for a single round.
 *
 * @param {object} calibData
 * @param {{lens: string[], judge: string[], lensCount: number, judgePerFinding: number}} cfg
 * @param {number} findingCount
 * @returns {number}
 */
export function estimateRoundCost(calibData, cfg, findingCount) {
  let lensCost = 0
  for (const name of cfg.lens) {
    const t = getAvgTokens(calibData, 'lens', name) || DEFAULT_LENS_TOKENS
    lensCost += t
  }

  let judgeCost = 0
  for (const name of cfg.judge) {
    const t = getAvgTokens(calibData, 'judge', name) || DEFAULT_JUDGE_TOKENS
    judgeCost += t
  }

  return lensCost + findingCount * judgeCost
}

/**
 * Build a cost matrix: rows = round counts, cols = finding counts per round.
 *
 * @param {object} calibData
 * @param {{lens: string[], judge: string[], lensCount: number, judgePerFinding: number}} cfg
 * @param {number[]} roundList
 * @param {number[]} findingList
 * @returns {number[][]} matrix[roundsIndex][findingIndex]
 */
export function buildMatrix(calibData, cfg, roundList, findingList) {
  return roundList.map(rounds =>
    findingList.map(findings => rounds * estimateRoundCost(calibData, cfg, findings))
  )
}

/**
 * Format a token matrix as a plain text table.
 */
export function formatMatrix(matrix, roundList, findingList) {
  const headers = ['轮数 \\ F', ...findingList.map(f => `F=${f}`)]
  const rows = matrix.map((row, i) => [
    `${roundList[i]} 轮`,
    ...row.map(v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`),
  ])

  const colWidths = headers.map((h, j) =>
    Math.max(h.length, ...rows.map(r => r[j].length))
  )

  const fmt = (cells) => cells.map((c, j) => c.padEnd(colWidths[j])).join('  ')

  return [fmt(headers), ...rows.map(fmt)].join('\n')
}
