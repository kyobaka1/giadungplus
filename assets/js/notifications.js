/**
 * Notification Bell JavaScript
 * Xử lý hiển thị và tương tác với notification bell
 */

(function() {
    'use strict';

    // Config
    const CONFIG = {
        apiBaseUrl: '/api/notifications',
        pollInterval: 30000, // 30 giây
        maxNotifications: 50,
    };

    // State
    let state = {
        unreadCount: 0,
        notifications: [],
        isLoading: false,
        pollTimer: null,
        initialized: false, // để tránh phát âm thanh ở lần load đầu tiên
    };

    // DOM Elements
    const elements = {
        bellButton: null,
        bellContainer: null,
        dropdown: null,
        badge: null,
        count: null,
        list: null,
        loading: null,
        empty: null,
        markAllReadButton: null,
        closeButton: null,
        itemTemplate: null,
    };

    // Audio for new notifications
    let notifyAudio = null;

    function getNotifyAudio() {
        if (!notifyAudio) {
            notifyAudio = new Audio('/static/sound/notify-1.mp3');
        }
        return notifyAudio;
    }

    function playNotifySound() {
        try {
            const audio = getNotifyAudio();
            // tua về đầu để nếu nhiều notify liên tiếp vẫn nghe rõ
            audio.currentTime = 0;
            audio.play().catch(() => {
                // Một số trình duyệt chặn auto-play nếu chưa có tương tác người dùng
            });
        } catch (e) {
            console.error('Error playing notify sound:', e);
        }
    }

    /**
     * Initialize notification bell
     */
    function init() {
        // Get DOM elements
        elements.bellContainer = document.getElementById('notificationBellContainer');
        if (!elements.bellContainer) {
            console.warn('Notification bell container not found');
            return;
        }

        elements.bellButton = document.getElementById('notificationBellButton');
        elements.dropdown = document.getElementById('notificationDropdown');
        elements.badge = document.getElementById('notificationBadge');
        elements.count = document.getElementById('notificationCount');
        elements.list = document.getElementById('notificationList');
        elements.loading = document.getElementById('notificationLoading');
        elements.empty = document.getElementById('notificationEmpty');
        elements.markAllReadButton = document.getElementById('markAllReadButton');
        elements.closeButton = document.getElementById('closeNotificationButton');
        elements.itemTemplate = document.getElementById('notificationItemTemplate');
        elements.overlay = document.getElementById('notificationOverlay');

        if (!elements.bellButton || !elements.dropdown) {
            console.warn('Notification bell elements not found');
            return;
        }

        // Event listeners
        elements.bellButton.addEventListener('click', toggleDropdown);
        elements.closeButton?.addEventListener('click', closeDropdown);
        elements.markAllReadButton?.addEventListener('click', markAllRead);

        // Click outside to close (không áp dụng cho overlay vì overlay tự đóng)
        document.addEventListener('click', (e) => {
            if (elements.overlay && !elements.overlay.classList.contains('hidden')) {
                // khi overlay đang hiện, close khi click overlay (xử lý riêng)
                return;
            }
            if (!elements.bellContainer.contains(e.target)) {
                closeDropdown();
            }
        });

        // Click overlay để đóng
        if (elements.overlay) {
            elements.overlay.addEventListener('click', () => {
                closeDropdown();
            });
        }

        // Load initial data
        loadUnreadCount();
        startPolling();

        // Load notifications when dropdown opens
        elements.bellButton.addEventListener('click', () => {
            if (!elements.dropdown.classList.contains('hidden')) {
                loadNotifications();
            }
        });
    }

    /**
     * Toggle dropdown
     */
    function toggleDropdown() {
        const isHidden = elements.dropdown.classList.contains('hidden');
        if (isHidden) {
            openDropdown();
        } else {
            closeDropdown();
        }
    }

    /**
     * Open dropdown
     */
    function openDropdown() {
        elements.dropdown.classList.remove('hidden');
        if (elements.overlay) {
            elements.overlay.classList.remove('hidden');
        }
        loadNotifications();
    }

    /**
     * Close dropdown
     */
    function closeDropdown() {
        elements.dropdown.classList.add('hidden');
        if (elements.overlay) {
            elements.overlay.classList.add('hidden');
        }
    }

    /**
     * Load unread count
     */
    async function loadUnreadCount() {
        try {
            const response = await fetch(`${CONFIG.apiBaseUrl}/unread-count/`, {
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            const newCount = data.count || 0;
            const prevCount = state.unreadCount;
            state.unreadCount = newCount;

            // Nếu đã init và số lượng chưa đọc tăng → phát âm thanh
            if (state.initialized && newCount > prevCount) {
                playNotifySound();
            }

            if (!state.initialized) {
                state.initialized = true;
            }

            updateBadge();
        } catch (error) {
            console.error('Error loading unread count:', error);
        }
    }

    /**
     * Load notifications list
     */
    async function loadNotifications() {
        if (state.isLoading) return;
        state.isLoading = true;

        // Show loading
        elements.loading?.classList.remove('hidden');
        elements.list?.classList.add('hidden');
        elements.empty?.classList.add('hidden');

        try {
            const response = await fetch(
                `${CONFIG.apiBaseUrl}/?limit=${CONFIG.maxNotifications}&offset=0`,
                {
                    credentials: 'include',
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            state.notifications = data.results || [];

            renderNotifications();

            // Update unread count
            state.unreadCount = state.notifications.filter(n => !n.is_read).length;
            updateBadge();
        } catch (error) {
            console.error('Error loading notifications:', error);
            showError();
        } finally {
            state.isLoading = false;
            elements.loading?.classList.add('hidden');
        }
    }

    /**
     * Render notifications list
     */
    function renderNotifications() {
        if (!elements.list) return;

        elements.list.innerHTML = '';

        if (state.notifications.length === 0) {
            elements.empty?.classList.remove('hidden');
            elements.list.classList.add('hidden');
            elements.markAllReadButton.style.display = 'none';
            return;
        }

        elements.empty?.classList.add('hidden');
        elements.list.classList.remove('hidden');

        // Show mark all read button if there are unread notifications
        const hasUnread = state.notifications.some(n => !n.is_read);
        if (elements.markAllReadButton) {
            elements.markAllReadButton.style.display = hasUnread ? 'block' : 'none';
        }

        state.notifications.forEach(notification => {
            const item = createNotificationItem(notification);
            elements.list.appendChild(item);
        });
    }

    /**
     * Create notification item element
     */
    function createNotificationItem(notification) {
        if (!elements.itemTemplate) {
            // Fallback: create manually
            const div = document.createElement('div');
            div.className = 'notification-item px-4 py-3 border-b border-slate-100 hover:bg-slate-50 cursor-pointer transition';
            div.setAttribute('data-delivery-id', notification.id);
            div.innerHTML = `
                <div class="flex items-start gap-3">
                    <div class="flex-shrink-0 mt-0.5">
                        <div class="w-2 h-2 rounded-full ${notification.is_read ? 'bg-gray-300' : 'bg-blue-600'} notification-dot"></div>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="text-sm font-medium ${notification.is_read ? 'text-gray-500' : 'text-slate-800'} notification-title">${escapeHtml(notification.title)}</div>
                        <div class="text-xs text-gray-600 mt-1 notification-body line-clamp-2">${escapeHtml(notification.body)}</div>
                        <div class="text-[10px] text-gray-400 mt-1 notification-time">${formatTime(notification.created_at)}</div>
                    </div>
                </div>
            `;
            div.addEventListener('click', () => handleNotificationClick(notification));
            return div;
        }

        // Use template
        const template = elements.itemTemplate.content.cloneNode(true);
        const item = template.querySelector('.notification-item');
        item.setAttribute('data-delivery-id', notification.id);

        // Update content
        const titleEl = item.querySelector('.notification-title');
        const bodyEl = item.querySelector('.notification-body');
        const timeEl = item.querySelector('.notification-time');
        const dotEl = item.querySelector('.notification-dot');

        if (titleEl) {
            titleEl.textContent = notification.title;
            titleEl.className = `text-sm font-medium ${notification.is_read ? 'text-gray-500' : 'text-slate-800'} notification-title`;
        }
        if (bodyEl) {
            bodyEl.textContent = notification.body;
        }
        if (timeEl) {
            timeEl.textContent = formatTime(notification.created_at);
        }
        if (dotEl) {
            dotEl.className = `w-2 h-2 rounded-full ${notification.is_read ? 'bg-gray-300' : 'bg-blue-600'} notification-dot`;
        }

        // Click handler
        item.addEventListener('click', () => handleNotificationClick(notification));

        return item;
    }

    /**
     * Handle notification click
     */
    async function handleNotificationClick(notification) {
        // Mark as read if not read
        if (!notification.is_read) {
            await markAsRead(notification.id);
        }

        // Navigate to link if available
        if (notification.link) {
            window.location.href = notification.link;
        } else {
            closeDropdown();
        }
    }

    /**
     * Mark notification as read
     */
    async function markAsRead(deliveryId) {
        try {
            const response = await fetch(`${CONFIG.apiBaseUrl}/${deliveryId}/mark-read/`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Update local state
            const notification = state.notifications.find(n => n.id === deliveryId);
            if (notification) {
                notification.is_read = true;
                renderNotifications();
            }

            // Sync lại với server để đảm bảo đúng trạng thái
            await loadUnreadCount();
            await loadNotifications();
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }

    /**
     * Mark all notifications as read
     */
    async function markAllRead() {
        try {
            const response = await fetch(`${CONFIG.apiBaseUrl}/mark-all-read/`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Sau khi server xử lý xong, reload dữ liệu từ API để đảm bảo trạng thái đúng
            await loadUnreadCount();
            await loadNotifications();
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
        }
    }

    /**
     * Update badge
     */
    function updateBadge() {
        if (!elements.badge || !elements.count) return;

        if (state.unreadCount > 0) {
            elements.badge.classList.remove('hidden');
            elements.count.textContent = state.unreadCount > 99 ? '99+' : state.unreadCount;
        } else {
            elements.badge.classList.add('hidden');
        }
    }

    /**
     * Start polling for unread count
     */
    function startPolling() {
        if (state.pollTimer) {
            clearInterval(state.pollTimer);
        }

        state.pollTimer = setInterval(() => {
            loadUnreadCount();
        }, CONFIG.pollInterval);
    }

    /**
     * Stop polling
     */
    function stopPolling() {
        if (state.pollTimer) {
            clearInterval(state.pollTimer);
            state.pollTimer = null;
        }
    }

    /**
     * Show error state
     */
    function showError() {
        if (elements.list) {
            elements.list.innerHTML = '<div class="px-4 py-8 text-center text-sm text-red-500">Lỗi khi tải thông báo</div>';
            elements.list.classList.remove('hidden');
        }
    }

    /**
     * Format time
     */
    function formatTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        const now = new Date();
        const diff = now - date;
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} ngày trước`;
        if (hours > 0) return `${hours} giờ trước`;
        if (minutes > 0) return `${minutes} phút trước`;
        return 'Vừa xong';
    }

    /**
     * Escape HTML
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Export for external use
    window.NotificationBell = {
        refresh: loadUnreadCount,
        loadNotifications: loadNotifications,
        stopPolling: stopPolling,
    };
})();

