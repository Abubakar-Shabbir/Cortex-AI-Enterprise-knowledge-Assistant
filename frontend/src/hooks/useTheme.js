import { useCallback, useState } from 'react';

// Same localStorage 'theme' contract as templates/base.html's inline
// script (index.html mirrors that boot-time check) - toggling here
// updates the same key, so the classic Django pages and this SPA never
// disagree about which theme is active.
export function useTheme() {
  const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'));

  const toggle = useCallback(() => {
    const next = !document.documentElement.classList.contains('dark');
    document.documentElement.classList.toggle('dark', next);
    localStorage.theme = next ? 'dark' : 'light';
    setIsDark(next);
  }, []);

  return { isDark, toggle };
}
