from django.shortcuts import get_object_or_404, render

from geonode.zalf.models import HighlightedCase, TrainingResource
from geonode.zalf.api.cms_utils import render_markdown


def case_detail(request, slug):
    obj = get_object_or_404(HighlightedCase, slug=slug, is_active=True)
    return render(request, 'zalf/cms_detail.html', {
        'page_title': obj.title,
        'image_url': obj.image.url if obj.image else None,
        'body_html': render_markdown(obj.body_markdown),
        'back_href': '/',
        'back_label': 'Back to home',
    })


def training_detail(request, slug):
    obj = get_object_or_404(TrainingResource, slug=slug, is_active=True)
    return render(request, 'zalf/cms_detail.html', {
        'page_title': obj.title,
        'page_subtitle': obj.organizer,
        'image_url': obj.thumbnail.url if obj.thumbnail else None,
        'body_html': render_markdown(obj.body_markdown),
        'back_href': '/trainings/',
        'back_label': 'Back to trainings',
    })


def trainings_list(request):
    return render(request, 'zalf/trainings.html')


def cms_index(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    return render(request, 'zalf/cms.html')
