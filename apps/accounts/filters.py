import django_filters as df
from accounts.models import Account

class AccountFilter(df.FilterSet):
    q = df.CharFilter(method="filter_q")
    is_active = df.BooleanFilter(method="filter_is_active")

    class Meta:
        model = Account
        fields = ["q", "is_active"]

    def filter_q(self, qs, name, value):
        return qs.search(value)

    def filter_is_active(self, qs, name, value):
        if value is True:
            return qs.filter(is_active=True)
        if value is False:
            return qs.exclude(is_active=True)
        return qs
