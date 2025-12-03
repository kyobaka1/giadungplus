// service-worker.js
// Service Worker cho Web Push Notification
// - Lắng nghe sự kiện 'push' và hiển thị notification
// - Xử lý 'notificationclick' để mở/focus tab tương ứng

self.addEventListener('push', function (event) {
  // Payload có thể được gửi dưới dạng text JSON trong event.data
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (e) {
      // Nếu không parse được JSON thì fallback sang text
      payload = { title: 'Thông báo', body: event.data.text() };
    }
  }

  const title = payload.title || 'Thông báo mới';
  const options = {
    body: payload.body || '',
    icon: payload.icon || '/static/favicon.png', // Có thể chỉnh lại icon
    data: {
      url: payload.url || '/',
      // Lưu toàn bộ payload để dùng nếu cần
      payload: payload,
    },
    tag: payload.tag || 'general',
    renotify: true,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  const urlToOpen = (event.notification && event.notification.data && event.notification.data.url) || '/';

  // Focus tab nếu đã mở, nếu không thì mở tab mới
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (let i = 0; i < clientList.length; i++) {
        const client = clientList[i];
        if ('focus' in client) {
          // Nếu URL đang mở khớp với urlToOpen thì focus
          if (client.url && client.url.indexOf(urlToOpen) !== -1) {
            return client.focus();
          }
        }
      }
      // Nếu chưa có tab phù hợp thì mở mới
      if (self.clients.openWindow) {
        return self.clients.openWindow(urlToOpen);
      }
    })
  );
});


