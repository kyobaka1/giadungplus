from django.contrib import admin
from marketing.models import MediaTrack

@admin.register(MediaTrack)
class MediaTrackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_name', 'page_title', 'file_extension', 'source_type', 'created_at')
    list_filter = ('file_extension', 'source_type', 'created_at', 'user_name')
    search_fields = ('user_name', 'page_title', 'page_url', 'media_url')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('user_name', 'created_at')
        }),
        ('Thông tin trang web', {
            'fields': ('page_url', 'page_title', 'tab_id')
        }),
        ('Thông tin media', {
            'fields': ('media_url', 'file_extension', 'mime_type', 'source_type', 'thumbnail_url')
        }),
    )
