from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.products.factories import ProductFactory, ModuleFactory
from apps.products.serializers import ProductSerializer, ModuleSerializer


@pytest.mark.django_db
class TestProductSerializer:
    """
    Test suite for the ProductSerializer.
    """

    def test_contains_expected_fields(self):
        """
        Ensure the serializer has the expected fields.
        """
        product = ProductFactory()
        serializer = ProductSerializer(instance=product)
        data = serializer.data
        expected_fields = {
            "id", "key", "name", "description", "available_module_keys",
            "target_segments", "use_cases", "is_active", "created_at", "updated_at"
        }
        assert set(data.keys()) == expected_fields

    def test_serialization_content(self):
        """
        Ensure key fields are correctly serialized.
        """
        product = ProductFactory(
            name="Test Product",
            key="TEST_PRODUCT",
            target_segments=["enterprise", "smb"]
        )
        serializer = ProductSerializer(instance=product)
        data = serializer.data
        assert data["name"] == "Test Product"
        assert data["key"] == "TEST_PRODUCT"
        assert data["target_segments"] == ["enterprise", "smb"]

    def test_valid_data_deserialization(self):
        """
        Ensure valid data is correctly deserialized.
        """
        valid_serializer_data = {
            "key": "NEW_PRODUCT",
            "name": "New Valid Product",
            "description": "A valid description.",
            "use_cases": ["case1", "case2"],
        }
        serializer = ProductSerializer(data=valid_serializer_data)
        assert serializer.is_valid(raise_exception=True)
        product = serializer.save()
        assert product.name == valid_serializer_data["name"]
        assert product.key == valid_serializer_data["key"]

    def test_invalid_data_deserialization(self):
        """
        Ensure invalid data (e.g., key too long) is correctly handled.
        """
        invalid_serializer_data = {
            "key": "a" * 51,
            "name": "Invalid Product",
        }
        serializer = ProductSerializer(data=invalid_serializer_data)
        assert not serializer.is_valid()
        assert "key" in serializer.errors


@pytest.mark.django_db
class TestModuleSerializer:
    """
    Test suite for the ModuleSerializer.
    """

    def test_contains_expected_fields(self):
        """
        Ensure the serializer has the expected fields.
        """
        module = ModuleFactory()
        serializer = ModuleSerializer(instance=module)
        data = serializer.data
        expected_fields = {
            "id", "key", "code", "name", "description", "subscribable",
            "configurable_attributes", "exposed_permissions", "is_active",
            "created_at", "updated_at",
        }
        assert set(data.keys()) == expected_fields

    def test_serialization_content(self):
        """
        Ensure key fields are correctly serialized.
        """
        module = ModuleFactory(
            name="Test Module",
            key="TEST_MODULE",
            code="TEST",
            configurable_attributes={"setting": "value"},
        )
        serializer = ModuleSerializer(instance=module)
        data = serializer.data
        assert data["name"] == "Test Module"
        assert data["key"] == "TEST_MODULE"
        assert data["code"] == "TEST"
        assert data["configurable_attributes"] == {"setting": "value"}

    def test_valid_data_deserialization(self):
        """
        Ensure valid data is correctly deserialized and creates a module.
        """
        valid_data = {
            "key": "NEW_MODULE",
            "code": "NEWM",
            "name": "New Module",
            "description": "A brand new module.",
            "configurable_attributes": {"setting": "string"},
            "exposed_permissions": ["perm.read"],
        }
        serializer = ModuleSerializer(data=valid_data)
        assert serializer.is_valid(raise_exception=True)
        module = serializer.save()
        assert module.key == "NEW_MODULE"
        assert module.code == "NEWM"

    def test_invalid_data_deserialization(self):
        """
        Ensure invalid data (e.g., invalid key format) is correctly handled.
        """
        invalid_data = {
            "key": "invalid-key",
            "code": "INV",
            "name": "Invalid Module",
        }
        serializer = ModuleSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert "key" in serializer.errors


@pytest.fixture
def api_client():
    return APIClient()
