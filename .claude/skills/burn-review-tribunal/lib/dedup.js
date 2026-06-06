// .claude/skills/burn-review-tribunal/lib/dedup.js

/**
 * Normalize a file path for dedup keys.
 * Strips ./ prefix, converts backslashes, lowercases.
 */
export function normalizePath(p) {
  return p
    .replace(/\\/g, '/')
    .replace(/^\.\//, '')
    .toLowerCase()
}

/**
 * Generate a dedup key for a finding.
 * Groups findings by: normalized file + 3-line bucket + category.
 */
export function dedupKey(f) {
  const file = normalizePath(f.file)
  const lineBucket = Math.floor((f.line - 1) / 3)
  return [file, lineBucket, f.category].join('|')
}

/**
 * Filter findings, keeping only those not in seen.
 * Mutates seen by adding fresh findings.
 *
 * @param {Array} findings
 * @param {Set} seen
 * @returns {Array} fresh findings
 */
export function dedupFindings(findings, seen) {
  const fresh = []
  for (const f of findings) {
    const key = dedupKey(f)
    if (!seen.has(key)) {
      seen.add(key)
      fresh.push(f)
    }
  }
  return fresh
}
