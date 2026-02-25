"""
Parser module for extracting financial facts from earnings release web pages.
Handles multiple formats including Intuit and Amazon earnings releases.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from datetime import datetime


class FinancialFactsParser:
    """Extract structured financial facts from earnings release HTML."""
    
    def parse(self, html: str, url: str, company: str, period: str) -> Dict[str, Any]:
        """
        Parse HTML and extract structured financial facts.
        
        Args:
            html: Raw HTML content
            url: Source URL
            company: Company name
            period: Reporting period
            
        Returns:
            Dictionary with extracted facts and metadata
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Extract text content
        text = soup.get_text(separator=' ', strip=True)
        
        # Extract facts
        facts = []
        
        # Revenue facts
        facts.extend(self._extract_revenue(text))
        
        # Earnings/Profit facts
        facts.extend(self._extract_earnings(text))
        
        # Growth metrics
        facts.extend(self._extract_growth(text))
        
        # Guidance (forward-looking statements)
        facts.extend(self._extract_guidance(text))
        
        # Extract tables if present
        tables = self._extract_tables(soup)
        
        # Add metadata to each fact
        for fact in facts:
            fact['source_url'] = url
            fact['company'] = company
            fact['period'] = period
        
        return {
            'company': company,
            'period': period,
            'source_url': url,
            'extracted_at': datetime.utcnow().isoformat() + 'Z',
            'facts': facts,
            'tables': tables,
            'extraction_status': 'success' if facts else 'no_data_found',
            'fact_count': len(facts)
        }
    
    def _extract_revenue(self, text: str) -> List[Dict[str, Any]]:
        """Extract revenue-related facts."""
        facts = []
        seen_values = set()
        
        # Pattern 1: "revenue to $X.X billion" or "revenue of $X.X billion"
        pattern1 = r'revenue\s+(?:to|of|was|reached|totaled|grew\s+to)\s+\$\s?([\d,]+\.?\d*)\s*(billion|million|thousand)'
        for match in re.finditer(pattern1, text, re.IGNORECASE):
            value = float(match.group(1).replace(',', ''))
            unit = match.group(2).lower()
            key = f"{value}_{unit}"
            
            if key not in seen_values:
                seen_values.add(key)
                facts.append({
                    'fact_type': 'revenue',
                    'metric': 'total_revenue',
                    'value': value,
                    'unit': f'{unit}_usd',
                    'confidence': 'high',
                    'source_text': match.group(0)[:150]
                })
        
        # Pattern 2: "$X.X billion revenue" or "$X.X billion in revenue"
        pattern2 = r'\$\s?([\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?revenue'
        for match in re.finditer(pattern2, text, re.IGNORECASE):
            value = float(match.group(1).replace(',', ''))
            unit = match.group(2).lower()
            key = f"{value}_{unit}"
            
            if key not in seen_values:
                seen_values.add(key)
                facts.append({
                    'fact_type': 'revenue',
                    'metric': 'total_revenue',
                    'value': value,
                    'unit': f'{unit}_usd',
                    'confidence': 'high',
                    'source_text': match.group(0)[:150]
                })
        
        # Pattern 3: "Net sales increased X% to $Y.Y billion" (Amazon style)
        pattern3 = r'(?:net\s+)?sales?\s+(?:increased|grew)\s+[\d.]+%?\s+to\s+\$\s?([\d,]+\.?\d*)\s*(billion|million)'
        for match in re.finditer(pattern3, text, re.IGNORECASE):
            value = float(match.group(1).replace(',', ''))
            unit = match.group(2).lower()
            key = f"{value}_{unit}_sales"
            
            if key not in seen_values:
                seen_values.add(key)
                facts.append({
                    'fact_type': 'revenue',
                    'metric': 'net_sales',
                    'value': value,
                    'unit': f'{unit}_usd',
                    'confidence': 'high',
                    'source_text': match.group(0)[:150]
                })
        
        return facts
    
    def _extract_earnings(self, text: str) -> List[Dict[str, Any]]:
        """Extract earnings/profit metrics."""
        facts = []
        seen_values = set()
        
        # EPS patterns - improved to capture various formats including "$X.XX per diluted share"
        eps_patterns = [
            r'diluted\s+(?:net\s+)?(?:income|earnings)\s+per\s+share\s+(?:of\s+)?\$\s?([\d.]+)',
            r'EPS\s+(?:of\s+)?\$\s?([\d.]+)',
            r'earnings\s+per\s+share\s+(?:of\s+)?\$\s?([\d.]+)',
            r'\$\s?([\d.]+)\s+per\s+(?:diluted\s+)?share',
            r'(?:or\s+)?\$\s?([\d.]+)\s+per\s+diluted\s+share',  # Amazon format
        ]
        
        for pattern in eps_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = float(match.group(1))
                key = f"eps_{value}"
                
                if key not in seen_values and 0 < value < 1000:  # Sanity check
                    seen_values.add(key)
                    facts.append({
                        'fact_type': 'earnings',
                        'metric': 'eps',
                        'value': value,
                        'unit': 'usd_per_share',
                        'confidence': 'high',
                        'source_text': match.group(0)[:150]
                    })
        
        # Net Income patterns - improved to capture "to $X.X billion"
        net_income_patterns = [
            r'net\s+income\s+(?:increased|grew|was|reached|of)\s+(?:to\s+)?\$\s?([\d,]+\.?\d*)\s*(billion|million|thousand)?',
            r'\$\s?([\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?net\s+income',
        ]
        
        for pattern in net_income_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = float(match.group(1).replace(',', ''))
                unit = match.group(2).lower() if match.group(2) else 'usd'
                key = f"net_income_{value}_{unit}"
                
                if key not in seen_values:
                    seen_values.add(key)
                    facts.append({
                        'fact_type': 'earnings',
                        'metric': 'net_income',
                        'value': value,
                        'unit': f'{unit}_usd' if unit != 'usd' else unit,
                        'confidence': 'high',
                        'source_text': match.group(0)[:150]
                    })
        
        # Operating Income - improved
        operating_patterns = [
            r'operating\s+income\s+(?:increased|grew|was|reached)\s+(?:to\s+)?\$\s?([\d,]+\.?\d*)\s*(billion|million)?',
            r'\$\s?([\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?operating\s+income',
        ]
        
        for pattern in operating_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = float(match.group(1).replace(',', ''))
                unit = match.group(2).lower() if match.group(2) else 'usd'
                key = f"operating_income_{value}_{unit}"
                
                if key not in seen_values:
                    seen_values.add(key)
                    facts.append({
                        'fact_type': 'earnings',
                        'metric': 'operating_income',
                        'value': value,
                        'unit': f'{unit}_usd' if unit != 'usd' else unit,
                        'confidence': 'high',
                        'source_text': match.group(0)[:150]
                    })
        
        return facts
    
    def _extract_growth(self, text: str) -> List[Dict[str, Any]]:
        """Extract growth percentages and rates."""
        facts = []
        seen_values = set()
        
        # Growth patterns - improved to capture "increased X%" format
        growth_patterns = [
            r'(?:increased|grew|growth\s+of|up)\s+([\d.]+)\s*%',
            r'([\d.]+)\s*%\s+(?:increase|growth|up)',
            r'([\d.]+)\s*%\s+year[- ]over[- ]year',
            r'(?:sales|revenue|income)\s+(?:increased|grew)\s+([\d.]+)%',
        ]
        
        for pattern in growth_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = float(match.group(1))
                key = f"growth_{value}"
                
                # Filter realistic growth rates
                if key not in seen_values and 0 <= value <= 1000:
                    seen_values.add(key)
                    direction = 'increase'
                    if any(word in match.group(0).lower() for word in ['decrease', 'decline', 'down']):
                        direction = 'decrease'
                    
                    facts.append({
                        'fact_type': 'growth',
                        'metric': 'growth_rate',
                        'value': value,
                        'unit': 'percent',
                        'direction': direction,
                        'confidence': 'medium',
                        'source_text': match.group(0)[:150]
                    })
        
        return facts
    
    def _extract_guidance(self, text: str) -> List[Dict[str, Any]]:
        """Extract forward-looking guidance statements."""
        facts = []
        seen_values = set()
        
        # Guidance patterns - improved to capture ranges
        guidance_patterns = [
            r'(?:guidance|expected?|forecast|outlook|projects?)\s+(?:to\s+be\s+)?(?:between\s+)?\$\s?([\d,]+\.?\d*)\s*(?:billion|million)',
            r'estimates?\s+(?:of\s+)?\$\s?([\d,]+\.?\d*)\s*(billion|million)',
        ]
        
        for pattern in guidance_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = float(match.group(1).replace(',', ''))
                # Try to get unit from either group 2 or search in match
                unit_match = re.search(r'(billion|million)', match.group(0), re.IGNORECASE)
                unit = unit_match.group(1).lower() if unit_match else 'usd'
                key = f"guidance_{value}_{unit}"
                
                if key not in seen_values:
                    seen_values.add(key)
                    facts.append({
                        'fact_type': 'guidance',
                        'metric': 'forward_guidance',
                        'value': value,
                        'unit': f'{unit}_usd',
                        'confidence': 'medium',
                        'source_text': match.group(0)[:150]
                    })
        
        return facts
    
    def _extract_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract and structure table data."""
        tables_data = []
        
        tables = soup.find_all('table')
        
        for idx, table in enumerate(tables):
            rows = []
            headers = []
            
            # Extract headers
            thead = table.find('thead')
            if thead:
                header_row = thead.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # If no thead, try first row
            if not headers:
                first_row = table.find('tr')
                if first_row:
                    potential_headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]
                    # Check if it looks like headers
                    if potential_headers and not all(re.match(r'^[\d,.$\s-]+$', h) for h in potential_headers if h):
                        headers = potential_headers
            
            # Extract data rows
            tbody = table.find('tbody') or table
            for row in tbody.find_all('tr'):
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                if cells and cells != headers:
                    rows.append(cells)
            
            if rows:
                tables_data.append({
                    'table_index': idx,
                    'headers': headers if headers else None,
                    'rows': rows[:10],  # Limit to first 10 rows
                    'row_count': len(rows)
                })
        
        return tables_data


def parse_html(html: str, url: str, company: str, period: str) -> Dict[str, Any]:
    """
    Convenience function to parse HTML and extract facts.
    
    Args:
        html: Raw HTML content
        url: Source URL
        company: Company name
        period: Reporting period
        
    Returns:
        Extracted facts dictionary
    """
    parser = FinancialFactsParser()
    return parser.parse(html, url, company, period)