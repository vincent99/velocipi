// @ts-check

import eslint from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';
import pluginVue from 'eslint-plugin-vue';
import vueTs from '@vue/eslint-config-typescript';

export default defineConfig(
  eslint.configs.recommended,
  tseslint.configs.recommended,
  pluginVue.configs['flat/recommended'],
  vueTs(),
  {
    rules: {
      curly: ['error', 'all'],
      'vue/multi-word-component-names': 'off',
      'vue/valid-template-root': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          args: 'all',
          argsIgnorePattern: '^_',
          caughtErrors: 'all',
          caughtErrorsIgnorePattern: '^_',
          destructuredArrayIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          ignoreRestSiblings: true,
        },
      ],
    },
  }
);
