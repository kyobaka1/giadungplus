// background.js - Service Worker for GDP Media Tracker Extension

// Tracked domains/keywords
const TRACKED_KEYWORDS = ['tmall', 'douyin', '1688', 'taobao', 'xiaohongshu', 'pinterest'];

// Check if URL should be tracked
function shouldTrackUrl(url) {
  if (!url) return false;
  const urlLower = url.toLowerCase();
  return TRACKED_KEYWORDS.some(keyword => urlLower.includes(keyword));
}

// Send media data to backend
async function sendMediaToBackend(data) {
  try {
    const result = await chrome.storage.sync.get(['apiUrl', 'userName']);
    let apiUrl = result.apiUrl || 'http://127.0.0.1:8000/marketing/tools/get-videos/api/';
    const userName = result.userName || 'anonymous';
    
    // Normalize API URL - remove trailing slash, then add /api/ if needed
    apiUrl = apiUrl.trim();
    if (apiUrl.endsWith('/')) {
      apiUrl = apiUrl.slice(0, -1);
    }
    // If URL doesn't end with /api/, add it
    if (!apiUrl.endsWith('/api')) {
      if (apiUrl.endsWith('/api/')) {
        // Already has /api/, do nothing
      } else {
        // Add /api/ to the end
        apiUrl = apiUrl + '/api/';
      }
    } else {
      // Ends with /api, add trailing slash
      apiUrl = apiUrl + '/';
    }
    
    if (!userName || userName === 'anonymous') {
      console.warn('[GDP Media Tracker Background] ⚠️ Username not configured. Please set it in options.');
      return;
    }
    
    const payload = {
      ...data,
      user_name: userName
    };
    
    console.log('[GDP Media Tracker Background] ========== SENDING TO BACKEND ==========');
    console.log('[GDP Media Tracker Background] API URL:', apiUrl);
    console.log('[GDP Media Tracker Background] Username:', userName);
    console.log('[GDP Media Tracker Background] Payload:', {
      ...payload,
      media_url: payload.media_url ? payload.media_url.substring(0, 200) : 'no media_url'
    });
    
    // Test if server is reachable first (optional, but helpful for debugging)
    try {
      const testResponse = await fetch(apiUrl.replace('/api/', '/'), { 
        method: 'GET',
        mode: 'no-cors' // Just to test connectivity
      });
      console.log('[GDP Media Tracker Background] Server connectivity test passed');
    } catch (testError) {
      console.warn('[GDP Media Tracker Background] ⚠️ Server connectivity test failed (this is OK, continuing anyway)');
    }
    
    console.log('[GDP Media Tracker Background] Making fetch request to:', apiUrl);
    
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      mode: 'cors', // Explicitly set CORS mode
      credentials: 'omit' // Don't send cookies
    });
    
    console.log('[GDP Media Tracker Background] ✅ Response received!');
    console.log('[GDP Media Tracker Background] Response status:', response.status);
    console.log('[GDP Media Tracker Background] Response statusText:', response.statusText);
    console.log('[GDP Media Tracker Background] Response headers:', Object.fromEntries(response.headers.entries()));
    
    if (response.ok) {
      const result = await response.json();
      console.log('[GDP Media Tracker Background] ✅ Media tracked successfully:', result);
    } else {
      const errorText = await response.text();
      console.error('[GDP Media Tracker Background] ❌ Failed to track media. Status:', response.status);
      console.error('[GDP Media Tracker Background] Error response:', errorText);
    }
  } catch (error) {
    console.error('[GDP Media Tracker Background] ❌ Exception sending media to backend:');
    console.error('[GDP Media Tracker Background] Error name:', error.name);
    console.error('[GDP Media Tracker Background] Error message:', error.message);
    console.error('[GDP Media Tracker Background] Error stack:', error.stack);
    
    // Check if it's a network error
    if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError') || error.name === 'TypeError') {
      console.error('[GDP Media Tracker Background] ⚠️ ========== NETWORK ERROR ==========');
      console.error('[GDP Media Tracker Background] ⚠️ Possible causes:');
      console.error('[GDP Media Tracker Background] ⚠️ 1. Django server not running (check terminal)');
      console.error('[GDP Media Tracker Background] ⚠️ 2. Wrong API URL (check extension options)');
      console.error('[GDP Media Tracker Background] ⚠️ 3. Service worker cannot access 127.0.0.1 - try localhost instead');
      console.error('[GDP Media Tracker Background] ⚠️');
      console.error('[GDP Media Tracker Background] ⚠️ Current API URL:', apiUrl);
      console.error('[GDP Media Tracker Background] ⚠️ Try changing to: http://localhost:8000/marketing/tools/get-videos/api/');
      console.error('[GDP Media Tracker Background] ⚠️ Or if using HTTPS: https://127.0.0.1:8000/marketing/tools/get-videos/api/');
    }
  }
}

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[GDP Media Tracker Background] Received message:', message);
  
  if (message.type === 'MEDIA_DETECTED') {
    const tab = sender.tab;
    console.log('[GDP Media Tracker Background] Tab info:', {
      url: tab ? tab.url : 'no tab',
      title: tab ? tab.title : 'no title',
      id: tab ? tab.id : 'no id'
    });
    
    if (!tab) {
      console.error('[GDP Media Tracker Background] No tab information available');
      sendResponse({ success: false, reason: 'No tab information' });
      return true;
    }
    
    if (!shouldTrackUrl(tab.url)) {
      console.warn('[GDP Media Tracker Background] URL not in tracked list:', tab.url);
      sendResponse({ success: false, reason: 'URL not in tracked list' });
      return true;
    }
    
    console.log('[GDP Media Tracker Background] ✅ URL is tracked, preparing to send to backend...');
    
    const mediaData = {
      page_url: tab.url,
      page_title: tab.title || '',
      media_url: message.mediaUrl,
      file_extension: message.fileExtension,
      mime_type: message.mimeType || '',
      source_type: message.sourceType || 'video_tag',
      tab_id: tab.id,
      thumbnail_url: message.thumbnailUrl || ''
    };
    
    console.log('[GDP Media Tracker Background] Media data to send:', {
      ...mediaData,
      media_url: mediaData.media_url.substring(0, 200)
    });
    
    sendMediaToBackend(mediaData).then(() => {
      console.log('[GDP Media Tracker Background] ✅ Backend request completed');
      sendResponse({ success: true });
    }).catch((error) => {
      console.error('[GDP Media Tracker Background] ❌ Backend request failed:', error);
      sendResponse({ success: false, reason: error.message });
    });
    
    return true; // Keep channel open for async response
  } else {
    console.log('[GDP Media Tracker Background] Unknown message type:', message.type);
    sendResponse({ success: false, reason: 'Unknown message type' });
    return true;
  }
});

// Note: Network request monitoring via webRequest API is not used in Manifest V3
// Content script detection is the primary method for tracking media files
// The content script scans for video/audio elements and data attributes

// Listen for tab updates to track new pages
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && shouldTrackUrl(tab.url)) {
    // Content script will handle media detection on page load
    console.log('[GDP Media Tracker] Tracking page:', tab.url);
  }
});

