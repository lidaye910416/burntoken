// .claude/skills/burn-review-tribunal/lib/config.js
import { readFileSync, existsSync } from 'fs'

const ENV_PATTERN = /\$\{([A-Z_][A-Z0-9_]*)\}/g

/**
 * Replace ${ENV_VAR} placeholders in a string.
 * Unset vars become empty string.
 */
export function expandEnv(s) {
  return s.replace(ENV_PATTERN, (_, name) => process.env[name] ?? '')
}

/**
 * Load and parse a providers.json file.
 * Expands env placeholders in all string values.
 * Returns null if file does not exist.
 */
export function loadProvidersFile(path) {
  if (!existsSync(path)) return null
  const raw = readFileSync(path, 'utf8')
  return JSON.parse(expandEnv(raw))
}

/**
 * Resolve a preset by name from a config object.
 * Returns null if not found.
 */
export function resolvePreset(config, name) {
  return config.presets?.[name] ?? null
}
