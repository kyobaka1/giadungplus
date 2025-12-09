// options.js - Options page script for GDP Media Tracker Extension

// Load saved settings
document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.sync.get(['userName', 'apiUrl'], (result) => {
    if (result.userName) {
      document.getElementById('userName').value = result.userName;
    }
    if (result.apiUrl) {
      document.getElementById('apiUrl').value = result.apiUrl;
    } else {
      // Set default API URL
      document.getElementById('apiUrl').value = 'http://127.0.0.1:8000/marketing/tools/get-videos/api/';
    }
  });
});

// Save settings
document.getElementById('settingsForm').addEventListener('submit', (e) => {
  e.preventDefault();
  
  const userName = document.getElementById('userName').value.trim();
  const apiUrl = document.getElementById('apiUrl').value.trim();
  
  if (!userName) {
    showStatus('Vui lòng nhập username!', 'error');
    return;
  }
  
  chrome.storage.sync.set({
    userName: userName,
    apiUrl: apiUrl || 'http://127.0.0.1:8000/marketing/tools/get-videos/api/'
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

