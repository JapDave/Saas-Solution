from rest_framework.pagination import PageNumberPagination

class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    # make absolutely sure '?page_size=' is honored
    def get_page_size(self, request):
        try:
            raw = request.query_params.get(self.page_size_query_param)
            if raw is not None:
                val = int(raw)
                if val > 0:
                    return min(val, self.max_page_size)
        except Exception:
            pass
        return self.page_size