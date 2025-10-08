import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.products.tests.factories import ProductFactory, ModuleFactory
from apps.products.serializers import ProductSerializer, ModuleSerializer

User = get_user_model()


@pytest.fixture
def user(db):
    """Fixture for creating a user."""
    return User.objects.create_user(email="test@example.com", password="password123")


@pytest.fixture
def api_client(user):
    """Fixture for an authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestProductViewSet:
    """
    Test suite for the ProductViewSet.
    """

    def test_list_products_unauthenticated(self):
        """
        Ensure unauthenticated users cannot list products.
        """
        client = APIClient()
        url = reverse("product-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_active_products(self, api_client):
        """
        Ensure the viewset lists only active products.
        """
        ProductFactory.create_batch(3, is_active=True)
        ProductFactory(is_active=False)

        url = reverse("product-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

    def test_retrieve_active_product(self, api_client):
        """
        Ensure a single active product can be retrieved.
        """
        product = ProductFactory(is_active=True)
        url = reverse("product-detail", kwargs={"uuid": product.uuid})
        response = api_client.get(url)

        serializer = ProductSerializer(product)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == serializer.data["id"]
        assert response.data["key"] == serializer.data["key"]

    def test_retrieve_inactive_product_fails(self, api_client):
        """
        Ensure retrieving an inactive product returns a 404 error.
        """
        product = ProductFactory(is_active=False)
        url = reverse("product-detail", kwargs={"uuid": product.uuid})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestModuleViewSet:
    """
    Test suite for the ModuleViewSet.
    """

    def test_list_modules_unauthenticated(self):
        """
        Ensure unauthenticated users cannot list modules.
        """
        client = APIClient()
        url = reverse("module-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_active_modules(self, api_client):
        """
        Ensure the viewset lists only active modules.
        """
        ModuleFactory.create_batch(2, is_active=True)
        ModuleFactory(is_active=False)

        url = reverse("module-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_retrieve_active_module(self, api_client):
        """
        Ensure a single active module can be retrieved.
        """
        module = ModuleFactory(is_active=True)
        url = reverse("module-detail", kwargs={"uuid": module.uuid})
        response = api_client.get(url)

        serializer = ModuleSerializer(module)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == serializer.data

    def test_retrieve_inactive_module_fails(self, api_client):
        """
        Ensure retrieving an inactive module returns a 404 error.
        """
        module = ModuleFactory(is_active=False)
        url = reverse("module-detail", kwargs={"uuid": module.uuid})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_config_schema_action(self, api_client):
        """
        Test the custom 'config-schema' action on the ModuleViewSet.
        """
        schema_data = {"setting1": "string", "setting2": "integer"}
        module = ModuleFactory(is_active=True, configurable_attributes=schema_data)
        url = reverse("module-config-schema", kwargs={"uuid": module.uuid})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == schema_data
