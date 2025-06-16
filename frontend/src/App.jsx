import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import FilesList from './pages/FilesList';
import FileDetail from './pages/FileDetail';
import IntelligentSearch from './pages/IntelligentSearch';
import UserManagement from './pages/UserManagement';

// Components
import Navbar from './components/Navbar';
import Footer from './components/Footer';
import ProtectedRoute from './components/ProtectedRoute';
import AuthCallback from './components/AuthCallback';
import { AuthProvider, useAuth } from './hooks/useAuth';

// Create a client for react-query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Role-based redirect component
const RoleBasedRedirect = () => {
  const { user } = useAuth();
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (user.role === 'admin' || user.role === 'manager') {
    return <Navigate to="/dashboard" replace />;
  } else {
    return <Navigate to="/search" replace />;
  }
};

// Admin or Manager route wrapper
const AdminOrManagerRoute = ({ children }) => {
  const { user } = useAuth();
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (user.role !== 'admin' && user.role !== 'manager') {
    return <Navigate to="/search" replace />;
  }
  
  return children;
};

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

// Layout component that conditionally renders Navbar
const AppLayout = ({ children }) => {
  const location = useLocation();
  const showNavbar = location.pathname !== '/login';
  
  return (
    <div className="app">
      {showNavbar && <Navbar />}
      <main className="content">
        {children}
      </main>
      <Footer />
    </div>
  );
};

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppLayout>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/auth/callback" element={<AuthCallback />} />
              <Route path="/dashboard" element={
                <ProtectedRoute>
                  <AdminOrManagerRoute>
                    <Dashboard />
                  </AdminOrManagerRoute>
                </ProtectedRoute>
              } />
              <Route path="/documents" element={
                <ProtectedRoute>
                  <AdminOrManagerRoute>
                    <FilesList />
                  </AdminOrManagerRoute>
                </ProtectedRoute>
              } />
              <Route path="/files" element={<Navigate to="/documents" replace />} />
              <Route path="/files/:id" element={
                <ProtectedRoute>
                  <AdminOrManagerRoute>
                    <FileDetail />
                  </AdminOrManagerRoute>
                </ProtectedRoute>
              } />
              <Route path="/search" element={
                <ProtectedRoute>
                  <IntelligentSearch />
                </ProtectedRoute>
              } />
              <Route path="/users" element={
                <ProtectedRoute>
                  <AdminOrManagerRoute>
                    <UserManagement />
                  </AdminOrManagerRoute>
                </ProtectedRoute>
              } />
              <Route path="/" element={<RoleBasedRedirect />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AppLayout>
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
