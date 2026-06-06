import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    testTimeout: 10000,
    include: ['tests/**/*.{test,spec}.?(c|m)[jt]s?(x)', 'tests/test-*.?(c|m)[jt]s?(x)'],
  },
})
