import React from 'react';
import DashboardFetcher from './dashboard';
import { Toaster } from 'react-hot-toast';
function App() {
  return (
    <div className="App">
      <DashboardFetcher />
      <Toaster position="top-right" reverseOrder={false} />
    </div>
  );
}

export default App;
