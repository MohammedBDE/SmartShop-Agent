"""Seed script: catalog, discount codes and knowledge base with embeddings.

Run with:  python -m server.db.seed
"""

import logging
import sys

from server.db import connection
from server.services import rag

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


PRODUCTS = [
    {
        "name": "Classic Cotton T-Shirt",
        "category": "T-Shirts",
        "price": 69.90,
        "description": "A 100% cotton regular-fit t-shirt for everyday wear, available in several colours.",
        "variants": [("S", 14), ("M", 9), ("L", 0), ("XL", 6), ("XXL", 3)],
    },
    {
        "name": "Oversized Printed T-Shirt",
        "category": "T-Shirts",
        "price": 89.00,
        "description": "A relaxed oversized t-shirt with a front print, made from heavy 220 gsm jersey.",
        "variants": [("S", 4), ("M", 11), ("L", 7), ("XL", 0)],
    },
    {
        "name": "Linen Summer Shirt",
        "category": "Shirts",
        "price": 159.00,
        "description": "A lightweight linen shirt with roll-up long sleeves, ideal for hot weather.",
        "variants": [("S", 5), ("M", 8), ("L", 4), ("XL", 2)],
    },
    {
        "name": "Denim Shirt",
        "category": "Shirts",
        "price": 179.00,
        "description": "A light-blue denim shirt with two chest pockets.",
        "variants": [("M", 6), ("L", 5), ("XL", 1)],
    },
    {
        "name": "Slim Fit Jeans",
        "category": "Trousers",
        "price": 199.00,
        "description": "Slim-cut jeans made from comfortable stretch denim.",
        "variants": [("30", 7), ("32", 12), ("34", 5), ("36", 0), ("38", 2)],
    },
    {
        "name": "Formal Chino Trousers",
        "category": "Trousers",
        "price": 229.00,
        "description": "Straight-cut formal trousers suitable for work and events.",
        "variants": [("30", 3), ("32", 6), ("34", 6), ("36", 4)],
    },
    {
        "name": "Sport Shorts",
        "category": "Trousers",
        "price": 79.00,
        "description": "Quick-dry sport shorts with side pockets.",
        "variants": [("S", 10), ("M", 10), ("L", 8), ("XL", 5)],
    },
    {
        "name": "Cotton Hoodie",
        "category": "Jackets",
        "price": 189.00,
        "description": "A mid-weight cotton hoodie with a front kangaroo pocket.",
        "variants": [("S", 6), ("M", 0), ("L", 9), ("XL", 4), ("XXL", 2)],
    },
    {
        "name": "Denim Jacket",
        "category": "Jackets",
        "price": 279.00,
        "description": "A classic denim jacket with metal buttons.",
        "variants": [("S", 3), ("M", 5), ("L", 3), ("XL", 0)],
    },
    {
        "name": "Padded Winter Jacket",
        "category": "Jackets",
        "price": 399.00,
        "description": "A water-resistant jacket with an insulating thermal lining.",
        "variants": [("M", 4), ("L", 6), ("XL", 3)],
    },
    {
        "name": "Floral Summer Dress",
        "category": "Dresses",
        "price": 249.00,
        "description": "A midi summer dress in light fabric with a floral print.",
        "variants": [("S", 5), ("M", 7), ("L", 2), ("XL", 0)],
    },
    {
        "name": "Long Evening Dress",
        "category": "Dresses",
        "price": 549.00,
        "description": "An elegant full-length evening dress for special occasions.",
        "variants": [("S", 2), ("M", 3), ("L", 1)],
    },
    {
        "name": "Silk Blouse",
        "category": "Blouses",
        "price": 189.00,
        "description": "A long-sleeved blouse with a soft silky finish.",
        "variants": [("S", 8), ("M", 6), ("L", 4)],
    },
    {
        "name": "Wool Sweater",
        "category": "Blouses",
        "price": 219.00,
        "description": "A warm crew-neck wool sweater.",
        "variants": [("S", 3), ("M", 5), ("L", 5), ("XL", 2)],
    },
    {
        "name": "White Sneakers",
        "category": "Shoes",
        "price": 329.00,
        "description": "Everyday sneakers with a cushioned sole for daily walking.",
        "variants": [("40", 4), ("41", 6), ("42", 8), ("43", 5), ("44", 0)],
    },
    {
        "name": "Classic Leather Shoes",
        "category": "Shoes",
        "price": 449.00,
        "description": "Formal shoes made from genuine leather.",
        "variants": [("41", 3), ("42", 4), ("43", 2), ("44", 1)],
    },
    {
        "name": "Summer Sandals",
        "category": "Shoes",
        "price": 139.00,
        "description": "Lightweight sandals with adjustable straps.",
        "variants": [("38", 5), ("39", 6), ("40", 4), ("41", 3)],
    },
    {
        "name": "Canvas Backpack",
        "category": "Accessories",
        "price": 159.00,
        "description": "A canvas backpack with a padded sleeve for laptops up to 15 inches.",
        "variants": [("one-size", 12)],
    },
    {
        "name": "Leather Belt",
        "category": "Accessories",
        "price": 89.00,
        "description": "A genuine leather belt with a metal buckle.",
        "variants": [("90", 6), ("95", 7), ("100", 4), ("105", 0)],
    },
    {
        "name": "Summer Hat",
        "category": "Accessories",
        "price": 59.00,
        "description": "A light cotton hat with sun protection.",
        "variants": [("one-size", 15)],
    },
    {
        "name": "Winter Scarf",
        "category": "Accessories",
        "price": 69.00,
        "description": "A warm scarf knitted from soft, non-itchy yarn.",
        "variants": [("one-size", 9)],
    },
    {
        "name": "Cotton Pyjama Set",
        "category": "Loungewear",
        "price": 129.00,
        "description": "A two-piece cotton pyjama set.",
        "variants": [("S", 6), ("M", 8), ("L", 5), ("XL", 3)],
    },
    {
        "name": "Cotton Socks 3-Pack",
        "category": "Underwear",
        "price": 39.00,
        "description": "A pack of three pairs of cotton socks.",
        "variants": [("39-42", 20), ("43-46", 14)],
    },
    {
        "name": "Full Tracksuit",
        "category": "Sportswear",
        "price": 349.00,
        "description": "A matching jacket and trousers set in stretch fabric.",
        "variants": [("S", 2), ("M", 5), ("L", 4), ("XL", 3), ("XXL", 0)],
    },
]


DISCOUNT_CODES = [
    {"code": "WELCOME10", "percent_off": 10, "amount_off": None, "min_order_total": 0,
     "active": True, "expires_at": None},
    {"code": "SUMMER25", "percent_off": 25, "amount_off": None, "min_order_total": 300,
     "active": True, "expires_at": None},
    {"code": "FLAT50", "percent_off": None, "amount_off": 50, "min_order_total": 250,
     "active": True, "expires_at": None},
    {"code": "STUDENT15", "percent_off": 15, "amount_off": None, "min_order_total": 150,
     "active": True, "expires_at": None},
    {"code": "WINTER20", "percent_off": 20, "amount_off": None, "min_order_total": 0,
     "active": False, "expires_at": None},
    {"code": "SPRING30", "percent_off": 30, "amount_off": None, "min_order_total": 0,
     "active": True, "expires_at": "2024-05-31 23:59:59+00"},
]


KB_DOCUMENTS = [
    {
        "title": "Return Policy",
        "source_type": "policy",
        "content": """Any item may be returned within 14 days of delivery, provided it is unused, in its original condition, with the original tags still attached, and accompanied by the purchase invoice or the order number.

To start a return, open the "My Orders" page in your account, select the order and click "Request a return", or contact customer service with your order number ready. A return code is issued within one business day.

Refunds are issued to the original payment method within 7 to 10 business days after the item reaches our warehouse and passes inspection. If the order was paid cash on delivery, the refund is made by bank transfer once you provide your account details.

Return shipping costs 20 ILS and is deducted from the refund, unless the reason for the return is a defective item or a mistake on our side, in which case the return is completely free.

Items excluded from returns: underwear and socks for hygiene reasons, items discounted as part of a final clearance and marked "final sale", and made-to-order items."""
    },
    {
        "title": "Exchange and Size Change Policy",
        "source_type": "policy",
        "content": """Exchanges are available within 14 days of delivery and cover a change of size or colour for the same product only. To swap an item for a different product, return the first item and place a new order.

The first exchange for a size change is free and no shipping fee is charged. A second exchange on the same order carries a 20 ILS shipping fee.

An exchange depends on the requested size or colour being in stock when the returned item arrives. If the requested size is unavailable, we offer a choice between a full refund or store credit worth 5% more than the original amount.

The full exchange cycle, from the moment we receive the returned item until the replacement is delivered, takes 5 to 8 business days domestically."""
    },
    {
        "title": "Delivery and Shipping Policy",
        "source_type": "policy",
        "content": """Domestic delivery takes 2 to 5 business days depending on the area. Orders confirmed before 2:00 PM are dispatched the same business day; later orders are dispatched the next business day.

The flat delivery fee is 25 ILS per order, and delivery is completely free for any order whose value after discount exceeds 200 ILS.

Express 24-hour delivery is available to major cities for 45 ILS, and the order must be confirmed before 1:00 PM on a business day. Express delivery is not available on Fridays, Saturdays and public holidays.

You may also choose pickup from an approved collection point for 15 ILS, or free pickup from our main store during opening hours.

Once an order ships you receive a tracking number by SMS and email, and you can follow the shipment from the "Track Order" page on the website."""
    },
    {
        "title": "Accepted Payment Methods",
        "source_type": "policy",
        "content": """We accept the major credit cards Visa, Mastercard and American Express, as well as payment through digital wallets and local payment applications.

Cash on delivery is available for domestic orders up to 800 ILS and carries a 10 ILS service fee.

Orders above 400 ILS can be split into three interest-free instalments with participating credit cards.

All payments are processed through an encrypted payment gateway, and the store never stores card numbers on its servers. A tax invoice is generated automatically and emailed to you once the order is complete."""
    },
    {
        "title": "Warranty and Product Quality",
        "source_type": "policy",
        "content": """All products carry a 30-day warranty against manufacturing defects from the date of delivery, covering seam failure, zip defects and sole separation on shoes.

The warranty does not cover normal wear and tear or damage caused by misuse or by washing the item contrary to the care instructions printed on it.

If you find a manufacturing defect, send a clear photograph of it together with your order number to customer service. Once verified, we provide a free replacement or a full refund, with free shipping in both directions.

Leather shoes carry an extended 60-day warranty on the sole and the stitching."""
    },
    {
        "title": "Order Cancellation and Changes",
        "source_type": "policy",
        "content": """An order can be cancelled or modified free of charge as long as its status has not changed to "Processing", which normally leaves a window of about two hours after checkout.

Once an order enters processing it cannot be cancelled online, but you may still refuse it at the door or return it later under the return policy.

The delivery address can be changed before the order ships by contacting customer service with the order number.

If a prepaid order is cancelled, the amount is returned to the original payment method within 3 to 5 business days."""
    },
    {
        "title": "Data Privacy",
        "source_type": "policy",
        "content": """We collect only the data needed to fulfil an order: name, phone number, email address and delivery address.

We do not sell customer data and do not share it with third parties, except with the courier company, which needs the address and phone number to complete the delivery.

You may request deletion of your account and data at any time by contacting customer service. Deletion is completed within 14 days, and only invoices are retained, for the period required by law.

Marketing messages are sent only to customers who explicitly subscribed, and you can unsubscribe from the link at the bottom of every message."""
    },
    {
        "title": "FAQ: Sizes",
        "source_type": "faq",
        "content": """How do I choose the right size? Use the size chart on each product page, and measure a similar garment you already own so you can compare centimetres rather than relying on the letter size alone.

Do the sizes run true? Most t-shirts and shirts run true to the usual size, while oversized t-shirts are intentionally one full size wider by design.

What if I am between two sizes? We recommend the larger size for shirts and jackets, and the smaller size for garments made from stretch fabric.

Can I change the size after buying? Yes, the first exchange for a size change is free within 14 days under the exchange policy.

Are shoe sizes European? Yes, all shoe sizes in the store use the European system, and each product page includes a conversion table to US sizes."""
    },
    {
        "title": "FAQ: Orders and Order Status",
        "source_type": "faq",
        "content": """How do I track my order? From the "Track Order" page using your order number or the tracking number sent to you by SMS after dispatch.

What do the order statuses mean? "Awaiting confirmation" means payment has not completed yet, "Processing" means the order is being prepared in the warehouse, "Shipped" means it is with the courier, and "Delivered" means it reached you.

I did not receive an order confirmation, what should I do? Check your spam folder first, and if you still find nothing contact customer service with your phone number.

Can I add an item to an existing order? No, but you can place a new order. If both orders are placed on the same day to the same address we try to merge the shipment and refund the extra delivery fee.

I received the wrong item, what should I do? Contact us within 48 hours with a photo of the item and your order number, and we will send the correct item with free shipping in both directions."""
    },
    {
        "title": "FAQ: Discount Codes",
        "source_type": "faq",
        "content": """How do I use a discount code? Enter the code in the "Discount code" field at checkout and click "Apply"; the discount appears immediately in the order summary.

Why is my code not working? The common reasons are an expired code, an order value below the required minimum, or a code that is no longer active.

Can I use more than one code on the same order? No, only one discount code is applied per order.

Does the delivery fee count towards the minimum for a discount? No, the minimum is calculated on the value of the products before the delivery fee is added.

Does a discount code apply to items that are already reduced? Discounts are generally not combined, and codes do not apply to items in a "final sale" clearance."""
    },
    {
        "title": "FAQ: Availability and Stock",
        "source_type": "faq",
        "content": """The size I want is unavailable, will it come back? Most core sizes are restocked roughly every two weeks, and you can enable "Notify me when available" on the product page to be alerted as soon as it returns.

Is the quantity shown on the site accurate? Yes, stock is updated in real time with every purchase, although a rare conflict can occur when two customers buy the last piece at the same moment.

Can I reserve an item? We do not offer reservations through the website, but an item can be held for 24 hours at the main store by calling the branch.

Are the same products available in the branches? Online stock is separate from branch stock, so please confirm with the branch directly before travelling."""
    },
    {
        "title": "FAQ: Customer Service and Opening Hours",
        "source_type": "faq",
        "content": """What are customer service hours? Sunday to Thursday from 9:00 AM to 6:00 PM, Friday from 9:00 AM to 1:00 PM, and closed on Saturday.

How can I contact you? Through the website chat, by email, or by phone during working hours. We answer emails within one business day at most.

What are the main store opening hours? Sunday to Thursday from 10:00 AM to 8:00 PM, and Friday from 10:00 AM to 2:00 PM.

Is support available in other languages? Yes, the customer service team speaks English, Hebrew and Arabic."""
    },
    {
        "title": "FAQ: Account and Registration",
        "source_type": "faq",
        "content": """Do I need an account to buy? No, you can check out as a guest, but an account lets you track orders, save addresses and check out faster next time.

I forgot my password, what should I do? Click "Forgot password" on the login page and you will receive a reset link valid for one hour.

Can I change the email address linked to my account? Yes, from the account settings page; the new address must be confirmed by a verification message.

How do I delete my account? Email customer service from your registered address and the account is deleted within 14 days."""
    },
    {
        "title": "FAQ: Gift Wrapping",
        "source_type": "faq",
        "content": """Do you offer gift wrapping? Yes, wrapping is available for 15 ILS per order and includes a box, a ribbon and a greeting card.

Can the price be hidden from the invoice? Yes, enable the "This order is a gift" option and the invoice is emailed to you only, instead of being placed inside the parcel.

Can an item received as a gift be returned? Yes, within 14 days of delivery. The refund is issued as store credit if the person returning the item is not the original payer.

Can the order be sent to a different address? Yes, you can set a delivery address different from the billing address at checkout."""
    },
    {
        "title": "Size Guide",
        "source_type": "catalog",
        "content": """Tops, in centimetres (chest circumference): size S is 88 to 94, size M is 96 to 102, size L is 104 to 110, size XL is 112 to 118, and size XXL is 120 to 126.

Trousers, in inches (waist circumference): size 30 equals 76 centimetres, size 32 equals 81, size 34 equals 86, size 36 equals 91, and size 38 equals 97.

Shoes use European sizes from 38 to 46; European size 42 corresponds to US men's size 8.5.

Each garment can vary slightly with its cut and fabric, so every product page shows its own measurement table in centimetres."""
    },
    {
        "title": "Store Departments",
        "source_type": "catalog",
        "content": """The store covers t-shirts, shirts, trousers, jackets, dresses, blouses, shoes, accessories, sportswear and loungewear.

The t-shirt department includes both classic and oversized cuts, in fabric weights from 160 to 240 gsm.

The shoe department includes sneakers, classic leather shoes and summer sandals, in European sizes 38 to 46.

The accessories department includes bags, belts, hats and scarves, most of them in one size.

New seasonal products are added at the beginning of every month and appear in the "New Arrivals" section."""
    },
    {
        "title": "Fabric Care Instructions",
        "source_type": "catalog",
        "content": """Cotton: wash at 30 degrees with similar colours, and dry in the shade to preserve the colour and prevent shrinking.

Linen: wash on a gentle cycle at 30 degrees, and iron while slightly damp to remove creases more easily.

Wool: wash by hand in cold water or on a dedicated wool cycle, and dry flat on a level surface rather than hanging, so the garment does not stretch.

Silk and silky fabrics: dry cleaning is preferred; if washed by hand, use cold water and do not rub or wring.

Leather: clean with a damp cloth and treat with a leather care cream every few months, keeping it away from direct heat sources.

Precise care instructions are always printed on the inner label of each garment, and that label takes precedence in case of conflict."""
    },
    {
        "title": "International Orders",
        "source_type": "policy",
        "content": """We currently ship to a limited list of countries, which appears at checkout when you select your country.

International shipping is priced by weight and destination, starting at 80 ILS, and is not covered by the free shipping offer.

International delivery takes 7 to 21 business days depending on the destination and customs processing.

Customs duties and local taxes in the destination country are the customer's responsibility and are not included in the amount paid on the website.

Returns from abroad are possible within 14 days, but the customer bears the full cost of return shipping, and the original shipping fee is not refunded."""
    },
]


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """Split on paragraphs, then pack paragraphs into overlapping windows."""
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks = []
    current = ""

    for paragraph in paragraphs:
        if not current:
            current = paragraph
        elif len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap and len(current) > overlap else ""
            current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph

    if current:
        chunks.append(current)

    return chunks


def reset_tables():
    connection.execute(
        "TRUNCATE kb_chunks, kb_documents, product_variants, products, discount_codes "
        "RESTART IDENTITY CASCADE;"
    )
    logger.info("Catalog and knowledge-base tables truncated")


def seed_products():
    for product in PRODUCTS:
        row = connection.execute(
            """
            INSERT INTO products (name, category, price, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (product["name"], product["category"], product["price"], product["description"]),
        )
        product_id = row["id"]

        for index, (size, stock) in enumerate(product["variants"], start=1):
            connection.execute(
                """
                INSERT INTO product_variants (product_id, size, stock_quantity, sku)
                VALUES (%s, %s, %s, %s);
                """,
                (product_id, size, stock, f"SKU-{product_id:03d}-{index:02d}"),
            )

    logger.info("Inserted %d products", len(PRODUCTS))


def seed_discount_codes():
    for code in DISCOUNT_CODES:
        connection.execute(
            """
            INSERT INTO discount_codes
                (code, percent_off, amount_off, min_order_total, active, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                code["code"], code["percent_off"], code["amount_off"],
                code["min_order_total"], code["active"], code["expires_at"],
            ),
        )
    logger.info("Inserted %d discount codes", len(DISCOUNT_CODES))


def seed_knowledge_base():
    model = rag.get_model()
    total_chunks = 0

    for document in KB_DOCUMENTS:
        row = connection.execute(
            """
            INSERT INTO kb_documents (title, source_type, content)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (document["title"], document["source_type"], document["content"]),
        )
        document_id = row["id"]

        chunks = chunk_text(document["content"])
        vectors = model.encode(chunks, normalize_embeddings=True, batch_size=16)

        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            connection.execute(
                """
                INSERT INTO kb_chunks (document_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s::vector);
                """,
                (
                    document_id,
                    index,
                    chunk,
                    rag.to_pgvector([float(value) for value in vector]),
                ),
            )

        total_chunks += len(chunks)
        logger.info("%-40s -> %d chunks", document["title"], len(chunks))

    logger.info("Inserted %d documents and %d chunks", len(KB_DOCUMENTS), total_chunks)


def main():
    health = connection.check_health()
    if health["database"] != "up":
        logger.error("Database is not reachable: %s", health["error"])
        sys.exit(1)
    if health["tables_missing"]:
        logger.error("Missing tables: %s", health["tables_missing"])
        logger.error("Start the database with: docker compose up -d")
        sys.exit(1)

    reset_tables()
    seed_products()
    seed_discount_codes()
    seed_knowledge_base()
    logger.info("Seeding finished successfully")


if __name__ == "__main__":
    main()
