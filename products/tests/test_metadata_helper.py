# products/tests/test_metadata_helper.py
"""
Tests for metadata_helper.py - GDP metadata parsing and injection.
"""

import unittest
from products.services.metadata_helper import (
    extract_gdp_metadata,
    inject_gdp_metadata,
    init_empty_metadata,
    get_variant_metadata,
    update_variant_metadata,
)
from products.services.dto import (
    ProductMetadataDTO,
    VariantMetadataDTO,
    ImportInfoDTO,
    PackagingInfoDTO,
)


class TestMetadataExtraction(unittest.TestCase):
    """Test extract_gdp_metadata function"""
    
    def test_extract_metadata_with_valid_json(self):
        """Test extracting valid GDP metadata from description"""
        description = """
        Sản phẩm chất lượng cao
        
        [GDP_META]{"web_product_id":"123","variants":[{"id":1}]}[/GDP_META]
        """
        
        metadata, original_desc = extract_gdp_metadata(description)
        
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.web_product_id, "123")
        self.assertEqual(len(metadata.variants), 1)
        self.assertEqual(metadata.variants[0].id, 1)
        self.assertEqual(original_desc.strip(), "Sản phẩm chất lượng cao")
    
    def test_extract_metadata_without_gdp_meta(self):
        """Test extraction when no GDP_META marker exists"""
        description = "Sản phẩm thông thường"
        
        metadata, original_desc = extract_gdp_metadata(description)
        
        self.assertIsNone(metadata)
        self.assertEqual(original_desc, "Sản phẩm thông thường")
    
    def test_extract_metadata_with_invalid_json(self):
        """Test extraction with malformed JSON"""
        description = """
        Sản phẩm
        
        [GDP_META]{invalid json}[/GDP_META]
        """
        
        metadata, original_desc = extract_gdp_metadata(description)
        
        self.assertIsNone(metadata)
        self.assertEqual(original_desc.strip(), "Sản phẩm")
    
    def test_extract_metadata_with_none_description(self):
        """Test extraction with None description"""
        metadata, original_desc = extract_gdp_metadata(None)
        
        self.assertIsNone(metadata)
        self.assertEqual(original_desc, "")
    
    def test_extract_metadata_with_empty_description(self):
        """Test extraction with empty description"""
        metadata, original_desc = extract_gdp_metadata("")
        
        self.assertIsNone(metadata)
        self.assertEqual(original_desc, "")
    
    def test_extract_metadata_with_complex_json(self):
        """Test extraction with complex nested metadata"""
        metadata_obj = ProductMetadataDTO(
            web_product_id="WEB-456",
            custom_description="Custom desc",
            variants=[
                VariantMetadataDTO(
                    id=100,
                    import_info=ImportInfoDTO(
                        china_price_cny=50.0,
                        supplier_sku="SKU-100"
                    ),
                    packaging_info=PackagingInfoDTO(
                        box_length_cm=30.0,
                        box_width_cm=20.0,
                        units_per_carton=10
                    )
                )
            ]
        )
        
        # Inject then extract
        description = inject_gdp_metadata("Original description", metadata_obj)
        extracted_metadata, original_desc = extract_gdp_metadata(description)
        
        self.assertIsNotNone(extracted_metadata)
        self.assertEqual(extracted_metadata.web_product_id, "WEB-456")
        self.assertEqual(len(extracted_metadata.variants), 1)
        self.assertEqual(extracted_metadata.variants[0].id, 100)
        self.assertEqual(extracted_metadata.variants[0].import_info.china_price_cny, 50.0)
        self.assertEqual(extracted_metadata.variants[0].packaging_info.units_per_carton, 10)


class TestMetadataInjection(unittest.TestCase):
    """Test inject_gdp_metadata function"""
    
    def test_inject_metadata_with_description(self):
        """Test injecting metadata into existing description"""
        original_desc = "Sản phẩm tốt"
        metadata = ProductMetadataDTO(
            web_product_id="123",
            variants=[VariantMetadataDTO(id=1)]
        )
        
        result = inject_gdp_metadata(original_desc, metadata)
        
        self.assertIn("[GDP_META]", result)
        self.assertIn("[/GDP_META]", result)
        self.assertIn("Sản phẩm tốt", result)
        self.assertIn('"web_product_id":"123"', result)
    
    def test_inject_metadata_without_description(self):
        """Test injecting metadata with empty description"""
        metadata = ProductMetadataDTO(
            web_product_id="123",
            variants=[]
        )
        
        result = inject_gdp_metadata("", metadata)
        
        self.assertTrue(result.startswith("[GDP_META]"))
        self.assertTrue(result.endswith("[/GDP_META]"))
    
    def test_inject_then_extract_roundtrip(self):
        """Test inject -> extract roundtrip preserves data"""
        original_desc = "Test product description"
        metadata = ProductMetadataDTO(
            web_product_id="999",
            custom_description="Custom",
            variants=[
                VariantMetadataDTO(id=10),
                VariantMetadataDTO(id=20)
            ]
        )
        
        # Inject
        injected = inject_gdp_metadata(original_desc, metadata)
        
        # Extract
        extracted_metadata, extracted_desc = extract_gdp_metadata(injected)
        
        # Verify
        self.assertEqual(extracted_desc, original_desc)
        self.assertEqual(extracted_metadata.web_product_id, "999")
        self.assertEqual(len(extracted_metadata.variants), 2)


class TestInitEmptyMetadata(unittest.TestCase):
    """Test init_empty_metadata function"""
    
    def test_init_empty_metadata_with_variants(self):
        """Test initializing empty metadata for product with variants"""
        product_id = 12345
        variant_ids = [100, 200, 300]
        
        metadata = init_empty_metadata(product_id, variant_ids)
        
        self.assertIsNone(metadata.web_product_id)
        self.assertIsNone(metadata.custom_description)
        self.assertEqual(len(metadata.variants), 3)
        self.assertEqual(metadata.variants[0].id, 100)
        self.assertEqual(metadata.variants[1].id, 200)
        self.assertEqual(metadata.variants[2].id, 300)
    
    def test_init_empty_metadata_without_variants(self):
        """Test initializing empty metadata for product without variants"""
        metadata = init_empty_metadata(12345, [])
        
        self.assertEqual(len(metadata.variants), 0)


class TestGetVariantMetadata(unittest.TestCase):
    """Test get_variant_metadata function"""
    
    def test_get_variant_metadata_found(self):
        """Test getting metadata for existing variant"""
        product_metadata = ProductMetadataDTO(
            variants=[
                VariantMetadataDTO(id=1, import_info=ImportInfoDTO(china_price_cny=10.0)),
                VariantMetadataDTO(id=2, import_info=ImportInfoDTO(china_price_cny=20.0)),
            ]
        )
        
        variant_meta = get_variant_metadata(product_metadata, 2)
        
        self.assertIsNotNone(variant_meta)
        self.assertEqual(variant_meta.id, 2)
        self.assertEqual(variant_meta.import_info.china_price_cny, 20.0)
    
    def test_get_variant_metadata_not_found(self):
        """Test getting metadata for non-existent variant"""
        product_metadata = ProductMetadataDTO(
            variants=[VariantMetadataDTO(id=1)]
        )
        
        variant_meta = get_variant_metadata(product_metadata, 999)
        
        self.assertIsNone(variant_meta)
    
    def test_get_variant_metadata_with_none(self):
        """Test getting metadata with None product metadata"""
        variant_meta = get_variant_metadata(None, 1)
        
        self.assertIsNone(variant_meta)


class TestUpdateVariantMetadata(unittest.TestCase):
    """Test update_variant_metadata function"""
    
    def test_update_existing_variant_metadata(self):
        """Test updating metadata for existing variant"""
        product_metadata = ProductMetadataDTO(
            variants=[
                VariantMetadataDTO(id=1, import_info=ImportInfoDTO(china_price_cny=10.0)),
                VariantMetadataDTO(id=2),
            ]
        )
        
        updated_variant = VariantMetadataDTO(
            id=1,
            import_info=ImportInfoDTO(china_price_cny=99.0)
        )
        
        result = update_variant_metadata(product_metadata, 1, updated_variant)
        
        self.assertEqual(len(result.variants), 2)
        self.assertEqual(result.variants[0].import_info.china_price_cny, 99.0)
    
    def test_add_new_variant_metadata(self):
        """Test adding metadata for non-existent variant"""
        product_metadata = ProductMetadataDTO(
            variants=[VariantMetadataDTO(id=1)]
        )
        
        new_variant = VariantMetadataDTO(
            id=3,
            import_info=ImportInfoDTO(china_price_cny=50.0)
        )
        
        result = update_variant_metadata(product_metadata, 3, new_variant)
        
        self.assertEqual(len(result.variants), 2)
        self.assertEqual(result.variants[1].id, 3)


if __name__ == '__main__':
    unittest.main()
