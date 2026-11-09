// Strictest practical setup: typed rules, complexity cap, shallow nesting, no magic numbers.
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

const MAX_COMPLEXITY = 15;
const MAX_DEPTH = 2;

export default defineConfig(
  {
    ignores: [
      "node_modules/",
      ".venv/",
      "site/",
      // Baseline: the prototype's local dashboard (served by `nm-health serve`), not linted until it is next changed.
      "nm_health/web/static/",
    ],
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
);
