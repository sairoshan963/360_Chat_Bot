from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [

    # Django Admin
    path('admin/', admin.site.urls),

    # API Docs (Swagger)
    path('api/schema/',  SpectacularAPIView.as_view(),       name='schema'),
    path('api/docs/',    SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Health check
    path('health/', include('shared.health_urls')),

    # API v1
    path('api/v1/auth/',          include('apps.auth_app.urls')),
    path('api/v1/users/',         include('apps.users.urls')),
    path('api/v1/cycles/',        include('apps.review_cycles.urls')),
    path('api/v1/tasks/',         include('apps.reviewer_workflow.urls')),
    path('api/v1/feedback/',      include('apps.feedback.urls')),
    path('api/v1/reports/',       include('apps.feedback.urls')),
    path('api/v1/dashboard/',     include('apps.dashboard.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/audit/',         include('apps.audit.urls')),
    path('api/v1/announcements/', include('apps.announcements.urls')),
    path('api/v1/support/',       include('apps.support.urls')),
    path('api/v1/chat/',          include('apps.chat_assistant.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
