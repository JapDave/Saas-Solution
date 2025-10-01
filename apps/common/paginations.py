from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default API pagination: 10 per page, client-tunable via ``?page_size=``."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        """Return the validated page size, falling back to :attr:`page_size`."""

        raw = request.query_params.get(self.page_size_query_param)
        if raw is None:
            return self.page_size
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({self.page_size_query_param: f"Must be an integer between 1 and {self.max_page_size}."})
        if value <= 0 or value > self.max_page_size:
            raise ValidationError({self.page_size_query_param: f"Must be between 1 and {self.max_page_size}."})
        return value
