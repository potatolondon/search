import logging

from google.appengine.api import search

from rest_framework import response

from ...indexers import clean_value

from ..adapters import SearchQueryAdapter

from .filters import KeywordSearch
from .pagination import SearchPageNumberPagination


class SearchMixin(object):
    """Mixin that provides search functionality for API views.

    Provides automatic serving of list requests from the Search API if the view
    is being searched. That is, if the `list` action is being called and the
    FE has queried it with `?search=<term>`.

    It doesn't service all list requests from the Search API to avoid issues
    where search documents are out of sync.
    """
    search_queryset = None
    search_param_name = "search"
    ordering_param_name = "order"
    use_search_for_ordering = True
    pagination_class = SearchPageNumberPagination

    def __init__(self, *args, **kwargs):
        super(SearchMixin, self).__init__(*args, **kwargs)
        if hasattr(self, "filter_backends"):
            self.filter_backends = (
                self.filter_backends[:] +
                [KeywordSearch(get_param=self.search_param_name)]
            )

    def get_search_queryset(self):
        """Get the search query that should be used for searching on this
        endpoint. The return value can either be a `search.Query` or a
        `searching.SearchQueryAdapter`.
        """
        django_qs = self.get_queryset()
        return self.search_queryset or SearchQueryAdapter.from_queryset(django_qs)

    def list(self, request, *args, **kwargs):
        django_queryset = self.get_queryset()

        # If the view is being searched, get the search queryset instead
        if self.is_searching():
            queryset = self.get_search_queryset()
        else:
            queryset = django_queryset

        queryset = self.filter_queryset(queryset)

        try:
            page = self.paginate_queryset(queryset)
        except search.QueryError:
            logging.exception("Query error")
            # There was an exception trying to parse the query string. Rather
            # than logging the query to the user, pretend there were no results
            page = None
            queryset = []

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return response.Response(serializer.data)

    def is_searching(self):
        query = clean_value(self.request.GET.get(self.search_param_name, ""))
        use_for_ordering = (
            self.use_search_for_ordering and
            self.ordering_param_name in self.request.GET
        )
        return self.action == "list" and (query or use_for_ordering)