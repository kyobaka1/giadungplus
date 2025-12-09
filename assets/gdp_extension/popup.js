// popup.js - Popup script for GDP Media Tracker Extension

document.addEventListener('DOMContentLoaded', () => {
  // Load settings and update status
  chrome.storage.sync.get(['userName', 'apiUrl'], (result) => {
    const statusEl = document.getElementById('status');
    const statusValueEl = document.getElementById('statusValue');
    
    if (result.userName && result.userName !== 'anonymous') {
      statusEl.className = 'status active';
      statusValueEl.textContent = `Đang track với username: ${result.userName}`;
    } else {
      statusEl.className = 'status inactive';
      statusValueEl.textContent = 'Chưa cấu hình username. Vui lòng cài đặt!';
    }
  });
  
  // Get current tab URL to check if it's being tracked
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      const url = tabs[0].url.toLowerCase();
      const trackedKeywords = ['tmall', 'douyin', '1688', 'taobao', 'xiaohongshu', 'pinterest'];
      const isTracked = trackedKeywords.some(keyword => url.includes(keyword));
      
      if (isTracked) {
        const info = document.querySelector('.info');
        info.innerHTML = `<strong>✓ Trang này đang được track!</strong><br>${tabs[0].url}`;
        info.style.background = '#d4edda';
        info.style.color = '#155724';
      }
    }
  });
  
  // Open options page
  document.getElementById('openOptions').addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
  });
  
  // Open videos page
  document.getElementById('viewVideos').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.storage.sync.get(['apiUrl'], (result) => {
      const apiUrl = result.apiUrl || 'http://127.0.0.1:8000/marketing/tools/get-videos/api/';
      const baseUrl = apiUrl.replace('/api/', '');
      chrome.tabs.create({ url: baseUrl });
    });
  });
});

