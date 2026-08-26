# Simple Product Catalog Enrichment System

## 1. Overview

The goal is to take product data from an e-commerce website and create a clean, enriched product catalog.

Example:

- Source website: Croma
- Product category: 4K LED TVs
- Additional sources: Amazon, Samsung, LG, Sony

The system:

1. Scrapes product pages.
2. Extracts product information.
3. Uses a predefined schema.
4. Fills missing information from other sources.
5. Resolves conflicts using fixed source priorities.
6. Validates the data.
7. Stores the final data in a database.
8. Exposes the data through a FastAPI API.

---

## 2. Simple Architecture

```text
                 Product URLs
                      |
                      v
                +-----------+
                |  Scraper  |
                +-----------+
                      |
                      v
              +---------------+
              | Data Extractor|
              +---------------+
                      |
                      v
              +---------------+
              | Common Schema |
              +---------------+
                      |
                      v
              +---------------+
              | Data Enricher |
              +---------------+
                      |
                      v
              +---------------+
              | Conflict      |
              | Resolution    |
              +---------------+
                      |
                      v
              +---------------+
              | Validator     |
              +---------------+
                      |
                      v
              +---------------+
              | SQLite DB     |
              +---------------+
                      |
                      v
                 FastAPI
```

---

## 3. Problem

For every product, we want to create a complete record.

For example, a TV might have:

```text
Product Name
Brand
Price
Screen Size
Resolution
Panel Type
Refresh Rate
Operating System
Model Number
```

Some information may be available on Croma but missing from Croma's page.

We can therefore use other sources:

```text
Croma
  |
  +-- Product information
  |
  +-- Missing fields
          |
          +--> Samsung
          +--> Amazon
          +--> LG
```

---

## 4. Predefined Product Schema

Instead of automatically discovering the schema, define it ourselves.

Example:

```python
class Product:
    name: str
    brand: str
    price: float
    screen_size: float
    resolution: str
    panel_type: str
    refresh_rate: int
    operating_system: str
    model_number: str
    source_url: str
```

This makes the system simple and predictable.

---

## 5. Scraper

The scraper fetches the product page.

Basic implementation:

```python
import requests
from bs4 import BeautifulSoup


def scrape_page(url):
    response = requests.get(url)

    soup = BeautifulSoup(response.text, "html.parser")

    return soup
```

The scraper extracts information such as:

- Product name
- Brand
- Price
- Specifications
- Description
- Product URL

For the first version, use:

```text
requests
BeautifulSoup
```

Only add Playwright or other browser-based tools if the website requires JavaScript rendering.

---

## 6. Data Extraction

Convert scraped HTML into a common Python dictionary.

Example:

```python
product = {
    "name": "Samsung 55 inch 4K TV",
    "brand": "Samsung",
    "price": 54999,
    "screen_size": 55,
    "resolution": "3840x2160",
    "panel_type": "QLED",
    "refresh_rate": 120,
    "operating_system": "Tizen",
    "model_number": "QA55...",
    "source_url": "https://example.com/product"
}
```

---

## 7. Data Enrichment

After extracting data from the main source, check for missing fields.

Example:

```python
if not product["screen_size"]:
    product["screen_size"] = manufacturer_data["screen_size"]
```

The basic flow is:

```text
Source Product
      |
      v
Extract available fields
      |
      v
Check missing fields
      |
      v
Search additional sources
      |
      v
Fill missing fields
```

There is no AI involved. The enrichment follows predefined Python rules.

---

## 8. Source Priority

Different sources have different levels of trust.

Use a simple priority system:

```python
SOURCE_PRIORITY = {
    "manufacturer": 3,
    "marketplace": 2,
    "retailer": 1
}
```

Priority:

```text
Manufacturer
     ↓
Amazon / Flipkart
     ↓
Croma / Other retailers
```

For example:

```text
Samsung website → 55 inches
Amazon          → 55 inches
Croma           → 54.6 inches
```

The manufacturer value wins because it has the highest priority.

---

## 9. Conflict Resolution

When multiple sources provide different values, select the value from the highest-priority source.

Example:

```python
def choose_value(observations):
    return max(
        observations,
        key=lambda x: SOURCE_PRIORITY[x["source_type"]]
    )
```

Example input:

```python
observations = [
    {
        "value": 55,
        "source_type": "manufacturer"
    },
    {
        "value": 54.6,
        "source_type": "retailer"
    }
]
```

Result:

```text
55
```

---

## 10. Validation

After enrichment, validate the final product.

Example:

```python
def validate_product(product):

    if product["screen_size"] < 10:
        return False

    if product["screen_size"] > 120:
        return False

    if product["price"] < 0:
        return False

    return True
```

Validation can include:

- Correct data types
- Valid ranges
- Required fields
- Valid enum values
- Basic cross-field checks
- Unit normalization

Example:

```text
"55 inches" → 55.0
"₹54,999"   → 54999
```

---

## 11. Database

Use SQLite for the first version.

No external database infrastructure is required.

### Products

Stores the final product information.

```text
products
-------------------------
id
name
brand
price
screen_size
resolution
panel_type
refresh_rate
operating_system
model_number
source_url
created_at
```

### Product Sources

Stores where the information came from.

```text
product_sources
-------------------------
id
product_id
source_type
source_url
scraped_data
created_at
```

This gives us a basic audit trail without creating a complicated database structure.

---

## 12. FastAPI

Expose the processed data through a simple API.

### Start enrichment

```text
POST /enrich
```

Starts the enrichment process.

### Get products

```text
GET /products
```

Returns enriched products.

### Get one product

```text
GET /products/{id}
```

Returns a specific product.

### Health check

```text
GET /healthz
```

Checks whether the API is running.

---

## 13. Project Structure

A simple project can look like this:

```text
product-enrichment/
│
├── app/
│   ├── main.py
│   ├── scraper.py
│   ├── extractor.py
│   ├── enricher.py
│   ├── validator.py
│   ├── database.py
│   └── models.py
│
├── data/
│   └── catalog.db
│
├── tests/
│   ├── test_scraper.py
│   ├── test_enricher.py
│   └── test_validator.py
│
├── requirements.txt
└── README.md
```

---

## 14. End-to-End Flow

The complete process is:

```text
1. Receive product URLs
          ↓
2. Scrape product pages
          ↓
3. Extract product fields
          ↓
4. Compare fields with predefined schema
          ↓
5. Find missing fields
          ↓
6. Get missing data from trusted sources
          ↓
7. Resolve conflicts using source priority
          ↓
8. Validate the final product
          ↓
9. Store product in SQLite
          ↓
10. Expose product through FastAPI
```

---

## 15. Why This Design

This version is intentionally simple.

### Advantages

- Easy to understand
- Easy to implement
- Easy to debug
- No LLM/API cost
- No LangGraph
- No complex agent architecture
- SQLite requires no infrastructure
- Python rules make the behavior predictable
- Easy to extend later

### Future Improvements

If the basic system works, components can be added gradually:

```text
Simple Scraper
      ↓
Better Scraper
      ↓
Multiple Sources
      ↓
Caching
      ↓
Background Jobs
      ↓
PostgreSQL
      ↓
AI/LLM-based extraction
```

The important point is to first build a working deterministic pipeline rather than starting with a complex multi-agent architecture.
