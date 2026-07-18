import DefaultTheme from 'vitepress/theme-without-fonts'
import type { Theme } from 'vitepress'

// Self-hosted app fonts (Fraunces/Hanken/JetBrains) + canonical design tokens,
// from the single shared source of truth consumed by the app too. Imported
// before custom.css so the --vp-* overrides can reference the token vars.
import '../../../shared/theme/fonts.css'
import '../../../shared/theme/tokens.css'
// Maps VitePress's --vp-* variables onto the app tokens (last import wins).
import './custom.css'

// theme-without-fonts is the default theme minus its bundled Inter @font-face,
// so no Inter woff2 ships; the shared fonts.css supplies the three app faces.
export default {
  extends: DefaultTheme,
} satisfies Theme
