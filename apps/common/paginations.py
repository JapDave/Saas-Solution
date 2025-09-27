from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError

class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    # make absolutely sure '?page_size=' is honored
    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw is None:
            return self.page_size
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({self.page_size_query_param: f"Must be an integer between 1 and {self.max_page_size}."})
        if val <= 0 or val > self.max_page_size:
            raise ValidationError({self.page_size_query_param: f"Must be between 1 and {self.max_page_size}."})
        return val

