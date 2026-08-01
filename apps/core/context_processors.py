from .models import ProductLine


def app_context(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "product_lines": ProductLine.objects.all(),
        "active_path": request.path,
    }
