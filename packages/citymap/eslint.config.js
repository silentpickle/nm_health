// Copyright (c) 2026 nm_health contributors
// Strictest practical setup: typed rules, complexity cap, shallow nesting, no magic numbers (mirrors the repo root).
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

const MAX_COMPLEXITY = 15;
const MAX_DEPTH = 2;

export default defineConfig(
  {
    ignores: ["node_modules/", ".venv/"],
  },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      complexity: ["error", MAX_COMPLEXITY],
      "max-depth": ["error", MAX_DEPTH],
      "no-magic-numbers": "off",
      "@typescript-eslint/no-magic-numbers": [
        "error",
        {
          ignore: [0, 1, -1],
          ignoreDefaultValues: true,
          ignoreArrayIndexes: false,
          enforceConst: true,
        },
      ],
    },
  },
  {
    files: ["tests/**/*.js"],
    languageOptions: { globals: { ...globals.node } },
    rules: {
      // node:test runs every test() it is handed; nothing awaits the promise it returns.
      "@typescript-eslint/no-floating-promises": [
        "error",
        {
          allowForKnownSafeCalls: [
            {
              from: "package",
              name: ["test", "it", "describe", "suite"],
              package: "node:test",
            },
          ],
        },
      ],
    },
  },
);
