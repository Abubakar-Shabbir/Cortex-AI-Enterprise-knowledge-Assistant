import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { SessionProvider } from './auth/SessionContext.jsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Reuse cached data across navigations by default instead of
      // refetching on every mount - individual hooks (api/hooks.js)
      // override this per-query where fresher data actually matters
      // (e.g. the documents list while a row is processing).
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter basename="/">
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
)
