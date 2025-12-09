// content.js - Content script for GDP Media Tracker Extension

// Tracked domains/keywords
const TRACKED_KEYWORDS = ['tmall', 'douyin', '1688', 'taobao', 'xiaohongshu', 'pinterest'];

// Tracked media URLs from network requests
const networkTrackedUrls = new Set();

// Check if current page should be tracked
function shouldTrackPage() {
  const url = window.location.href.toLowerCase();
  return TRACKED_KEYWORDS.some(keyword => url.includes(keyword));
}

// Extract file extension from URL
function getFileExtension(url) {
  if (!url || typeof url !== 'string') return null;
  
  // Try to match .mp3, .mp4, .mov in URL
  const match = url.match(/\.(mp3|mp4|mov)(\?|#|$)/i);
  if (match) {
    return match[1].toLowerCase();
  }
  
  // If no extension in URL, check if it's a known video/audio endpoint
  // Some sites use URLs like: https://example.com/video/123456 (no extension)
  // In this case, we might need to check mime type or other indicators
  // For now, return null if no extension found
  return null;
}

// Get thumbnail from video element
function getVideoThumbnail(video) {
  try {
    // Try to get poster attribute
    if (video.poster) return video.poster;
    
    // Try to capture current frame (requires video to be loaded)
    if (video.readyState >= 2) {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 320;
      canvas.height = video.videoHeight || 240;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL('image/jpeg', 0.8);
    }
  } catch (e) {
    console.warn('[GDP Media Tracker] Could not get video thumbnail:', e);
  }
  return null;
}

// Send media to background script
function sendMedia(mediaUrl, sourceType, mimeType, thumbnailUrl = null) {
  console.log('[GDP Media Tracker] sendMedia called with:', {
    mediaUrl: mediaUrl.substring(0, 200),
    sourceType: sourceType,
    mimeType: mimeType
  });
  
  const fileExtension = getFileExtension(mediaUrl);
  if (!fileExtension) {
    console.log('[GDP Media Tracker] Skipping URL (no valid extension):', mediaUrl.substring(0, 200));
    console.log('[GDP Media Tracker] URL does not match .mp3, .mp4, or .mov pattern');
    return;
  }
  
  console.log('[GDP Media Tracker] File extension detected:', fileExtension);
  
  // Normalize URL (remove fragments, clean up)
  let normalizedUrl = mediaUrl.split('#')[0].trim();
  
  console.log('[GDP Media Tracker] Preparing to send message to background script...');
  console.log('[GDP Media Tracker] Message payload:', {
    type: 'MEDIA_DETECTED',
    mediaUrl: normalizedUrl.substring(0, 200),
    fileExtension: fileExtension,
    mimeType: mimeType,
    sourceType: sourceType
  });
  
  chrome.runtime.sendMessage({
    type: 'MEDIA_DETECTED',
    mediaUrl: normalizedUrl,
    fileExtension: fileExtension,
    mimeType: mimeType,
    sourceType: sourceType,
    thumbnailUrl: thumbnailUrl
  }, (response) => {
    if (chrome.runtime.lastError) {
      console.error('[GDP Media Tracker] Error sending message to background:', chrome.runtime.lastError.message);
      return;
    }
    if (response && response.success) {
      console.log('[GDP Media Tracker] ✅ Message sent successfully to background script');
      console.log('[GDP Media Tracker] Response from background:', response);
    } else {
      console.warn('[GDP Media Tracker] ⚠️ Background script returned failure:', response);
    }
  });
}

// Tracked URLs to avoid duplicates
const trackedUrls = new Set();

// Scan for video and audio elements
function scanMediaElements() {
  if (!shouldTrackPage()) {
    console.log('[GDP Media Tracker] Page not tracked:', window.location.href);
    return;
  }
  
  console.log('[GDP Media Tracker] Scanning for media elements...');
  let foundCount = 0;
  
  // Find all video elements
  const videos = document.querySelectorAll('video');
  console.log(`[GDP Media Tracker] Found ${videos.length} video elements`);
  videos.forEach((video, index) => {
    console.log(`[GDP Media Tracker] Video ${index + 1}:`, {
      src: video.src,
      currentSrc: video.currentSrc,
      srcObject: video.srcObject ? 'has srcObject' : 'no srcObject',
      poster: video.poster,
      type: video.type
    });
    
    // Check main src
    if (video.src) {
      console.log(`[GDP Media Tracker] Video ${index + 1} has src:`, video.src.substring(0, 200));
      
      // Check if it's a blob or data URL
      if (video.src.startsWith('blob:') || video.src.startsWith('data:')) {
        console.log(`[GDP Media Tracker] Video ${index + 1} src is blob/data URL - cannot track`);
      } 
      // Check if already tracked
      else if (trackedUrls.has(video.src)) {
        console.log(`[GDP Media Tracker] Video ${index + 1} src already tracked`);
      }
      // Check if URL has valid extension
      else {
        const fileExt = getFileExtension(video.src);
        if (fileExt) {
          console.log(`[GDP Media Tracker] Video ${index + 1} src has valid extension: ${fileExt}`);
          const thumbnail = getVideoThumbnail(video);
          sendMedia(video.src, 'video_tag', video.type || 'video/mp4', thumbnail);
          trackedUrls.add(video.src);
          foundCount++;
        } else {
          console.log(`[GDP Media Tracker] Video ${index + 1} src has NO valid extension (.mp3/.mp4/.mov) in URL`);
          console.log(`[GDP Media Tracker] Video ${index + 1} src:`, video.src);
          console.log(`[GDP Media Tracker] Video ${index + 1} type:`, video.type);
          // Some sites use URLs without extension, but we can't track them without extension
        }
      }
    } else {
      console.log(`[GDP Media Tracker] Video ${index + 1} has NO src attribute`);
    }
    
    // Check currentSrc (actual playing source)
    if (video.currentSrc && video.currentSrc !== video.src) {
      console.log(`[GDP Media Tracker] Video ${index + 1} has currentSrc:`, video.currentSrc.substring(0, 200));
      if (!video.currentSrc.startsWith('blob:') && !video.currentSrc.startsWith('data:') && !trackedUrls.has(video.currentSrc)) {
        const thumbnail = getVideoThumbnail(video);
        sendMedia(video.currentSrc, 'video_tag', video.type || 'video/mp4', thumbnail);
        trackedUrls.add(video.currentSrc);
        foundCount++;
      } else {
        console.log(`[GDP Media Tracker] Video ${index + 1} currentSrc skipped (blob/data URL or already tracked)`);
      }
    }
    
    // Check srcObject (MediaStream or Blob)
    if (video.srcObject) {
      console.log(`[GDP Media Tracker] Video ${index + 1} has srcObject (MediaStream/Blob) - cannot extract URL`);
    }
    
    // Check source elements
    const sources = video.querySelectorAll('source');
    console.log(`[GDP Media Tracker] Video ${index + 1} has ${sources.length} source elements`);
    sources.forEach((source, srcIndex) => {
      console.log(`[GDP Media Tracker] Video ${index + 1} Source ${srcIndex + 1}:`, {
        src: source.src,
        type: source.type
      });
      if (source.src && !source.src.startsWith('blob:') && !source.src.startsWith('data:') && !trackedUrls.has(source.src)) {
        sendMedia(source.src, 'video_tag', source.type || 'video/mp4', null);
        trackedUrls.add(source.src);
        foundCount++;
      }
    });
  });
  
  // Find all audio elements
  const audios = document.querySelectorAll('audio');
  console.log(`[GDP Media Tracker] Found ${audios.length} audio elements`);
  audios.forEach(audio => {
    if (audio.src && !trackedUrls.has(audio.src)) {
      sendMedia(audio.src, 'audio_tag', audio.type || 'audio/mp3', null);
      trackedUrls.add(audio.src);
      foundCount++;
    }
    
    // Check source elements
    const sources = audio.querySelectorAll('source');
    sources.forEach(source => {
      if (source.src && !trackedUrls.has(source.src)) {
        sendMedia(source.src, 'audio_tag', source.type || 'audio/mp3', null);
        trackedUrls.add(source.src);
        foundCount++;
      }
    });
  });
  
  // Find video/audio URLs in data attributes
  const elementsWithMedia = document.querySelectorAll('[data-video], [data-audio], [data-src], [data-media], [data-url]');
  elementsWithMedia.forEach(el => {
    const mediaUrl = el.getAttribute('data-video') || 
                     el.getAttribute('data-audio') || 
                     el.getAttribute('data-src') ||
                     el.getAttribute('data-media') ||
                     el.getAttribute('data-url');
    if (mediaUrl && getFileExtension(mediaUrl) && !trackedUrls.has(mediaUrl)) {
      const sourceType = el.getAttribute('data-video') ? 'video_tag' : 'audio_tag';
      sendMedia(mediaUrl, sourceType, '', null);
      trackedUrls.add(mediaUrl);
      foundCount++;
    }
  });
  
  // Find URLs in style backgrounds (some sites embed video URLs in CSS)
  const styleElements = document.querySelectorAll('[style*="mp4"], [style*="mp3"], [style*="mov"]');
  styleElements.forEach(el => {
    const style = el.getAttribute('style') || '';
    const urlMatch = style.match(/url\(['"]?([^'"]+\.(mp4|mp3|mov)[^'"]*)/i);
    if (urlMatch && urlMatch[1] && !trackedUrls.has(urlMatch[1])) {
      sendMedia(urlMatch[1], 'video_tag', '', null);
      trackedUrls.add(urlMatch[1]);
      foundCount++;
    }
  });
  
  // Find in script tags (some sites have video URLs in JavaScript)
  const scripts = document.querySelectorAll('script[type="application/json"], script:not([src])');
  scripts.forEach(script => {
    try {
      const text = script.textContent || '';
      // Look for URLs with media extensions
      const urlRegex = /https?:\/\/[^\s"']+\.(mp4|mp3|mov)(\?[^\s"']*)?/gi;
      const matches = text.match(urlRegex);
      if (matches) {
        matches.forEach(url => {
          if (!trackedUrls.has(url)) {
            sendMedia(url, 'video_tag', '', null);
            trackedUrls.add(url);
            foundCount++;
          }
        });
      }
    } catch (e) {
      // Ignore JSON parse errors
    }
  });
  
  if (foundCount > 0) {
    console.log(`[GDP Media Tracker] Found and sent ${foundCount} media URLs`);
  }
}

// Monitor dynamically added media elements
const observer = new MutationObserver((mutations) => {
  if (!shouldTrackPage()) return;
  
  mutations.forEach((mutation) => {
    mutation.addedNodes.forEach((node) => {
      if (node.nodeType === 1) { // Element node
        // Check if it's a video or audio element
        if (node.tagName === 'VIDEO' || node.tagName === 'AUDIO') {
          setTimeout(() => scanMediaElements(), 500);
        }
        // Check for nested media elements
        if (node.querySelectorAll) {
          const videos = node.querySelectorAll('video, audio');
          if (videos.length > 0) {
            setTimeout(() => scanMediaElements(), 500);
          }
        }
      }
    });
  });
});

// Intercept fetch requests to catch media URLs
(function() {
  const originalFetch = window.fetch;
  window.fetch = function(...args) {
    const url = args[0];
    const fetchPromise = originalFetch.apply(this, args);
    
    if (typeof url === 'string' && shouldTrackPage()) {
      // Check if URL has media extension
      const fileExt = getFileExtension(url);
      if (fileExt && !networkTrackedUrls.has(url)) {
        console.log('[GDP Media Tracker] ✅ Intercepted fetch request with extension:', url.substring(0, 200));
        networkTrackedUrls.add(url);
        sendMedia(url, 'network_request', '', null);
      } else {
        // Even if no extension, check response headers for media content type
        fetchPromise.then(response => {
          const contentType = response.headers.get('content-type') || '';
          if ((contentType.includes('video/') || contentType.includes('audio/')) && !networkTrackedUrls.has(url)) {
            console.log('[GDP Media Tracker] ✅ Intercepted fetch with media content-type:', url.substring(0, 200), contentType);
            networkTrackedUrls.add(url);
            // Try to determine extension from content-type
            let ext = 'mp4';
            if (contentType.includes('mp3') || contentType.includes('mpeg')) ext = 'mp3';
            else if (contentType.includes('quicktime')) ext = 'mov';
            sendMedia(url, 'network_request', contentType, null);
          }
        }).catch(() => {});
      }
    }
    
    return fetchPromise;
  };
})();

// Intercept XMLHttpRequest to catch media URLs
(function() {
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
  
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this._trackedUrl = url;
    
    if (typeof url === 'string' && shouldTrackPage()) {
      const fileExt = getFileExtension(url);
      if (fileExt && !networkTrackedUrls.has(url)) {
        console.log('[GDP Media Tracker] ✅ Intercepted XHR request with extension:', url.substring(0, 200));
        networkTrackedUrls.add(url);
        sendMedia(url, 'network_request', '', null);
      }
    }
    
    return originalOpen.apply(this, [method, url, ...rest]);
  };
  
  // Also intercept response to check content-type
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(...args) {
    if (this._trackedUrl && shouldTrackPage() && !networkTrackedUrls.has(this._trackedUrl)) {
      this.addEventListener('readystatechange', function() {
        if (this.readyState === 2) { // HEADERS_RECEIVED
          const contentType = this.getResponseHeader('content-type') || '';
          if ((contentType.includes('video/') || contentType.includes('audio/')) && !networkTrackedUrls.has(this._trackedUrl)) {
            console.log('[GDP Media Tracker] ✅ Intercepted XHR with media content-type:', this._trackedUrl.substring(0, 200), contentType);
            networkTrackedUrls.add(this._trackedUrl);
            let ext = 'mp4';
            if (contentType.includes('mp3') || contentType.includes('mpeg')) ext = 'mp3';
            else if (contentType.includes('quicktime')) ext = 'mov';
            sendMedia(this._trackedUrl, 'network_request', contentType, null);
          }
        }
      }, { once: true });
    }
    return originalSend.apply(this, args);
  };
})();

// Monitor Performance API for network requests
function monitorPerformanceEntries() {
  if (!shouldTrackPage()) return;
  
  try {
    const entries = performance.getEntriesByType('resource');
    entries.forEach(entry => {
      if (entry.name && !networkTrackedUrls.has(entry.name)) {
        // Check if URL has media extension
        const fileExt = getFileExtension(entry.name);
        if (fileExt) {
          console.log('[GDP Media Tracker] ✅ Found media in Performance API (by extension):', entry.name.substring(0, 200));
          networkTrackedUrls.add(entry.name);
          sendMedia(entry.name, 'network_request', entry.initiatorType || '', null);
        } 
        // Check if it's a video/audio resource by checking the entry type or size
        // Large resources (> 1MB) with video/audio initiator types are likely media
        else if (entry.transferSize > 1024 * 1024 && 
                 (entry.initiatorType === 'video' || entry.initiatorType === 'audio' || entry.name.includes('video') || entry.name.includes('audio'))) {
          console.log('[GDP Media Tracker] ⚠️ Found potential media in Performance API (large resource):', entry.name.substring(0, 200));
          // Don't send yet, wait for more info or check if it's actually media
        }
      }
    });
  } catch (e) {
    console.warn('[GDP Media Tracker] Performance API error:', e);
  }
}

// Initialize
(function() {
  if (!shouldTrackPage()) {
    console.log('[GDP Media Tracker] Page not in tracked list:', window.location.href);
    return;
  }
  
  console.log('[GDP Media Tracker] Tracking page:', window.location.href);
  console.log('[GDP Media Tracker] Network interception enabled for fetch/XHR');
  
  // Monitor performance entries
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(monitorPerformanceEntries, 2000);
      setTimeout(scanMediaElements, 2000);
      setTimeout(monitorPerformanceEntries, 5000);
      setTimeout(scanMediaElements, 5000);
      setTimeout(monitorPerformanceEntries, 10000);
      setTimeout(scanMediaElements, 10000);
    });
  } else {
    setTimeout(monitorPerformanceEntries, 2000);
    setTimeout(scanMediaElements, 2000);
    setTimeout(monitorPerformanceEntries, 5000);
    setTimeout(scanMediaElements, 5000);
    setTimeout(monitorPerformanceEntries, 10000);
    setTimeout(scanMediaElements, 10000);
  }
  
  // Watch for dynamically added content
  if (document.body) {
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }
  
  // Re-scan periodically for lazy-loaded content
  setInterval(() => {
    monitorPerformanceEntries();
    scanMediaElements();
  }, 10000); // Every 10 seconds
  
  // Also scan when page becomes visible (user switches back to tab)
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      setTimeout(() => {
        monitorPerformanceEntries();
        scanMediaElements();
      }, 1000);
    }
  });
  
  // Monitor new performance entries as they're added
  if (window.PerformanceObserver) {
    try {
      const perfObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name && !networkTrackedUrls.has(entry.name)) {
            const fileExt = getFileExtension(entry.name);
            if (fileExt) {
              console.log('[GDP Media Tracker] ✅ New performance entry (by extension):', entry.name.substring(0, 200));
              networkTrackedUrls.add(entry.name);
              sendMedia(entry.name, 'network_request', entry.initiatorType || '', null);
            }
          }
        }
      });
      perfObserver.observe({ entryTypes: ['resource'] });
      console.log('[GDP Media Tracker] ✅ PerformanceObserver initialized');
    } catch (e) {
      console.warn('[GDP Media Tracker] PerformanceObserver not available:', e);
    }
  }
  
  // Also listen to video element events to catch when blob URLs are created
  // This happens when video loads from a real URL and creates a blob
  document.addEventListener('loadstart', function(e) {
    if (e.target && (e.target.tagName === 'VIDEO' || e.target.tagName === 'AUDIO')) {
      console.log('[GDP Media Tracker] Video/Audio loadstart event:', e.target.src);
    }
  }, true);
  
  document.addEventListener('loadedmetadata', function(e) {
    if (e.target && (e.target.tagName === 'VIDEO' || e.target.tagName === 'AUDIO')) {
      console.log('[GDP Media Tracker] Video/Audio loadedmetadata event:', {
        src: e.target.src,
        currentSrc: e.target.currentSrc,
        videoWidth: e.target.videoWidth,
        videoHeight: e.target.videoHeight
      });
    }
  }, true);
})();

