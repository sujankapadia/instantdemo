import { TooltipProvider } from '@/components/ui/tooltip'
import { Layout } from '@/components/Layout'

function App() {
  return (
    <TooltipProvider>
      <Layout />
    </TooltipProvider>
  )
}

export default App
