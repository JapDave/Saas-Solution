import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from apps.products.tests.factories import ProductFactory, ModuleFactory
from apps.products.models import Product, Module

@pytest.mark.django_db
class TestProductModel:
    """Tests for the Product model."""

    def test_create_product_with_factory(self):
        """Tests that a Product can be created successfully using its factory."""
        product = ProductFactory()
        assert product.pk is not None
        assert str(product) == product.name
        assert Product.objects.count() == 1
        assert product.is_active is True

    def test_product_key_uniqueness(self):
        """Tests that product keys are unique."""
        product = ProductFactory()
        with pytest.raises(IntegrityError):
            ProductFactory(key=product.key)

    def test_product_field_max_length(self):
        """Tests max_length constraints on Product fields using the model."""
        with pytest.raises(ValidationError) as excinfo:
            Product(key="a" * 51, name="test_name", description="test_description").full_clean()
        assert "key" in excinfo.value.message_dict

        with pytest.raises(ValidationError) as excinfo:
            Product(key="test_key", name="a" * 101, description="test_description").full_clean()
        assert "name" in excinfo.value.message_dict

        with pytest.raises(ValidationError) as excinfo:
            Product(key="test_key", name="test_name", description="a" * 501).full_clean()
        assert "description" in excinfo.value.message_dict

    def test_product_array_field_constraints(self):
        """Tests constraints on ArrayFields for the Product model."""
        # Test max number of items in array
        with pytest.raises(ValidationError):
            ProductFactory(target_segments=["item"] * 11).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory(use_cases=["item"] * 21).full_clean()

        # Test max length of an item in the array
        with pytest.raises(ValidationError):
            ProductFactory(target_segments=["a" * 51]).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory(use_cases=["a" * 101]).full_clean()


@pytest.mark.django_db
class TestModuleModel:
    """Tests for the Module model."""

    def test_create_module_with_factory(self):
        """Tests that a Module can be created successfully using its factory."""
        module = ModuleFactory()
        assert module.pk is not None
        assert str(module) == module.name
        assert Module.objects.count() == 1
        assert module.is_active is True
        assert module.subscribable is True

    def test_module_code_uniqueness_and_validation(self):
        """Tests uniqueness and format validation for the Module 'code' field."""
        # Test uniqueness
        module = ModuleFactory(code="VALID")
        with pytest.raises(IntegrityError):
            ModuleFactory(code="VALID")


    def test_module_field_max_length(self):
        """Tests max_length constraints on other Module fields using the model."""
        with pytest.raises(ValidationError) as excinfo:
            Module(key="TEST_KEY", code="TEST", name="a" * 101, description="test_description").full_clean()
        assert "name" in excinfo.value.message_dict

        with pytest.raises(ValidationError) as excinfo:
            Module(key="TEST_KEY", code="TEST", name="test_name", description="a" * 501).full_clean()
        assert "description" in excinfo.value.message_dict

    def test_module_array_field_constraints(self):
        """Tests constraints on ArrayFields for the Module model."""
        # Test max number of items in array
        with pytest.raises(ValidationError):
            ModuleFactory(exposed_permissions=["item"] * 51).full_clean()

        # Test max length of an item in the array
        with pytest.raises(ValidationError):
            ModuleFactory(exposed_permissions=["a" * 101]).full_clean()
