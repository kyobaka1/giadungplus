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
  //     vapidPublicKey: '...'
  //   };
  // </script>
  const DEFAULT_CONFIG = {
    apiRegisterUrl: '/api/push/register/',
    swUrl: '/static/js/service-worker.js', // Có thể override bằng GP_PUSH_CONFIG
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

  function isPushSupported() {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
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
      return true;
    }
    if (Notification.permission === 'denied') {
      console.warn('User đã từ chối notification.');
      return false;
    }
    const permission = await Notification.requestPermission();
    return permission === 'granted';
  }

  async function registerServiceWorker() {
    // Cho phép override URL nếu template đã set GP_PUSH_CONFIG.swUrl
    const swUrl = CONFIG.swUrl;
    return navigator.serviceWorker.register(swUrl);
  }

  async function initFirebaseMessaging() {
    if (!window.firebase || !window.firebase.messaging) {
      console.warn(
        'Firebase messaging chưa được load. Hãy include CDN firebase-app.js và firebase-messaging.js (v8) trước push-setup.js.'
      );
      return null;
    }

    if (!window.firebase.apps || window.firebase.apps.length === 0) {
      window.firebase.initializeApp(CONFIG.firebaseConfig);
    }

    try {
      const messaging = window.firebase.messaging();
      return messaging;
    } catch (err) {
      console.error('Lỗi khởi tạo Firebase messaging:', err);
      return null;
    }
  }

  async function getAndroidFcmToken(messaging) {
    try {
      const token = await messaging.getToken({
        vapidKey: CONFIG.vapidPublicKey,
      });
      return token;
    } catch (err) {
      console.error('Lỗi lấy FCM token:', err);
      return null;
    }
  }

  async function subscribeWithPushManager(registration) {
    try {
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(CONFIG.vapidPublicKey),
      });
      return subscription;
    } catch (err) {
      console.error('Lỗi subscribe PushManager:', err);
      return null;
    }
  }

  async function sendSubscriptionToServer(payload) {
    try {
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
        console.error('Đăng ký subscription thất bại:', res.status, await res.text());
        return false;
      }

      const data = await res.json();
      console.log('Đăng ký WebPush thành công:', data);
      return true;
    } catch (err) {
      console.error('Lỗi gửi subscription lên server:', err);
      return false;
    }
  }

  async function initPush() {
    if (!isPushSupported()) {
      console.warn('Trình duyệt không hỗ trợ Service Worker / Push / Notification.');
      return;
    }

    const granted = await requestNotificationPermission();
    if (!granted) {
      console.warn('User không cho phép gửi notification.');
      return;
    }

    let registration;
    try {
      registration = await registerServiceWorker();
      console.log('Service Worker registered:', registration);
    } catch (err) {
      console.error('Không thể đăng ký Service Worker:', err);
      return;
    }

    let deviceType = 'unknown';
    let payload = {
      device_type: deviceType,
      endpoint: null,
      keys: null,
      fcm_token: null,
    };

    if (isAndroidChrome()) {
      deviceType = 'android_web';
      const messaging = await initFirebaseMessaging();
      if (messaging) {
        const token = await getAndroidFcmToken(messaging);
        if (token) {
          payload.device_type = deviceType;
          payload.fcm_token = token;
          // Với FCM token trên Web, endpoint/keys không bắt buộc
        }
      }
    } else if (isIosSafari()) {
      // Safari iOS 16.4+ hỗ trợ Web Push, nhưng không dùng trực tiếp Firebase Messaging
      deviceType = 'ios_web';
      const sub = await subscribeWithPushManager(registration);
      if (sub) {
        const json = sub.toJSON();
        payload.device_type = deviceType;
        payload.endpoint = json.endpoint;
        payload.keys = json.keys || {};
      }
    } else {
      // Các browser khác (Desktop, Android khác, ...)
      deviceType = 'unknown';
      const sub = await subscribeWithPushManager(registration);
      if (sub) {
        const json = sub.toJSON();
        payload.device_type = deviceType;
        payload.endpoint = json.endpoint;
        payload.keys = json.keys || {};
      }
    }

    // Nếu không có token/subscription nào thì dừng
    if (!payload.fcm_token && !payload.endpoint) {
      console.warn('Không lấy được FCM token hoặc Push subscription.');
      return;
    }

    await sendSubscriptionToServer(payload);
  }

  // Tự khởi động khi DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPush);
  } else {
    initPush();
  }

  // Expose ra global nếu muốn gọi thủ công
  window.initPush = initPush;
})();


