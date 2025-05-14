import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import FilesList from './pages/FilesList';
import FileDetail from './pages/FileDetail';
import SearchPage from './pages/SearchPage';

// Components
import Navbar from './components/Navbar';
import Footer from './components/Footer';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider } from './hooks/useAuth';

// Create a client for react-query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// 404 Not Found Page Component
const NotFound = () => (
  <div className="page-container">
    <div className="card">
      <div className="empty-state">
        <div className="empty-icon"></div>
        <h3>404 - Không tìm thấy trang</h3>
        <p>Trang bạn tìm kiếm không tồn tại hoặc đã bị di chuyển.</p>
        <a href="/" className="btn-primary">Quay lại trang chủ</a>
      </div>
    </div>
  </div>
);

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <div className="app">
            <Navbar />
            <main className="content">
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/dashboard" element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                } />
                <Route path="/documents" element={
                  <ProtectedRoute>
                    <FilesList />
                  </ProtectedRoute>
                } />
                <Route path="/files" element={<Navigate to="/documents" replace />} />
                <Route path="/files/:id" element={
                  <ProtectedRoute>
                    <FileDetail />
                  </ProtectedRoute>
                } />
                <Route path="/search" element={
                  <ProtectedRoute>
                    <SearchPage />
                  </ProtectedRoute>
                } />
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
            <Footer />
          </div>
          <Toaster 
            position="top-right"
            toastOptions={{
              duration: 3000,
              style: {
                background: '#363636',
                color: '#fff',
              },
              success: {
                duration: 3000,
                style: {
                  background: '#1E293B',
                },
              },
            }}
          />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
