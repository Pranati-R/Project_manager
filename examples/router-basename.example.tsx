// React Router under a gateway path. import.meta.env.BASE_URL is what Vite's base/--base
// was set to ("/" without the gateway, "/myapp/" behind it), so this works in both places.
import { BrowserRouter, Routes, Route, createBrowserRouter } from 'react-router-dom'

// Option 1: <BrowserRouter>
export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  )
}

// Option 2: data routers
export const router = createBrowserRouter(
  [{ path: '/', element: <Home /> }, { path: '/settings', element: <Settings /> }],
  { basename: import.meta.env.BASE_URL },
)

// Vue Router:  createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })
// A hash router (<HashRouter>, createWebHashHistory()) needs no change at all.

function Home() { return <h1>Home</h1> }
function Settings() { return <h1>Settings</h1> }
