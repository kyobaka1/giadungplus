// options.js - Options page script for GDP Media Tracker Extension

// Default API URL (ẩn khỏi UI, tự động set)
const DEFAULT_API_URL = 'https://giadungplus.io.vn/marketing/tools/get-videos/api/';

// Load saved settings
document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.sync.get(['userName', 'apiUrl'], (result) => {
    if (result.userName) {
      document.getElementById('userName').value = result.userName;
    }
    
    // Luôn đảm bảo API URL được set (mặc định hoặc đã lưu)
    const apiUrl = result.apiUrl || DEFAULT_API_URL;
    
    // Lưu lại API URL nếu chưa có hoặc cần update
    if (!result.apiUrl || result.apiUrl !== DEFAULT_API_URL) {
      chrome.storage.sync.set({ apiUrl: DEFAULT_API_URL }, () => {
        console.log('[GDP Media Tracker Options] API URL set to:', DEFAULT_API_URL);
      });
    }
  });
});

// Save settings
document.getElementById('settingsForm').addEventListener('submit', (e) => {
  e.preventDefault();
  
  const userName = document.getElementById('userName').value.trim();
  
  if (!userName) {
    showStatus('Vui lòng nhập username!', 'error');
    return;
  }
  
  // Luôn dùng API URL mặc định (ẩn khỏi UI)
  chrome.storage.sync.set({
    userName: userName,
    apiUrl: DEFAULT_API_URL
  }, () => {
    if (chrome.runtime.lastError) {
      showStatus('Lỗi khi lưu cài đặt: ' + chrome.runtime.lastError.message, 'error');
    } else {
      showStatus('Đã lưu cài đặt thành công!', 'success');
    }
  });
});

// Show status message
function showStatus(message, type) {
  const statusEl = document.getElementById('status');
  statusEl.textContent = message;
  statusEl.className = 'status ' + type;
  
  // Auto hide after 3 seconds
  setTimeout(() => {
    statusEl.className = 'status';
  }, 3000);
}

