// .claude/skills/burn-review-tribunal/lib/tally.js

const SIGNIFICANCE_THRESHOLD = 0.6

/**
 * Tally judge votes for a single finding.
 *
 * Passes when:
 *   1. Majority (≥ 2/3) judges say "real"
 *   2. isReal says "real"
 *   3. isSignificant says "real" with confidence ≥ 0.6
 *   4. isActionable says "real"
 *
 * @param {object} finding
 * @param {Array<{lens: string, verdict: {verdict: string, confidence: number, reasoning: string}}>} votes
 * @returns {{finding: object, passed: boolean, votes: object}}
 */
export function tallyVotes(finding, votes) {
  const voteMap = {}
  for (const v of votes) {
    voteMap[v.lens] = v.verdict
  }

  const realCount = votes.filter(v => v.verdict?.verdict === 'real').length
  const majority = realCount >= Math.ceil(votes.length * 2 / 3)

  const passed = majority
    && voteMap.isReal?.verdict === 'real'
    && voteMap.isSignificant?.verdict === 'real'
    && (voteMap.isSignificant?.confidence ?? 0) >= SIGNIFICANCE_THRESHOLD
    && voteMap.isActionable?.verdict === 'real'

  return { finding, passed, votes: voteMap }
}
