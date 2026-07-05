import { useSocketConnection } from "@/hooks/useSocketConnection";
import { Dashboard } from "@/pages/Dashboard";

function App() {
  useSocketConnection();
  return <Dashboard />;
}

export default App;
