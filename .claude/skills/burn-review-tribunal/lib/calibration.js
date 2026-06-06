// .claude/skills/burn-review-tribunal/lib/calibration.js
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'
import { join } from 'path'

const CALIB_FILENAME = 'calibration.json'

function calibPath(dir) {
  return join(dir, CALIB_FILENAME)
}

/**
 * Load calibration data from disk.
 * Returns default empty data if file does not exist.
 */
export function loadCalibration(dir) {
  const path = calibPath(dir)
  if (!existsSync(path)) {
    return { lens: {}, judge: {} }
  }
  return JSON.parse(readFileSync(path, 'utf8'))
}

/**
 * Save calibration data to disk.
 * Creates dir if not exists. Sets file mode 0600.
 */
export function saveCalibration(dir, data) {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true })
  }
  const path = calibPath(dir)
  writeFileSync(path, JSON.stringify(data, null, 2), { mode: 0o600 })
}

/**
 * Record a new sample and update running average.
 * Mutates `data` in place.
 */
export function recordSample(data, category, name, tokens) {
  const bucket = data[category] ?? (data[category] = {})
  const entry = bucket[name] ?? (bucket[name] = { avg_output_tokens: 0, samples: 0 })
  const total = entry.avg_output_tokens * entry.samples + tokens
  entry.samples += 1
  entry.avg_output_tokens = total / entry.samples
}

/**
 * Get the running average output tokens for a category/name.
 * Returns 0 if no samples.
 */
export function getAvgTokens(data, category, name) {
  return data[category]?.[name]?.avg_output_tokens ?? 0
}
