from django.shortcuts import redirect

class PortRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0]
        if request.META.get('SERVER_PORT') == '80':
            return redirect(f"https://{host}:8000{request.get_full_path()}")
        return self.get_response(request)
