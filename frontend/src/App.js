import React, { useState, useEffect, useContext, createContext } from 'react';
import './App.css';

// Auth Context
const AuthContext = createContext();

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const savedSessionId = localStorage.getItem('dubcheck_session');
    if (savedSessionId) {
      setSessionId(savedSessionId);
      fetchUserProfile(savedSessionId);
    } else {
      setLoading(false);
    }
  }, []);

  const fetchUserProfile = async (sessionId) => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/user/profile`, {
        headers: {
          'Authorization': `Bearer ${sessionId}`
        }
      });
      
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        localStorage.removeItem('dubcheck_session');
        setSessionId(null);
      }
    } catch (error) {
      console.error('Error fetching user profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, name) => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, name })
      });

      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setSessionId(data.session_id);
        localStorage.setItem('dubcheck_session', data.session_id);
        return true;
      } else {
        // Try to register if login fails
        return await register(email, name);
      }
    } catch (error) {
      console.error('Login error:', error);
      return false;
    }
  };

  const register = async (email, name) => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, name })
      });

      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setSessionId(data.session_id);
        localStorage.setItem('dubcheck_session', data.session_id);
        return true;
      }
    } catch (error) {
      console.error('Registration error:', error);
    }
    return false;
  };

  const logout = () => {
    setUser(null);
    setSessionId(null);
    localStorage.removeItem('dubcheck_session');
  };

  return (
    <AuthContext.Provider value={{ user, sessionId, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

// Components
const Header = () => {
  const { user, logout } = useAuth();
  
  return (
    <header className="bg-white shadow-sm border-b">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center py-4">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <h1 className="text-2xl font-bold text-blue-600">DubCheck</h1>
            </div>
          </div>
          
          {user && (
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-600">Credits:</span>
                <span className="bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                  {user.credits}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-600">Plan:</span>
                <span className="bg-green-100 text-green-800 text-xs font-medium px-2.5 py-0.5 rounded-full capitalize">
                  {user.plan.replace('_', ' ')}
                </span>
              </div>
              <button
                onClick={logout}
                className="text-gray-500 hover:text-gray-700 text-sm"
              >
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

const LoginForm = () => {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    const success = await login(email, name);
    if (!success) {
      alert('Failed to login/register. Please try again.');
    }
    
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">DubCheck</h1>
          <p className="text-gray-600">AI-Powered Fact Checking</p>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter your email"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Full Name
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter your name"
            />
          </div>
          
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Processing...' : 'Login / Register'}
          </button>
        </form>
      </div>
    </div>
  );
};

const FactCheckForm = () => {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const { sessionId, user } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!text.trim()) {
      alert('Please enter text to fact-check');
      return;
    }
    
    setLoading(true);
    setResult(null);
    
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/fact-check`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${sessionId}`
        },
        body: JSON.stringify({ text })
      });
      
      if (response.ok) {
        const data = await response.json();
        setResult(data);
        // Refresh user data to update credits
        window.location.reload();
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to fact-check text');
      }
    } catch (error) {
      console.error('Fact-check error:', error);
      alert('An error occurred while fact-checking');
    } finally {
      setLoading(false);
    }
  };

  const getLikelihoodColor = (score) => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.6) return 'text-yellow-600';
    if (score >= 0.4) return 'text-orange-600';
    return 'text-red-600';
  };

  const getLikelihoodLabel = (score) => {
    if (score >= 0.8) return 'Highly Likely True';
    if (score >= 0.6) return 'Likely True';
    if (score >= 0.4) return 'Uncertain';
    return 'Likely False';
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="bg-white rounded-xl shadow-lg p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Fact-Check Text</h2>
        
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Text to Fact-Check
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter the text you want to fact-check..."
            />
          </div>
          
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500">
              Credits available: {user?.credits || 0}
            </div>
            <button
              type="submit"
              disabled={loading || !text.trim()}
              className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Analyzing...' : 'Fact-Check'}
            </button>
          </div>
        </form>
        
        {result && (
          <div className="mt-8 p-6 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Analysis Result</h3>
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-500">Likelihood:</span>
                <span className={`text-lg font-bold ${getLikelihoodColor(result.likelihood_score)}`}>
                  {(result.likelihood_score * 100).toFixed(1)}%
                </span>
              </div>
            </div>
            
            <div className="mb-4">
              <div className="flex items-center space-x-2 mb-2">
                <span className="text-sm font-medium text-gray-700">Assessment:</span>
                <span className={`text-sm font-semibold ${getLikelihoodColor(result.likelihood_score)}`}>
                  {getLikelihoodLabel(result.likelihood_score)}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all duration-300 ${
                    result.likelihood_score >= 0.8 ? 'bg-green-500' :
                    result.likelihood_score >= 0.6 ? 'bg-yellow-500' :
                    result.likelihood_score >= 0.4 ? 'bg-orange-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${result.likelihood_score * 100}%` }}
                />
              </div>
            </div>
            
            <div className="mb-4">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Reasoning:</h4>
              <p className="text-sm text-gray-600 leading-relaxed">{result.reasoning}</p>
            </div>
            
            {result.sources && result.sources.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-2">Sources:</h4>
                <div className="space-y-2">
                  {result.sources.map((source, index) => (
                    <div key={index} className="p-3 bg-white rounded border">
                      <h5 className="text-sm font-medium text-blue-600 mb-1">
                        <a href={source.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                          {source.title}
                        </a>
                      </h5>
                      <p className="text-xs text-gray-500">{source.snippet}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            <div className="mt-4 text-xs text-gray-500">
              Credits used: {result.credits_used}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const Dashboard = () => {
  const { user } = useAuth();
  const [factChecks, setFactChecks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchFactChecks();
  }, []);

  const fetchFactChecks = async () => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/user/fact-checks`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('dubcheck_session')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setFactChecks(data);
      }
    } catch (error) {
      console.error('Error fetching fact-checks:', error);
    } finally {
      setLoading(false);
    }
  };

  const getLikelihoodColor = (score) => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.6) return 'text-yellow-600';
    if (score >= 0.4) return 'text-orange-600';
    return 'text-red-600';
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="bg-white rounded-xl shadow-lg p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Recent Fact-Checks</h2>
        
        {loading ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : factChecks.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No fact-checks yet. Start by analyzing some text!
          </div>
        ) : (
          <div className="space-y-4">
            {factChecks.map((check, index) => (
              <div key={index} className="p-4 border rounded-lg hover:bg-gray-50 transition-colors">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <p className="text-sm text-gray-800 mb-2 line-clamp-2">
                      {check.text}
                    </p>
                  </div>
                  <div className="flex items-center space-x-2 ml-4">
                    <span className={`text-sm font-semibold ${getLikelihoodColor(check.likelihood_score)}`}>
                      {(check.likelihood_score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>Credits used: {check.credits_used}</span>
                  <span>{new Date(check.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const MainApp = () => {
  const [activeTab, setActiveTab] = useState('fact-check');
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            <button
              onClick={() => setActiveTab('fact-check')}
              className={`py-4 px-2 border-b-2 font-medium text-sm ${
                activeTab === 'fact-check'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Fact-Check
            </button>
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`py-4 px-2 border-b-2 font-medium text-sm ${
                activeTab === 'dashboard'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              History
            </button>
          </div>
        </div>
      </nav>
      
      <main className="py-8">
        {activeTab === 'fact-check' && <FactCheckForm />}
        {activeTab === 'dashboard' && <Dashboard />}
      </main>
    </div>
  );
};

const App = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

const AppContent = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return user ? <MainApp /> : <LoginForm />;
};

export default App;