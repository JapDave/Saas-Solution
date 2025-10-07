import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.products.factories import ProductFactory, ModuleFactory
from apps.products.models import Product, Module


@pytest.mark.django_db
class TestProductModel:
    """Tests for the Product model."""

    def test_create_product_with_factory(self):
        """A Product can be created successfully via the factory."""
        product = ProductFactory()
        assert product.pk is not None
        assert str(product) == product.name
        assert Product.objects.count() == 1
        assert product.is_active is True

    def test_product_key_uniqueness(self):
        """Product keys are unique at the database level."""
        product = ProductFactory()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductFactory(key=product.key)

    def test_product_field_max_length(self):
        """CharField max_length constraints are enforced."""
        with pytest.raises(ValidationError):
            ProductFactory.build(key="a" * 51).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory.build(name="a" * 101).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory.build(description="a" * 501).full_clean()

    def test_product_array_field_constraints(self):
        """ArrayField size and element length constraints are enforced."""
        with pytest.raises(ValidationError):
            ProductFactory.build(target_segments=["item"] * 11).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory.build(use_cases=["item"] * 21).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory.build(target_segments=["a" * 51]).full_clean()

        with pytest.raises(ValidationError):
            ProductFactory.build(use_cases=["a" * 101]).full_clean()


@pytest.mark.django_db
class TestModuleModel:
    """Tests for the Module model."""

    def test_create_module_with_factory(self):
        """A Module can be created successfully via the factory."""
        module = ModuleFactory()
        assert module.pk is not None
        assert str(module) == module.name
        assert Module.objects.count() == 1
        assert module.is_active is True
        assert module.subscribable is True

    def test_module_key_uniqueness_and_validation(self):
        """Module key must be unique and match the custom validator."""
        ModuleFactory(key="VALID_KEY")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ModuleFactory(key="VALID_KEY")

        with pytest.raises(ValidationError) as excinfo:
            ModuleFactory.build(key="invalid-key").full_clean()
        errors = excinfo.value.error_dict.get("key", [])
        assert any(err.code == "invalid_format" for err in errors)

        with pytest.raises(ValidationError) as excinfo:
            ModuleFactory.build(key="invalidkey").full_clean()
        errors = excinfo.value.error_dict.get("key", [])
        assert any(err.code == "invalid_format" for err in errors)

        with pytest.raises(ValidationError):
            ModuleFactory.build(key="A" * 51).full_clean()

    def test_module_code_uniqueness_and_validation(self):
        """Module code must be unique, uppercase, and meet length requirements."""
        ModuleFactory(code="VALID")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ModuleFactory(code="VALID")

        with pytest.raises(ValidationError) as excinfo:
            ModuleFactory.build(code="invalid").full_clean()
        errors = excinfo.value.error_dict.get("code", [])
        assert any(err.code == "invalid_format" for err in errors)

        with pytest.raises(ValidationError) as excinfo:
            ModuleFactory.build(code="A").full_clean()
        errors = excinfo.value.error_dict.get("code", [])
        assert any(err.code == "min_length" for err in errors)

        with pytest.raises(ValidationError):
            ModuleFactory.build(code="A" * 11).full_clean()

    def test_module_field_max_length(self):
        """Other Module CharField max_length values are enforced."""
        with pytest.raises(ValidationError):
            ModuleFactory.build(name="a" * 101).full_clean()

        with pytest.raises(ValidationError):
            ModuleFactory.build(description="a" * 501).full_clean()

    def test_module_array_field_constraints(self):
        """ArrayField constraints for modules are validated."""
        with pytest.raises(ValidationError):
            ModuleFactory.build(exposed_permissions=["item"] * 51).full_clean()

        with pytest.raises(ValidationError):
            ModuleFactory.build(exposed_permissions=["a" * 101]).full_clean()
