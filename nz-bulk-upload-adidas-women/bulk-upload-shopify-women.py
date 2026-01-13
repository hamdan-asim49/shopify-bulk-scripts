from bs4 import BeautifulSoup
import json
import requests
import re
import demjson3
import xml.etree.ElementTree as ET
import math
import time
import html
import sys
import os

# Add parent directory to path to import parameters
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parameters import SHOPIFY_STORE, ACCESS_TOKEN, API_VERSION, SHOPIFY_API_URL, SHOPIFY_GRAPHQL_URL, nzd_to_aud

URLS = ['https://www.jdsports.co.nz/women/womens-clothing/brand/adidas/',
        'https://www.jdsports.co.nz/women/womens-footwear/brand/adidas/']

def extract_dataObject_json(html):
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script', {'type': 'text/javascript'})

    for script in scripts:
        if script.string and 'var dataObject =' in script.string:
            try:
                match = re.search(r'var\s+dataObject\s*=\s*(\{.*?\});', script.string, re.DOTALL)
                if match:
                    js_obj = match.group(1)
                    parsed = demjson3.decode(js_obj)
                    return parsed
            except Exception as e:
                print(f"Error extracting dataObject: {e}")
                return None

    print("dataObject not found")
    return None

def get_product_description(html):
    soup = BeautifulSoup(html, 'html.parser')
    json_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_scripts:
        try:
            data = json.loads(script.string.strip())
            if data.get('@type') == 'Product':
                return data
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            print(f"Error parsing JSON: {e}")
            continue

def scrape_images_from_html(html):
    """Scrape image links from the product HTML when product description images are empty"""
    soup = BeautifulSoup(html, 'html.parser')
    images = []
    
    owl_zoom = soup.find('ul', {'id': 'owl-zoom'})
    if owl_zoom:
        li_tags = owl_zoom.find_all('li')
        for li in li_tags:
            img_tag = li.find('img')
            if img_tag and img_tag.get('data-src'):
                image_url = img_tag['data-src']
                if '?' in image_url:
                    image_url = image_url.split('?')[0]
                images.append(image_url)
    
    return images

def get_product_images(product_description, product_response_text):
    """Get product images, fallback to HTML scraping if description images are empty"""
    if product_description and 'image' in product_description:
        images = product_description['image']
        
        if not images or (len(images) == 1 and images[0] == '?v=1'):
            return scrape_images_from_html(product_response_text)
        else:
            return images
    else:
        return scrape_images_from_html(product_response_text)

def load_processed_skus():
    """Load previously processed SKUs from local JSON file"""
    try:
        with open("processed_skus.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"📁 Loaded {len(data)} previously processed SKUs")
            return data
    except FileNotFoundError:
        print("📁 No previous SKU file found, starting fresh")
        return {}
    except json.JSONDecodeError:
        print("📁 Error reading SKU file, starting fresh")
        return {}

def save_processed_skus(processed_skus):
    """Save processed SKUs to local JSON file"""
    with open("processed_skus.json", "w", encoding="utf-8") as f:
        json.dump(processed_skus, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved {len(processed_skus)} processed SKUs to file")

def get_shopify_product_id(sku):
    """Get Shopify product ID by searching for SKU in tags"""
    query = """
    query GetProductBySKU($query: String!) {
        products(first: 1, query: $query) {
            edges {
                node {
                    id
                    title
                    tags
                }
            }
        }
    }
    """
    
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }
    
    # Search for products with the specific SKU tag
    variables = {"query": f"tag:sku\\:{sku}"}
    
    try:
        response = requests.post(
            SHOPIFY_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=30
        )
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching product for SKU {sku}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching product for SKU {sku}: {e}")
        return None
    
    if "errors" in data:
        print(f"Error fetching product for SKU {sku}:", data["errors"])
        return None
        
    products = data["data"]["products"]["edges"]
    
    if products:
        return products[0]["node"]["id"]
    else:
        print(f"⚠️  Product with SKU {sku} not found in Shopify")
        return None

def delete_products_from_shopify(skus_to_delete):
    """Delete products from Shopify one by one using productDelete mutation"""
    if not skus_to_delete:
        print("🗑️  No products to delete")
        return
    
    print(f"🗑️  Preparing to delete {len(skus_to_delete)} products from Shopify")
    
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }
    
    mutation = """
    mutation productDelete($input: ProductDeleteInput!) {
      productDelete(input: $input) {
        deletedProductId
        userErrors {
          field
          message
        }
      }
    }
    """
    
    successfully_deleted = 0
    failed_deletions = 0
    
    for sku in skus_to_delete:
        # Get product ID for this SKU
        product_id = get_shopify_product_id(sku)
        if not product_id:
            print(f"⚠️  Could not find product ID for SKU {sku}, skipping deletion")
            failed_deletions += 1
            continue
        
        # Delete the product
        variables = {
            "input": {
                "id": product_id
            }
        }
        
        try:
            response = requests.post(
                SHOPIFY_GRAPHQL_URL, 
                json={"query": mutation, "variables": variables}, 
                headers=headers,
                timeout=30
            )
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error deleting product {sku}: {e}")
            failed_deletions += 1
            continue
        except Exception as e:
            print(f"❌ Unexpected error deleting product {sku}: {e}")
            failed_deletions += 1
            continue
        
        if "errors" in data:
            print(f"❌ GraphQL error deleting product {sku}: {data['errors']}")
            failed_deletions += 1
        elif data["data"]["productDelete"]["userErrors"]:
            print(f"❌ User error deleting product {sku}: {data['data']['productDelete']['userErrors']}")
            failed_deletions += 1
        elif data["data"]["productDelete"]["deletedProductId"]:
            print(f"✅ Successfully deleted product: SKU {sku} (ID: {product_id})")
            successfully_deleted += 1
        else:
            print(f"⚠️  Unexpected response for SKU {sku}: {data}")
            failed_deletions += 1
    
    print(f"🗑️  Deletion summary: {successfully_deleted} successful, {failed_deletions} failed")
    
    # Optional: Add a small delay between deletions to avoid rate limiting
    time.sleep(0.1)  # 100ms delay between each deletion

def generate_product_jsonl(product_list, processed_skus):
    """Generate JSONL file with productSet mutations for both create and update"""
    updates = []
    creates = []
    
    for product in product_list:
        parent_sku = product["sku"]
        
        # Check if this SKU was processed before
        if parent_sku in processed_skus:
            # Get the Shopify product ID
            shopify_id = get_shopify_product_id(parent_sku)
            if shopify_id:
                # UPDATE existing product
                # Build tags including discounted if compareAtPrice > price
                base_tags = [
                    "uploaded_by_script",
                    "nz-prod",
                    f"sku:{product['sku']}",
                    "new",
                    product["gender"],
                    product["productType"],
                    product["brand"],
                ]
                is_discounted = False
                try:
                    price_val = float(product.get("price", 0) or 0)
                    prev_val = float(product.get("previousPrice", 0) or 0)
                    is_discounted = prev_val > 0 and price_val > 0 and prev_val > price_val
                except Exception:
                    is_discounted = False
                if is_discounted:
                    base_tags.append("discounted")
                line = {
                    "input": {
                        "id": shopify_id,  # Include ID for update
                        "tags": base_tags,
                        "productOptions": [
                            {
                                "name": "Size",
                                "values": [{"name": variant["name"]} for variant in product["variants"]]
                            }
                        ],
                        "variants": [
                            {
                                "price": str(product["price"]),
                                "sku": product["sku"].split("_")[0],
                                "barcode": variant["upc"],
                                "compareAtPrice": str(product["previousPrice"]) if product["previousPrice"] != '' else '0',
                                "inventoryItem": {
                                    "tracked": True,
                                    "cost": str(product["originalCost"]) 
                                },
                                "optionValues": [
                                    {
                                        "optionName": "Size",
                                        "name": variant["name"]
                                    }
                                ],
                                "inventoryQuantities": [
                                    {
                                        "quantity": variant["quantity"],
                                        "locationId": "gid://shopify/Location/78755004615",
                                        "name": "available"
                                    }
                                ],
                            }
                            for variant in product["variants"]
                        ],
                        "files": [
                            {
                                    "alt": f"{product['name']} image",
                                    "originalSource": img.split("?")[0],
                                    "filename": f"{product['name']}-LUZActive-Image-{index}"
                                } for index, img in enumerate(product["images"], 1)
                        ]
                    }
                }
                updates.append(line)
                print(f"🔄 Updating product: {product['name']} (SKU: {parent_sku})")
            else:
                # If we can't find the product in Shopify, treat it as new
                creates.append(product)
                print(f"⚠️  Product with SKU {parent_sku} not found in Shopify, treating as new")
        else:
            # CREATE new product
            creates.append(product)
            print(f"✨ Creating new product: {product['name']} (SKU: {parent_sku})")
    
    # Write all operations to JSONL
    with open("products.jsonl", "w", encoding="utf-8") as f:
        # Write updates first
        for update in updates:
            f.write(json.dumps(update) + "\n")
        
        # Write creates
        for product in creates:
            # Build tags including discounted if compareAtPrice > price
            base_tags = [
                "uploaded_by_script",
                "nz-prod",
                f"sku:{product['sku']}",
                "new",
                product["gender"],
                product["productType"],
                product["brand"],
            ]
            is_discounted = False
            try:
                price_val = float(product.get("price", 0) or 0)
                prev_val = float(product.get("previousPrice", 0) or 0)
                is_discounted = prev_val > 0 and price_val > 0 and prev_val > price_val
            except Exception:
                is_discounted = False
            if is_discounted:
                base_tags.append("discounted")
            line = {
                "input": {
                    "title": product["name"],
                    "status": "DRAFT",
                    "productType": product["productType"],
                    "tags": base_tags,
                    "vendor": product["brand"],
                    "descriptionHtml": f"<p>{product['description']}</p>",
                    "productOptions": [
                        {
                            "name": "Size",
                            "values": [{"name": variant["name"]} for variant in product["variants"]]
                        }
                    ],
                    "variants": [
                        {
                            "price": str(product["price"]),
                            "sku": product["sku"].split("_")[0],
                            "barcode": variant["upc"],
                            "compareAtPrice": str(product["previousPrice"]) if product["previousPrice"] != '' else '0',
                            "inventoryItem": {
                                "tracked": True,
                                "cost": str(product["originalCost"])  # or your actual cost
                            },
                            "inventoryQuantities": [
                                {
                                    "quantity": variant["quantity"],
                                    "locationId": "gid://shopify/Location/78755004615",
                                    "name": "available"
                                }
                            ],
                            "optionValues": [
                                {
                                    "optionName": "Size",
                                    "name": variant["name"]
                                }
                            ]
                        }
                        for variant in product["variants"]
                    ],
                    "files": [
                        {
                            "alt": f"{product['name']} image",
                            "originalSource": img.split("?")[0],
                            "filename": f"{product['name']} - LUZActive - Image {index}"
                        } for index, img in enumerate(product["images"], 1)
                    ]
                }
            }
            f.write(json.dumps(line) + "\n")
    
    print(f"✅ Generated products.jsonl with {len(updates)} updates and {len(creates)} creates")
    return updates, creates

def create_staged_upload():
    query = """
    mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets {
          url
          parameters {
            name
            value
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": [{
            "filename": "products.jsonl",
            "mimeType": "text/jsonl",
            "resource": "BULK_MUTATION_VARIABLES",
            "httpMethod": "POST",
        }]
    }

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }

    try:
        response = requests.post(SHOPIFY_GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"GraphQL Request Error (staged upload): {e}")
        return None
    except Exception as e:
        print(f"Unexpected error (staged upload): {e}")
        return None

    if "errors" in data:
        print("GraphQL Errors:", data["errors"])
        return None

    staged_target = data["data"]["stagedUploadsCreate"]["stagedTargets"][0]
    return staged_target

def upload_to_staged_url(staged_upload):
    upload_url = staged_upload["url"]
    params = staged_upload["parameters"]

    try:
        with open("products.jsonl", "rb") as file:
            files = {"file": file}
            data = {param["name"]: param["value"] for param in params}
            response = requests.post(upload_url, data=data, files=files, timeout=60)
    except requests.exceptions.RequestException as e:
        print(f"❌ Upload request failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error during upload: {e}")
        return None

    if response.status_code in [200, 201, 204]:
        print("✅ File uploaded successfully.")
        try:
            root = ET.fromstring(response.text)
            key = root.find('Key').text
            return key
        except:
            return next((param["value"] for param in params if param["name"] == "key"), None)
    else:
        print(f"❌ Upload failed with status {response.status_code}")
        print(response.text)
        return None

def run_bulk_product_set(staged_upload_path):
    mutation = """
    mutation bulkOperationRunMutation($mutation: String!, $stagedUploadPath: String!) {
      bulkOperationRunMutation(
        mutation: $mutation,
        stagedUploadPath: $stagedUploadPath
      ) {
        bulkOperation {
          id
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    product_set_mutation = '''
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
    '''

    variables = {
        "mutation": product_set_mutation,
        "stagedUploadPath": staged_upload_path
    }

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }

    try:
        response = requests.post(SHOPIFY_GRAPHQL_URL, json={"query": mutation, "variables": variables}, headers=headers, timeout=60)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error running bulk product set: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error running bulk product set: {e}")
        return None

    print("📦 Bulk operation initiated:")
    print(json.dumps(data, indent=2))
    return data

def log_skipped_product(product_url, reason):
    """Log skipped products to a text file"""
    with open("skipped_products.txt", "a", encoding="utf-8") as f:
        f.write(f"{product_url} - {reason}\n")

def extract_price_data(html):
    """Extract price and previous price from recentData div"""
    soup = BeautifulSoup(html, 'html.parser')
    recent_data_div = soup.find('div', {'id': 'recentData'})
    
    if recent_data_div:
        data_price = recent_data_div.get('data-price', '')
        data_previous_price = recent_data_div.get('data-previous-price', '')
        original_cost = recent_data_div.get('data-price', '')
        # Convert prices to float, multiply by nzd_to_aud, add 150, ceil to whole number, then convert back to string
        if data_price and data_price.strip():
            try:
                price_float = math.ceil(float(data_price) * nzd_to_aud + 150)
                data_price = str(price_float)
            except ValueError:
                data_price = ''
        else:
            data_price = ''
        
        if original_cost and original_cost.strip():
            try:
                original_cost_float = math.ceil(float(original_cost) * nzd_to_aud)
                original_cost = str(original_cost_float)
            except ValueError:
                original_cost = ''
        else:
            original_cost = ''
        
        if data_previous_price and data_previous_price.strip():
            try:
                prev_price_float = math.ceil(float(data_previous_price) * nzd_to_aud + 150)
                data_previous_price = str(prev_price_float)
            except ValueError:
                data_previous_price = ''
        else:
            data_previous_price = ''
        
        return data_price, data_previous_price, original_cost, True  # True indicates div was found
    else:
        print("⚠️  recentData div not found")
        return '', '', '', False  # False indicates div was not found

def variant_quantity_from_html(html, page_id_variant):
    btn_class = f"btn-{page_id_variant.replace('.', '-')}"
    soup = BeautifulSoup(html, 'html.parser')
    button = soup.find('button', {'class': lambda x: x and btn_class in x})
    return 0 if button else 1

def check_bulk_operation_status():
    """Check the status of current bulk operation"""
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }
    
    query = """
    query getCurrentBulkOperation {
      currentBulkOperation(type: MUTATION) {
        id
        type
        status
        errorCode
        createdAt
        completedAt
        objectCount
        fileSize
        url
        partialDataUrl
      }
    }
    """
    
    try:
        response = requests.post(
            SHOPIFY_GRAPHQL_URL,
            json={"query": query},
            headers=headers,
            timeout=30
        )
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error checking bulk operation status: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error checking bulk operation status: {e}")
        return None
    
    if "errors" in data:
        print(f"❌ Error checking bulk operation status: {data['errors']}")
        return None
    
    bulk_operation = data["data"]["currentBulkOperation"]
    return bulk_operation

def wait_for_bulk_operation_completion(check_interval=120):  # 2 minutes = 120 seconds
    """
    Wait for any active bulk operation to complete before proceeding
    check_interval: seconds between status checks (default 120 = 2 minutes)
    """
    print("🔍 Checking for active bulk operations...")
    
    while True:
        status_info = check_bulk_operation_status()
        
        if not status_info:
            print("✅ No active bulk operation found - ready to proceed!")
            break
        
        current_status = status_info['status']
        operation_id = status_info['id']
        
        if current_status in ['COMPLETED', 'FAILED', 'CANCELED']:
            print(f"✅ Previous bulk operation {operation_id} is {current_status.lower()} - ready to proceed!")
            break
        elif current_status in ['RUNNING', 'CREATED']:
            print(f"⏳ Bulk operation {operation_id} is {current_status.lower()}...")
            print(f"   Created: {status_info.get('createdAt', 'Unknown')}")
            if status_info.get('objectCount'):
                print(f"   Objects processed: {status_info['objectCount']}")
            print(f"   Waiting {check_interval // 60} minutes before checking again...")
            time.sleep(check_interval)
        else:
            print(f"❓ Unknown bulk operation status: {current_status}")
            print(f"   Waiting {check_interval // 60} minutes before checking again...")
            time.sleep(check_interval)

def run_bulk_product_set_with_queue(staged_upload_path):
    """
    Run bulk product set operation with queue management
    Will wait for any active operations to complete first
    """
    print("🚀 Preparing to start bulk operation...")
    
    # Wait for any active bulk operations to complete
    wait_for_bulk_operation_completion()
    
    # Now proceed with the bulk operation
    print("🎯 Starting new bulk operation...")
    
    mutation = """
    mutation bulkOperationRunMutation($mutation: String!, $stagedUploadPath: String!) {
      bulkOperationRunMutation(
        mutation: $mutation,
        stagedUploadPath: $stagedUploadPath
      ) {
        bulkOperation {
          id
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    product_set_mutation = '''
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
    '''

    variables = {
        "mutation": product_set_mutation,
        "stagedUploadPath": staged_upload_path
    }

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }

    try:
        response = requests.post(SHOPIFY_GRAPHQL_URL, json={"query": mutation, "variables": variables}, headers=headers, timeout=60)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error running bulk product set with queue: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error running bulk product set with queue: {e}")
        return None
    
    if "errors" in data:
        print("❌ GraphQL Errors:", data["errors"])
        return data
    
    if data["data"]["bulkOperationRunMutation"]["userErrors"]:
        print("❌ User Errors:", data["data"]["bulkOperationRunMutation"]["userErrors"])
        return data
    
    bulk_operation = data["data"]["bulkOperationRunMutation"]["bulkOperation"]
    if bulk_operation:
        print(f"✅ Bulk operation started successfully!")
        print(f"   Operation ID: {bulk_operation['id']}")
        print(f"   Status: {bulk_operation['status']}")
    else:
        print("⚠️  Bulk operation response was empty")
    
    print("📦 Full bulk operation response:")
    print(json.dumps(data, indent=2))
    return data

def fetch_total_product_counts(urls):
    headers = {}
    payload = {}

    # Load previously processed SKUs
    processed_skus = load_processed_skus()
    all_product_data = []
    current_jd_skus = set()  # Track current SKUs from JD Sports
    failed_skus = set()

    for url in urls:
        try:
            response = requests.request("GET", url, headers=headers, data=payload)
            data = extract_dataObject_json(response.text)
        except requests.exceptions.RequestException as e:
            print(f"⏭️  Skipping URL due to connection error: {url} - {e}")
            log_skipped_product(url, f"Connection error: {str(e)}")
            continue
        except Exception as e:
            print(f"⏭️  Skipping URL due to unexpected error: {url} - {e}")
            log_skipped_product(url, f"Unexpected error: {str(e)}")
            continue
        if not data:
            print(f"⏭️  Skipping URL due to missing dataObject: {url}")
            log_skipped_product(url, "Missing dataObject")
            continue
        totalPages = data.get('itemPageCount', 0)
        itemsPerPage = data.get('itemPagePer', 0)
        itemsDone = 0
        count = 1
        for page in range(1, totalPages + 1):
            collectionPaginatedURl = f"{url}?from={itemsDone}"
            try:
                response = requests.get(collectionPaginatedURl, headers=headers, timeout=30)
                data = extract_dataObject_json(response.text)
            except requests.exceptions.RequestException as e:
                print(f"❌ Could not fetch products from a page: {collectionPaginatedURl}")
                print(f"   Error details: {e}")
                log_skipped_product(collectionPaginatedURl, f"Connection error: {str(e)}")
                sys.exit(1)
            except Exception as e:
                print(f"❌ Could not fetch products from a page: {collectionPaginatedURl}")
                print(f"   Error details: {e}")
                log_skipped_product(collectionPaginatedURl, f"Unexpected error: {str(e)}")
                sys.exit(1)
            if not data or 'items' not in data:
                print(f"⏭️  Skipping page due to missing items: {collectionPaginatedURl}")
                log_skipped_product(collectionPaginatedURl, "Missing items in dataObject")
                continue
            for item in data['items']:
                # Check if this PLU already exists in current_jd_skus
                if item.get("plu") in current_jd_skus:
                    print(f'⏭️  Skipping duplicate PLU: {item.get("plu")} - {item.get("description")})')
                    continue
                
                # Track current SKU
                if item.get("plu"):
                    current_jd_skus.add(item.get("plu"))
                    
                product_url = f'https://www.jdsports.co.nz/product/{item.get("description", "").replace(" ", "-").lower()}/{item.get("plu", "")}'
                print(f'{count} - {product_url}')
                
                try:
                    product_response = requests.get(product_url, headers=headers, timeout=30)
                    product_data = extract_dataObject_json(product_response.text)
                    product_description = get_product_description(product_response.text)
                except requests.exceptions.Timeout:
                    print(f"⏭️  Skipping product due to connection timeout: {product_url}")
                    log_skipped_product(product_url, "Connection timeout")
                    failed_skus.add(item.get("plu"))
                    continue
                except requests.exceptions.ConnectionError as e:
                    print(f"⏭️  Skipping product due to connection error: {product_url}")
                    log_skipped_product(product_url, f"Connection error: {str(e)}")
                    failed_skus.add(item.get("plu"))
                    continue
                except requests.exceptions.RequestException as e:
                    print(f"⏭️  Skipping product due to request error: {product_url}")
                    log_skipped_product(product_url, f"Request error: {str(e)}")
                    failed_skus.add(item.get("plu"))
                    continue
                except Exception as e:
                    print(f"⏭️  Skipping product due to unexpected error: {product_url} - {e}")
                    log_skipped_product(product_url, f"Unexpected error: {str(e)}")
                    failed_skus.add(item.get("plu"))
                    continue
                
                # Extract price data from recentData div
                try:
                    data_price, data_previous_price, original_cost, price_div_found = extract_price_data(product_response.text)
                except Exception as e:
                    print(f"⏭️  Skipping product due to price extraction error: {product_url} - {e}")
                    log_skipped_product(product_url, f"Price extraction error: {str(e)}")
                    failed_skus.add(item.get("plu"))
                    continue
                
                # Skip product if recentData div is not found
                if not price_div_found:
                    print(f"⏭️  Skipping product due to missing recentData div: {product_url}")
                    log_skipped_product(product_url, "Missing recentData div")
                    failed_skus.add(item.get("plu"))
                    continue
                
                # Skip product if price data is empty
                if not data_price or not data_price.strip():
                    print(f"⏭️  Skipping product due to empty price data: {product_url}")
                    log_skipped_product(product_url, "Empty price data")
                    failed_skus.add(item.get("plu"))
                    continue
                
                print("\n**************************\n")
                
                try:
                    product_images = get_product_images(product_description, product_response.text)
                except Exception as e:
                    print(f"⏭️  Skipping product due to image extraction error: {product_url} - {e}")
                    log_skipped_product(product_url, f"Image extraction error: {str(e)}")
                    failed_skus.add(item.get("plu"))
                    continue
                
                # Add quantity to each variant based on button presence in HTML
                variants_with_quantity = []
                for variant in product_data.get('variants', []):
                    page_id_variant = variant.get('page_id_variant')
                    if page_id_variant:
                        try:
                            quantity = variant_quantity_from_html(product_response.text, page_id_variant)
                        except Exception as e:
                            print(f"Error extracting quantity for variant: {e}")
                            quantity = 1
                    else:
                        quantity = 1
                    variant_with_quantity = variant.copy()
                    variant_with_quantity['quantity'] = quantity
                    # Decode HTML entities in variant name
                    if 'name' in variant_with_quantity:
                        variant_with_quantity['name'] = html.unescape(variant_with_quantity['name'])
                    variants_with_quantity.append(variant_with_quantity)
                
                product_upload_data = {
                    "sku": product_data.get('plu', ''),
                    "name": html.unescape(product_data.get('description', '')),
                    "price": data_price,
                    "variants": variants_with_quantity,
                    "images": product_images,
                    "description": product_description['description'] if product_description and 'description' in product_description else "",
                    "previousPrice": data_previous_price,
                    "originalCost": original_cost,
                }
                
                # Split category on '/' and extract gender and productType
                category = product_description['category'] if product_description and 'category' in product_description else ""
                category_parts = category.split('/') if category else []
                gender = category_parts[0].strip() if len(category_parts) > 0 else ""
                productType = category_parts[1].strip() if len(category_parts) > 1 else ""
                product_upload_data['gender'] = gender
                product_upload_data['productType'] = productType
                
                brand = product_description['brand'] if product_description and 'brand' in product_description else ""
                brand_name = brand['name'] if brand and 'name' in brand else ""
                product_upload_data['brand'] = brand_name
                print(product_upload_data)
                all_product_data.append(product_upload_data)
                count += 1
                
            itemsDone += itemsPerPage
    
    # Find SKUs that were in processed_skus but not in current JD Sports data
    previous_skus = set(processed_skus.keys())
    skus_to_delete = previous_skus - current_jd_skus
    
    print(f"\n🔍 SKU Analysis:")
    print(f"   Previous SKUs: {len(previous_skus)}")
    print(f"   Current JD SKUs: {len(current_jd_skus)}")
    print(f"   SKUs to delete: {len(skus_to_delete)}")
    print(f"   SKUS Failed: {len(failed_skus)}")
    
    if skus_to_delete:
        print(f"   Products to delete: {list(skus_to_delete)}")
        
        # Delete products that are no longer on JD Sports
        delete_products_from_shopify(skus_to_delete)
        
        # Remove deleted SKUs from processed_skus
        for sku in skus_to_delete:
            if sku in processed_skus:
                del processed_skus[sku]
                print(f"🗑️  Removed SKU {sku} from processed_skus")
    
    # Generate JSONL with update/create logic based on processed SKUs
    updates, creates = generate_product_jsonl(all_product_data, processed_skus)
    
    # Update processed SKUs with all current products
    latest_processed_skus = {}
    for product in all_product_data:
        latest_processed_skus[product["sku"]] = {
            "name": product["name"],
            "processed_at": json.dumps(None, default=str)  # You can add timestamp if needed
        }
    
    # Save updated processed SKUs
    save_processed_skus(latest_processed_skus)
    
    # Check if skipped products file exists and show summary
    try:
        with open("skipped_products.txt", "r", encoding="utf-8") as f:
            skipped_lines = f.readlines()
            if skipped_lines:
                print(f"📝 Skipped products summary: {len(skipped_lines)} products were skipped")
                print("   Check 'skipped_products.txt' for details")
            else:
                print("📝 No products were skipped")
    except FileNotFoundError:
        print("📝 No products were skipped")
    
    print(f"📊 Summary: {len(updates)} updates, {len(creates)} creates, {len(skus_to_delete)} deletions")
    #print(all_product_data)
    
    # Only proceed with create/update operations if there are products to process
    if all_product_data:
        staged = create_staged_upload()
        if staged:
            staged_path = upload_to_staged_url(staged)
            if staged_path:
                run_bulk_product_set_with_queue(staged_path)
            else:
                print("❌ Failed to upload file, cannot proceed with bulk operation")
        else:
            print("❌ Failed to create staged upload")

import time

start_time = time.time()
fetch_total_product_counts(URLS)
end_time = time.time()
execution_time_minutes = (end_time - start_time) / 60
print(f"\n⏱️  Total execution time: {execution_time_minutes:.2f} minutes")