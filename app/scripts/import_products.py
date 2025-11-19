import csv
import requests
import os
import time

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def post_with_retries(url, data, retries=3, delay=1):
    for attempt in range(retries):
        try:
            response = requests.post(url, json=data)
            if response.status_code in (200, 201):
                return response
            else:
                print(f"Attempt {attempt+1}: Failed with status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}: Request error: {e}")
        time.sleep(delay)
    return None

# ✅ Only this line is changed:
API_URL = os.getenv("API_URL", "https://bharat-products-e0et.onrender.com/api/products")


def import_products(csv_path):
    if not os.path.exists(csv_path):
        print(f"❌ File not found: {csv_path}")
        return

    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        total = 0
        success = 0
        skipped = 0
        failed = 0

        for row in reader:
            total += 1
            name = (row.get("name") or "").strip()
            price = safe_float(row.get("price"), default=None)

            if not name or price is None or price <= 0:
                print(f"⚠️ Skipped (invalid data): {name or 'Unnamed Product'} - Price: {row.get('price')}")
                skipped += 1
                continue

            product_data = {
                "name": name,
                "description": row.get("description"),
                "brand": row.get("brand"),
                "category": row.get("category"),
                "price": price,
                "region": row.get("region"),
                "tags": row.get("tags"),
                "image_url": row.get("image_url") if row.get("image_url", "").startswith("http") else "https://via.placeholder.com/300",
                "rating": safe_float(row.get("rating"), default=0.0),
                "stock": safe_int(row.get("stock")),
            }

            response = post_with_retries(API_URL, product_data)

            if response:
                print(f"✅ Added: {name}")
                success += 1
            else:
                print(f"❌ Failed to add: {name}")
                failed += 1

            time.sleep(0.1)

        print("\n✅ Import Summary:")
        print(f"Total products processed: {total}")
        print(f"Successfully added: {success}")
        print(f"Skipped (invalid data): {skipped}")
        print(f"Failed requests: {failed}")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, "products.csv")
    print(f"📄 Looking for: {csv_path}")
    import_products(csv_path)
