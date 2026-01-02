# orders/services/pdf_customer_extractor.py
"""
Accurate customer info extraction from Shopee shipping label PDFs.
Uses column-aware parsing to separate sender (left) from receiver (right).
"""

import re
from typing import Dict, Optional, List
from io import BytesIO
import pdfplumber
import logging

logger = logging.getLogger(__name__)

# Column threshold: words with x >= this value belong to customer column (Đến:)
CUSTOMER_COLUMN_X_MIN = 140.0  # Safely below 151.3 to catch all customer data

# Shop name prefixes to strip from customer name
SHOP_PREFIXES = [
    "Gia Dụng Plus +",
    "Gia Dụng Plus Store",
    "Gia Dụng Plus Official",
    "Gia Dụng Plus HCM",
    "Gia Dụng Plus HN",
    "Gia Dụng Plus",
    "Phaledo Official",
    "Phaledo Offcial",  # typo in old code
    "PHALEDO ®",
    "PHALEDO",
    "lteng_vn",
    "LTENG VIETNAM",
    "LTENG HCM",
    "LTENG",
]


def is_masked_data(text: str) -> bool:
    """Check if text contains masked data (e.g., "A******h")."""
    return "*****" in text if text else False


def extract_customer_column_text(pdf_bytes: bytes, top_percent: float = 0.25) -> List[str]:
    """
    Extract text from customer column (right side, "Đến:") only.
    Chỉ đọc phần đầu file PDF (top_percent% đầu) vì bố cục cố định ở trên.
    
    Args:
        pdf_bytes: PDF file content
        top_percent: Percentage of page height to read (default 0.25 = 25% đầu)
    
    Returns:
        List of text lines from customer column, grouped by y-position
    """
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return []
            
            page = pdf.pages[0]
            page_height = page.height
            
            # Chỉ đọc phần đầu file (top_percent% đầu theo chiều dọc)
            y_max = page_height * top_percent
            
            words = page.extract_words()
            
            # Filter words: 
            # 1. In customer column (x >= threshold)
            # 2. In top portion of page (top <= y_max)
            customer_words = [
                w for w in words 
                if w['x0'] >= CUSTOMER_COLUMN_X_MIN and w['top'] <= y_max
            ]
            
            if not customer_words:
                logger.warning(f"No words found in customer column (top {top_percent*100}%)")
                return []
            
            # Group words by y-position (same line)
            lines_dict = {}
            for word in customer_words:
                y = round(word['top'], 1)  # Round to group nearby words
                if y not in lines_dict:
                    lines_dict[y] = []
                lines_dict[y].append(word)
            
            # Sort by y-position and build lines
            lines = []
            for y in sorted(lines_dict.keys()):
                # Sort words in line by x-position
                line_words = sorted(lines_dict[y], key=lambda w: w['x0'])
                line_text = ' '.join(w['text'] for w in line_words)
                lines.append(line_text)
            
            return lines
            
    except Exception as e:
        logger.error(f"Failed to extract customer column text: {e}", exc_info=True)
        return []


def extract_customer_name_from_column(lines: List[str]) -> Optional[str]:
    """
    Extract customer name from right column lines.
    
    Pattern: First non-header line after "Đến:" or "Đến" contains customer name.
    """
    if not lines:
        return None
    
    # Find "Đến:" or "Đến" line (some PDFs use "Đến" without colon)
    start_idx = 0
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        # Check if line contains "Đến:" or starts with "Đến"
        if "Đến:" in line_stripped or line_stripped.startswith("Đến"):
            start_idx = i + 1  # Name is right after "Đến:"
            break
    
    if start_idx >= len(lines):
        return None
    
    # Customer name is the first content line after "Đến:"
    # But we need to skip order numbers/tracking codes that might appear after "Đến:"
    raw_name = None
    for i in range(start_idx, min(start_idx + 3, len(lines))):  # Check up to 3 lines after "Đến:"
        candidate = lines[i].strip()
        
        # Skip if it looks like an order number/tracking code
        # Patterns: "đơn hàng:XXXXX", "Mã vận đơn: XXXX", long alphanumeric codes, etc.
        candidate_lower = candidate.lower()
        
        # Skip lines with "đơn hàng:", "mã vận đơn", "vận đơn:", etc.
        if any(marker in candidate_lower for marker in ['đơn hàng:', 'mã vận đơn', 'vận đơn:', 'đơn hàng:']):
            continue
        
        # Skip very long alphanumeric strings (tracking codes)
        if len(candidate) > 15 and (candidate.isupper() or any(char.isdigit() for char in candidate[:10])):
            # Check if it's mostly alphanumeric (likely a code)
            alnum_ratio = sum(1 for c in candidate if c.isalnum()) / len(candidate) if candidate else 0
            if alnum_ratio > 0.8:
                continue
        
        # This looks like a name
        raw_name = candidate
        break
    
    if not raw_name:
        return None
    
    # Strip shop prefixes (shouldn't be here but just in case)
    clean_name = raw_name
    for prefix in SHOP_PREFIXES:
        if prefix in clean_name:
            clean_name = clean_name.replace(prefix, "")
    
    clean_name = clean_name.strip()
    
    # Don't extract if masked or if it looks like a code
    if is_masked_data(clean_name):
        logger.debug(f"Customer name is masked: {clean_name}")
        return None
    
    # Don't extract if it's clearly not a name (too long, all caps with numbers, etc.)
    if len(clean_name) > 25 and (clean_name.isupper() or any(char.isdigit() for char in clean_name[:10])):
        logger.debug(f"Customer name looks like a code: {clean_name}")
        return None
    
    return clean_name if clean_name else None


def extract_customer_address_from_column(lines: List[str]) -> Optional[str]:
    """
    Extract customer address from right column lines.
    
    Pattern: Address starts after "Đến:" header and customer name.
    Address can span multiple lines. Stop when we hit empty line or non-address content.
    """
    if len(lines) < 2:
        return None
    
    # Find "Đến:" or "Đến" line (some PDFs use "Đến" without colon)
    start_idx = 0
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        # Check if line contains "Đến:" or starts with "Đến"
        if "Đến:" in line_stripped or line_stripped.startswith("Đến"):
            start_idx = i + 1  # Name is after "Đến:"
            break
    
    # Address starts after name
    address_start_idx = start_idx + 1
    
    if address_start_idx >= len(lines):
        return None
    
    # Collect address lines - join multiple lines until we hit empty line or non-address content
    # Address typically ends before things like "chịu lực", "khối lượng", "chữ ký", product info, etc.
    stop_keywords = [
        'chịu lực',
        'khối lượng',
        'chữ ký',
        'xác nhận',
        'lưu ý',
        'mã đơn hàng',
        'đơn hàng:',
        'đơn/',
        'ngày đặt hàng',
        'ngày đặt',
        'chất liệu',
        'tặng kèm',
        'miếng',
        'treo đồ',
        'keo dán',
        'ốc vít',
        'dán miễn phí',
        'góc',
        '/ 304',
        '001',  # Mã bưu điện/code thường ở cuối address
        'LTENG',
        'PHALEDO',
        ') LTENG',  # Pattern: "...) LTENG"
        ') PHALEDO',
        'chịu nhiệt',
        'nắp vuông',
        'nắp tròn',
        'vị, muối',
        'bột ngọt',
        'mật ong',
        'sl:',
        'sl :',
        ')',  # Pattern: "21)" at end of line
        # Note: "thị trấn" removed from stop keywords because it's part of valid addresses
    ]
    
    address_lines = []
    for i in range(address_start_idx, len(lines)):
        line = lines[i].strip()
        
        # Stop if empty line
        if not line:
            break
        
        # Check if this line contains stop keywords (non-address content)
        line_lower = line.lower()
        contains_stop_keyword = any(keyword.lower() in line_lower for keyword in stop_keywords)
        
        if contains_stop_keyword:
            # If this line starts with stop keyword, don't include it at all
            # If it appears later in the line, include only the part before it
            earliest_idx = len(line)
            matched_keyword = None
            
            for keyword in stop_keywords:
                if keyword.lower() in line_lower:
                    idx = line_lower.find(keyword.lower())
                    if idx >= 0 and idx < earliest_idx:
                        earliest_idx = idx
                        matched_keyword = keyword
            
            if earliest_idx > 0:
                # Keep part before keyword (might be partial address)
                partial_line = line[:earliest_idx].strip().rstrip(',')
                if partial_line:
                    address_lines.append(partial_line)
            break
        
        # Add this line to address
        address_lines.append(line)
    
    # Clean up: Remove lines that are clearly not address and clean stop keywords
    cleaned_address_lines = []
    for line in address_lines:
        line_stripped = line.strip()
        
        # Skip very short lines (likely artifacts)
        if len(line_stripped) < 3:
            continue
        
        # Remove stop keywords if they appear in the line (even if not at start)
        line_lower = line_stripped.lower()
        for keyword in sorted(stop_keywords, key=len, reverse=True):  # Sort by length to match longer keywords first
            if keyword.lower() in line_lower:
                # Remove keyword and everything after it
                idx = line_lower.find(keyword.lower())
                if idx >= 0:
                    line_stripped = line_stripped[:idx].strip().rstrip(',')
                    line_lower = line_stripped.lower()
                    if not line_stripped:
                        break
        
        # Also check for patterns like "21)" at end of line
        if line_stripped and line_stripped.strip().endswith(')'):
            # Remove trailing pattern like "21)" or "001)"
            import re
            line_stripped = re.sub(r'\s*\d+\)\s*$', '', line_stripped).strip().rstrip(',')
        
        if not line_stripped:
            continue
        
        # Skip lines that are mostly uppercase with numbers (like "THỊ TRẤN KIẾN XƯƠNG 001")
        # But keep normal address lines that happen to have some caps
        words = line_stripped.split()
        # Skip lines that are ALL CAPS with numbers and short (likely postal codes)
        if len(words) <= 5 and line_stripped.isupper() and any(char.isdigit() for char in line_stripped):
            # Likely a postal code or location code (like "THỊ TRẤN KIẾN XƯƠNG 001"), skip
            continue
        # Skip lines that are just numbers or very short codes
        if len(line_stripped) <= 5 and (line_stripped.isdigit() or line_stripped.isupper()):
            continue
        # Skip lines that are ALL CAPS single words (like "THỊ TRẤN", "KIẾN", "XƯƠNG")
        # These are often parts of postal codes printed separately
        if len(words) <= 2 and line_stripped.isupper() and len(line_stripped) <= 15:
            continue
        
        cleaned_address_lines.append(line_stripped)
    
    address_lines = cleaned_address_lines
    
    if not address_lines:
        return None
    
    # Join all address lines with space (preserve line breaks as spaces)
    full_address = ' '.join(address_lines)
    
    # Clean up: remove trailing commas and whitespace
    clean_address = full_address.strip().rstrip(',')
    
    # Don't extract if masked
    if is_masked_data(clean_address):
        logger.debug(f"Customer address is masked: {clean_address}")
        return None
    
    return clean_address if clean_address else None


def extract_customer_info_from_pdf(pdf_bytes: bytes) -> Dict[str, Optional[str]]:
    """
    Extract customer information from Shopee shipping label PDF.
    
    Uses column-aware parsing to separate:
    - Left column (Từ:) = Shop info (ignored)
    - Right column (Đến:) = Customer info (extracted)
    
    Args:
        pdf_bytes: PDF file content as bytes
        
    Returns:
        Dict with keys:
        - "name": Customer name
        - "address": Detailed address (address1 only)
        
    Example:
        {
            "name": "Hoàng Thắm",
            "address": "448/25 Phan Huy Ich"
        }
    """
    try:
        # Extract text from customer column only
        customer_lines = extract_customer_column_text(pdf_bytes)
        
        if not customer_lines:
            logger.warning("No customer column text extracted")
            return {"name": None, "address": None}
        
        logger.debug(f"Customer column lines: {customer_lines}")
        
        name = extract_customer_name_from_column(customer_lines)
        address = extract_customer_address_from_column(customer_lines)
        
        result = {
            "name": name,
            "address": address,
        }
        
        logger.info(f"Extracted customer info: name={name}, address={address}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to extract customer info from PDF: {e}", exc_info=True)
        return {"name": None, "address": None}
