// push-setup.js
// JS frontend để:
// - Kiểm tra hỗ trợ Service Worker + Push
// - Đăng ký service worker
// - Xin quyền notification
// - Lấy FCM token (Android Chrome) HOẶC subscription (Safari iOS / browser khác)
// - Gửi dữ liệu về backend Django qua API /api/push/register/

(function () {
  // Cho phép override config từ template Django:
  // <script>
  //   window.GP_PUSH_CONFIG = {
  //     apiRegisterUrl: '/api/push/register/',
  //     swUrl: '{% static "js/service-worker.js" %}',
  //     vapidPublicKey: '...',
  //     username: '{{ request.user.username }}', // optional: đẩy kèm username
  //   };
  // </script>
  const DEFAULT_CONFIG = {
    apiRegisterUrl: '/api/push/register/',
    swUrl: '/static/js/service-worker.js', // Có thể override bằng GP_PUSH_CONFIG
    username: null, // có thể set từ template nếu muốn backend map user theo username
    vapidPublicKey:
      'BMAinpH2KhQxtclH3XM3UJ_9e-NvlKTzY-WIszcXxCkll7ISLR3BEdWKmgBgkXvjjILJz5Uh375hHwRj3IvaIHU', // từ keypair.txt
    firebaseConfig: {
      apiKey: 'AIzaSyCztxeRD5xqgMevLAOY5aWoRrPO39tuooQ',
      authDomain: 'giadungplus-44b34.firebaseapp.com',
      projectId: 'giadungplus-44b34',
      storageBucket: 'giadungplus-44b34.firebasestorage.app',
      messagingSenderId: '362492099944',
      appId: '1:362492099944:web:f1dba4f8da485db8916add',
      measurementId: 'G-TFE9159KNC',
    },
  };

  const CONFIG = Object.assign({}, DEFAULT_CONFIG, window.GP_PUSH_CONFIG || {});

  // Flag debug cho WebPush client:
  // - Bật khi URL có ?push_debug=1 hoặc global window.GP_PUSH_DEBUG = true
  const DEBUG_PUSH =
    typeof window !== 'undefined' &&
    window.location &&
    (window.location.search.indexOf('push_debug=1') !== -1 ||
      (window.GP_PUSH_DEBUG && window.GP_PUSH_DEBUG === true));

  // Helper để log ra HTML (luôn hiển thị, không cần DEBUG_PUSH)
  function logToHTML(message, type = 'info') {
    try {
      const logContainer = document.getElementById('push-log-content');
      const debugPanel = document.getElementById('push-debug-log');
      
      if (logContainer && debugPanel) {
        // Hiển thị panel nếu đang ẩn
        if (debugPanel.style.display === 'none') {
          debugPanel.style.display = 'block';
        }
        
        const time = new Date().toLocaleTimeString('vi-VN');
        const div = document.createElement('div');
        div.className = 'py-1 border-b border-slate-100 last:border-0';
        
        // Màu sắc theo type
        let colorClass = 'text-slate-600';
        let icon = '•';
        if (type === 'success') {
          colorClass = 'text-green-600';
          icon = '✅';
        } else if (type === 'error') {
          colorClass = 'text-red-600';
          icon = '❌';
        } else if (type === 'warning') {
          colorClass = 'text-amber-600';
          icon = '⚠️';
        }
        
        div.innerHTML = `<span class="text-slate-400">[${time}]</span> <span class="${colorClass}">${icon} ${message}</span>`;
        logContainer.appendChild(div);
        
        // Auto scroll to bottom
        logContainer.scrollTop = logContainer.scrollHeight;
      }
    } catch (e) {
      // ignore errors
    }
  }

  // Debug helper: log ra console + HTML (nếu có #webpush-debug-client)
  function logPushDebug(message, data) {
    if (!DEBUG_PUSH) return;
    try {
      const prefix = '[PushClient] ';
        if (data !== undefined) {
          console.log(prefix + message, data);
        } else {
          console.log(prefix + message);
        }
      const el = document.getElementById('webpush-debug-client');
      if (el) {
        const time = new Date().toISOString().split('T')[1].split('.')[0];
        const line =
          '[' + time + '] ' + message + (data !== undefined ? ' ' + JSON.stringify(data) : '');
        const div = document.createElement('div');
        div.textContent = line;
        el.appendChild(div);
      }
    } catch (e) {
      // ignore debug errors
    }
  }

  function isPushSupported() {
    const supported =
      'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    if (!supported) {
      logPushDebug('Push không được hỗ trợ trên trình duyệt này.', {
        hasServiceWorker: 'serviceWorker' in navigator,
        hasPushManager: 'PushManager' in window,
        hasNotification: 'Notification' in window,
      });
    }
    return supported;
  }

  // Phát hiện loại thiết bị chi tiết hơn (ưu tiên userAgentData nếu có)
  async function getDeviceType() {
    try {
      if (navigator.userAgentData) {
        const brands = navigator.userAgentData.brands || [];
        const mobile = navigator.userAgentData.mobile;
        if (mobile) return 'mobile';
        if (brands.some((b) => b.brand && b.brand.includes('Chromium'))) return 'desktop';
        if (brands.some((b) => b.brand && b.brand.includes('Android'))) return 'android';
      }
    } catch (e) {
      console.warn('Lỗi đọc navigator.userAgentData:', e);
    }

    // fallback: userAgent cũ
    const ua = (navigator.userAgent || '').toLowerCase();
    if (/iphone|ipad|ipod/.test(ua)) return 'ios';
    if (/android/.test(ua)) return 'android';
    if (/windows|mac|linux/.test(ua)) return 'desktop';
    return 'unknown';
  }

  // Chuẩn hoá device_type gửi lên server theo enum backend
  // - ios  → ios_web
  // - android|mobile → android_web
  // - desktop/unknown → unknown
  async function getNormalizedDeviceType() {
    const raw = await getDeviceType();
    if (raw === 'ios') return 'ios_web';
    if (raw === 'android' || raw === 'mobile') return 'android_web';
    return 'unknown';
  }

  function isAndroidChrome() {
    const ua = navigator.userAgent || '';
    return /Android/i.test(ua) && /Chrome/i.test(ua) && !/OPR|Edg|SamsungBrowser/i.test(ua);
  }

  function isIosSafari() {
    const ua = navigator.userAgent || '';
    const isIOS = /iPhone|iPad|iPod/i.test(ua);
    const isSafari = /Safari/i.test(ua) && !/CriOS|FxiOS|OPiOS|EdgiOS/i.test(ua);
    return isIOS && isSafari;
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function requestNotificationPermission() {
    if (Notification.permission === 'granted') {
      logPushDebug('Notification.permission đã là granted, bỏ qua requestPermission().');
      return true;
    }
    if (Notification.permission === 'denied') {
      console.warn('User đã từ chối notification.');
      logPushDebug('Notification.permission = denied, dừng lại.');
      return false;
    }
    const permission = await Notification.requestPermission();
    logPushDebug('Kết quả Notification.requestPermission()', { permission });
    return permission === 'granted';
  }

  async function registerServiceWorker() {
    // Cho phép override URL nếu template đã set GP_PUSH_CONFIG.swUrl
    const swUrl = CONFIG.swUrl;
    logPushDebug('Đăng ký Service Worker với swUrl=' + swUrl);
    return navigator.serviceWorker.register(swUrl);
  }

  async function initFirebaseMessaging() {
    logToHTML('Kiểm tra Firebase...', 'info');
    
    if (!window.firebase) {
      const msg = '❌ window.firebase không tồn tại. Firebase chưa được load.';
      logToHTML(msg, 'error');
      logToHTML('Cần include firebase-app.js trước push-setup.js', 'error');
      console.warn(msg);
      logPushDebug(msg);
      return null;
    }
    
    if (!window.firebase.messaging) {
      const msg = '❌ window.firebase.messaging không tồn tại.';
      logToHTML(msg, 'error');
      logToHTML('Cần include firebase-messaging.js trước push-setup.js', 'error');
      console.warn(msg);
      logPushDebug(msg);
      return null;
    }
    
    logToHTML('✅ Firebase đã được load', 'success');
    logToHTML('Firebase apps hiện có: ' + (window.firebase.apps ? window.firebase.apps.length : 0), 'info');

    if (!window.firebase.apps || window.firebase.apps.length === 0) {
      logToHTML('Đang khởi tạo Firebase app...', 'info');
      try {
        window.firebase.initializeApp(CONFIG.firebaseConfig);
        logToHTML('✅ Firebase app đã được khởi tạo', 'success');
      } catch (initErr) {
        logToHTML('❌ Lỗi khởi tạo Firebase app: ' + String(initErr), 'error');
        return null;
      }
    } else {
      logToHTML('Firebase app đã được khởi tạo trước đó', 'info');
    }

    try {
      logToHTML('Đang tạo Firebase messaging instance...', 'info');
      const messaging = window.firebase.messaging();
      logToHTML('✅ Firebase messaging instance đã được tạo', 'success');
      return messaging;
    } catch (err) {
      const errorMsg = err && err.message ? err.message : String(err);
      logToHTML('❌ Lỗi khởi tạo Firebase messaging: ' + errorMsg, 'error');
      console.error('Lỗi khởi tạo Firebase messaging:', err);
      logPushDebug('Lỗi khởi tạo Firebase messaging', { error: String(err) });
      return null;
    }
  }

  async function getAndroidFcmToken(messaging, registration) {
    try {
      logToHTML('Đang lấy FCM token với VAPID key...', 'info');
      
      // Đảm bảo Service Worker đã active trước khi lấy token
      if (registration && !registration.active) {
        logToHTML('⚠️ Service Worker chưa active, đang chờ...', 'warning');
        const maxWait = 5000;
        const step = 500;
        let waited = 0;
        while (!registration.active && waited < maxWait) {
          await new Promise(resolve => setTimeout(resolve, step));
          waited += step;
        }
        if (!registration.active) {
          logToHTML('❌ Service Worker vẫn chưa active sau khi chờ', 'error');
        } else {
          logToHTML('✅ Service Worker đã active', 'success');
        }
      }
      
      const tokenOptions = {
        vapidKey: CONFIG.vapidPublicKey,
      };
      
      // Nếu có Service Worker registration, thêm vào options
      if (registration && registration.active) {
        tokenOptions.serviceWorkerRegistration = registration;
      }
      
      logToHTML('Gọi messaging.getToken()...', 'info');
      const token = await messaging.getToken(tokenOptions);
      
      if (token) {
        logToHTML('✅ Đã lấy được FCM token (Android Chrome)', 'success');
        logPushDebug('Đã lấy được FCM token (Android Chrome).');
        return token;
      } else {
        logToHTML('❌ messaging.getToken() trả về null', 'error');
        return null;
      }
    } catch (err) {
      const errorMsg = err && err.message ? err.message : String(err);
      const errorName = err && err.name ? err.name : 'UnknownError';
      logToHTML('❌ Lỗi lấy FCM token: ' + errorName + ' - ' + errorMsg, 'error');
      logToHTML('Chi tiết lỗi: ' + JSON.stringify(err), 'error');
      console.error('Lỗi lấy FCM token:', err);
      logPushDebug('Lỗi lấy FCM token', { error: String(err), name: errorName, message: errorMsg });
      return null;
    }
  }

  async function subscribeWithPushManager(registration) {
    try {
      logToHTML('Thực hiện subscribe với PushManager...', 'info');
      logPushDebug('Thực hiện subscribe với PushManager... chuẩn bị chờ service worker active.');

      // Dùng trực tiếp registration trả về từ navigator.serviceWorker.register.
      // Tránh await navigator.serviceWorker.ready vì trên một số trình duyệt (scope không control trang)
      // nó sẽ không bao giờ resolve.
      const targetRegistration = registration;

      logPushDebug('Trạng thái service worker sau register', {
        scope: targetRegistration.scope,
        hasActive: !!targetRegistration.active,
        installing: !!targetRegistration.installing,
        waiting: !!targetRegistration.waiting,
      });

      // Chờ tối đa ~5s cho đến khi service worker active (nếu có thay đổi).
      const maxWaitMs = 5000;
      const stepMs = 500;
      let waited = 0;
      while (!targetRegistration.active && waited < maxWaitMs) {
        logPushDebug('Service worker chưa active, tiếp tục chờ...', {
          scope: targetRegistration.scope,
          waitedMs: waited,
          hasActive: !!targetRegistration.active,
          installing: !!targetRegistration.installing,
          waiting: !!targetRegistration.waiting,
        });
        await new Promise((resolve) => setTimeout(resolve, stepMs));
        waited += stepMs;
      }

      if (!targetRegistration.active) {
        logPushDebug(
          'Service worker vẫn chưa active sau khi chờ, vẫn thử gọi pushManager.subscribe (có thể lỗi InvalidStateError).',
          {
            scope: targetRegistration.scope,
            hasActive: !!targetRegistration.active,
          }
        );
      }

      // Kiểm tra lại trước khi subscribe
      const hasPushManager = !!targetRegistration.pushManager;
      logPushDebug('Trạng thái trước khi gọi pushManager.subscribe', {
        scope: targetRegistration.scope,
        hasPushManager,
        hasActive: !!targetRegistration.active,
      });

      if (!hasPushManager) {
        const msg = '❌ Không tìm thấy pushManager trên registration. Trình duyệt không hỗ trợ Web Push cho scope này.';
        logToHTML(msg, 'error');
        logPushDebug('Không tìm thấy pushManager trên registration này. Trình duyệt không hỗ trợ Web Push cho scope hiện tại.');
        return null;
      }

      let subscription = null;
      try {
        logToHTML('Gọi pushManager.subscribe()...', 'info');
        subscription = await targetRegistration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(CONFIG.vapidPublicKey),
        });
        logToHTML('✅ pushManager.subscribe() thành công', 'success');
      } catch (err) {
        const errorName = err && err.name ? err.name : 'UnknownError';
        const errorMsg = err && err.message ? err.message : String(err);
        logToHTML('❌ Lỗi khi gọi pushManager.subscribe: ' + errorName + ' - ' + errorMsg, 'error');
        logPushDebug('Lỗi ngay khi gọi pushManager.subscribe', {
          name: errorName,
          message: errorMsg,
        });
        throw err;
      }

      logToHTML('✅ Đã subscribe PushManager thành công', 'success');
      logPushDebug('Đã subscribe PushManager thành công.');
      return subscription;
    } catch (err) {
      const errorMsg = err && err.message ? err.message : String(err);
      const errorName = err && err.name ? err.name : 'UnknownError';
      logToHTML('❌ Lỗi subscribe PushManager: ' + errorName + ' - ' + errorMsg, 'error');
      console.error('Lỗi subscribe PushManager:', err);
      logPushDebug('Lỗi subscribe PushManager', { error: String(err) });
      return null;
    }
  }

  async function sendSubscriptionToServer(payload) {
    try {
      logPushDebug('Gửi subscription lên server...', {
        url: CONFIG.apiRegisterUrl,
        device_type: payload.device_type,
        hasEndpoint: !!payload.endpoint,
        hasFcmToken: !!payload.fcm_token,
      });

      const res = await fetch(CONFIG.apiRegisterUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify(payload),
        credentials: 'include', // gửi kèm session nếu user đã login
      });

      if (!res.ok) {
        const text = await res.text();
        console.error('Đăng ký subscription thất bại:', res.status, text);
        logPushDebug('Đăng ký subscription thất bại', {
          status: res.status,
          body: text.slice(0, 200),
        });
        return false;
      }

      const data = await res.json();
      if (DEBUG_PUSH) {
        console.log('Đăng ký WebPush thành công:', data);
      }
      logPushDebug('Đăng ký WebPush thành công.', data);
      return true;
    } catch (err) {
      console.error('Lỗi gửi subscription lên server:', err);
      logPushDebug('Lỗi gửi subscription lên server', { error: String(err) });
      return false;
    }
  }

  async function initPush() {
    logToHTML('===== BẮT ĐẦU initPush() =====', 'info');
    logPushDebug('Bắt đầu initPush()...');
    
    // Log thông tin môi trường
    logToHTML('User Agent: ' + navigator.userAgent, 'info');
    logToHTML('Is Android Chrome: ' + isAndroidChrome(), 'info');
    logToHTML('Is iOS Safari: ' + isIosSafari(), 'info');
    logToHTML('Notification permission: ' + Notification.permission, 'info');
    logToHTML('Service Worker support: ' + ('serviceWorker' in navigator), 'info');
    logToHTML('PushManager support: ' + ('PushManager' in window), 'info');
    
    if (!isPushSupported()) {
      logToHTML('❌ Trình duyệt không hỗ trợ Service Worker / Push / Notification', 'error');
      logPushDebug('Dừng initPush vì không hỗ trợ Push.');
      return;
    }
    logToHTML('✅ Trình duyệt hỗ trợ Push', 'success');

    logToHTML('Đang xin quyền notification...', 'info');
    const granted = await requestNotificationPermission();
    logToHTML('Kết quả xin quyền: ' + (granted ? 'GRANTED' : 'DENIED'), granted ? 'success' : 'error');
    
    if (!granted) {
      logToHTML('❌ User không cho phép gửi notification', 'error');
      logPushDebug('User không cho phép gửi notification, dừng initPush.');
      return;
    }
    logToHTML('✅ User đã cho phép notification', 'success');

    let registration;
    try {
      logToHTML('Đang đăng ký Service Worker...', 'info');
      registration = await registerServiceWorker();
      logToHTML('✅ Service Worker đã được đăng ký (scope: ' + registration.scope + ')', 'success');
      logToHTML('  - Active: ' + !!registration.active + ', Installing: ' + !!registration.installing + ', Waiting: ' + !!registration.waiting, 'info');
      if (DEBUG_PUSH) {
        console.log('Service Worker registered:', registration);
      }
      logPushDebug('Service Worker đã được đăng ký thành công.');
    } catch (err) {
      logToHTML('❌ Không thể đăng ký Service Worker: ' + String(err), 'error');
      logPushDebug('Không thể đăng ký Service Worker', { error: String(err) });
      return;
    }

    // Device type mặc định (chuẩn hoá theo enum backend)
    let deviceType = await getNormalizedDeviceType();
    logToHTML('Device type (normalized): ' + deviceType, 'info');
    logPushDebug('Device type (normalized) = ' + deviceType);
    let payload = {
      device_type: deviceType,
      endpoint: null,
      keys: null,
      fcm_token: null,
    };

    if (isAndroidChrome()) {
      // Android Chrome: ưu tiên gắn nhãn android_web
      logToHTML('Nhánh Android Chrome: deviceType=android_web', 'info');
      deviceType = 'android_web';
      logToHTML('Đang khởi tạo Firebase Messaging...', 'info');
      const messaging = await initFirebaseMessaging();
      if (messaging) {
        logToHTML('✅ Firebase Messaging đã được khởi tạo', 'success');
        logToHTML('Đang lấy FCM token (cần Service Worker active)...', 'info');
        // Truyền registration vào để đảm bảo Service Worker active
        const token = await getAndroidFcmToken(messaging, registration);
        if (token) {
          logToHTML('✅ Đã lấy được FCM token: ' + token.substring(0, 50) + '...', 'success');
          payload.device_type = deviceType;
          payload.fcm_token = token;
          // Với FCM token trên Web, endpoint/keys không bắt buộc
        } else {
          logToHTML('❌ Không lấy được FCM token', 'error');
          logToHTML('⚠️ Thử fallback: subscribe với PushManager...', 'warning');
          // Fallback: thử subscribe với PushManager nếu không lấy được FCM token
          const sub = await subscribeWithPushManager(registration);
          if (sub) {
            logToHTML('✅ Fallback thành công: đã subscribe PushManager', 'success');
            const json = sub.toJSON();
            payload.device_type = deviceType;
            payload.endpoint = json.endpoint;
            payload.keys = json.keys || {};
            logToHTML('Endpoint: ' + json.endpoint, 'info');
          } else {
            logToHTML('❌ Fallback cũng thất bại', 'error');
          }
        }
      } else {
        logToHTML('❌ Không thể khởi tạo Firebase Messaging', 'error');
        logToHTML('⚠️ Thử fallback: subscribe với PushManager...', 'warning');
        // Fallback: thử subscribe với PushManager
        const sub = await subscribeWithPushManager(registration);
        if (sub) {
          logToHTML('✅ Fallback thành công: đã subscribe PushManager', 'success');
          const json = sub.toJSON();
          payload.device_type = deviceType;
          payload.endpoint = json.endpoint;
          payload.keys = json.keys || {};
          logToHTML('Endpoint: ' + json.endpoint, 'info');
        } else {
          logToHTML('❌ Fallback cũng thất bại', 'error');
        }
      }
    } else if (isIosSafari()) {
      // Safari iOS 16.4+ hỗ trợ Web Push, nhưng không dùng trực tiếp Firebase Messaging
      logToHTML('Nhánh iOS Safari: deviceType=ios_web', 'info');
      deviceType = 'ios_web';
      logPushDebug('Nhánh iOS Safari: deviceType=ios_web, chuẩn bị subscribe PushManager...');
      logToHTML('Đang subscribe với PushManager...', 'info');
      const sub = await subscribeWithPushManager(registration);
      if (sub) {
        logToHTML('✅ Đã subscribe PushManager thành công', 'success');
        const json = sub.toJSON();
        payload.device_type = deviceType;
        payload.endpoint = json.endpoint;
        payload.keys = json.keys || {};
        logToHTML('Endpoint: ' + json.endpoint, 'info');
      } else {
        logToHTML('❌ Không thể subscribe PushManager', 'error');
      }
    } else {
      // Các browser khác (Desktop, Android khác, ...) giữ nguyên deviceType đã chuẩn hoá trước đó
      logToHTML('Nhánh browser khác: deviceType=' + deviceType, 'info');
      logToHTML('Đang subscribe với PushManager...', 'info');
      const sub = await subscribeWithPushManager(registration);
      if (sub) {
        logToHTML('✅ Đã subscribe PushManager thành công', 'success');
        const json = sub.toJSON();
        payload.device_type = deviceType;
        payload.endpoint = json.endpoint;
        payload.keys = json.keys || {};
        logToHTML('Endpoint: ' + json.endpoint, 'info');
      } else {
        logToHTML('❌ Không thể subscribe PushManager', 'error');
      }
    }

    // Nếu không có token/subscription nào thì dừng
    if (!payload.fcm_token && !payload.endpoint) {
      logToHTML('❌ Không lấy được FCM token hoặc Push subscription', 'error');
      logToHTML('Payload: ' + JSON.stringify(payload), 'warning');
      return;
    }

    // Đính kèm username nếu config có (giúp backend map user_id khi không có session)
    if (CONFIG.username) {
      payload.username = CONFIG.username;
      logToHTML('Đã thêm username: ' + CONFIG.username, 'info');
    }

    logToHTML('Payload cuối cùng: device_type=' + payload.device_type + ', hasEndpoint=' + !!payload.endpoint + ', hasFcmToken=' + !!payload.fcm_token, 'info');
    
    logToHTML('Đang gửi subscription lên server...', 'info');
    const serverResult = await sendSubscriptionToServer(payload);
    logToHTML(serverResult ? '✅ THÀNH CÔNG - Đã gửi subscription lên server' : '❌ THẤT BẠI - Không thể gửi subscription lên server', serverResult ? 'success' : 'error');
    logToHTML('===== KẾT THÚC initPush() =====', 'info');
  }

  // iOS Safari (PWA / Add to Home Screen) yêu cầu gọi Notification.requestPermission()
  // trong context user gesture (onclick). Vì vậy:
  // - iOS Safari + standalone mode: KHÔNG auto-init, chỉ expose window.initPush,
  //   để template gắn vào nút "Bật thông báo".
  // - Các nền tảng khác: vẫn auto-init khi DOM ready.
  const isStandaloneDisplayMode =
    window.matchMedia && window.matchMedia('(display-mode: standalone)').matches;
  const isNavigatorStandalone = typeof window.navigator !== 'undefined' && window.navigator.standalone === true;
  const isStandaloneIos = isIosSafari() && (isStandaloneDisplayMode || isNavigatorStandalone);

  if (!isStandaloneIos) {
    // Tự khởi động khi DOM ready (Android, desktop, Safari thường)
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initPush);
    } else {
      initPush();
    }
  }

  // Expose ra global để:
  // - iOS PWA gọi qua nút "Bật thông báo"
  // - các nơi khác có thể gọi thủ công nếu cần
  window.initPush = initPush;
})();


