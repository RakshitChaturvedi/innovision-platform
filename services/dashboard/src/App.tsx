import { AppRoutes } from "./routes/AppRoutes";
import SocketProvider from "./realtime/SocketProvider";

function App() {
  return (<SocketProvider> <AppRoutes /> </SocketProvider>);
}

export default App;