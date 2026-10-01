from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from repository_sso.adapters import SilentProbeMixin


class TestSocialAdapter(SilentProbeMixin, DefaultSocialAccountAdapter):
    pass
