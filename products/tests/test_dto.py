# products/tests/test_dto.py
"""
Tests for DTO validation and serialization.
"""

import unittest
from products.services.dto import (
    ProductDTO,
    ProductVariantDTO,
    ProductMetadataDTO,
    VariantMetadataDTO,
    ImportInfoDTO,
    PackagingInfoDTO,
    WebsiteInfoDTO,
    VariantPriceDTO,
    VariantInventoryDTO,
)


class TestMetadataDTOs(unittest.TestCase):
    """Test metadata DTO creation and validation"""
    
    def test_import_info_dto_creation(self):
        """Test ImportInfoDTO creation"""
        import_info = ImportInfoDTO(
            china_price_cny=50.5,
            supplier_sku="SKU-123",
            import_model_sku="MODEL-123"
        )
        
        self.assertEqual(import_info.china_price_cny, 50.5)
        self.assertEqual(import_info.supplier_sku, "SKU-123")
    
    def test_packaging_info_dto_creation(self):
        """Test PackagingInfoDTO creation"""
        packaging = PackagingInfoDTO(
            box_length_cm=30.0,
            box_width_cm=20.0,
            box_height_cm=10.0,
            weight_with_box_g=1000.0,
            units_per_carton=20
        )
        
        self.assertEqual(packaging.box_length_cm, 30.0)
        self.assertEqual(packaging.units_per_carton, 20)
    
    def test_website_info_dto_creation(self):
        """Test WebsiteInfoDTO creation"""
        website_info = WebsiteInfoDTO(
            web_variant_ids=["WEB-1", "WEB-2"]
        )
        
        self.assertEqual(len(website_info.web_variant_ids), 2)
    
    def test_variant_metadata_dto_creation(self):
        """Test VariantMetadataDTO creation with nested DTOs"""
        variant_meta = VariantMetadataDTO(
            id=123,
            import_info=ImportInfoDTO(china_price_cny=100.0),
            packaging_info=PackagingInfoDTO(units_per_carton=10),
            website_info=WebsiteInfoDTO(web_variant_ids=["W1"])
        )
        
        self.assertEqual(variant_meta.id, 123)
        self.assertEqual(variant_meta.import_info.china_price_cny, 100.0)
        self.assertEqual(variant_meta.packaging_info.units_per_carton, 10)
    
    def test_product_metadata_dto_creation(self):
        """Test ProductMetadataDTO creation"""
        product_meta = ProductMetadataDTO(
            web_product_id="PROD-123",
            custom_description="Custom desc",
            variants=[
                VariantMetadataDTO(id=1),
                VariantMetadataDTO(id=2)
            ]
        )
        
        self.assertEqual(product_meta.web_product_id, "PROD-123")
        self.assertEqual(len(product_meta.variants), 2)


class TestProductDTOs(unittest.TestCase):
    """Test ProductDTO and VariantDTO"""
    
    def test_product_variant_dto_creation(self):
        """Test ProductVariantDTO creation"""
        variant = ProductVariantDTO(
            id=100,
            tenant_id=1,
            product_id=50,
            sku="TEST-SKU",
            name="Test Variant",
            variant_retail_price=100000.0,
            weight_value=500.0
        )
        
        self.assertEqual(variant.id, 100)
        self.assertEqual(variant.sku, "TEST-SKU")
        self.assertEqual(variant.variant_retail_price, 100000.0)
    
    def test_product_dto_creation(self):
        """Test ProductDTO creation"""
        product = ProductDTO(
            id=1,
            tenant_id=1,
            name="Test Product",
            status="active",
            brand="Test Brand",
            description="Product description"
        )
        
        self.assertEqual(product.id, 1)
        self.assertEqual(product.name, "Test Product")
        self.assertEqual(product.brand, "Test Brand")
    
    def test_product_dto_with_variants(self):
        """Test ProductDTO with variants"""
        product = ProductDTO(
            id=1,
            tenant_id=1,
            name="Test Product",
            variants=[
                ProductVariantDTO(
                    id=10,
                    tenant_id=1,
                    product_id=1,
                    sku="SKU-1",
                    name="Variant 1"
                ),
                ProductVariantDTO(
                    id=20,
                    tenant_id=1,
                    product_id=1,
                    sku="SKU-2",
                    name="Variant 2"
                )
            ]
        )
        
        self.assertEqual(product.variant_count, 2)
        self.assertEqual(product.variants[0].sku, "SKU-1")


class TestComputedFields(unittest.TestCase):
    """Test computed fields on DTOs"""
    
    def test_product_original_description(self):
        """Test original_description computed field"""
        product = ProductDTO(
            id=1,
            tenant_id=1,
            name="Test",
            description="Original text\n\n[GDP_META]{\"web_product_id\":\"123\"}[/GDP_META]"
        )
        
        self.assertEqual(product.original_description, "Original text")
    
    def test_product_variant_count(self):
        """Test variant_count computed field"""
        product = ProductDTO(
            id=1,
            tenant_id=1,
            name="Test",
            variants=[
                ProductVariantDTO(id=1, tenant_id=1, product_id=1, sku="S1", name="V1"),
                ProductVariantDTO(id=2, tenant_id=1, product_id=1, sku="S2", name="V2"),
                ProductVariantDTO(id=3, tenant_id=1, product_id=1, sku="S3", name="V3"),
            ]
        )
        
        self.assertEqual(product.variant_count, 3)
    
    def test_variant_total_inventory(self):
        """Test variant total_inventory computed field"""
        variant = ProductVariantDTO(
            id=1,
            tenant_id=1,
            product_id=1,
            sku="SKU",
            name="Variant",
            inventories=[
                VariantInventoryDTO(location_id=1, variant_id=1, on_hand=10.0),
                VariantInventoryDTO(location_id=2, variant_id=1, on_hand=20.0),
            ]
        )
        
        self.assertEqual(variant.total_inventory, 30.0)
    
    def test_product_total_inventory_all_variants(self):
        """Test product total_inventory_all_variants computed field"""
        product = ProductDTO(
            id=1,
            tenant_id=1,
            name="Test",
            variants=[
                ProductVariantDTO(
                    id=1, tenant_id=1, product_id=1, sku="S1", name="V1",
                    inventories=[
                        VariantInventoryDTO(location_id=1, variant_id=1, on_hand=10.0)
                    ]
                ),
                ProductVariantDTO(
                    id=2, tenant_id=1, product_id=1, sku="S2", name="V2",
                    inventories=[
                        VariantInventoryDTO(location_id=1, variant_id=2, on_hand=5.0)
                    ]
                ),
            ]
        )
        
        self.assertEqual(product.total_inventory_all_variants, 15.0)


class TestDTOSerialization(unittest.TestCase):
    """Test DTO serialization and deserialization"""
    
    def test_metadata_dto_to_dict(self):
        """Test ProductMetadataDTO serialization to dict"""
        metadata = ProductMetadataDTO(
            web_product_id="123",
            variants=[
                VariantMetadataDTO(
                    id=1,
                    import_info=ImportInfoDTO(china_price_cny=50.0)
                )
            ]
        )
        
        data = metadata.to_dict()
        
        self.assertEqual(data['web_product_id'], "123")
        self.assertEqual(len(data['variants']), 1)
        self.assertEqual(data['variants'][0]['id'], 1)
    
    def test_metadata_dto_from_dict(self):
        """Test ProductMetadataDTO deserialization from dict"""
        data = {
            "web_product_id": "456",
            "variants": [
                {"id": 10, "import_info": {"china_price_cny": 100.0}}
            ]
        }
        
        metadata = ProductMetadataDTO.from_dict(data)
        
        self.assertEqual(metadata.web_product_id, "456")
        self.assertEqual(len(metadata.variants), 1)
        self.assertEqual(metadata.variants[0].import_info.china_price_cny, 100.0)
    
    def test_product_dto_to_json_str(self):
        """Test ProductDTO to JSON string"""
        product = ProductDTO(
            id=1,
            tenant_id=1,
            name="Test Product"
        )
        
        json_str = product.to_json_str()
        
        self.assertIn('"id":1', json_str)
        self.assertIn('"name":"Test Product"', json_str)
    
    def test_product_dto_from_json_str(self):
        """Test ProductDTO from JSON string"""
        json_str = '{"id":1,"tenant_id":1,"name":"Test"}'
        
        product = ProductDTO.from_json_str(json_str)
        
        self.assertEqual(product.id, 1)
        self.assertEqual(product.name, "Test")


if __name__ == '__main__':
    unittest.main()
