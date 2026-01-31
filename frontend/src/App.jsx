import React, { useState, useEffect, useRef } from 'react';
import { Camera, Settings, History, Utensils, Flame, ChevronRight, X, Save, Trash2, Loader2, Mail, Lock, User as UserIcon, LogOut, Info, Clock, Calendar, Plus, Upload, Percent, Share2, Copy, Check, Maximize2, Coffee, Sun, Apple, Moon, ShieldAlert, BarChart3, Users, ListTodo } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import axios from 'axios';

// Configure Axios Defaults
axios.defaults.baseURL = import.meta.env.VITE_API_URL || '';

const App = () => {
  const [view, setView] = useState('loading'); // loading, login, register, dashboard, verify
  const [token, setToken] = useState(localStorage.getItem('jinu_token'));
  const [user, setUser] = useState(null);
  const [data, setData] = useState({ target: 2000, consumed: 0, protein: 0, carbs: 0, fat: 0, daily_summary: '', grouped_history: [], trend: [] });
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [newTarget, setNewTarget] = useState(2000);
  const [newPassword, setNewPassword] = useState('');
  const [mealDescription, setMealDescription] = useState('');
  const [mealType, setMealType] = useState('Lunch');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedMeal, setSelectedMeal] = useState(null);

  const getSuggestedMealType = (currentHistory) => {
    // Singapore Time check
    const now = new Date();
    const utcHour = now.getUTCHours();
    const sgHour = (utcHour + 8) % 24;
    
    const today = currentHistory.find(d => d.display_date === "Today");
    const loggedTypes = today ? today.meals.map(m => m.meal_type) : [];

    if (sgHour >= 5 && sgHour < 11) {
      return loggedTypes.includes("Breakfast") ? "Snacks" : "Breakfast";
    } else if (sgHour >= 11 && sgHour < 15) {
      return loggedTypes.includes("Lunch") ? "Snacks" : "Lunch";
    } else if (sgHour >= 15 && sgHour < 18) {
      return "Snacks";
    } else if (sgHour >= 18 && sgHour < 23) {
      return loggedTypes.includes("Dinner") ? "Snacks" : "Dinner";
    }
    return "Snacks";
  };

  const handleOpenUpload = () => {
    const suggestion = getSuggestedMealType(data.grouped_history);
    setMealType(suggestion);
    setMealDescription('');
    setSelectedFiles([]);
    setPreviews([]);
    setShowUploadModal(true);
  };

  const selectedMealRef = useRef(null);
  const [copiedDay, setCopiedDay] = useState(null);
  const [shareConfig, setShareConfig] = useState({ enabled: false, token: null });
  const [isPublicView, setIsPublicView] = useState(false);
  const [adminData, setAdminStats] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const fileInputRef = useRef(null);

  const mealTypes = [
    { name: 'Breakfast', icon: <Coffee size={14} /> },
    { name: 'Lunch', icon: <Sun size={14} /> },
    { name: 'Snacks', icon: <Apple size={14} /> },
    { name: 'Dinner', icon: <Moon size={14} /> }
  ];

  // Auth States
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [authError, setAuthError] = useState('');

  const queryParams = new URLSearchParams(window.location.search);
  const telegramIdFromUrl = queryParams.get('telegram_id');
  const shareTokenFromUrl = window.location.pathname.startsWith('/share/') ? window.location.pathname.split('/')[2] : null;

  useEffect(() => {
    if (window.location.pathname === '/verify') {
      setView('verify');
      const v_token = queryParams.get('token');
      handleVerifyEmail(v_token);
      return;
    }

    if (shareTokenFromUrl) {
      setIsPublicView(true);
      fetchPublicData(shareTokenFromUrl);
      
      // Auto-refresh public view every 60 seconds
      const interval = setInterval(() => fetchPublicData(shareTokenFromUrl), 60000);
      return () => clearInterval(interval);
    } else if (token) {
      checkAuth();
      
      // Live Sync: Refresh dashboard every 30 seconds to catch trainer comments
      // This is very lightweight and not taxing on the server.
      const interval = setInterval(() => fetchData(token), 30000);
      
      // Also refresh when user switches back to the app tab
      const handleVisibility = () => {
        if (document.visibilityState === 'visible') fetchData(token);
      };
      window.addEventListener('visibilitychange', handleVisibility);
      
      return () => {
        clearInterval(interval);
        window.removeEventListener('visibilitychange', handleVisibility);
      };
    } else {
      const path = window.location.pathname;
      if (path === '/register') {
        setView('register');
      } else {
        setView('login');
      }
    }
  }, [token]);

  const checkAuth = async () => {
    try {
      const response = await axios.get('/users/me', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUser(response.data);
      setNewTarget(response.data.daily_target);
      setView('dashboard');
      fetchData(token);
      fetchShareStatus(token);
    } catch (err) {
      handleLogout();
    }
  };

  const fetchShareStatus = async (authToken) => {
    try {
      const res = await axios.get('/share/status', { headers: { Authorization: `Bearer ${authToken}` } });
      setShareConfig(res.data);
    } catch (e) {}
  };

  const toggleShare = async () => {
    try {
      const res = await axios.post(`/share/toggle?enabled=${!shareConfig.enabled}`, {}, { headers: { Authorization: `Bearer ${token}` } });
      setShareConfig(res.data);
    } catch (e) { alert("Failed to toggle sharing"); }
  };

  const resetShareToken = async () => {
    if (!confirm("Resetting will break the old share link. Continue?")) return;
    try {
      const res = await axios.post('/share/reset', {}, { headers: { Authorization: `Bearer ${token}` } });
      setShareConfig(prev => ({ ...prev, token: res.data.token }));
    } catch (e) {}
  };

  const fetchPublicData = async (token) => {
    setLoading(true);
    try {
      const res = await axios.get(`/public/stats/${token}`);
      setData(res.data);
      setView('dashboard');
    } catch (err) {
      alert("This share link is invalid or has been disabled.");
      window.location.href = '/';
    } finally {
      setLoading(false);
    }
  };

  const submitDailyFeedback = async (date, comment) => {
    try {
      const formData = new FormData();
      formData.append('note', comment);
      await axios.post(`/public/daily-feedback/${shareTokenFromUrl}/${date}`, formData);
      fetchPublicData(shareTokenFromUrl);
    } catch (e) { alert("Failed to add feedback"); }
  };

  const fetchAdminStats = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/stats', { headers: { Authorization: `Bearer ${token}` } });
      setAdminStats(res.data);
      setView('admin');
    } catch (e) { alert("Admin access denied"); }
    finally { setLoading(false); }
  };

  const handleLogout = () => {
    localStorage.removeItem('jinu_token');
    setToken(null);
    setUser(null);
    setView('login');
  };

  const fetchData = async (authToken, silent = false) => {
    if (!silent) setLoading(true);
    else setIsRefreshing(true);
    try {
      const response = await axios.get('/stats', {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      setData(response.data);
    } catch (err) {
      console.error("Fetch failed", err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('username', email);
      formData.append('password', password);
      
      const response = await axios.post('/auth/login', formData);
      const newToken = response.data.access_token;
      localStorage.setItem('jinu_token', newToken);
      setToken(newToken);
    } catch (err) {
      setAuthError(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyEmail = async (v_token) => {
    if (!v_token) {
      setAuthError("No verification token provided.");
      return;
    }
    try {
      await axios.get(`/auth/verify-email?token=${v_token}`);
      alert("Email verified successfully! You can now log in.");
      window.location.href = '/';
    } catch (err) {
      setAuthError(err.response?.data?.detail || "Verification failed. Token may be expired.");
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setAuthError('');
    setLoading(true);
    try {
      await axios.post('/auth/register', {
        email,
        password,
        name,
        telegram_id: telegramIdFromUrl
      });
      alert("Registration successful! Please check your email to verify your account before logging in.");
      setView('login');
    } catch (err) {
      setAuthError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (event) => {
    const files = Array.from(event.target.files);
    setSelectedFiles([...selectedFiles, ...files]);
    
    const newPreviews = files.map(file => URL.createObjectURL(file));
    setPreviews([...previews, ...newPreviews]);
  };

  const removeFile = (index) => {
    const newFiles = [...selectedFiles];
    newFiles.splice(index, 1);
    setSelectedFiles(newFiles);

    const newPreviews = [...previews];
    newPreviews.splice(index, 1);
    setPreviews(newPreviews);
  };

  const handleUploadSubmit = async () => {
    if (!mealDescription && selectedFiles.length === 0) {
      alert("Please provide at least a photo or a description.");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    selectedFiles.forEach(file => {
      formData.append('files', file);
    });
    formData.append('description', mealDescription);
    formData.append('meal_type', mealType);

    try {
      await axios.post('/upload-meal', formData, {
        headers: { 
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${token}`
        }
      });
      setShowUploadModal(false);
      resetUploadForm();
      fetchData(token, true);
    } catch (err) {
      if (err.response?.status === 429) {
        alert("⚠️ AI Quota Limit Reached\n\nYour app is working fine, but the AI service is temporarily overloaded. This is an external limit, not a bug. Please wait a minute and try again!");
      } else {
        alert(err.response?.data?.detail || "Upload failed. Please try again.");
      }
    } finally {
      setUploading(false);
    }
  };

  const resetUploadForm = () => {
    setMealDescription('');
    setMealType('Lunch');
    setSelectedFiles([]);
    setPreviews([]);
  };

  const deleteMeal = async (mealId) => {
    if (!confirm("Are you sure you want to delete this entry?")) return;
    
    // Optimistic Update
    const prevData = { ...data };
    const newGroupedHistory = data.grouped_history.map(day => ({
      ...day,
      meals: day.meals.filter(m => m.id !== mealId)
    })).filter(day => day.meals.length > 0);
    
    setData({ ...data, grouped_history: newGroupedHistory });
    if (selectedMeal?.id === mealId) setSelectedMeal(null);

    try {
      await axios.delete(`/meal/${mealId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchData(token); // Silent refresh in background
    } catch (err) {
      setData(prevData);
      alert("Failed to delete meal.");
    }
  };

  const saveSettings = async () => {
    try {
      let url = '/settings?';
      if (newTarget) url += `daily_target=${newTarget}&`;
      if (newPassword) url += `password=${encodeURIComponent(newPassword)}`;
      
      await axios.post(url, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setShowSettings(false);
      setNewPassword('');
      fetchData(token);
    } catch (err) {
      alert("Failed to save settings");
    }
  };

  const exportDay = (day) => {
    const text = `🥗 Calorie Tracker Report - ${day.display_date}\n\n` +
      `🔥 Total: ${day.totals.calories} kcal\n` +
      `🥩 Protein: ${day.totals.protein}g\n` +
      `🍞 Carbs: ${day.totals.carbs}g\n` +
      `🥑 Fat: ${day.totals.fat}g\n\n` +
      `📝 Meals:\n` +
      day.meals.map(m => `- [${m.meal_type || 'Meal'}] ${m.food}: ${m.calories} kcal (P:${m.protein}g, C:${m.carbs}g, F:${m.fat}g)`).join('\n') +
      (day.date === new Date().toISOString().split('T')[0] && data.daily_summary ? `\n\n💡 AI Note: ${data.daily_summary}` : '');

    navigator.clipboard.writeText(text);
    setCopiedDay(day.date);
    setTimeout(() => setCopiedDay(null), 2000);
  };

  const progress = Math.min((data.consumed / data.target) * 100, 100);

  if (view === 'admin' && adminData) return (
    <div className="min-h-screen bg-[#0F172A] text-slate-100 p-6">
      <div className="flex justify-between items-center mb-10">
        <div>
          <h1 className="text-2xl font-black tracking-tight">Admin Dashboard</h1>
          <p className="text-slate-500 text-xs font-bold uppercase tracking-widest">System Overview</p>
        </div>
        <button onClick={() => setView('dashboard')} className="px-4 py-2 bg-slate-800 rounded-xl text-xs font-bold">BACK TO APP</button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-10">
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-[32px]">
          <Users className="text-indigo-500 mb-2" size={24} />
          <span className="block text-3xl font-black">{adminData.total_users}</span>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Total Users</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-[32px]">
          <BarChart3 className="text-emerald-500 mb-2" size={24} />
          <span className="block text-3xl font-black">{adminData.total_meals}</span>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Total Logs</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-[32px]">
          <Flame className="text-amber-500 mb-2" size={24} />
          <span className="block text-3xl font-black">{adminData.meals_today}</span>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Logs Today</span>
        </div>
      </div>

      <h2 className="text-lg font-bold mb-6 flex items-center gap-2"><Users size={20} className="text-indigo-500"/> User Directory</h2>
      <div className="bg-slate-900 border border-slate-800 rounded-[32px] overflow-hidden mb-10">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-800/50 text-[10px] font-black uppercase text-slate-500 tracking-widest">
            <tr>
              <th className="px-6 py-4">Name</th>
              <th className="px-6 py-4">Email</th>
              <th className="px-6 py-4 text-center">Logs</th>
              <th className="px-6 py-4">Last Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {adminData.users.map(u => (
              <tr key={u.id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-6 py-4 font-bold">{u.name}</td>
                <td className="px-6 py-4 text-slate-400">{u.email}</td>
                <td className="px-6 py-4 text-center font-black text-indigo-400">{u.meal_count}</td>
                <td className="px-6 py-4 text-xs text-slate-500">{new Date(u.last_active).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="text-lg font-bold mb-6 flex items-center gap-2"><ListTodo size={20} className="text-emerald-500"/> Recent Activity</h2>
      <div className="space-y-4">
        {adminData.recent_logs.map(log => (
          <div 
            key={log.id} 
            onClick={() => setSelectedMeal(log)}
            className="bg-slate-900 border border-slate-800 p-4 rounded-2xl flex justify-between items-center cursor-pointer hover:bg-slate-800 transition-all hover:border-indigo-500/50 group"
          >
            <div>
              <p className="text-xs font-black text-indigo-500 uppercase tracking-tighter group-hover:text-indigo-400 transition-colors">{log.user}</p>
              <p className="font-bold text-slate-200">{log.food}</p>
              <p className="text-[10px] text-slate-500">{new Date(log.time).toLocaleString()}</p>
            </div>
            <div className="text-right flex flex-col items-end gap-2">
              <div className="text-right">
                <p className="font-black text-white leading-none">{log.calories}</p>
                <p className="text-[8px] font-bold text-slate-500 uppercase">kcal</p>
              </div>
              {log.has_image && <span className="text-[8px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded uppercase font-black border border-emerald-500/20">Image ✓</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  if (view === 'verify') return (
    <div className="min-h-screen bg-[#0F172A] text-slate-100 flex flex-col justify-center px-6 py-12">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <h1 className="text-sm font-black tracking-[0.4em] text-indigo-500 mb-6 uppercase opacity-80">VERIFICATION</h1>
        <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 py-10 px-8 rounded-[40px] shadow-2xl">
          {authError ? (
            <>
              <div className="text-red-500 mb-6 font-bold">{authError}</div>
              <button onClick={() => window.location.href = '/'} className="text-indigo-400 font-bold underline">Back to Login</button>
            </>
          ) : (
            <div className="flex flex-col items-center">
              <Loader2 className="animate-spin text-indigo-500 mb-4" size={32} />
              <p className="font-bold">Verifying your email...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  if (view === 'loading') return (
    <div className="h-screen bg-slate-950 flex items-center justify-center">
      <Loader2 className="animate-spin text-indigo-500" size={32} />
    </div>
  );

  if (view === 'login' || view === 'register') return (
    <div className="min-h-screen bg-[#0F172A] text-slate-100 flex flex-col justify-center px-6 py-12">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-10">
        <h1 className="text-sm font-black tracking-[0.4em] text-indigo-500 mb-6 uppercase opacity-80">FUEL</h1>
        <div className="w-24 h-24 bg-[#0F172A] rounded-[32px] flex items-center justify-center mx-auto mb-8 shadow-2xl overflow-hidden border-2 border-indigo-500/30">
          <img src="/logo.png" className="w-full h-full object-cover" alt="Fuel Logo" />
        </div>
        <h2 className="text-xl font-bold tracking-tight text-white mb-1">
          {view === 'login' ? 'Welcome Back' : 'Create Account'}
        </h2>
        <p className="text-sm text-slate-400 font-medium">
          {view === 'login' ? 'Sign in to track your fitness goals' : 'Start your health journey today'}
        </p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 py-10 px-8 rounded-[40px] shadow-2xl">
          <form className="space-y-6" onSubmit={view === 'login' ? handleLogin : handleRegister}>
            {view === 'register' && (
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Full Name</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                    <UserIcon size={18} />
                  </div>
                  <input
                    type="text" required
                    value={name} onChange={(e) => setName(e.target.value)}
                    className="block w-full pl-12 pr-4 py-4 bg-slate-800/50 border border-slate-700 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                    placeholder="Enter your name"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Email Address</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                  <Mail size={18} />
                </div>
                <input
                  type="email" required
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  className="block w-full pl-12 pr-4 py-4 bg-slate-800/50 border border-slate-700 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  placeholder="name@example.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Password</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                  <Lock size={18} />
                </div>
                <input
                  type="password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="block w-full pl-12 pr-4 py-4 bg-slate-800/50 border border-slate-700 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {authError && (
              <div className="bg-red-500/10 border border-red-500/50 text-red-500 text-xs font-bold p-4 rounded-xl text-center">
                {authError}
              </div>
            )}

            {telegramIdFromUrl && view === 'register' && (
              <div className="bg-emerald-500/10 border border-emerald-500/50 text-emerald-400 text-[10px] font-bold p-3 rounded-xl text-center uppercase tracking-tighter">
                ✅ Telegram Account Detected (ID: {telegramIdFromUrl})
              </div>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full flex justify-center items-center py-4 px-4 border border-transparent rounded-2xl shadow-lg text-sm font-black text-white bg-indigo-600 hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-all active:scale-95 disabled:opacity-50"
            >
              {loading ? <Loader2 className="animate-spin" size={20} /> : (view === 'login' ? 'SIGN IN' : 'CREATE ACCOUNT')}
            </button>
          </form>

          <div className="mt-8 text-center">
            <button
              onClick={() => setView(view === 'login' ? 'register' : 'login')}
              className="text-sm font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              {view === 'login' ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#0F172A] text-slate-100 font-sans pb-32">
      <input 
        type="file" 
        accept="image/*" 
        multiple
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden" 
      />

      {/* Glass Header */}
      <div className="sticky top-0 z-20 backdrop-blur-xl bg-slate-900/80 px-6 py-4 border-b border-slate-800 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#0F172A] rounded-xl flex items-center justify-center shadow-lg overflow-hidden border border-indigo-500/20">
             <img src="/logo.png" className="w-full h-full object-cover" alt="Fuel Logo" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight">
              {isPublicView ? `${data.user_name}'s Fuel` : `Hi, ${user?.name || 'User'}`}
            </h1>
          </div>
        </div>
        {!isPublicView && (
          <div className="flex gap-2">
            {user?.email === 'jhbong84@gmail.com' && (
              <button 
                onClick={fetchAdminStats}
                className="p-2.5 bg-indigo-500/10 rounded-xl text-indigo-400 hover:bg-indigo-500 hover:text-white transition-all"
              >
                <ShieldAlert size={20} />
              </button>
            )}
            <button 
              onClick={() => setShowSettings(true)}
              className="p-2.5 bg-slate-800/50 rounded-xl text-slate-400 hover:text-white transition-colors"
            >
              <Settings size={20} />
            </button>
            <button 
              onClick={handleLogout}
              className="p-2.5 bg-slate-800/50 rounded-xl text-slate-400 hover:text-red-400 transition-colors"
            >
              <LogOut size={20} />
            </button>
          </div>
        )}
      </div>

      <div className="px-6 py-8">
        {/* Modern Ring Progress */}
        <div className="flex flex-col items-center mb-10">
          <div className="relative flex justify-center items-center w-56 h-56">
            <svg className="w-full h-full -rotate-90">
              <circle cx="112" cy="112" r="95" fill="transparent" stroke="#1E293B" strokeWidth="12" />
              <circle
                cx="112" cy="112" r="95"
                fill="transparent"
                stroke="url(#gradient)"
                strokeWidth="14"
                strokeDasharray={596}
                strokeDashoffset={596 - (596 * progress) / 100}
                strokeLinecap="round"
                className="transition-all duration-1000"
              />
              <defs>
                <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#6366f1" />
                  <stop offset="100%" stopColor="#a855f7" />
                </linearGradient>
              </defs>
            </svg>
            <div className="absolute text-center">
              <span className="block text-5xl font-black text-white tracking-tighter">{data.consumed}</span>
              <span className="text-[10px] uppercase font-bold text-slate-500 tracking-[0.2em]">Calories</span>
            </div>
          </div>
          <div className="mt-4 flex gap-2 text-xs font-bold text-slate-400 bg-slate-800/50 px-4 py-2 rounded-full border border-slate-700 shadow-sm">
             <span>TARGET: {data.target}</span>
             <span className="text-slate-600">|</span>
             <span className="text-indigo-400">LEFT: {Math.max(data.target - data.consumed, 0)}</span>
          </div>
          
          {/* Todays Macros */}
          <div className="mt-6 flex gap-4 w-full max-w-sm justify-between">
            <div className="flex-1 bg-slate-900/50 p-3 rounded-2xl border border-slate-800 text-center">
              <span className="block text-indigo-400 text-lg font-black">{data.protein}g</span>
              <span className="text-[8px] uppercase font-bold text-slate-500">Protein</span>
            </div>
            <div className="flex-1 bg-slate-900/50 p-3 rounded-2xl border border-slate-800 text-center">
              <span className="block text-emerald-400 text-lg font-black">{data.carbs}g</span>
              <span className="text-[8px] uppercase font-bold text-slate-500">Carbs</span>
            </div>
            <div className="flex-1 bg-slate-900/50 p-3 rounded-2xl border border-slate-800 text-center">
              <span className="block text-amber-400 text-lg font-black">{data.fat}g</span>
              <span className="text-[8px] uppercase font-bold text-slate-500">Fat</span>
            </div>
          </div>
        </div>

        {/* Daily Summary Note */}
        {data.daily_summary && (
          <div className="bg-indigo-600/10 border-l-4 border-indigo-500 p-6 rounded-2xl mb-8 relative overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-indigo-400">
                <Info size={16} />
                <h2 className="text-xs font-bold uppercase tracking-widest">Consumption Pattern</h2>
              </div>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed font-medium italic">
              "{data.daily_summary}"
            </p>
          </div>
        )}

        {/* 7-Day Trend Chart */}
        <div className="bg-slate-900/40 border border-slate-800 p-6 rounded-[32px] mb-8">
          <div className="flex justify-between items-center mb-6">
             <h2 className="text-sm font-bold text-slate-400 uppercase tracking-widest">7-Day Activity</h2>
             <div className="flex items-center gap-1 text-emerald-400 text-xs font-bold">
               <Flame size={12} /> Sync Active
             </div>
          </div>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.trend}>
                <defs>
                  <linearGradient id="colorAmt" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <Tooltip contentStyle={{ backgroundColor: '#1E293B', border: 'none', borderRadius: '12px' }} itemStyle={{ color: '#fff', fontSize: '12px' }} />
                <Area type="monotone" dataKey="amount" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorAmt)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Grouped Meal History */}
        <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
          <History size={20} className="text-indigo-500" /> Meal Journey
        </h2>
        
        <div className="space-y-10">
          {isRefreshing && (
            <div className="animate-pulse">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-20 h-5 bg-slate-800 rounded-full"></div>
                <div className="flex-1 h-[1px] bg-slate-800"></div>
              </div>
              <div className="bg-slate-900/50 border border-slate-800 p-4 rounded-[28px] flex items-center mb-4">
                <div className="w-20 h-20 bg-slate-800 rounded-2xl mr-4"></div>
                <div className="flex-1">
                  <div className="w-24 h-3 bg-slate-800 rounded mb-2"></div>
                  <div className="w-32 h-4 bg-slate-800 rounded"></div>
                </div>
              </div>
            </div>
          )}
          {data.grouped_history.length > 0 ? data.grouped_history.map((day) => (
            <div key={day.date} className="relative">
              {/* Date Header */}
              <div className="flex items-center gap-3 mb-4">
                <div className="px-4 py-1.5 bg-indigo-600 rounded-full text-[10px] font-black uppercase tracking-wider shadow-lg shadow-indigo-500/20">
                  {day.display_date}
                </div>
                <div className="flex-1 h-[1px] bg-slate-800"></div>
                {!isPublicView && (
                  <button 
                    onClick={() => exportDay(day)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-800 text-[10px] font-bold transition-all ${copiedDay === day.date ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' : 'text-slate-400 hover:text-white bg-slate-900/50'}`}
                  >
                    {copiedDay === day.date ? <><Check size={12} /> COPIED</> : <><Share2 size={12} /> EXPORT</>}
                  </button>
                )}
              </div>

              {/* Day Stats Recap */}
              <div className="flex gap-3 mb-4 px-2 text-[10px] font-black text-slate-500 uppercase tracking-tighter">
                <span>{day.totals.calories} kcal</span>
                <span>P:{day.totals.protein}g</span>
                <span>C:{day.totals.carbs}g</span>
                <span>F:{day.totals.fat}g</span>
              </div>

              {/* Daily Consumption Pattern (Past) */}
              {day.ai_summary && day.display_date !== "Today" && (
                <div className="mt-4 mb-6 bg-indigo-600/10 border-l-4 border-indigo-500 p-5 rounded-2xl relative overflow-hidden">
                  <div className="flex items-center gap-2 mb-2 text-indigo-400">
                    <Info size={14} />
                    <h2 className="text-[10px] font-black uppercase tracking-widest">Consumption Pattern</h2>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed font-medium italic">
                    "{day.ai_summary}"
                  </p>
                </div>
              )}

              {/* Meals for this day */}
              <div className="space-y-4">
                {day.meals.map((meal) => (
                  <div 
                    key={meal.id} 
                    onClick={() => setSelectedMeal(meal)}
                    className="group bg-slate-900/50 border border-slate-800 p-4 rounded-[28px] flex items-center transition-all hover:bg-slate-800/60 hover:border-slate-700 cursor-pointer"
                  >
                    <div className="w-20 h-20 rounded-2xl overflow-hidden mr-4 border-2 border-slate-800 shadow-xl shrink-0 bg-slate-800 flex items-center justify-center relative">
                      {meal.images && meal.images.length > 0 ? (
                        <>
                          <img src={meal.images[0]} alt={meal.food} className="w-full h-full object-cover" />
                          {meal.images.length > 1 && (
                            <div className="absolute bottom-1 right-1 bg-indigo-600/90 backdrop-blur-sm text-white text-[8px] font-black px-1.5 py-0.5 rounded-md shadow-lg border border-indigo-400">
                              +{meal.images.length - 1}
                            </div>
                          )}
                        </>
                      ) : (
                        <Utensils className="text-slate-600" size={24} />
                      )}
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <Maximize2 className="text-white" size={20} />
                      </div>
                    </div>
                    <div className="flex-1 min-w-0 pr-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[8px] font-black uppercase px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded-md border border-slate-700">{meal.meal_type || 'Meal'}</span>
                        <h3 className="font-bold text-slate-100 text-base truncate">{meal.food}</h3>
                      </div>
                      
                      {/* Meal Item Breakdown */}
                      {meal.items && meal.items.length > 0 && (
                        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 mb-2">
                          {meal.items.map((item, idx) => (
                            <div key={idx} className="flex items-center gap-1 text-[10px] font-medium text-slate-400">
                              <span className="text-indigo-400 font-bold">{item.portion}x</span>
                              <span className="truncate max-w-[100px]">{item.name}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="flex items-center gap-2 mt-1 mb-2">
                        <Clock size={10} className="text-slate-500" />
                        <span className="text-[10px] text-slate-500 font-bold uppercase">
                          {new Date(meal.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <div className="flex gap-2">
                        <span className="px-2 py-0.5 bg-indigo-500/10 text-indigo-400 rounded-md text-[9px] font-black border border-indigo-500/20">P:{meal.protein}g</span>
                        <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded-md text-[9px] font-black border border-emerald-500/20">C:{meal.carbs}g</span>
                        <span className="px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded-md text-[9px] font-black border border-amber-500/20">F:{meal.fat}g</span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-3 shrink-0">
                      <div className="text-right">
                        <span className="block text-lg font-black text-white leading-none">{meal.calories}</span>
                        <span className="text-[9px] text-indigo-500 font-black uppercase tracking-tighter">kcal</span>
                      </div>
                      {!isPublicView && (
                        <button 
                          onClick={(e) => { e.stopPropagation(); deleteMeal(meal.id); }}
                          className="p-2 text-slate-700 hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Daily Trainer Feedback */}
              {(day.trainer_feedback || isPublicView) && (
                <div className="mt-6 bg-indigo-500/10 p-5 rounded-[28px] border border-indigo-500/20 shadow-xl shadow-indigo-500/5">
                  <div className="flex items-center gap-2 mb-3 text-indigo-400">
                    <Utensils size={14} />
                    <span className="text-[10px] font-black uppercase tracking-widest">Daily Trainer Feedback</span>
                  </div>
                  {isPublicView ? (
                    <div className="flex flex-col gap-3">
                      <textarea
                        className="w-full bg-slate-950/50 border border-slate-800 rounded-2xl p-4 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-all min-h-[80px] resize-none"
                        placeholder={`Provide feedback for ${day.display_date}...`}
                        defaultValue={day.trainer_feedback || ''}
                        onBlur={(e) => submitDailyFeedback(day.date, e.target.value)}
                      />
                      <p className="text-[8px] text-slate-500 text-center font-bold uppercase tracking-tighter opacity-60">Saves when you tap out</p>
                    </div>
                  ) : (
                    <p className="text-sm text-indigo-200 font-medium italic leading-relaxed">
                      "{day.trainer_feedback || "No feedback yet for today."}"
                    </p>
                  )}
                </div>
              )}
            </div>
          )) : (
            <div className="text-center py-12 text-slate-500 text-sm border-2 border-dashed border-slate-800 rounded-[32px]">
              No meals logged yet.
            </div>
          )}
        </div>
      </div>

      {/* Modern Bottom Bar */}
      {!isPublicView && (
        <div className="fixed bottom-8 left-6 right-6 z-50 flex justify-center">
          <div className="bg-slate-900/90 backdrop-blur-2xl border border-slate-800/50 h-20 px-10 rounded-full shadow-2xl flex justify-between items-center w-full max-w-md relative">
            <button className="text-indigo-500"><History size={24} /></button>
            
            <div className="relative">
              <button 
                onClick={handleOpenUpload}
                disabled={uploading}
                className={`relative w-16 h-16 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-500/20 flex items-center justify-center text-white -mt-16 border-4 border-slate-900 transition-all active:scale-95 ${uploading ? 'opacity-50' : 'hover:bg-indigo-500'}`}
              >
                {uploading ? <Loader2 className="animate-spin" size={28} /> : <Plus size={28} />}
              </button>
            </div>

            <button className="text-slate-600" onClick={() => setShowSettings(true)}><Settings size={24} /></button>
          </div>
        </div>
      )}

      {/* Meal Detail Modal (Click to Enlarged View) */}
      {selectedMeal && (
        <div 
          onClick={() => setSelectedMeal(null)}
          className="fixed inset-0 z-[70] bg-slate-950/95 backdrop-blur-xl flex items-center justify-center p-6 cursor-pointer"
        >
          <div 
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg bg-slate-900 rounded-[40px] border border-slate-800 overflow-hidden animate-in zoom-in duration-300 shadow-2xl max-h-[90vh] overflow-y-auto cursor-default"
          >
            <div className="relative w-full bg-slate-950 overflow-hidden">
              <div className="flex overflow-x-auto snap-x snap-mandatory hide-scrollbar">
                {selectedMeal.images && selectedMeal.images.length > 0 ? (
                  selectedMeal.images.map((img, i) => (
                    <div key={i} className="min-w-full snap-center relative flex items-center justify-center overflow-hidden">
                      {/* Blurred Background Layer */}
                      <img src={img} className="absolute inset-0 w-full h-full object-cover blur-2xl opacity-30 scale-110" />
                      {/* Main Image Layer - No fixed aspect ratio, using max-height */}
                      <img 
                        src={img} 
                        className="relative z-10 w-full max-h-[70vh] object-contain shadow-2xl" 
                        style={{ minHeight: '300px' }}
                      />
                    </div>
                  ))
                ) : (
                  <div className="w-full aspect-video flex items-center justify-center">
                    <Utensils className="text-slate-700" size={48} />
                  </div>
                )}
              </div>
              
              {selectedMeal.images?.length > 1 && (
                <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-1.5 px-3 py-1.5 bg-black/30 backdrop-blur-md rounded-full">
                  {selectedMeal.images.map((_, i) => (
                    <div key={i} className="w-1.5 h-1.5 rounded-full bg-white/50"></div>
                  ))}
                </div>
              )}

              <button 
                onClick={() => setSelectedMeal(null)}
                className="absolute top-6 right-6 p-3 bg-black/50 text-white rounded-full backdrop-blur-md hover:bg-black transition-colors z-[80]"
              >
                <X size={24} />
              </button>
            </div>
            
            <div className="p-8">
              <div className="flex justify-between items-start mb-6">
                <div className="flex-1 min-w-0 pr-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-black uppercase px-2 py-1 bg-slate-800 text-indigo-400 rounded-lg border border-slate-700">{selectedMeal.meal_type || 'Meal'}</span>
                  </div>
                  <h2 className="text-2xl font-black text-white leading-tight mb-2 tracking-tight break-words">{selectedMeal.food}</h2>
                  
                  {/* Item Breakdown in Modal */}
                  {selectedMeal.items && selectedMeal.items.length > 0 && (
                    <div className="flex flex-wrap gap-3 mb-4">
                      {selectedMeal.items.map((item, idx) => (
                        <div key={idx} className="px-3 py-1 bg-slate-800 rounded-xl border border-slate-700 flex items-center gap-2 shadow-sm">
                          <span className="text-indigo-400 font-black text-xs">{item.portion}x</span>
                          <span className="text-xs font-bold text-slate-300">{item.name}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center gap-2 text-slate-500">
                    <Clock size={14} />
                    <span className="text-xs font-bold uppercase">{new Date(selectedMeal.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <span className="block text-4xl font-black text-indigo-500 tracking-tighter">{selectedMeal.calories}</span>
                  <span className="text-xs font-black text-slate-500 uppercase tracking-widest">KCAL TOTAL</span>
                </div>
              </div>

              {selectedMeal.description && (
                <div className="bg-slate-800/50 p-5 rounded-3xl mb-8 border border-slate-700/50">
                  <p className="text-sm text-slate-300 font-medium italic break-words">"{selectedMeal.description}"</p>
                </div>
              )}

              <div className="grid grid-cols-3 gap-4 mb-8">
                <div className="bg-indigo-500/10 border border-indigo-500/20 p-4 rounded-3xl text-center">
                  <span className="block text-xl font-black text-indigo-400">{selectedMeal.protein}g</span>
                  <span className="text-[10px] font-black text-slate-500 uppercase">Protein</span>
                </div>
                <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 rounded-3xl text-center">
                  <span className="block text-xl font-black text-emerald-400">{selectedMeal.carbs}g</span>
                  <span className="text-[10px] font-black text-slate-500 uppercase">Carbs</span>
                </div>
                <div className="bg-amber-500/10 border border-amber-500/20 p-4 rounded-3xl text-center">
                  <span className="block text-xl font-black text-amber-400">{selectedMeal.fat}g</span>
                  <span className="text-[10px] font-black text-slate-500 uppercase">Fat</span>
                </div>
              </div>

              {!isPublicView && (
                <button 
                  onClick={() => deleteMeal(selectedMeal.id)}
                  className="w-full py-5 bg-red-500/10 hover:bg-red-500/20 text-red-500 font-black rounded-3xl transition-all border border-red-500/20 uppercase text-xs tracking-widest"
                >
                  Delete Entry
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Enhanced Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-[60] bg-slate-950/95 backdrop-blur-md flex items-end sm:items-center justify-center overflow-y-auto">
          <div className="w-full max-w-md bg-slate-900 rounded-t-[40px] sm:rounded-[40px] p-8 border border-slate-800 animate-in slide-in-from-bottom sm:zoom-in duration-300 shadow-2xl my-auto">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-2xl font-black tracking-tight">Log a Meal</h2>
              <button onClick={() => setShowUploadModal(false)} className="p-2 text-slate-500"><X /></button>
            </div>
            
            <div className="space-y-6">
              {/* Meal Type Selection */}
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] block mb-3">Meal Type</label>
                <div className="grid grid-cols-4 gap-2">
                  {mealTypes.map((type) => (
                    <button
                      key={type.name}
                      onClick={() => setMealType(type.name)}
                      className={`flex flex-col items-center justify-center py-3 rounded-2xl border-2 transition-all ${mealType === type.name ? 'bg-indigo-600 border-indigo-500 text-white' : 'bg-slate-800/50 border-slate-800 text-slate-400 hover:border-slate-700'}`}
                    >
                      {type.icon}
                      <span className="text-[8px] font-bold mt-1 uppercase">{type.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Photo Upload Section */}
              <div>
                <div className="flex justify-between items-end mb-3">
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] block">Food Photos</label>
                  <span className="text-[8px] font-bold text-indigo-400 uppercase bg-indigo-500/10 px-2 py-0.5 rounded-md border border-indigo-500/20">Tip: Include a fork for scale</span>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {previews.map((src, idx) => (
                    <div key={idx} className="relative aspect-square rounded-2xl overflow-hidden border-2 border-slate-800">
                      <img src={src} className="w-full h-full object-cover" />
                      <button 
                        onClick={() => removeFile(idx)}
                        className="absolute top-1 right-1 bg-red-500 text-white rounded-full p-1 shadow-lg"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                  <button 
                    onClick={() => fileInputRef.current.click()}
                    className="aspect-square rounded-2xl border-2 border-dashed border-slate-800 flex flex-col items-center justify-center text-slate-500 hover:text-indigo-400 hover:border-indigo-500 transition-all"
                  >
                    <Upload size={20} />
                    <span className="text-[8px] font-bold mt-1 uppercase">Add Photo</span>
                  </button>
                </div>
              </div>

              {/* Description Section */}
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] block mb-3">What did you eat?</label>
                <textarea 
                  value={mealDescription}
                  onChange={(e) => setMealDescription(e.target.value)}
                  placeholder="e.g. 2 pieces of fried chicken, some coleslaw and a small mashed potato."
                  className="w-full bg-slate-800/50 border-2 border-slate-800 rounded-3xl px-6 py-4 text-sm font-medium text-white focus:outline-none focus:border-indigo-600 transition-all min-h-[100px] resize-none placeholder:text-slate-600"
                />
              </div>
              
              <button 
                onClick={handleUploadSubmit}
                disabled={uploading || (!mealDescription && selectedFiles.length === 0)}
                className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:hover:bg-indigo-600 text-white font-black py-6 rounded-[32px] flex items-center justify-center gap-3 transition-all shadow-lg shadow-indigo-900/20"
              >
                {uploading ? <Loader2 className="animate-spin" size={24} /> : <><Save size={24} /> SAVE MEAL</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 z-[60] bg-slate-950/90 backdrop-blur-md flex items-end sm:items-center justify-center">
          <div className="w-full max-w-md bg-slate-900 rounded-t-[40px] sm:rounded-[40px] p-10 border border-slate-800 animate-in slide-in-from-bottom sm:zoom-in duration-300 shadow-2xl">
            <div className="flex justify-between items-center mb-8">
              <h2 className="text-2xl font-black tracking-tight">Profile Settings</h2>
              <button onClick={() => setShowSettings(false)} className="p-2 text-slate-500"><X /></button>
            </div>
            <div className="space-y-8">
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] block mb-4">Target Calories (kcal)</label>
                <input 
                  type="number" 
                  value={newTarget}
                  onChange={(e) => setNewTarget(e.target.value)}
                  className="w-full bg-slate-800/50 border-2 border-slate-800 rounded-3xl px-8 py-6 text-4xl font-black text-white focus:outline-none focus:border-indigo-600 transition-all"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] block mb-4">Update Password</label>
                <input 
                  type="password" 
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Leave blank to keep current"
                  className="w-full bg-slate-800/50 border-2 border-slate-800 rounded-3xl px-8 py-4 text-xl font-bold text-white focus:outline-none focus:border-indigo-600 transition-all placeholder:text-slate-600"
                />
              </div>
              <button 
                onClick={saveSettings}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-black py-6 rounded-[32px] flex items-center justify-center gap-3 transition-all shadow-lg shadow-indigo-900/20"
              >
                <Save size={24} /> SAVE CHANGES
              </button>

              <div className="pt-8 mt-8 border-t border-slate-800">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h3 className="text-sm font-bold text-white uppercase tracking-widest">Fuel Share</h3>
                    <p className="text-[10px] text-slate-500 font-medium">Allow unguessable public read-only access</p>
                  </div>
                  <button 
                    onClick={toggleShare}
                    className={`w-12 h-6 rounded-full transition-all relative ${shareConfig.enabled ? 'bg-indigo-600' : 'bg-slate-700'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${shareConfig.enabled ? 'left-7' : 'left-1'}`}></div>
                  </button>
                </div>

                {shareConfig.enabled && (
                  <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                    <div className="p-4 bg-slate-950/50 border border-slate-800 rounded-2xl">
                      <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-2">Your Secure Link</p>
                      <div className="flex items-center gap-2">
                        <input 
                          readOnly 
                          value={`${window.location.origin}/share/${shareConfig.token}`}
                          className="flex-1 bg-transparent text-xs text-slate-400 truncate outline-none"
                        />
                        <button 
                          onClick={() => {
                            navigator.clipboard.writeText(`${window.location.origin}/share/${shareConfig.token}`);
                            alert("Link copied!");
                          }}
                          className="p-2 bg-slate-800 rounded-lg text-indigo-400 hover:bg-indigo-500 hover:text-white transition-all"
                        >
                          <Copy size={14} />
                        </button>
                      </div>
                    </div>
                    <button 
                      onClick={resetShareToken}
                      className="w-full py-3 border border-slate-800 text-slate-500 text-[10px] font-black uppercase tracking-widest rounded-2xl hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/20 transition-all"
                    >
                      Reset & Revoke Link
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
