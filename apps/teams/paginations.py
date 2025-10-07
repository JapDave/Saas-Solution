from apps.common.paginations import StandardPagination


class TeamPagination(StandardPagination):
    """Teams use the shared pagination behaviour with a larger default page size."""

    page_size = 25


__all__ = ["TeamPagination"]
