import axios from 'axios';

const http = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000',
  timeout: 60000,
});

// 请求拦截器：自动携带 token
http.interceptors.request.use(
  (config) => {
    // 从 localStorage 获取 token
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：处理错误
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error);

    // 401 未授权：跳转到登录页
    if (error.response?.status === 401) {
      // 清除本地 token
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');

      // 如果不是在登录页，则跳转到登录页
      if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

export default http;
