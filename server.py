import logging
import os
import time
from typing import Any, Dict, List, Optional
from collections import Counter
from mercari import search, getItemInfo, MercariSort, MercariOrder, MercariSearchStatus
from pydantic import Field
from fastmcp import FastMCP

# Initialize logger
logger = logging.getLogger(__name__)

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


mcp = FastMCP(name="MercariSearchComplete")

@mcp.tool(name="search_mercari_jp",
          description="""Search Mercari Japan with intelligent category filtering to reduce noise.
Automatically detects relevant categories and returns comprehensive item data for ALL matching items including:
- Price, condition, description
- Seller ratings and sales history
- Shipping details and timeline
- Photos and engagement metrics

Args:
    keyword (str): Search term in Japanese or English (e.g., 'iPhone15 Pro 256GB')
    exclude_keywords (str): Space-separated keywords to exclude (e.g., 'ジャンク ケース')
    min_price (int, optional): Minimum price in JPY
    max_price (int, optional): Maximum price in JPY

Note: Returns ALL matching items without limit for comprehensive analysis.""")
def search_mercari_items_filtered(
    keyword: str = Field(..., description="The main keyword to search for (e.g., 'iPhone15 Pro 256GB')."),
    exclude_keywords: str = Field("", description="Space-separated keywords to exclude (e.g., 'ジャンク max')."),
    min_price: Optional[int] = Field(None, description="Minimum price in JPY.", ge=0),
    max_price: Optional[int] = Field(None, description="Maximum price in JPY.", ge=0)
) -> List[Dict[str, Any]]:
    """
    Performs a two-phase smart search on Mercari Japan:
    1. Category Discovery: Samples items to identify top categories
    2. Focused Search: Re-searches with category filters to reduce noise

    Returns comprehensive item data including seller ratings, shipping details,
    and engagement metrics.

    Returns:
        A list of dictionaries for items matching all criteria.
        Returns an empty list if no items are found or an error occurs.
    """
    # Input validation
    if not keyword or not keyword.strip():
        logger.error("Keyword parameter is empty or contains only whitespace")
        return []

    if min_price is not None and max_price is not None and min_price > max_price:
        logger.error(f"Invalid price range: min_price ({min_price}) is greater than max_price ({max_price})")
        return []

    items_found: List[Dict[str, Any]] = []
    top_category_ids: List[int] = []

    # Phase 1: Category Discovery
    try:
        logger.info(f"Phase 1: Discovering categories for keyword '{keyword}'")

        # Perform initial search with SCORE sorting to get most relevant items
        search_results = search(
            keyword,
            sort=MercariSort.SORT_SCORE,
            order=MercariOrder.ORDER_DESC,
            status=MercariSearchStatus.ON_SALE,
            exclude_keywords=exclude_keywords
        )

        # Sample up to 50 items to discover categories (allows for some failures)
        category_counter = Counter()
        sample_count = 0
        attempt_count = 0
        max_attempts = 50  # Try up to 50 items to get 30 successful samples
        failed_items = []

        for item in search_results:
            # Stop if we have enough successful samples
            if sample_count >= 30:
                break

            # Stop if we've tried too many items without success
            if attempt_count >= max_attempts:
                logger.warning(f"Reached max attempts ({max_attempts}) with only {sample_count} successful samples")
                break

            attempt_count += 1

            try:
                # Get full item details including category information
                full_item = getItemInfo(item.id)

                # Rate limiting: Add small delay to avoid triggering anti-bot detection
                time.sleep(0.15)

                # Apply price filters manually since old library doesn't support them in search
                if min_price is not None and full_item.price < min_price:
                    continue
                if max_price is not None and full_item.price > max_price:
                    continue

                if full_item.item_category and full_item.item_category.id:
                    category_counter[full_item.item_category.id] += 1
                    sample_count += 1
            except Exception as item_err:
                # Track failed items with error type for categorization
                error_type = type(item_err).__name__
                error_msg = str(item_err)
                failed_items.append({
                    "id": item.id,
                    "error": error_msg,
                    "error_type": error_type
                })
                # Log at INFO level so users can see what's failing
                logger.info(f"Failed to fetch item {item.id} during category discovery: [{error_type}] {error_msg[:100]}")
                # Still add delay even on failure to avoid rapid-fire retries
                time.sleep(0.15)
                continue

        # Log summary of failures with error type breakdown
        if failed_items:
            # Categorize errors by type
            error_breakdown = {}
            for item in failed_items:
                error_type = item['error_type']
                error_breakdown[error_type] = error_breakdown.get(error_type, 0) + 1

            logger.info(f"Category discovery: {sample_count} successful, {len(failed_items)} failed out of {attempt_count} attempts")
            logger.info(f"  Error breakdown: {error_breakdown}")

            # Log first few errors in detail for debugging
            for failed in failed_items[:3]:
                logger.debug(f"  Error details for {failed['id']}: {failed['error']}")

        # Extract top 3 categories by frequency
        if category_counter:
            top_categories = category_counter.most_common(3)
            top_category_ids = [cat_id for cat_id, count in top_categories]
            logger.info(f"Discovered {len(top_category_ids)} categories from {sample_count} items: {top_categories}")

            # Warn if sample size is too small for reliable category discovery
            if sample_count < 5:
                logger.warning(f"Low sample count ({sample_count}) - category filtering may not be representative")
        else:
            logger.warning("No categories discovered, proceeding without category filter")
            if attempt_count > 0:
                logger.warning(f"All {attempt_count} item fetch attempts failed - check error logs above for details")
            else:
                logger.warning("Search returned no items to sample")

    except Exception as e:
        logger.warning(f"Phase 1 category discovery failed: {e}. Proceeding without category filter")

    # Phase 2: Focused Search
    try:
        logger.info(f"Phase 2: Performing focused search with {len(top_category_ids)} category filters")

        # Perform category-filtered search with PRICE sorting for best deals
        filtered_results = search(
            keyword,
            sort=MercariSort.SORT_PRICE,
            order=MercariOrder.ORDER_ASC,
            status=MercariSearchStatus.ON_SALE,
            exclude_keywords=exclude_keywords,
            category_ids=top_category_ids if top_category_ids else None
        )

        # Iterate through all filtered results
        phase2_failed = []
        phase2_success = 0

        for item in filtered_results:

            try:
                # Get full item details including description, seller ratings, shipping info
                full_item = getItemInfo(item.id)

                # Rate limiting: Add small delay to avoid triggering anti-bot detection
                time.sleep(0.15)

                # Apply price filters manually
                if min_price is not None and full_item.price < min_price:
                    continue
                if max_price is not None and full_item.price > max_price:
                    continue

                # Build comprehensive result dictionary
                item_data = {
                    "name": full_item.name,
                    "price": full_item.price,
                    "url": f"https://jp.mercari.com/item/{full_item.id}",
                    "description": full_item.description,
                    "condition": full_item.item_condition.name if full_item.item_condition else "Unknown",
                    "seller": {
                        "name": full_item.seller.name if full_item.seller else "Unknown",
                        "rating_score": full_item.seller.score if full_item.seller else 0,
                        "good_ratings": full_item.seller.ratings.good if full_item.seller and full_item.seller.ratings else 0,
                        "normal_ratings": full_item.seller.ratings.normal if full_item.seller and full_item.seller.ratings else 0,
                        "bad_ratings": full_item.seller.ratings.bad if full_item.seller and full_item.seller.ratings else 0,
                        "total_sales": full_item.seller.num_sell_items if full_item.seller else 0
                    },
                    "created_timestamp": full_item.created,
                    "updated_timestamp": full_item.updated,
                    "shipping": {
                        "payer": full_item.shipping_payer.name if full_item.shipping_payer else "Unknown",
                        "method": full_item.shipping_method.name if full_item.shipping_method else "Unknown",
                        "from_area": full_item.shipping_from_area.name if full_item.shipping_from_area else "Unknown",
                        "duration": f"{full_item.shipping_duration.min_days}-{full_item.shipping_duration.max_days} days" if full_item.shipping_duration else "Unknown"
                    },
                    "num_likes": full_item.num_likes,
                    "num_comments": full_item.num_comments,
                    "category": full_item.item_category.name if full_item.item_category else "Unknown",
                    "photos": full_item.photos[:3] if full_item.photos else []
                }

                items_found.append(item_data)
                phase2_success += 1

            except Exception as item_err:
                # Track failed items with error type for categorization
                error_type = type(item_err).__name__
                error_msg = str(item_err)
                phase2_failed.append({
                    "id": item.id,
                    "error": error_msg,
                    "error_type": error_type
                })
                # Log at INFO level so users can see what's failing
                logger.info(f"Failed to fetch item {item.id} in Phase 2: [{error_type}] {error_msg[:100]}")
                # Still add delay even on failure to avoid rapid-fire retries
                time.sleep(0.15)
                continue

        # Log Phase 2 summary with error type breakdown
        if phase2_failed:
            # Categorize errors by type
            error_breakdown = {}
            for item in phase2_failed:
                error_type = item['error_type']
                error_breakdown[error_type] = error_breakdown.get(error_type, 0) + 1

            logger.info(f"Phase 2: {phase2_success} successful, {len(phase2_failed)} failed")
            logger.info(f"  Error breakdown: {error_breakdown}")

            # Log first few errors for debugging
            for failed in phase2_failed[:3]:
                logger.debug(f"  Error details for {failed['id']}: {failed['error']}")

        logger.info(f"Returning {len(items_found)} items after category filtering (no limit)")

    except Exception as e:
        logger.error(f"Phase 2 focused search failed: {e}")
        return []

    return items_found


if __name__ == "__main__":
    host: str = os.getenv("MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("MCP_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port)
