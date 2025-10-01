import django_filters as df

from apps.accounts.models import Account


class AccountFilter(df.FilterSet):
    """Filter configuration used for account listing endpoints."""

    q = df.CharFilter(method="filter_q")
    is_active = df.BooleanFilter(method="filter_is_active")

    class Meta:
        model = Account
        fields = ["q", "is_active"]

    def filter_q(self, queryset, name, value):
        """Apply the search helper when a query string is provided."""

        return queryset.search(value)

    def filter_is_active(self, queryset, name, value):
        """Filter by active state when explicitly requested."""

        if value is True:
            return queryset.filter(is_active=True)
        if value is False:
            return queryset.filter(is_active=False)
        return queryset
