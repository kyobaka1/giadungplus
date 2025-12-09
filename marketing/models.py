from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class MediaTrack(models.Model):
    """
    Model để lưu thông tin video/audio được track từ Chrome Extension
    """
    SOURCE_TYPE_CHOICES = [
        ('video_tag', 'Video Tag'),
        ('audio_tag', 'Audio Tag'),
        ('network_request', 'Network Request'),
    ]
    
    # Thông tin cơ bản
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Thông tin trang web
    page_url = models.TextField(help_text="URL của trang web chứa media")
    page_title = models.CharField(max_length=500, blank=True, null=True)
    
    # Thông tin media
    media_url = models.TextField(help_text="URL của file video/audio (.mp3, .mp4, .mov)")
    file_extension = models.CharField(max_length=10, help_text="mp4, mp3, mov")
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    source_type = models.CharField(
        max_length=50, 
        choices=SOURCE_TYPE_CHOICES, 
        default='video_tag',
        help_text="Nguồn phát hiện media"
    )
    
    # Thông tin người dùng
    user_name = models.CharField(
        max_length=150, 
        db_index=True,
        help_text="Username được setup từ extension, trùng với username trên admin"
    )
    
    # Metadata bổ sung
    tab_id = models.IntegerField(blank=True, null=True, help_text="Chrome tab ID")
    thumbnail_url = models.TextField(blank=True, null=True, help_text="URL ảnh đại diện video")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_name', '-created_at']),
            models.Index(fields=['file_extension']),
        ]
        verbose_name = "Media Track"
        verbose_name_plural = "Media Tracks"
    
    def __str__(self):
        return f"{self.user_name} - {self.file_extension} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
